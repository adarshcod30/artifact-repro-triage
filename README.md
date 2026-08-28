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

### Measured: the negative control

Agreement with expert badges answers *"does it match the experts?"*. It does not
isolate *why*. So each artifact also gets a falsified twin whose README references
files that provably do not exist — ground truth is exact by construction.

| | Result |
|---|---|
| Injected false claims | **75** |
| Detected by the verifier | **75 (100%)** |
| False positives | **0** |

The baseline reads only prose and has no mechanism capable of detecting a
fabricated path. Its blindness here is structural, not incidental.

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

*(Completed after the final evaluation run.)*

## Hot take

*(Completed after the final evaluation run.)*
