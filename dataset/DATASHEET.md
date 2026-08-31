# Datasheet — Research Artifact README Consistency

## What this is

Per-artifact measurements for 742 public research-software repositories: how many
file paths each README references, how many of those resolve against the
repository's actual file tree, and what reproducibility infrastructure is present.

Produced by [artifact-repro-triage](https://github.com/adarshcod30/artifact-repro-triage).

## How it was collected

1. Harvested software deposits from the public Zenodo API using venue names and
   the phrases "replication package" / "reproduction package" / "artifact
   evaluation", **stratified across publication years 2018-2026**. 766
   distinct GitHub repositories were found; 742 profiled successfully.
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

## Limitations — read these before drawing conclusions

- **Sampling is not random.** Zenodo's search is keyword-based. The corpus was
  harvested stratified across publication years 2018-2026 specifically to avoid
  the recency skew an earlier version had, but it remains a keyword sample of
  Zenodo software deposits, not a random sample of research software. 356 of
  742 repositories were pushed within the last three months.
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
