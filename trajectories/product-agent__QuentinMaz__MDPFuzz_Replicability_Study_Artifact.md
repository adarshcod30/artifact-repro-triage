# Trajectory — `QuentinMaz/MDPFuzz_Replicability_Study_Artifact`

- **Paper**: Policy Testing with MDPFuzz (Replicability Study)
- **Pinned commit**: `627c5d556e77`
- **Files in repository**: 1,129
- **Expert badge (held out from both agents)**: `Reusable`

---

## Step 0 — Shared agent instructions

Both agents receive this verbatim. The task definition is held constant; only the evidence differs.

```
You are assessing a research software artifact the way an ACM
Artifact Evaluation Committee reviewer would, and assigning the badge tier it
would most likely receive.

The tiers, per ACM's published definitions:

- "Available": the artifact is placed in a public archival repository. This tier
  involves NO evaluation of whether the artifact works. It reflects archival
  only.
- "Functional": the artifact is documented, consistent, complete, exercisable,
  and includes evidence of verification and validation. A reviewer could follow
  the documentation and exercise the artifact.
- "Reusable": everything in Functional, plus documentation and structure of a
  quality that significantly exceeds minimal functionality, such that others can
  reuse and repurpose it.

Answer with the single tier you judge most likely, a calibrated confidence in
[0,1], and up to six short reasons. Be honest about uncertainty: a low
confidence routes the artifact to a human reviewer, which is a correct and
useful outcome when the evidence is genuinely thin.
```

## Step 1 — Input preparation (both agents)

Scrubber found no badge self-disclosure in this README.

## Step 2 — Tool call: deterministic claim verification

*Solution only. No model involved — ordinary Python over the repository's real file tree.*

**Tool input**: 3 candidate paths extracted from the README.

**Tool response**:

```
VERIFIED REPOSITORY FACTS (checked against the actual file tree):
- files in repository: 1129
- README size: 8638 bytes
- dependency manifest present: True
- container definition present: True
- CI configuration present: False
- build/install script present: False
- test files present: False
- licence present: True

README PATH CLAIMS: 3 checked, 0 could NOT be found in the repository.
Every path the README references was found.
The README references no checkable file paths.
```

## Step 3 — BASELINE agent

**Prompt** (8,793 chars; README truncated here for readability):

```
Artifact repository: QuentinMaz/MDPFuzz_Replicability_Study_Artifact
Paper: Policy Testing with MDPFuzz (Replicability Study)

README (verbatim):
---
# Policy Testing with MDPFuzz (Replicability Study): Artifact

This repository is the artifact of the paper *Policy Testing with MDPFuzz (Replicability Study)*.
Its content consists of a <ins>reproduction</ins> study and a <ins>replication</ins> study of the paper [MDPFuzz: testing models solving Markov decision processes](https://dl.acm.org/doi/abs/10.1145/3533767.3534388).
<!-- To that regard, the submission was already supported by two distinct code basis of the studies. -->
This present artifact's structure reflects this, as it is composed of two main folders, namely: `reproduction/` and `replication/`.
The very own nature of the work makes that it involves a tremendous amount of computations; yet we design the code such that the results should be similar if not identical to the ones in the paper.
We additionally include a demontration as well as step-by-step instructions to entirely reproduce the two studies.
Since we acknowledge that running all the experiments is almost untractable, we include Zenodo links to the data used in the original submission for the two studies.

## Getting Started

### Introduction

The studies consist in executing testing methods for Reinforcement Learning models (also known as *policies*) in diff
… README continues …
```

**Final answer**:

```json
{
  "tier": "Functional",
  "confidence": 0.8,
  "reasons": [
    "The artifact is placed in a public archival repository.",
    "The README provides detailed instructions on how to set up and run the experiments.",
    "A Docker image is provided to simplify the setup process.",
    "Step-by-step instructions are given for both reproduction and replication studies.",
    "A demonstration is included to show the functionality of the artifact.",
    "The artifact includes evidence of verification and validation through the provided demonstration and instructions."
  ],
  "escalated_to_human": false
}
```

## Step 3 — SOLUTION agent

**Prompt** (9,808 chars; README truncated here for readability):

```
Artifact repository: QuentinMaz/MDPFuzz_Replicability_Study_Artifact
Paper: Policy Testing with MDPFuzz (Replicability Study)

VERIFIED FACTS. Each line was established by running code against the repository, not by reading its documentation. Where these contradict the README, they are what actually holds.

== Documentation consistency ==
Files in repository: 1129
README size: 8638 bytes
README references 3 file path(s); 0 do NOT exist in the repository.
  All referenced paths were found.

== Environment reproducibility ==
Dependencies: replication/cart/requirements.txt: 23/23 pinned, 0 bounded, 0 floating (100% pinned)
Container: Dockerfile: 1 of 1 base image(s) unpinned (continuumio/miniconda3)
CI configuration present: False
Tests present: False
Licence present: True

== Portability ==
No machine-specific values found across 12 inspected file(s).

== External links ==
7 URL(s) checked, 0 dead (2 unverifiable).

README (verbatim):
---
# Policy Testing with MDPFuzz (Replicability Study): Artifact

This repository is the artifact of the paper *Policy Testing with MDPFuzz (Replicability Study)*.
Its content consists of a <ins>reproduction</ins> study and a <ins>replication</ins> study of the paper [MDPFuzz: testing models solving Markov decision processes](https://dl.acm.org/doi/abs/10.1145/3533767.3534388).
<!-- To that regard, the submission was already supported by two distin
… README continues …
```

**Final answer**:

```json
{
  "tier": "Functional",
  "confidence": 0.8,
  "reasons": [
    "The artifact is placed in a public archival repository.",
    "The README is detailed and provides step-by-step instructions for reproducing the studies.",
    "All referenced paths in the README exist in the repository, indicating documentation consistency.",
    "Dependencies are mostly pinned, ensuring environment reproducibility.",
    "A Docker image is provided, though with one unpinned base image, which slightly reduces reproducibility confidence.",
    "A demonstration is provided, showing that the artifact can be exercised to some extent."
  ],
  "escalated_to_human": false
}
```

## Step 4 — Outcome

- **baseline**: predicted `Functional`, expert badge `Reusable`
- **solution**: predicted `Functional`, expert badge `Reusable`

See `results/falsified_run.json` for the same agents run against this artifact's falsified twin, which is the reported experiment.
