# Related Work and Evidence Base

Written to answer three questions honestly, in this order:

1. **Is the problem real?** — or did I invent a defect that nobody suffers from.
2. **Has this already been built?** — ground rule 2 requires being clear about what
   existed before this competition.
3. **What, if anything, is new here?** — stated narrowly, without inflating it.

Every claim below links to a paper. Where the literature already does what this
project does, that is said plainly rather than omitted.

---

## 1. The problem is documented, not assumed

### Research artifacts are frequently incomplete

| Finding | Source |
|---|---|
| Of 106 research artifacts assessed against the ACM badging policy, only **39.70%** were completely accessible, and "most of the analyzed research artifacts are incomplete" | Guevara-Vega et al., [*Research artifacts for human-oriented experiments in software engineering*](https://doi.org/10.1016/j.jss.2024.112187), JSS 2024 |
| A reproducibility study of 8 EMNLP 2021 papers found "source code releases leave much to be desired"; the authors recommend conferences **"require self-contained artifacts and provide a venue to evaluate such artifacts at the time of publication"** | Arvan, Pina & Parde, [*Reproducibility in Computational Linguistics: Is Source Code Enough?*](https://doi.org/10.18653/v1/2022.emnlp-main.150), EMNLP 2022 |
| **1,921 of 2,702** Python builds (71.1%) were unreproducible due to dependency errors | Mukherjee, Almanza & Rubio-González, [*Fixing dependency errors for Python build reproducibility*](https://doi.org/10.1145/3460319.3464797), ISSTA 2021 |
| Across ~750 ML-security papers (2013–2022): **no statistically significant difference in artifact availability before and after** Artifact Evaluation Committees were introduced — though artifacts that pass AE "work at a higher rate" than those that do not | Olszewski et al., [*"Get in Researchers; We're Measuring Reproducibility"*](https://doi.org/10.1145/3576915.3623130), CCS 2023 |
| An 11-year follow-up measuring both indirect (availability) and direct (running the code) reproducibility across applied security conferences | Olszewski et al., [*Reproducibility in Applied Security Conferences*](https://doi.org/10.1145/3736731.3746151), 2025 |

The Arvan et al. recommendation matters most here: they independently arrived at
**"evaluate artifacts at the time of publication"**, which is exactly the moment
this tool is built for. The Olszewski finding matters second-most: AE improves
artifacts that go through it but has not moved availability overall — so the
bottleneck is reviewer capacity, not policy.

### Documentation drifts from code, measurably

| Finding | Source |
|---|---|
| Across **3,000+ GitHub projects**, "most projects contain at least one outdated code element reference at some point in their history" | Tan, Wagner & Treude, [*Detecting outdated code element references in software repository documentation*](https://doi.org/10.1007/s10664-023-10397-6), EMSE 2023 |
| README quality in SE research artifacts averaged **49.8%** across 2017–2022; link rot averaged **9.4%** (up to 29.8% in some years); only **56.4%** of artifacts were reachable at their published links | [*Research Artifacts in Software Engineering Publications: Status and Trends*](https://arxiv.org/pdf/2404.06852) |
| **Over 40%** of "functional" artifacts from 2024–2025 fail within months from drifting dependencies, unpinned versions and incomplete environments | [*Large Language Models for Software Engineering: A Reproducibility Crisis*](https://arxiv.org/html/2512.00651v1) |

---

## 2. Prior art — what already existed

**This project did not invent the idea of checking documentation against the
repository.** Two published systems do exactly that, and both predate it.

### READU (Baek, Krampf & Pradel, 2026) — the closest work

[*READU: Inconsistency-Driven Just-in-Time Detection and Repair of README Bugs*](https://arxiv.org/abs/2607.15780)

> "README bugs often manifest as inconsistencies between documentation and
> another source of truth: either repository-internal facts, such as source code,
> or repository-external facts, such as external dependencies."

That is the same core insight as this project's verifier. READU goes **further**
in several respects: it runs just-in-time on commits, it **automatically repairs**
the bugs it finds (217 of 244 true positives), and it reports 44 confirmed fixes
in real projects. It achieves **75% precision** on 6,000 commits from six popular
repositories including Linux and Spring Boot.

**Where it differs from this project:** READU evaluates on general open-source
software, not research artifacts; it measures detection on a commit sample rather
than **prevalence across a population**; and it does not address artifact
evaluation or compare against an LLM reading the README alone.

### Tan, Wagner & Treude (2023) — outdated code element references

[*Detecting outdated code element references in software repository documentation*](https://doi.org/10.1007/s10664-023-10397-6)

Detects code elements (functions, classes) that survive in documentation after
every source instance has been deleted, across 3,000+ GitHub projects, and files
real issues against affected repositories. Again: general OSS, and *code
elements* rather than *file paths*, but the same family of check.

### Honest consequence

**The mechanism in this project is not novel.** A reviewer who knows this
literature will recognise the verifier immediately, and should. What follows is
what remains after removing everything prior work already established.

---

## 3. What this project adds, stated narrowly

| Contribution | Why prior work does not cover it |
|---|---|
| **Prevalence in *research artifacts* specifically** — 742 artifacts, 6,840 documented file references, 56.3% carrying at least one broken claim | Tan et al. measure general OSS; READU measures detection on a commit sample, not population prevalence. Neither reports a rate for research artifacts. |
| **The defect does not accumulate with age** — flat across four years (0.256 / 0.232 / 0.305 / 0.234), oldest bucket n=173 at median 1,423 days | The literature attributes artifact failure to *drift* (unpinned dependencies, incomplete environments). This measurement says broken path claims are present **at publication**, so they are a different failure mode from decay. |
| **Ecosystem variation** — Java 0.340 and Rust 0.364 versus Python 0.192 and Notebooks 0.104 | Not reported anywhere found. |
| **A causal comparison against an LLM reading prose** — baseline 0%, solution 93–100% on two model families, with a **placebo-evidence control** that collapses detection to 0% | READU has no LLM baseline; Tan et al. predates LLM baselines. The placebo isolates *the evidence* as the cause rather than the prose. |
| **Targeted at the artifact-evaluation reviewer** | Arvan et al. call for evaluation "at the time of publication"; no tool found is built for that reviewer's hour. |
| **Output mapped onto the named ACM badge criteria**, with the one criterion no machine can settle marked as such | READU and Tan et al. report documentation bugs. Neither expresses findings as evidence for or against `Documented` / `Consistent` / `Complete` / `Exercisable` - the decision an AE reviewer actually has to make. |

The honest summary: **the contribution is measurement and framing, not the
detector.** The detector is a competent re-implementation of an idea that already
exists in the literature; what is new is pointing it at research artifacts at
scale, and demonstrating that a language model cannot substitute for it.

### Why the criteria mapping matters, and its limit

ACM defines `Artifacts Evaluated - Functional` as four named qualities. Quoting
them exactly is what makes the mapping checkable rather than rhetorical:

| Quality | ACM definition | What a machine can establish |
|---|---|---|
| **Documented** | "At a minimum, an inventory of artifacts is included, and sufficient description is provided to enable the artifacts to be exercised." | That a README exists and makes concrete, checkable references. **Not** whether the description is *sufficient*. |
| **Consistent** | "The artifacts are relevant to the associated paper and contribute in some inherent way to generating its main results." | **Nothing.** This requires reading the paper. Always escalated. |
| **Complete** | "To the extent possible, all components relevant to the paper in question are included." | A documented file that does not exist is direct evidence of incompleteness. **Not** whether the missing component matters. |
| **Exercisable** | "Included scripts and / or software used to generate the results in the associated paper can be successfully executed." | That the scripts exist and the environment is pinned - a *necessary* condition. **Never** the sufficient one: nothing here is executed. |

Criteria quoted from the ACM Artifact Review and Badging policy as reproduced on
the [ICSE 2025 artifact evaluation page](https://conf.researchr.org/track/icse-2025/icse-2025-artifact-evaluation).
The ACM policy page itself refused automated retrieval (HTTP 403), so the text
was taken from a conference reproduction of it; a reviewer should check it
against the primary source.

**The limit, stated plainly:** this mapping does not make the tool an artifact
evaluator. It answers a strict subset of one badge's criteria, and the subset it
answers is the mechanical one. `test_consistent_is_never_claimed_as_machine_checkable`
in the regression suite exists to keep it that way.

---

## 4. Threats to validity, restated against the literature

- **Precision.** This project reports 100% precision on a hand-audited sample of
  its own labelled corpus (n=37 findings), after fixing three false-positive
  classes. READU reports 75% on a larger, harder, general-OSS corpus with an LLM
  judge. **These numbers are not comparable** — different corpora, different
  claim types, and ours is a small hand audit rather than a systematic evaluation.
  Ours should be read as "no false positives survived a manual check of 37
  findings", not as a precision figure competitive with READU's.
- **Sampling.** A keyword sample of Zenodo software deposits, stratified by
  publication year. Not a random sample of research software.
- **n=15 for the labelled comparison.** ISSTA 2024 was the only venue found
  publishing machine-readable badge outcomes across 12 venues probed.
- **No repair.** READU repairs; this project only reports and suggests.
- **Badge-agreement MAE is a single-run point estimate.** The model is not
  deterministic at temperature 0; observed baseline MAE moved between 0.733 and
  0.800 across same-day re-runs. The *conclusion* is robust — the best constant
  control requires no model and scores 0.667 exactly, below every observed value
  — but the individual figures should be read as approximate. The falsified
  experiment, which carries the positive claim, does report 3 trials and a range.
- **Badge leakage is defended by pattern matching, which is not a proof.** Ten
  phrasings are asserted redacted and six innocent sentences asserted intact,
  and no tier word survives anywhere in the stored corpus. A phrasing nobody
  thought of could still leak. The defence errs toward over-redaction on
  purpose: both systems receive byte-identical scrubbed text, so over-redaction
  costs realism equally and cannot bias the comparison, while leakage voids it.
- **No user study.** No evidence that a reviewer is actually faster with this,
  or that the badge-criteria framing helps them. The claim is that the output is
  *addressed to* the reviewer's decision, not that it measurably improves it.
- **The criteria mapping is an interpretation.** Reading a broken path reference
  as evidence against `Complete` is a judgement, defensible but not official.
  ACM has not blessed it, and an AE chair might map it differently.

---

## 5. Search method, and its limits

Literature was searched through OpenAlex/Semantic Scholar (~250M records) via
queries on documentation–code inconsistency, artifact evaluation, reproducibility
badges, and automated reproducibility checking, plus targeted web search for
measurement studies.

**This is not a systematic review.** Two of the later searches drifted off-topic
through lexical matching and returned unrelated results, and a formal duplication
test over-specified and returned near-zero matches — which the tool itself warns
is "a retrieval artefact, not evidence of an open gap". Relevant work may have
been missed. If a reviewer knows of prior work this project failed to cite, that
is a gap in this search, not a claim of novelty against it.
