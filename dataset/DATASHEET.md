# Datasheet — Research Artifact README Consistency

## What this is

Per-artifact measurements for 732 public research-software repositories: how many
file paths each README references, how many of those resolve against the
repository's actual file tree, and what reproducibility infrastructure is present.

Produced by [artifact-repro-triage](https://github.com/adarshcod30/artifact-repro-triage).

## How it was collected

1. Harvested software deposits from the public Zenodo API using venue names and
   the phrases "replication package" / "reproduction package" / "artifact
   evaluation". 398 distinct GitHub repositories were found; 732 profiled
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

- **Sampling is not random.** Zenodo's search is keyword-based and its default
  sort favours recent deposits. The corpus skews heavily toward artifacts pushed
  within the last three months (355 of 732). Do not treat it as
  representative of all research software.
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
