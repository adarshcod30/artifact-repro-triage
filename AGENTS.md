# Agent Instructions

The challenge asks for "the instructions that shape each agent". This is that
document. Three agents are involved; only two call a model.

---

## 1. Baseline agent — `src/artifact_triage/baseline/run.py`

**Purpose.** A deliberately *fair* representation of what a human artifact
reviewer does today: read the documentation and form a judgement.

**Instructions.** The shared ACM rubric in `common/rubric.py`, verbatim.

**Input.** The scrubbed README, nothing else.

**Output contract.** `{tier, confidence, reasons[]}` — identical to the solution,
so a single shared scorer handles both.

**Why it is fair.** Same model, same rubric, same output schema, same scrubbed
README. The *only* difference from the solution is that none of the README's
claims have been checked. Any weaker construction would inflate the measured
improvement and would be caught by a judge reading both prompts.

---

## 2. Solution agent — `src/artifact_triage/solution/run.py`

**Purpose.** Judge verified facts rather than unchecked claims.

**Instructions.** The same shared ACM rubric, plus one added directive:

> Weigh the verified facts above the README's own claims wherever the two
> disagree. A README that references files which do not exist has not been kept
> consistent with the artifact, whatever it asserts about itself.

**Input.** The same scrubbed README, preceded by a block of verified repository
facts produced by the tool below.

**Human checkpoint.** Any answer with confidence below
`ARTIFACT_TRIAGE_ESCALATE_BELOW` (default `0.55`) is **escalated to a qualified
human reviewer** and is not scored as a prediction. This satisfies ground rules 4
and 5: the consequential judgement — one that affects an author's work — is never
made autonomously when the evidence is thin.

---

## 3. Claim verifier — `src/artifact_triage/solution/verify.py`

**Not a model.** Ordinary deterministic Python, and that is the point.

**Purpose.** Extract every file path the README references and check each against
the repository's real file tree.

**Why deterministic.** It cannot hallucinate, costs nothing, runs offline, returns
identical output on every machine, and every finding is citable by path. Asking a
model *"does this file exist?"* would reintroduce the exact failure mode the
project exists to detect.

**Verified behaviour.** 75/75 injected false claims detected, 0 false positives,
identical across all trials (`eval/negative_control.py`).

---

## Build agent — Claude Code (Opus)

This repository was written by Claude Code. Its trajectory, including every human
checkpoint, is exported to `trajectories/build-agent.md` by
`scripts/export_build_trajectory.py`, which redacts secrets and refuses to write
if any known secret pattern survives.

---

## Design principle

The capability menu in the challenge brief is context, tools, memory,
verification, skills, and orchestration — and it notes that *purposeful choices
matter more than the number of components*.

This system deliberately uses **one model call and one deterministic tool**. No
multi-agent orchestration, no memory, no retrieval. The measured improvement
(0% → 97% detection) comes entirely from changing *what the model is shown*, not
from adding components. A second agent would have added cost and failure surface
without touching the failure mode being addressed.
