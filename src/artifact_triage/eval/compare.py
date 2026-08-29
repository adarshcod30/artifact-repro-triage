"""Score the baseline and the solution with the one shared scorer.

`make eval` previously pointed at a module that did not exist - a documented
command that fails when run, which is precisely the defect this project detects.
It is fixed here, and `scripts/verify_targets.py` now proves every documented
command actually runs.

This reads the recorded runs rather than re-invoking the model, so it costs
nothing and can be run repeatedly.
"""
from __future__ import annotations

import json
from pathlib import Path

from artifact_triage.eval.metrics import (Prediction, TIERS, comparison_table,
                                          score)

BASELINE = Path("results/baseline.json")
SOLUTION = Path("results/solution.json")
OUT = Path("results/comparison.json")
HISTORY = Path("results/comparison_history.jsonl")


def load(path: Path, name: str):
    if not path.exists():
        raise SystemExit(f"{path} missing - run `make {name}` first")
    return json.loads(path.read_text())


def rebuild(raw: list[dict], usd_in: float, usd_out: float, name: str,
            labels: dict[str, str]):
    preds = [
        Prediction(
            artifact_id=r["artifact_id"],
            predicted=r.get("tier"),
            confidence=float(r.get("confidence") or 0.0),
            escalated=bool(r.get("escalated", False)),
            evidence=r.get("reasons") or [],
        )
        for r in raw
    ]
    return score(name, preds, labels, usd_in, usd_out)


def constant_controls(labels: dict[str, str]) -> list:
    """Zero-skill baselines. If a real system cannot beat these, say so."""
    out = []
    for tier in TIERS:
        preds = [Prediction(a, tier, 1.0) for a in labels]
        out.append(score(f"always-{tier}", preds, labels, 0.0, 0.0))
    return out


def main() -> None:
    b = load(BASELINE, "baseline")
    s = load(SOLUTION, "solution")

    labels: dict[str, str] = {}
    for p in Path("data/fixtures").glob("*.json"):
        fx = json.loads(p.read_text())
        labels[fx["artifact_id"]] = fx["_label"]["badge"]

    rb = rebuild(b["raw"], 0.80, 3.20, "baseline", labels)
    rs = rebuild(s["raw"], 0.80, 3.20, "solution", labels)
    print(comparison_table([rb, rs]))

    print("\nZERO-SKILL CONTROLS (no model, no input)")
    print("-" * 52)
    controls = constant_controls(labels)
    best = min(controls, key=lambda r: r.mae if r.mae is not None else 9e9)
    for c in controls:
        mark = "  <-- best" if c is best else ""
        print(f"  {c.system:<22} MAE {c.mae:.3f}   "
              f"exact {c.exact_accuracy:.3f}{mark}")
    print("-" * 52)

    beaten = [r for r in (rb, rs)
              if r.mae is not None and best.mae is not None and r.mae >= best.mae]
    if beaten:
        names = ", ".join(r.system for r in beaten)
        print(f"\n  *** {names} do NOT beat a zero-skill constant predictor. ***")
        print("  Badge agreement is uninformative on this corpus. The committee")
        print("  badged the curated Zenodo deposit; we analyse the living GitHub")
        print("  mirror. See results/falsified_run.json for the experiment whose")
        print("  ground truth is exact by construction.")
    else:
        print("\n  Both systems beat every zero-skill control.")

    # Append-only history of every scoring, because the model is NOT
    # deterministic even at temperature 0. `falsified_run.py` already knew
    # this - it runs 3 trials and reports a range, with a comment saying "a
    # single run is not a reportable number". That standard was never applied
    # here, so the badge-agreement MAE was published as a two-decimal point
    # estimate that moved between 0.733 and 0.800 across re-runs.
    #
    # The conclusion is unaffected: the best constant control is deterministic
    # (no model, no input) at 0.667, below every observed value. But the
    # precision was overclaimed, and the fix is to record the spread instead of
    # overwriting it.
    HISTORY.parent.mkdir(exist_ok=True)
    with HISTORY.open("a") as f:
        f.write(json.dumps({"baseline_mae": rb.mae, "solution_mae": rs.mae,
                            "best_control": best.system,
                            "best_control_mae": best.mae}) + "\n")
    hist = [json.loads(ln) for ln in HISTORY.read_text().splitlines() if ln]
    if len(hist) > 1:
        for name in ("baseline", "solution"):
            vals = [h[f"{name}_mae"] for h in hist]
            print(f"  {name:<9} MAE over {len(vals)} recorded run(s): "
                  f"mean {sum(vals)/len(vals):.3f}  "
                  f"range {min(vals):.3f}-{max(vals):.3f}")

    OUT.write_text(json.dumps({
        "baseline": rb.to_dict(), "solution": rs.to_dict(),
        "runs_recorded": len(hist),
        "baseline_mae_range": [min(h["baseline_mae"] for h in hist),
                               max(h["baseline_mae"] for h in hist)],
        "solution_mae_range": [min(h["solution_mae"] for h in hist),
                               max(h["solution_mae"] for h in hist)],
        "controls": [c.to_dict() for c in controls],
        "best_control": best.system,
        "systems_beaten_by_control": [r.system for r in beaten],
    }, indent=1))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
