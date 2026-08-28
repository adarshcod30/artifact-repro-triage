# Artifact Reproducibility Triage

**Does this research artifact actually do what its README says?**

A coding-agent workflow that reads a research software artifact, checks the
repository's own claims against its real file tree, and produces an
evidence-backed reproducibility assessment — with the uncertain cases routed to a
human instead of guessed at.

Built for the micro1 Frontier Engineering Challenge 2026 (Agentic Workflows).

---

## 1. Who has this problem?

Two groups, with the same underlying need:

**Artifact Evaluation Committee reviewers.** Every major software-engineering
conference (ICSE, ISSTA, ASE, FSE) runs an artifact track. Volunteer reviewers —
usually PhD students — are each assigned several artifacts and must decide
whether each is *Functional* (documented, consistent, complete, exercisable) or
*Reusable* (significantly exceeding minimal functionality). Committees are
chronically short of reviewers, and the work is unpaid.

**Researchers deciding what to build on.** Before investing a week reproducing a
baseline, you want to know whether the artifact will actually run.

## 2. What bottleneck makes it worth solving?

A README is a set of promises. Nothing checks them.

An artifact's documentation says "install with `requirements.txt`", "run
`scripts/run_experiments.sh`", "see `configs/default.yaml`". A reviewer reads
fluent, confident, well-structured prose and forms an impression — because
reading prose is what a human reviewer can cheaply do. Verifying that each named
file *exists* means cross-referencing dozens of paths against a repository that
may hold tens of thousands of files.

So the failure mode is specific and expensive: **a convincing README that is not
consistent with its own repository**. That gap is invisible to a reader and
obvious to a checker. In this corpus, one Reusable-badged artifact references
**15 files that do not exist**.

This is also the failure mode the whole challenge is about — output that is
convincing rather than correct.

## 3. Does the agent solve it well?

### The baseline (a fair one)

One direct prompt: the scrubbed README plus the ACM badge rubric, asked for a
tier. Same model, same rubric, same output schema, same README the solution sees.
It is what a reviewer actually does today — read the documentation and judge.

### The solution

Before the model sees anything, **every file path the README references is
checked against the repository's real file tree**. Those results are placed in the
prompt as established fact, and the model is instructed to weigh verified facts
above the README's own claims.

The verification is ordinary deterministic Python. It cannot hallucinate, costs
nothing, and every finding is citable by path. The model then reasons over
*evidence* instead of over *prose*.

Low-confidence answers are **escalated to a human reviewer** rather than recorded
as guesses — the product working as intended, not a failure.

### Measured result

Agreement with expert badges turned out to be uninformative, and we can prove it
rather than assert it — see *Honest negative result* below. The primary
experiment instead uses ground truth we author ourselves: each artifact is paired
with a **falsified twin** whose README references five files that provably do not
exist.

Same model, same rubric, same input pair. Only the evidence differs.

| Metric | Baseline | Solution |
|---|---|---|
| Noticed the falsified README | **0%** | **97%** |
| Range over 3 trials | 0% – 0% | 90% – 100% |
| Per-trial | `[0.0, 0.0, 0.0]` | `[1.0, 0.9, 1.0]` |
| Deterministic verifier | — | **75/75 claims (100%), 0 false positives** |

The baseline is *perfectly stable at zero*: across 45 opportunities it never once
downgraded a repository whose documentation had been corrupted. That is not a
tuning gap. It reads only prose, so it has no mechanism capable of detecting a
fabricated path — the blindness is structural.

Rates are floor-adjusted: an artifact already rated `Available` (the lowest tier)
on clean input cannot be downgraded further, so it is outside the metric's reach.
Both raw and adjusted figures are reported and the excluded artifacts are named
in `results/falsified_run.json`.

Model: `us.amazon.nova-pro-v1:0` on AWS Bedrock. Total cost of the reported
experiment: **$0.42**.

### Honest negative result

The evaluation this project *started* with — predicting ACM badge tier — does not
work, and the write-up keeps it visible rather than quietly dropping it.

| System | MAE (badge tiers, lower better) |
|---|---|
| Constant predictor, always `"Functional"` | **0.667** |
| Baseline | 0.733 |
| Solution | 1.000 |

**A zero-skill constant beats both systems.** The baseline only appeared better
because it collapsed onto the middle class (14 of 15 predictions), which MAE
rewards on a 3-class ordinal problem.

The cause is a ground-truth mismatch: the committee badged the curated **Zenodo
deposit**, while we analyse the living **GitHub mirror**, where README drift is
normal. The verifier is behaving correctly and being penalised for it — `LPR`
genuinely has 15 of 17 README paths missing, the solution correctly downgrades
it, and its badge says `Reusable`.

