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

**Tool input**: 2 candidate paths extracted from the README.

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

README PATH CLAIMS: 2 checked, 0 could NOT be found in the repository.
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
    "There is a demonstration provided that shows how to run a small-scale experiment.",
    "The artifact includes documentation for each case study and use case.",
    "The artifact is designed to be exercisable, with provided Docker images and virtual environments.",
    "The README mentions the inclusion of step-by-step instructions and a demonstration, indicating efforts towards verification and validation."
  ],
  "escalated_to_human": false
}
```

## Step 3 — SOLUTION agent

**Prompt** (9,488 chars; README truncated here for readability):

```
Artifact repository: QuentinMaz/MDPFuzz_Replicability_Study_Artifact
Paper: Policy Testing with MDPFuzz (Replicability Study)

VERIFIED REPOSITORY FACTS (checked against the actual file tree):
- files in repository: 1129
- README size: 8638 bytes
- dependency manifest present: True
- container definition present: True
- CI configuration present: False
- build/install script present: False
- test files present: False
- licence present: True

README PATH CLAIMS: 2 checked, 0 could NOT be found in the repository.
Every path the README references was found.
The README references no checkable file paths.

README (verbatim):
---
# Policy Testing with MDPFuzz (Replicability Study): Artifact

This repository is the artifact of the paper *Policy Testing with MDPFuzz (Replicability Study)*.
Its content consists of a <ins>reproduction</ins> study and a <ins>replication</ins> study of the paper [MDPFuzz: testing models solving Markov decision processes](https://dl.acm.org/doi/abs/10.1145/3533767.3534388).
<!-- To that regard, the submission was already supported by two distinct code basis of the studies. -->
This present artifact's structure reflects this, as it is composed of two main folders, namely: `reproduction/` and `replication/`.
The very own nature of the work makes that it involves a tremendous amount of computations; yet we design the code such that the results should be similar
… README continues …
```

**Final answer**:

```json
{
  "tier": "Functional",
  "confidence": 0.8,
  "reasons": [
    "The artifact is placed in a public repository and includes a detailed README with step-by-step instructions.",
    "A Docker image is provided, simplifying the setup process and ensuring consistency across different environments.",
    "The README provides clear instructions on how to run the experiments, both inside and outside the Docker container.",
    "A demonstration is included to show the functionality of the artifact, though it is small-scale due to the computational requirements.",
    "The artifact includes a dependency manifest and a license, contributing to its usability and legal clarity.",
    "The absence of CI configuration, build/install scripts, and test files slightly reduces confidence in the tier, but the provided Docker image and detailed instructions mitigate this."
  ],
  "escalated_to_human": false
}
```

## Step 4 — Outcome

- **baseline**: predicted `Functional`, expert badge `Reusable`
- **solution**: predicted `Functional`, expert badge `Reusable`

See `results/falsified_run.json` for the same agents run against this artifact's falsified twin, which is the reported experiment.
