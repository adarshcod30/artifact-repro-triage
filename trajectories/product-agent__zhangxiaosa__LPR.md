# Trajectory — `zhangxiaosa/LPR`

- **Paper**: LPR: Large Language Models-Aided Program Reduction
- **Pinned commit**: `1cd376048ae5`
- **Files in repository**: 31,020
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

**Tool input**: 17 candidate paths extracted from the README.

**Tool response**:

```
VERIFIED REPOSITORY FACTS (checked against the actual file tree):
- files in repository: 31020
- README size: 12082 bytes
- dependency manifest present: False
- container definition present: False
- CI configuration present: False
- build/install script present: False
- test files present: False
- licence present: False

README PATH CLAIMS: 17 checked, 15 could NOT be found in the repository.
Paths the README references that do not exist:
  - perses_deploy.jar   (nothing similar in the repository)
  - script/summarize_perses_or_vulcan.py   (nothing similar in the repository)
  - scripts/analyze_and_draw.sh   (nothing similar in the repository)
  - scripts/keep_running.sh   (nothing similar in the repository)
  - scripts/run_creduce.py   (nothing similar in the repository)
  - scripts/run_lpr.py   (nothing similar in the repository)
  - scripts/run_perses.py   (nothing similar in the repository)
  - scripts/run_vulcan.py   (nothing similar in the repository)
  - scripts/summarize_lpr.py   (nothing similar in the repository)
  - summarize_creduce.py   (nothing similar in the repository)
  - summarize_perses_or_vulcan.py   (nothing similar in the repository)
  - summarize_xxx.py   (nothing similar in the repository)
  - tmp/LPR/tools/token_counter_deploy.jar   (nothing similar in the repository)
  - token_counter_deploy.jar   (nothing similar in the repository)
  - vulcan_deploy.jar   (nothing similar in the repository)
The README references no checkable file paths.
```

> This is the feedback that shapes the next step. 15 of 17 referenced paths do not exist, and each is citable by name — the model reasons over these facts instead of over the README's prose.

## Step 3 — BASELINE agent

**Prompt** (12,206 chars; README truncated here for readability):

```
Artifact repository: zhangxiaosa/LPR
Paper: LPR: Large Language Models-Aided Program Reduction

README (verbatim):
---
# Artifact for "LPR: Large Language Models-Aided Program Reduction"


Thank you for evaluating this artifact!

To evaluate this artifact, a Linux machine with [docker](https://docs.docker.com/get-docker/) installed is needed.

### List of Claims Supported by the Artifact

- LPR is more effective than Vulcan.

- LPR is on par with Vulcan in terms of efficiency. LPR is more efficient than Vulcan on complex programs.

- LPR generalizes well on C, Rust and JavaScript.

- To evaluate LPR, access to LLMs is required. You need either use gpt-3.5-turbo APIs or run CodeLlama on your server.

- The output of LLM is non-deterministic, so you may not exactly reproduce the previous results. 
To ease the artifact evaluation, we include the precomputed results.

### Notes

- All the experiments take long time to finish, so it is recommended to use tools like screen and tmux to 
manage sessions if the experiments are run on remote server. We also provide flags for multi-processing.

- The evaluation results of LPR may not exactly the same as shown in the paper, 
because LLMs have internal randomness. Replicating the experiments for multiple times will mitigate such impact. 
However, the deviation should be trivial, and the results should still support the original claims in th
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
    "The artifact includes scripts and tools necessary to reproduce the results.",
    "Precomputed results are provided to facilitate evaluation.",
    "The documentation explains the non-deterministic nature of LLM outputs and provides guidance on handling it.",
    "The artifact includes benchmark suites and detailed commands to run different reduction algorithms."
  ],
  "escalated_to_human": false
}
```

## Step 3 — SOLUTION agent

**Prompt** (13,856 chars; README truncated here for readability):

```
Artifact repository: zhangxiaosa/LPR
Paper: LPR: Large Language Models-Aided Program Reduction

VERIFIED FACTS. Each line was established by running code against the repository, not by reading its documentation. Where these contradict the README, they are what actually holds.

== Documentation consistency ==
Files in repository: 31020
README size: 12082 bytes
README references 17 file path(s); 15 do NOT exist in the repository.
  - MISSING: perses_deploy.jar   (nothing similar exists)
  - MISSING: script/summarize_perses_or_vulcan.py   (nothing similar exists)
  - MISSING: scripts/analyze_and_draw.sh   (nothing similar exists)
  - MISSING: scripts/keep_running.sh   (nothing similar exists)
  - MISSING: scripts/run_creduce.py   (nothing similar exists)
  - MISSING: scripts/run_lpr.py   (nothing similar exists)
  - MISSING: scripts/run_perses.py   (nothing similar exists)
  - MISSING: scripts/run_vulcan.py   (nothing similar exists)
  - MISSING: scripts/summarize_lpr.py   (nothing similar exists)
  - MISSING: summarize_creduce.py   (nothing similar exists)
  - MISSING: summarize_perses_or_vulcan.py   (nothing similar exists)
  - MISSING: summarize_xxx.py   (nothing similar exists)

== Environment reproducibility ==
Dependencies: no dependency manifest found
Container: no Dockerfile present.
CI configuration present: False
Tests present: False
Licence present: False

== Portabilit
… README continues …
```

**Final answer**:

```json
{
  "tier": "Available",
  "confidence": 0.85,
  "reasons": [
    "The artifact is placed in a public archival repository.",
    "However, the documentation is inconsistent with the actual files present in the repository.",
    "Missing scripts and tools as referenced in the README.",
    "No dependency manifest, Dockerfile, CI configuration, or tests are present.",
    "The environment setup and execution instructions are provided, but the actual files and scripts needed are missing.",
    "The artifact does not meet the criteria for 'Functional' or 'Reusable' tiers due to the significant documentation and file inconsistencies."
  ],
  "escalated_to_human": true
}
```

> **Human checkpoint.** Confidence fell below the escalation threshold, so this artifact is routed to a qualified reviewer rather than recorded as a guess.


## Step 4 — Outcome

- **baseline**: predicted `Functional`, expert badge `Reusable`
- **solution**: predicted `Available`, expert badge `Reusable`

See `results/falsified_run.json` for the same agents run against this artifact's falsified twin, which is the reported experiment.
