# Trajectory — `THU-WingTecher/DeepConstr`

- **Paper**: Towards More Complete Constraints for Deep Learning Library Testing via Complementary Set Guided Refinement
- **Pinned commit**: `fdb1e5d809ca`
- **Files in repository**: 41,822
- **Expert badge (held out from both agents)**: `Available`

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

The README **disclosed its own badge tier**. Redacted before either agent saw it: `{'badge_image': 4}`

## Step 2 — Tool call: deterministic claim verification

*Solution only. No model involved — ordinary Python over the repository's real file tree.*

**Tool input**: 27 candidate paths extracted from the README.

**Tool response**:

```
VERIFIED REPOSITORY FACTS (checked against the actual file tree):
- files in repository: 41822
- README size: 16631 bytes
- dependency manifest present: True
- container definition present: False
- CI configuration present: False
- build/install script present: False
- test files present: True
- licence present: True

README PATH CLAIMS: 27 checked, 5 could NOT be found in the repository.
Paths the README references that do not exist:
  - DeepConstr/data/records   (closest real file: deepconstr/gen/record.py)
  - DeepConstr/results/tf_exp.csv   (nothing similar in the repository)
  - DeepConstr/results/torch_exp.csv   (nothing similar in the repository)
  - DeepConstr/results/unnormal_val_deepconstr_torch.json   (nothing similar in the repository)
  - pt_gen.csv   (nothing similar in the repository)
The README references no checkable file paths.
```

> This is the feedback that shapes the next step. 5 of 27 referenced paths do not exist, and each is citable by name — the model reasons over these facts instead of over the README's prose.

## Step 3 — BASELINE agent

**Prompt** (16,191 chars; README truncated here for readability):

```
Artifact repository: THU-WingTecher/DeepConstr
Paper: Towards More Complete Constraints for Deep Learning Library Testing via Complementary Set Guided Refinement

README (verbatim):
---
# Towards More Complete Constraints for Deep Learning Library Testing via Complementary Set Guided Refinement

<p align="center">
    <!-- <a href="https://arxiv.org/abs/2302.02261">[REDACTED] -->
    <a href="https://doi.org/10.5281/zenodo.12669927">[REDACTED]
    <a href="https://github.com/THU-WingTecher/DeepConstr/blob/main/LICENSE">[REDACTED]</a>
    <a href="https://hub.docker.com/repository/docker/gwihwan/artifact-issta24/tags">[REDACTED]</a>
</p>

Welcome to the artifact repository of the DeepConstr paper which is accepted by ISSTA 2024.

### Source Code Structure 
```
|-- build        # Directory for compiling PyTorch and TensorFlow
|-- data         # Data directory, contains records of constraints and intersected operator names
|-- deepconstr   # Main implementation of DeepConstr
|   |-- error.py     # Error handling module for DeepConstr
|   |-- gen          # Implementation for test case generation from SMT-expression
|   |-- grammar      # Implementation for SMT-expression grammar to convert natural language into SMT-expression
|   |-- train        # Implementation for constraint extraction and refinement
|   |-- logger.py    # Logging module for DeepConstr
|   `-- utils.py     # Ut
… README continues …
```

**Final answer**:

```json
{
  "tier": "Functional",
  "confidence": 0.8,
  "reasons": [
    "The artifact is placed in a public archival repository.",
    "The README provides detailed documentation on how to set up, run, and use the artifact.",
    "The artifact includes scripts for conducting experiments and generating test cases.",
    "The documentation explains how to extract constraints and reproduce experiments.",
    "The artifact appears to be exercisable based on the provided commands and setup instructions.",
    "The README mentions evidence of verification and validation through bug finding and experiment reproduction."
  ],
  "escalated_to_human": false
}
```

## Step 3 — SOLUTION agent

**Prompt** (17,722 chars; README truncated here for readability):

```
Artifact repository: THU-WingTecher/DeepConstr
Paper: Towards More Complete Constraints for Deep Learning Library Testing via Complementary Set Guided Refinement

VERIFIED FACTS. Each line was established by running code against the repository, not by reading its documentation. Where these contradict the README, they are what actually holds.

== Documentation consistency ==
Files in repository: 41822
README size: 16631 bytes
README references 27 file path(s); 5 do NOT exist in the repository.
  - MISSING: DeepConstr/data/records   (closest real file: deepconstr/gen/record.py)
  - MISSING: DeepConstr/results/tf_exp.csv   (nothing similar exists)
  - MISSING: DeepConstr/results/torch_exp.csv   (nothing similar exists)
  - MISSING: DeepConstr/results/unnormal_val_deepconstr_torch.json   (nothing similar exists)
  - MISSING: pt_gen.csv   (nothing similar exists)

== Environment reproducibility ==
Dependencies: requirements.txt: 0/15 pinned, 0 bounded, 15 floating (0% pinned)
  - unpinned: z3-solver
  - unpinned: hydra-core>=1.1.0
  - unpinned: hydra_colorlog
  - unpinned: multipledispatch
  - unpinned: appdirs
  - unpinned: numpy
Container: no Dockerfile present.
CI configuration present: False
Tests present: True
Licence present: True

== Portability ==
No machine-specific values found across 12 inspected file(s).

== External links ==
5 URL(s) checked, 1 dead (0 unverifiable).
  
… README continues …
```

**Final answer**:

```json
{
  "tier": "Functional",
  "confidence": 0.7,
  "reasons": [
    "The artifact is placed in a public archival repository, satisfying the 'Available' tier.",
    "The README provides detailed setup and usage instructions, suggesting the artifact is documented.",
    "The presence of tests indicates some level of verification and validation.",
    "Several file paths referenced in the README do not exist, indicating documentation inconsistency.",
    "All dependencies are floating, which may affect reproducibility and stability.",
    "No Dockerfile is present, which could hinder environment reproducibility."
  ],
  "escalated_to_human": false
}
```

## Step 4 — Outcome

- **baseline**: predicted `Functional`, expert badge `Available`
- **solution**: predicted `Functional`, expert badge `Available`

See `results/falsified_run.json` for the same agents run against this artifact's falsified twin, which is the reported experiment.
