"""Negative control: inject known-false claims and measure who notices.

WHY THIS EXISTS
---------------
Scoring against ACM badges answers "does the system agree with experts?" It does
not isolate *why*. This does.

For each artifact we synthesise a falsified twin: the README gains a handful of
plausible instructions referencing files that provably do not exist in the
repository. Ground truth is exact by construction - we know precisely which
claims are false, because we wrote them.

That converts a fuzzy question into a measurable one:
  - The verifier is deterministic, so its detection rate should be 1.00. Any
    miss is a bug in the checker, not an opinion.
  - The baseline reads only prose. It has no mechanism to detect a fabricated
    path, so it should be near-blind by construction - and that is the point.

Injections are seeded, so the control is reproducible.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from artifact_triage.solution.verify import verify

# Plausible paths a real research README would reference. Injected only when
# genuinely absent from the target repository.
CANDIDATES = [
    "scripts/run_experiments.sh", "configs/default.yaml", "src/train_model.py",
    "tools/evaluate_all.py", "docker/build_image.sh", "data/prepare_dataset.py",
    "bin/reproduce_table3.sh", "experiments/rq2_analysis.py",
    "setup/install_deps.sh", "notebooks/figure4.ipynb",
    "src/baseline_runner.py", "configs/experiment_grid.json",
]

TEMPLATE = """

## Reproducing the results

Install the environment and run the full pipeline:

```bash
bash {p0}
python {p1} --config {p2}
```

Individual stages can be run separately. See `{p3}` for the analysis step
and `{p4}` for the figure generation.
"""


def falsify(fixture: dict, n: int = 5, seed: int = 0) -> tuple[dict, list[str]]:
    """Append instructions referencing n paths that do not exist in this repo."""
    rng = random.Random(f"{fixture['artifact_id']}:{seed}")
    existing = set(fixture["file_tree"])
    basenames = {p.rsplit("/", 1)[-1] for p in fixture["file_tree"]}
    pool = [c for c in CANDIDATES
            if c not in existing and c.rsplit("/", 1)[-1] not in basenames]
    if len(pool) < n:
        return fixture, []
    picked = rng.sample(pool, n)
    twin = json.loads(json.dumps(fixture))  # deep copy
    twin["artifact_id"] = fixture["artifact_id"] + "#falsified"
    twin["readme"] = fixture["readme"] + TEMPLATE.format(
        p0=picked[0], p1=picked[1], p2=picked[2], p3=picked[3], p4=picked[4])
    # Re-derive claims the same way the real pipeline does, so nothing is special-cased.
    from artifact_triage.corpus.fetch import referenced_paths
    twin["readme_referenced_paths"] = referenced_paths(twin["readme"])
    return twin, picked


def main() -> None:
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    out_dir = Path("data/negative_control")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_injected = total_detected = 0
    false_positives = 0
    rows = []
    for p in fixtures:
        fx = json.loads(p.read_text())
        twin, injected = falsify(fx)
        if not injected:
            continue
        before = verify(fx)
        after = verify(twin)
        detected = [i for i in injected if i in after.broken_paths]
        # A real path must never be flagged. Anything newly broken that we did
        # not inject is a false positive in the checker.
        newly_broken = set(after.broken_paths) - set(before.broken_paths)
        fp = sorted(newly_broken - set(injected))
        total_injected += len(injected)
        total_detected += len(detected)
        false_positives += len(fp)
        rows.append({"artifact_id": fx["artifact_id"], "injected": injected,
                     "detected": detected, "false_positives": fp,
                     "broken_before": before.claims_broken,
                     "broken_after": after.claims_broken})
        (out_dir / p.name).write_text(json.dumps(twin, indent=1))
        print(f"  {len(detected)}/{len(injected)} detected"
              f"{'  FP:' + str(len(fp)) if fp else '':>8}   {fx['artifact_id']}")

    rate = total_detected / total_injected if total_injected else 0.0
    print(f"\n{'=' * 62}")
    print(f"injected false claims  : {total_injected}")
    print(f"detected by verifier   : {total_detected}   ({rate:.1%})")
    print(f"false positives        : {false_positives}")
    print(f"{'=' * 62}")
    Path("results").mkdir(exist_ok=True)
    Path("results/negative_control.json").write_text(json.dumps(
        {"injected": total_injected, "detected": total_detected,
         "detection_rate": round(rate, 4), "false_positives": false_positives,
         "per_artifact": rows}, indent=1))
    print("-> results/negative_control.json")
    if rate < 1.0:
        print("\nWARNING: detection is not 100% - the checker has a gap.")


if __name__ == "__main__":
    main()
