"""Publish the measurements as a dataset others can reuse.

The prevalence sweep produced a per-artifact record for 376 research
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
   evaluation". 398 distinct GitHub repositories were found; {n} profiled
   successfully.
2. For each, the complete recursive file tree and the README were read through
   the GitHub API, pinned to an explicit commit. **No repository was cloned and
   no code was executed.**
3. Every file path referenced in the README was checked for existence.

All measurement code is deterministic. Re-running it on the same commits produces
byte-identical output.

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

## Licence

Measurements: CC0. The underlying repositories retain their own licences.
Only public data was used; no credentials and no personal information.
"""


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"{SRC} missing - run `make prevalence` first")
    data = json.loads(SRC.read_text())
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
    (OUT_DIR / "DATASHEET.md").write_text(
        DATASHEET.format(n=len(rows), fresh=fresh))

    print(f"  {csv_path}    {csv_path.stat().st_size:,} bytes")
    print(f"  {jsonl_path}  {jsonl_path.stat().st_size:,} bytes")
    print(f"  {OUT_DIR/'DATASHEET.md'}")
    print(f"\n  {len(rows)} artifacts, {sum(r['claims'] for r in rows):,} claims measured")


if __name__ == "__main__":
    main()
