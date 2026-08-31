"""Publish the measurements as a dataset others can reuse.

The prevalence sweep produced a per-artifact record for hundreds of research
repositories: how many file paths their README references, how many resolve,
what reproducibility infrastructure is present, and when the repository was last
touched. That is a research dataset in its own right, and it is more durable than
any conclusion drawn from it - somebody testing a different hypothesis should not
have to re-run the sweep.

Two formats:
  - CSV     for spreadsheets and R
  - JSONL   one record per line, for streaming

A DATASHEET is written alongside, because a dataset without provenance and
stated limits invites exactly the over-claiming this project is about.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

SRC = Path("results/prevalence.json")
OUT_DIR = Path("dataset")

FIELDS = [
    "artifact_id", "n_files", "claims", "broken", "broken_ratio",
    "has_dependency_manifest", "has_container", "has_ci", "has_tests",
    "has_licence", "readme_bytes", "stale_days", "stars", "archived",
    "leaked_tier",
]

DATASHEET = """# Datasheet — Research Artifact README Consistency

## What this is

Per-artifact measurements for {n} public research-software repositories: how many
file paths each README references, how many of those resolve against the
repository's actual file tree, and what reproducibility infrastructure is present.

Produced by [artifact-repro-triage](https://github.com/adarshcod30/artifact-repro-triage).

## How it was collected

1. Harvested software deposits from the public Zenodo API using venue names and
   the phrases "replication package" / "reproduction package" / "artifact
   evaluation", **stratified across publication years 2018-2026**. {discovered}
   distinct GitHub repositories were found; {n} profiled successfully.
2. For each, the complete recursive file tree and the README were read through
   the GitHub API, pinned to an explicit commit. **No repository was cloned and
   no code was executed.**
3. Every file path referenced in the README was checked for existence. URLs are
   stripped first, so links to other projects are not counted as this
   repository's claims.

**Derived values are never cached.** The per-repository cache stores only what
was fetched - the raw README and the file tree - and everything computed from
them is recomputed on load. An earlier version cached the extracted path list,
so fixing the extractor silently could not change any cached artifact while the
provenance stamp still reported the output as current.

All measurement code is deterministic. Re-running it on the same commits
reproduces every measured value exactly, with one stated exception:
`stale_days` is an age, so it is computed against the run's own reference time
(recorded as `measured_at`) and necessarily advances between runs. Every other
field - claims, broken, ratios, signals - is byte-identical.

That exception used to be unstated, and the sentence here simply claimed
byte-identical output. It was not true, which is the same defect this dataset
was built to measure.

## Fields

| Field | Meaning |
|---|---|
| `artifact_id` | GitHub `owner/repo` |
| `n_files` | files at the pinned commit |
| `claims` | file paths referenced by the README |
| `broken` | of those, how many do not exist |
| `broken_ratio` | `broken / claims` |
| `has_*` | dependency manifest, container, CI, tests, licence |
| `readme_bytes` | README size after badge redaction |
| `stale_days` | days since the last push |
| `stars`, `archived` | repository metadata |
| `leaked_tier` | README disclosed an ACM artifact tier |

## What is in it

| | |
|---|---|
| Artifacts | {n} |
| Documented file references checked | {claims:,} |
| References resolving to nothing (`broken`) | {broken:,} ({rate:.1%}) |
| Artifacts with at least one broken reference | {with_broken} of {checkable} ({prevalence:.1%}) |

## READ THIS BEFORE BENCHMARKING AGAINST THESE LABELS

**An `exists=true` label does NOT mean the path works as written.** The checker
that produced these labels is deliberately lenient: it accepts a path if it
exists exactly, **or if any real path ends with it**, or if any file anywhere in
the tree shares its basename. A README saying `src/train.py` is labelled correct
when the file actually lives at `experiments/train.py`.

Measured across this corpus:

| How a reference resolved | | |
|---|---|---|
| `exact` — works as written | {r_exact:,} | {r_exact_pct:.1%} |
| `directory` — a directory reference matched a directory | {r_dir:,} | {r_dir_pct:.1%} |
| `suffix` — found somewhere else in the tree | {r_suffix:,} | {r_suffix_pct:.1%} |
| `basename` — a file of that name exists *somewhere* | {r_base:,} | {r_base_pct:.1%} |
| **broken — not found at all** | **{broken:,}** | **{rate:.1%}** |

**{lenient:,} of {resolved:,} resolutions ({lenient_pct:.1%}) did not work as
written.** Two consequences:

1. **The broken rate here is a LOWER BOUND.** The rate at which a documented
   path fails *as a reader would follow it* is materially higher.
2. **A detector that correctly flags a relocated file will be scored a false
   positive against these labels.** If you are benchmarking, either re-derive
   the labels with your own resolution rule, or restrict to the `exact` subset.

The leniency is deliberate — flagging a file that plainly exists somewhere is
the most annoying error a checker can make — but it is a *choice*, and it is
measured rather than assumed. Reproduce with `make resolution`.

## Limitations — read these before drawing conclusions

- **Sampling is not random.** Zenodo's search is keyword-based. The corpus was
  harvested stratified across publication years 2018-2026 specifically to avoid
  the recency skew an earlier version had, but it remains a keyword sample of
  Zenodo software deposits, not a random sample of research software. {fresh} of
  {n} repositories were pushed within the last three months.
- **Only GitHub-mirrored artifacts appear.** Deposits without a GitHub link are
  absent, and those may differ systematically.
- **Path extraction is conservative.** It requires a recognised source or config
  extension, so claims phrased in prose are missed. `claims` is a lower bound.
- **A resolved path is not a working artifact.** This measures documentation
  consistency only. Nothing here was executed, so nothing here shows that an
  artifact reproduces its paper.
- **`broken` can include legitimate references to other projects.** A README
  discussing another repository's files will have them counted. Measured on this
  project's own README, where all six flagged paths were quotations.
  **Links are no longer among them.** External URLs used to be extracted as
  repository paths - the token pattern cannot contain `:`, so
  `https://github.com/other/repo/blob/main/x.py` degraded to a path that by
  construction can never exist here. That was **126 of 1,190 reported-broken
  paths (10.6%)**, now zero. Prose references to another project's files can
  still be counted; URLs cannot.

## Licence

Measurements: CC0. The underlying repositories retain their own licences.
Only public data was used; no credentials and no personal information.
"""


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"{SRC} missing - run `make prevalence` first")
    data = json.loads(SRC.read_text())
    pv = data
    # The label-quality breakdown belongs WITH the dataset, not only in the
    # README. Someone benchmarking against these labels reads this file.
    ra_path = Path("results/resolution_audit.json")
    ra = json.loads(ra_path.read_text()) if ra_path.exists() else {}
    by = ra.get("by_resolution", {})
    tot = max(ra.get("total_claims", 1), 1)
    rows = data["per_artifact"]
    OUT_DIR.mkdir(exist_ok=True)

    csv_path = OUT_DIR / "artifact_readme_consistency.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = dict(r)
            if row.get("stale_days") is not None:
                row["stale_days"] = round(row["stale_days"], 1)
            w.writerow(row)

    jsonl_path = OUT_DIR / "artifact_readme_consistency.jsonl"
    with jsonl_path.open("w") as f:
        for r in rows:
            f.write(json.dumps({k: r.get(k) for k in FIELDS + ["broken_paths"]}) + "\n")

    fresh = sum(1 for r in rows
                if r.get("stale_days") is not None and r["stale_days"] < 90)
    discovered = sum(1 for _ in open("data/discovered.jsonl")) \
        if Path("data/discovered.jsonl").exists() else len(rows)
    (OUT_DIR / "DATASHEET.md").write_text(
        DATASHEET.format(
            n=len(rows), fresh=fresh, discovered=discovered,
            claims=pv.get("total_claims", 0), broken=pv.get("total_broken", 0),
            rate=pv.get("broken_claim_rate", 0.0),
            with_broken=pv.get("n_with_broken", 0),
            checkable=pv.get("n_checkable", 0),
            prevalence=pv.get("prevalence", 0.0),
            r_exact=by.get("exact", 0), r_exact_pct=by.get("exact", 0) / tot,
            r_dir=by.get("directory", 0), r_dir_pct=by.get("directory", 0) / tot,
            r_suffix=by.get("suffix", 0), r_suffix_pct=by.get("suffix", 0) / tot,
            r_base=by.get("basename", 0), r_base_pct=by.get("basename", 0) / tot,
            lenient=ra.get("resolved_leniently", 0),
            resolved=ra.get("resolved", 1),
            lenient_pct=ra.get("resolved_leniently", 0) / max(ra.get("resolved", 1), 1),
        ))

    print(f"  {csv_path}    {csv_path.stat().st_size:,} bytes")
    print(f"  {jsonl_path}  {jsonl_path.stat().st_size:,} bytes")
    print(f"  {OUT_DIR/'DATASHEET.md'}")
    print(f"\n  {len(rows)} artifacts, {sum(r['claims'] for r in rows):,} claims measured")


if __name__ == "__main__":
    main()
