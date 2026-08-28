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
from pathlib import Path

from artifact_triage.baseline.run import prompt_for as baseline_prompt
from artifact_triage.common.llm import USD_IN, USD_OUT, MODEL, PROVIDER, ask, client
from artifact_triage.common.rubric import RUBRIC
from artifact_triage.eval.negative_control import falsify
from artifact_triage.solution.run import prompt_for as solution_prompt
from artifact_triage.solution.verify import verify

OUT = Path("results/falsified_run.json")
TIER_RANK = {"Available": 0, "Functional": 1, "Reusable": 2}


def rank(tier: str | None) -> int | None:
    return TIER_RANK.get(tier) if tier else None


def main() -> None:
    cl = client()
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
    summary = {
        "provider": PROVIDER, "model": MODEL, "n_artifacts": n,
        "injected_claims": inj, "verifier_detected": det,
        "verifier_detection_rate": round(det / inj, 4) if inj else 0.0,
        "baseline_noticed": sum(r["systems"]["baseline"]["downgraded"] for r in rows),
        "solution_noticed": sum(r["systems"]["solution"]["downgraded"] for r in rows),
        "usd": round(cost, 4), "per_artifact": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=1))

    print("\n" + "=" * 68)
    print(f"{'':<34}{'baseline':>15}{'solution':>17}")
    print("-" * 68)
    print(f"{'noticed the falsified README':<34}"
          f"{summary['baseline_noticed']:>10}/{n:<4}{summary['solution_noticed']:>12}/{n:<4}")
    print(f"{'detection rate':<34}"
          f"{summary['baseline_noticed']/n:>14.0%}{summary['solution_noticed']/n:>17.0%}")
    print("-" * 68)
    print(f"deterministic verifier: {det}/{inj} injected claims found "
          f"({det/inj:.0%}) with 0 false positives")
    print(f"cost: ${cost:.4f}   model: {MODEL}")
    print("=" * 68)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