## 4. Can another person reproduce the result?

Yes, from a clean environment, in seconds and offline. See
[REPRODUCTION.md](REPRODUCTION.md).

Every API response is cached into committed fixtures, so `make repro` never
re-scrapes Zenodo, never clones a repository, and never depends on a rate limit.
Artifacts are pinned to explicit commit SHAs.

---

## Ground truth

Labels are **ACM Artifact Evaluation badges from ISSTA 2024** — assigned by an
expert committee, published, and entirely independent of this project. The corpus
is 15 artifacts whose repository links the authors themselves published in their
Zenodo deposits.

Badges are ordinal: `Available` (0) < `Functional` (1) < `Reusable` (2).

**An honest caveat, stated up front.** `Available` involves *no quality
evaluation* — it means "archived". So `Available` vs `Functional` is partly a
question of what the authors applied for, not of quality. Only
`Functional → Reusable` is a true expert quality ordering, and the results are
read with that in mind.

### Leakage defence

27% of the corpus (4 of 15) announced its own badge tier inside its README. Those
spans are redacted before any model sees them, and the scrubber carries an
executable post-condition asserting no tier word survives. A scrubber that is
merely *believed* to work is worth nothing.

---

## Metrics

Primary is **Mean Absolute Rank Error (MAE)** in badge tiers — badges are ordinal,
so one tier off is meaningfully better than two, which plain accuracy discards.

The task is asymmetric, as triage always is: calling an unevaluated artifact
*Reusable* tells a researcher to build on something never checked to work, while
the reverse merely wastes some time. **Overclaim rate** is therefore reported
separately rather than averaged away.

---

## Repository layout

```
src/artifact_triage/
  corpus/     sources.py  scrape expert badge labels
              zenodo.py   resolve artifacts to their deposits
              github.py   repo metadata
              fetch.py    build scrubbed fact sheets (tree API, zero disk)
              scrub.py    redact badge self-disclosure
  baseline/   run.py      one direct prompt over the README
  solution/   verify.py   deterministic claim verification
              run.py      judge verified facts, escalate the uncertain
  eval/       metrics.py  one scorer, shared by both systems
              negative_control.py  injected-falsehood test
```

`baseline` and `solution` feed a **single shared scorer**. Fairness is structural:
there is no code path by which one side is scored differently from the other.

---

## Improvement Changelog

See [CHANGELOG.md](CHANGELOG.md) — every iteration, the evidence that prompted it,
and what was decided, including the experiments that were removed.

## Main failure mode

**The verifier only checks claims that are shaped like file paths.**

It answers one question extremely well — *does this named file exist?* — with
100% detection and zero false positives. It cannot touch the claims that matter
most: *"this reproduces Table 3"*, *"results match the paper within 2%"*,
*"tested on Ubuntu 22.04"*. Those are semantic, and verifying them requires
actually running the artifact.

So a README could pass every check here and still be useless: every path resolves,
every script exists, and the pipeline produces numbers unrelated to the paper.
The system narrows a reviewer's search; it does not replace the reviewer. That is
why low-confidence cases escalate to a human rather than resolving to a guess.

Two narrower limits, both measured rather than assumed:

- **We analyse the GitHub mirror, not the archived deposit that was evaluated.**
  This is what invalidated the badge comparison, and it is stated in the results
  rather than buried.
- **n = 15.** ISSTA 2024 was the only venue found publishing machine-readable
  badge outcomes; other conferences document the criteria but not the results.

## Hot take

**Give an agent a control group before you give it a metric.**

Every genuine defect in this project was found by a control, and every one of them
was invisible to the headline number:

- The **negative control** — injecting claims I knew to be false — found two real
  bugs in my own verifier. Detection went 84% → 96% → 100% as each surfaced. The
  badge comparison could never have found them: it has no notion of a *known*
  wrong answer.
- The **constant predictor** — a control so trivial it needs no model, no input,
  and four lines of code — invalidated the entire primary metric by beating both
  systems.
- A **surprising measurement** turned out to be my own truncation bug. Four of
  fifteen file trees were capped at 4,000 paths, manufacturing phantom broken
  claims in exactly the artifacts driving the result.

Without those controls this project would have shipped a confident, plausible,
well-formatted number that meant nothing. Which is precisely the failure mode it
was built to detect — *convincing rather than correct* — reproduced one level up,
in the evaluation of the tool rather than in the tool itself.

The practical rule: **an agent's evaluation deserves the same adversarial scrutiny
as the agent.** If you cannot state what result would prove your metric worthless,
you do not yet know what your metric measures.
