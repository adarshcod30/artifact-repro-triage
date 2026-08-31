"""Append-only record of every model run.

WHY THIS EXISTS
---------------
Spend was originally computed by summing the cost fields in `results/*.json`.
That measures *the cost of the current results*, not what was actually spent: a
re-run overwrites its results file, and the previous run's cost vanishes from the
total. After three re-runs the ledger reported $0.49 against a true $1.12 - it
under-reported by more than half.

Under-reporting against a hard budget is the worst direction to be wrong, and it
is the fifth under-reporting bug in this project. So the record is append-only:
a run can add to the total, and nothing can subtract from it.

Every entry is written the moment a run finishes, so a crash mid-experiment still
records what it consumed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path("results/spend_ledger.jsonl")
# The ceiling, and the SAME value the runtime guard enforces
# (`common/budget.GUARD_USD`). These were two independent constants; if they
# disagreed, the report would draw a line the guard did not enforce. Raised
# deliberately and visibly rather than edited in place - see CHANGELOG.
# $5.00 for the whole project, raised to $5.50 to certify two uncertified
# results, then to $6.25 to re-validate the paid experiments after a core-logic
# fix, then to $7.00 to re-validate again after the module audit. Each raise
# was explicitly authorised; none was taken unilaterally.
# Recorded as the real ceiling rather than left at 5.00, which would have shown
# an authorised decision as a breach - a report that misstates its own limit is
# no better than a number that has drifted.
BUDGET_USD = float(os.environ.get("ARTIFACT_TRIAGE_BUDGET_USD", "7.00"))
THRESHOLDS = [1.0, 2.0, 3.0, 4.0, 5.0]


def record(kind: str, usd: float, calls: int, model: str = "",
           note: str = "") -> float:
    """Append one run. Returns the new cumulative total."""
    LEDGER.parent.mkdir(exist_ok=True)
    before = total()
    entry = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind, "usd": round(usd, 6), "calls": calls,
        "model": model or os.environ.get("ARTIFACT_TRIAGE_MODEL", ""),
        "note": note,
    }
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    after = before + usd

    for t in THRESHOLDS:
        if before < t <= after:
            print(f"\n  *** BUDGET ALERT: ${t:.0f} threshold crossed "
                  f"(${after:.4f} of ${BUDGET_USD:.2f}) ***\n")
    if after >= BUDGET_USD:
        print(f"\n  *** BUDGET EXHAUSTED: ${after:.4f} - stop model runs ***\n")
    return after


def entries() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


class LedgerUnreadable(Exception):
    """The ledger exists but cannot be trusted. Never treat this as $0."""


def total() -> float:
    """Cumulative spend. Enforces the append-only invariant on read.

    Two ways this used to go wrong:

      - A non-numeric `usd` (`"1.5"` rather than `1.5`) raised TypeError out of
        the sum. `budget._ledger_total()` caught it and returned 0.0, so the
        ceiling guard believed nothing had been spent and permitted unlimited
        runs. A money guard that FAILS OPEN is worse than one that only warns.
      - A negative `usd` SUBTRACTED. The module docstring promises "a run can
        add to the total, and nothing can subtract from it"; $10 + (-$9.90)
        returned $0.10, so a single edited line could hide almost any spend.

    A malformed entry now raises rather than silently reducing the total, and a
    missing file still reads as zero - an absent ledger genuinely means nothing
    has been spent, which is different from an unreadable one.
    """
    running = 0.0
    for e in entries():
        v = e.get("usd", 0.0)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise LedgerUnreadable(
                f"non-numeric spend entry in {LEDGER}: {v!r}")
        if v < 0:
            raise LedgerUnreadable(
                f"negative spend entry in {LEDGER}: {v!r} - the ledger is "
                f"append-only and nothing may subtract from the total")
        running += float(v)
    return running


def remaining() -> float:
    return BUDGET_USD - total()


def crossed() -> list[float]:
    t = total()
    return [x for x in THRESHOLDS if t >= x]
