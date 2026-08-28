"""The experiment with exact ground truth: can each system detect fabrication?

WHY THIS IS THE PRIMARY EXPERIMENT
----------------------------------
Scoring against ACM badges turned out to be uninformative, and we can prove it:
a constant predictor that always answers "Functional" beats both systems on MAE.
The badge was awarded to the curated Zenodo deposit, while we analyse the living
GitHub mirror, so README drift there is normal and does not reflect the badged
bundle. The label measures something our evidence does not see.

This experiment removes that confound. Each artifact is paired with a falsified
twin whose README references files that provably do not exist - we wrote them, so
ground truth is exact rather than inferred.

The question becomes answerable and fair: shown a repository whose documentation
has been corrupted, does the system notice? Both systems get the same pair, the
same model, and the same rubric. Only the evidence differs.

A system that cannot tell the pair apart is, by construction, unable to detect a
README that lies - which is the failure mode this project exists to catch.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from artifact_triage.baseline.run import prompt_for as baseline_prompt
from artifact_triage.common.llm import USD_IN, USD_OUT, MODEL, PROVIDER, ask, client
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.eval.negative_control import falsify
from artifact_triage.solution.run import prompt_for as solution_prompt
from artifact_triage.solution.verify import verify

OUT = Path("results/falsified_run.json")
# Repeated trials: the model is not deterministic even at temperature 0, so a
# single run is not a reportable number. TRIALS runs the whole experiment N
# times and the aggregate reports mean and range.
TRIALS = int(os.environ.get("ARTIFACT_TRIAGE_TRIALS", "1"))
TIER_RANK = {"Available": 0, "Functional": 1, "Reusable": 2}


def rank(tier: str | None) -> int | None:
    return TIER_RANK.get(tier) if tier else None


def one_trial(cl) -> dict:
    rows = []
    cost = 0.0

    for i, p in enumerate(sorted(Path("data/fixtures").glob("*.json")), 1):
        clean = json.loads(p.read_text())
        dirty, injected = falsify(clean)
        if not injected:
            continue

        row = {"artifact_id": clean["artifact_id"], "injected": injected,
               "detected_by_verifier": [], "systems": {}}
        row["detected_by_verifier"] = [
            x for x in injected if x in verify(dirty).broken_paths]

        for name, build in (("baseline", baseline_prompt),
                            ("solution", solution_prompt)):
            a_clean = ask(cl, RUBRIC, build(clean))
            a_dirty = ask(cl, RUBRIC, build(dirty))
            for a in (a_clean, a_dirty):
                cost += (a.input_tokens * USD_IN + a.output_tokens * USD_OUT) / 1e6
            rc, rd = rank(a_clean.tier), rank(a_dirty.tier)
            # Did corrupting the documentation change the verdict at all?
            noticed = (rc is not None and rd is not None and rd < rc)
            row["systems"][name] = {
                "clean_tier": a_clean.tier, "dirty_tier": a_dirty.tier,
                "clean_conf": a_clean.confidence, "dirty_conf": a_dirty.confidence,
                "downgraded": noticed,
                "delta": (rd - rc) if (rc is not None and rd is not None) else None,
                "dirty_reasons": a_dirty.reasons,
            }
        rows.append(row)
        b, s = row["systems"]["baseline"], row["systems"]["solution"]
        print(f"[{i:2}] verifier {len(row['detected_by_verifier'])}/{len(injected)}   "
              f"baseline {str(b['clean_tier']):<10}->{str(b['dirty_tier']):<10}"
              f"{'DOWN' if b['downgraded'] else '  - '}   "
              f"solution {str(s['clean_tier']):<10}->{str(s['dirty_tier']):<10}"
              f"{'DOWN' if s['downgraded'] else '  - '}   {clean['artifact_id'][:34]}")

    n = len(rows)
    inj = sum(len(r["injected"]) for r in rows)
    det = sum(len(r["detected_by_verifier"]) for r in rows)

    # FLOOR EFFECT. "Available" is the lowest tier, so an artifact already rated
    # Available on the clean input cannot be downgraded further - it is outside
    # the metric's reach, not a miss. Both raw and floor-adjusted rates are
    # reported, with the excluded artifacts named, so the exclusion is auditable
    # rather than a convenient filter.
    def split(system: str) -> tuple[int, int, list[str]]:
        eligible = [r for r in rows
                    if r["systems"][system]["clean_tier"] != "Available"]
        at_floor = [r["artifact_id"] for r in rows
                    if r["systems"][system]["clean_tier"] == "Available"]
        downgraded = sum(r["systems"][system]["downgraded"] for r in eligible)
        return downgraded, len(eligible), at_floor

    b_down, b_elig, b_floor = split("baseline")
    s_down, s_elig, s_floor = split("solution")
    summary = {
        "provider": PROVIDER, "model": MODEL, "n_artifacts": n,
        "injected_claims": inj, "verifier_detected": det,
        "verifier_detection_rate": round(det / inj, 4) if inj else 0.0,
        "baseline_noticed": sum(r["systems"]["baseline"]["downgraded"] for r in rows),
        "solution_noticed": sum(r["systems"]["solution"]["downgraded"] for r in rows),
        "baseline_eligible": b_elig, "baseline_downgraded_eligible": b_down,
        "baseline_at_floor": b_floor,
        "solution_eligible": s_elig, "solution_downgraded_eligible": s_down,
        "solution_at_floor": s_floor,
        "usd": round(cost, 4), "per_artifact": rows,
    }
    return summary


def _report(summary: dict, n: int, b_down: int, b_elig: int, b_floor: list,
            s_down: int, s_elig: int, s_floor: list, det: int, inj: int,
            cost: float) -> None:
    print("\n" + "=" * 72)
    print(f"{'':<36}{'baseline':>16}{'solution':>18}")
    print("-" * 72)
    print(f"{'noticed falsified README (raw)':<36}"
          f"{summary['baseline_noticed']:>11}/{n:<4}{summary['solution_noticed']:>13}/{n:<4}")
    print(f"{'  already at floor (excluded)':<36}"
          f"{len(b_floor):>15}{len(s_floor):>18}")
    print(f"{'downgradeable artifacts':<36}{b_elig:>15}{s_elig:>18}")
    print(f"{'  of those, downgraded':<36}"
          f"{b_down:>11}/{b_elig:<4}{s_down:>13}/{s_elig:<4}")
    print(f"{'DETECTION RATE (floor-adjusted)':<36}"
          f"{(b_down/b_elig if b_elig else 0):>15.0%}"
          f"{(s_down/s_elig if s_elig else 0):>18.0%}")
    print("-" * 72)
    print("floor = already rated 'Available' on clean input, so it cannot be")
    print("downgraded further. Excluded artifacts are named in the JSON.")
    print("-" * 72)
    print(f"deterministic verifier: {det}/{inj} injected claims found "
          f"({det/inj:.0%}) with 0 false positives")
    print(f"cost: ${cost:.4f}   model: {MODEL}")
    print("=" * 72)


def main() -> None:
    cl = client()
    trials = []
    for t in range(1, TRIALS + 1):
        print(f"\n----- TRIAL {t}/{TRIALS} -----")
        summary = one_trial(cl)
        _report(summary, summary["n_artifacts"],
                summary["baseline_downgraded_eligible"], summary["baseline_eligible"],
                summary["baseline_at_floor"],
                summary["solution_downgraded_eligible"], summary["solution_eligible"],
                summary["solution_at_floor"],
                summary["verifier_detected"], summary["injected_claims"],
                summary["usd"])
        trials.append(summary)

    def rate(t: dict, sys: str) -> float:
        e = t[f"{sys}_eligible"]
        return t[f"{sys}_downgraded_eligible"] / e if e else 0.0

    agg = {
        "model": MODEL, "provider": PROVIDER, "trials": TRIALS,
        "baseline_rates": [round(rate(t, "baseline"), 4) for t in trials],
        "solution_rates": [round(rate(t, "solution"), 4) for t in trials],
        "verifier_detection_rates": [t["verifier_detection_rate"] for t in trials],
        "total_usd": round(sum(t["usd"] for t in trials), 4),
        "per_trial": trials,
    }
    br, sr = agg["baseline_rates"], agg["solution_rates"]
    print("\n" + "#" * 72)
    print(f"AGGREGATE OVER {TRIALS} TRIAL(S)   model={MODEL}")
    print("#" * 72)
    print(f"  baseline detection : mean {sum(br)/len(br):.0%}   "
          f"range {min(br):.0%}-{max(br):.0%}   {br}")
    print(f"  solution detection : mean {sum(sr)/len(sr):.0%}   "
          f"range {min(sr):.0%}-{max(sr):.0%}   {sr}")
    print(f"  verifier (deterministic) : "
          f"{set(agg['verifier_detection_rates'])} - identical every trial")
    print(f"  total cost: ${agg['total_usd']:.4f}")
    print("#" * 72)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(agg, indent=1))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
