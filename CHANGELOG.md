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

## Fact-sheet extraction

| Stage | What I tried and why | Evidence | Decision / Learning |
|---|---|---|---|
| Iteration 9 | Shallow-clone each repo to read its file tree and README. | `zhangxiaosa/LPR` alone was **15 GB**; the run drove the disk from 18 GB free to **1.9 GB (100% full)** before I killed it. Research repos routinely commit datasets, models and VM images. | **Removed.** `--depth 1` still transfers every blob at HEAD. |
| Iteration 10 | Replaced cloning with the GitHub tree API: recursive file listing plus the README endpoint. | 15/15 fact sheets built in seconds, **0 bytes of disk**, pinned to explicit commit SHAs. The same repo reports 430 MB of HEAD blobs versus 15 GB cloned - the rest was history and LFS. | Kept. Faster, safer, and deterministic. The thing I actually needed (does path X exist?) never required file contents. |
| Iteration 11 | First tree-API run timed out at 2 minutes. | Every call slept 2.2s - a throttle sized for `/search/*` (30 req/min) applied to the whole REST API (5000/hr). | Throttle now depends on endpoint. Build time went from >120s to seconds. |
| **Leakage measured** | Ran the scrubber across all 15 fact sheets to quantify the risk rather than assume it. | **4 of 15 READMEs (27%) disclosed their own ACM badge tier.** | Confirms the scrubber is load-bearing, not defensive decoration. Without it, 27% of the corpus would hand the model its own answer. |

## Claim verification (the core mechanism)

| Stage | What I tried and why | Evidence | Decision / Learning |
|---|---|---|---|
| Iteration 12 | Extract every file path a README references, then check each against the real file tree. A README is a set of promises; broken promises are hard evidence, established with zero model calls. | First run reported implausible ratios - 55 of 58 claims "broken" on one artifact. | Investigated instead of reporting it. |
| Iteration 13 | Inspected the extracted claims directly. | The extractor matched any token containing a dot: version numbers (`3.10.12`, `0.01`), Java class names (`com.baidu...EchoServiceTest.testDy`), module paths (`vllm.entrypoints.openai.api`), bare domains (`github.com`). | Required a real source/config extension plus structural checks. Claims fell 58 -> 21 and 29 -> 7 on the worst offenders. **A dot does not make a path.** |
| Iteration 14 | Measured whether broken-claim ratio alone separates the badge tiers. | It does not, even after the fix: Available 0.260, Functional 0.081, Reusable 0.243 - non-monotonic, and two outliers dominate at n=15. | **Reported rather than buried.** Also surfaced a ground-truth subtlety: `Available` involves *no quality evaluation at all* - it means "archived", so Available vs Functional is partly "what did the authors apply for". Only Functional -> Reusable is a true expert quality ordering. |
| Iteration 15 | Kept the verifier as an *input to the judge* rather than as a standalone predictor. | Verifier still finds real, checkable defects: `zhangxiaosa/LPR` references 12 files that do not exist; `THU-WingTecher/DeepConstr` references 18. | Kept. Whether verified facts beat a raw README *for the model* is the experiment the baseline/solution comparison exists to answer - it is not settled by the raw signal's own correlation. |

| Iteration 16 | Noticed `zhangxiaosa/LPR` reported 12 broken paths despite having 31,020 files. Checked whether the fact sheet was complete. | **4 of 15 fixtures had a truncated file tree** - I stored `paths[:4000]`, so any path beyond the 4000th was reported "not found". The four truncated artifacts were exactly the outliers driving the Iteration 14 result. | Removed the cap. `THU-WingTecher/DeepConstr` fell from 18 broken claims to 4. **My headline negative result had been contaminated by my own bug** - the lesson is that a surprising measurement should be debugged before it is believed. |
| Iteration 17 | Re-measured separation on complete trees. | Available 0.093, Functional 0.081, Reusable 0.215 - still non-monotonic, but now driven by a single genuine outlier (LPR references 12 files that do not exist even against its full tree). | Reframed the verifier honestly: it is a **sparse, high-precision defect detector**, not a tier classifier. It fires rarely; when it fires the defect is real and citable by path. |

## Experiments removed

- **Shallow cloning** (Iteration 9). Filled the disk to 100% on a 15-artifact corpus. Taught me that repo *size at HEAD* and *clone size* differ by more than an order of magnitude, and that the fact I needed (path existence) never justified transferring bytes at all.
- **GitHub search for missing repos** (Iterations 4-5). Recovered 20 artifacts, but a measured false-positive rate that two rounds of hardening could not eliminate. Cutting it traded corpus size for label integrity. The lesson is on-theme: fuzzy matching produced *confident, plausible, wrong* answers - precisely the failure mode this project exists to detect.
- **Downloading Zenodo deposits** (Iteration 1). Correct in principle - the deposit is the badged unit - but 326 GB makes it unusable, and it would have pushed our own reproduction time from seconds to hours. Analysing the GitHub mirror trades a little fidelity for a pipeline judges can actually re-run.

## Known threats to validity

- The badge was awarded to the Zenodo deposit; we analyse the GitHub mirror, which may have drifted since. Mitigated by pinning to a commit and recording it.
- 12 of 43 artifacts never resolved to Zenodo. Corpus is therefore a subset, not the full venue.
