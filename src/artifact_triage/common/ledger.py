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
BUDGET_USD = 5.00
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


def total() -> float:
    return sum(e.get("usd", 0.0) for e in entries())


def remaining() -> float:
    return BUDGET_USD - total()


def crossed() -> list[float]:
    t = total()
    return [x for x in THRESHOLDS if t >= x]
