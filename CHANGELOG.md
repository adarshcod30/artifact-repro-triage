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

| Iteration 4 | Recover the 28 artifacts without a Zenodo repo link by searching GitHub for the paper title. | 20 recovered - but inspection found `jekyll/minima` matched to a patch-generation paper, `sleuthkit/sleuthkit` to an unrelated fuzzer named Sleuth, and `SimonHung/LodeRunner_TotalRecall` (a game) to "Total Recall? How Good are Static Call Graphs Really?". | Keyword overlap on repo *metadata* matches almost anything. Generic paper vocabulary is not a fingerprint. |
| Iteration 5 | Harden verification: require the repo's README to corroborate - verbatim title phrase, an ISSTA 2024 citation, or full keyword coverage. | False positives fell from 20 to 5, but the LodeRunner game *still* passed: its README genuinely contains "total recall". | Tightening a fuzzy matcher shrinks the error rate without eliminating the error class. |
| Iteration 6 | **Removed GitHub search entirely.** Kept only repo links the artifact authors published in their own Zenodo deposits. | Corpus: 15 artifacts, zero false positives, badges balanced 6 Reusable / 4 Available / 5 Functional. All 15 slugs verified live against the GitHub API. | Kept. Since the corpus *is* the ground truth, a wrong label is worse than a smaller N. 15 clears the brief's "ten or more cases" target. |
| Bugfix | Two repo slugs were truncated (`upbea`, `..._Artifac`). | `"upbeat".rstrip(".git")` returns `"upbea"` - `rstrip` strips any trailing characters in the set, not the suffix. | Replaced with `removesuffix`. Would have broken 2 of 15 clones with a confusing 404. |

## Scrubber (leakage defence)

| Stage | What I tried and why | Evidence | Decision / Learning |
|---|---|---|---|
| Iteration 7 | Artifacts often announce their own badge in the README. Built a scrubber so the model judges the work instead of reading the answer. | Self-test caught three bugs in my first version: redactions nested inside each other; `.../badge/artifact-reusable-green` kept the tier word after the word "badge" alone was redacted; and "results **were** reproduced" evaded a pattern expecting adjacent words. | Reordered patterns so broad structures (images, URLs, whole sentences) fire before the bare-word rule, and made the redaction token keyword-free so it cannot re-match. |
| Iteration 8 | Added a post-condition asserting no tier word survives scrubbing, rather than trusting the patterns. | All six adversarial samples now scrub clean; the assertion fails loudly if any `reusable`/`functional` survives. | Kept. A scrubber that is merely *believed* to work is worth nothing - the audit has to be executable. |

## Experiments removed

- **GitHub search for missing repos** (Iterations 4-5). Recovered 20 artifacts, but a measured false-positive rate that two rounds of hardening could not eliminate. Cutting it traded corpus size for label integrity. The lesson is on-theme: fuzzy matching produced *confident, plausible, wrong* answers - precisely the failure mode this project exists to detect.
- **Downloading Zenodo deposits** (Iteration 1). Correct in principle - the deposit is the badged unit - but 326 GB makes it unusable, and it would have pushed our own reproduction time from seconds to hours. Analysing the GitHub mirror trades a little fidelity for a pipeline judges can actually re-run.

## Known threats to validity

- The badge was awarded to the Zenodo deposit; we analyse the GitHub mirror, which may have drifted since. Mitigated by pinning to a commit and recording it.
- 12 of 43 artifacts never resolved to Zenodo. Corpus is therefore a subset, not the full venue.
