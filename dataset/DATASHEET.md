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

## What is in it

| | |
|---|---|
| Artifacts | 742 |
| Documented file references checked | 6,815 |
| References resolving to nothing (`broken`) | 1,254 (18.4%) |
| Artifacts with at least one broken reference | 340 of 608 (55.9%) |

## READ THIS BEFORE BENCHMARKING AGAINST THESE LABELS

**An `exists=true` label does NOT mean the path works as written.** The checker
that produced these labels is deliberately lenient: it accepts a path if it
exists exactly, **or if any real path ends with it**, or if any file anywhere in
the tree shares its basename. A README saying `src/train.py` is labelled correct
when the file actually lives at `experiments/train.py`.

Measured across this corpus:

| How a reference resolved | | |
|---|---|---|
| `exact` — works as written | 2,833 | 41.6% |
| `directory` — a directory reference matched a directory | 602 | 8.8% |
| `suffix` — found somewhere else in the tree | 2,007 | 29.4% |
| `basename` — a file of that name exists *somewhere* | 111 | 1.6% |
| **broken — not found at all** | **1,254** | **18.4%** |

**2,118 of 5,561 resolutions (38.1%) did not work as
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
