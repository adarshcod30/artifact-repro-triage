"""Track cumulative model spend against a hard budget.

The project runs under a $5 ceiling. Almost everything valuable here is
deterministic and free - the verifier, link checking, prevalence, issue
validation, the CLI's default mode and the whole test suite make zero model
calls - so the budget is spent only on the baseline/solution comparison, which
is the one thing that genuinely needs a model.

This reads every results file that records token usage and reports the running
total, so the figure is derived from actual recorded usage rather than estimated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BUDGET_USD = 5.00
THRESHOLDS = [1.0, 2.0, 3.0, 4.0, 5.0]
LEDGER = Path("results/spend.json")


@dataclass
class Entry:
    source: str
    usd: float
    calls: int
    note: str = ""


def collect() -> list[Entry]:
    out: list[Entry] = []

    def load(path: str):
        p = Path(path)
        return json.loads(p.read_text()) if p.exists() else None

    if (d := load("results/baseline.json")):
        r = d["report"]
        out.append(Entry("baseline run", r["usd"], r["n"],
                         "one prompt per artifact"))
    if (d := load("results/solution.json")):
        r = d["report"]
        out.append(Entry("solution run", r["usd"], r["n"],
                         "verified facts per artifact"))
    if (d := load("results/falsified_run.json")):
        # Aggregate form (multiple trials) or a single-trial summary.
        if "total_usd" in d:
            trials = d.get("trials", len(d.get("per_trial", [])) or 1)
            calls = sum(t.get("n_artifacts", 0) * 4 for t in d.get("per_trial", []))
            out.append(Entry("falsified experiment", d["total_usd"], calls,
                             f"{trials} trials x 2 systems x clean+dirty"))
        elif "usd" in d:
            out.append(Entry("falsified experiment", d["usd"],
                             d.get("n_artifacts", 0) * 4, "1 trial"))
    return out


def free_components() -> list[str]:
    """Everything that produces results without spending anything."""
    return [
        "deterministic claim verifier (verify.py)",
        "negative control - 75 injected claims (negative_control.py)",
        "link-rot checking (links.py)",
        "prevalence sweep across 398 artifacts (prevalence.py)",
        "GitHub issue validation (issue_validation.py)",
        "corpus build from cached fixtures (corpus/*)",
        "CLI default mode (cli.py, no --model)",
        "regression test suite (tests/)",
    ]


def report(previous_total: float | None = None) -> float:
    entries = collect()
    total = sum(e.usd for e in entries)
    calls = sum(e.calls for e in entries)

    print("=" * 68)
    print("MODEL SPEND")
    print("=" * 68)
    for e in entries:
        print(f"  {e.source:<26} ${e.usd:>7.4f}  {e.calls:>4} calls   {e.note}")
    print("-" * 68)
    print(f"  {'TOTAL':<26} ${total:>7.4f}  {calls:>4} calls")
    print(f"  {'BUDGET':<26} ${BUDGET_USD:>7.2f}")
    print(f"  {'REMAINING':<26} ${BUDGET_USD - total:>7.4f}  "
          f"({100 * total / BUDGET_USD:.1f}% used)")
    print("-" * 68)

    bar_w = 50
    filled = int(bar_w * min(total / BUDGET_USD, 1.0))
    print(f"  [{'#' * filled}{'.' * (bar_w - filled)}]")

    crossed = [t for t in THRESHOLDS if total >= t and
               (previous_total is None or previous_total < t)]
    for t in crossed:
        print(f"\n  *** BUDGET ALERT: ${t:.0f} threshold reached "
              f"(${total:.4f} spent) ***")
    if total >= BUDGET_USD:
        print("\n  *** BUDGET EXHAUSTED - no further model calls ***")

    print("\n  Produced with ZERO model spend:")
    for c in free_components():
        print(f"    - {c}")
    print("=" * 68)

    LEDGER.parent.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps({
        "total_usd": round(total, 4), "budget_usd": BUDGET_USD,
        "remaining_usd": round(BUDGET_USD - total, 4),
        "total_calls": calls,
        "thresholds_crossed": [t for t in THRESHOLDS if total >= t],
        "entries": [e.__dict__ for e in entries],
    }, indent=1))
    return total


if __name__ == "__main__":
    prev = None
    if LEDGER.exists():
        prev = json.loads(LEDGER.read_text()).get("total_usd")
    report(prev)
