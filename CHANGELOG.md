# Improvement Changelog

Every meaningful iteration, the evidence that prompted it, and what I decided next.
Schema follows the challenge brief.

## Corpus construction

| Stage | What I tried and why | Evidence | Decision / Learning |
|---|---|---|---|
| Baseline | Scrape ISSTA 2024 Artifact Evaluation page for expert badge labels. Needed ground truth I did not author myself. | 43 artifacts parsed via the `data-facet-badge` attribute. Distribution: Available 23, Functional 11, Reusable 9. | Kept. Labels are expert-assigned, published, and independent of this project. Parsing the data attribute (not visible text) survives theme changes. |
| Iteration 1 | Resolve each title to its Zenodo deposit and download the artifact for analysis. The deposit is literally what the committee badged. | Total corpus download would be **326 GB**. Largest single artifact 190 GB; only 6 of 21 resolved deposits were under 100 MB. | **Removed.** Downloading deposits is infeasible and would also wreck our own reproducibility - a judge cannot re-run a 326 GB pipeline. |
| Iteration 2 | 11 of 43 rows were lost during resolution. Investigated rather than accepting the loss. | All 11 failures were `HTTP 429 TOO MANY REQUESTS`, not genuine absences. | Added exponential backoff (2s doubling, 6 attempts). Resolved rows went **19 -> 28**. Lesson: a silent "not found" was really a rate limit. |
| Iteration 3 | Harvest GitHub mirrors from Zenodo metadata instead of downloading deposits. Research artifacts almost always mirror their code on GitHub. | 15 of 31 resolved records carry a GitHub repo. Badge spread 6 Reusable / 4 Available / 5 Functional - better balanced than the raw 43. | Kept. Shallow clone measured at 2.3s / 8.6 MB per repo, versus 326 GB for deposits. |

## Experiments removed

- **Downloading Zenodo deposits** (Iteration 1). Correct in principle - the deposit is the badged unit - but 326 GB makes it unusable, and it would have pushed our own reproduction time from seconds to hours. Analysing the GitHub mirror trades a little fidelity for a pipeline judges can actually re-run.

## Known threats to validity

- The badge was awarded to the Zenodo deposit; we analyse the GitHub mirror, which may have drifted since. Mitigated by pinning to a commit and recording it.
- 12 of 43 artifacts never resolved to Zenodo. Corpus is therefore a subset, not the full venue.
