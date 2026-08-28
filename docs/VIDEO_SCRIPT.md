# Solution Video — Script (target 4:30, hard cap 5:00)

The brief requires, in order: the problem and the simple baseline → one realistic
execution start to finish → the final comparison → the changelog briefly → the
change that contributed most → one experiment you removed.

This script covers all six. Timings are cumulative.

---

## 0:00 – 0:35 — The problem

> "Every major software-engineering conference runs an artifact evaluation
> track. Volunteer reviewers — usually PhD students — decide whether a paper's
> released code is *Functional* or *Reusable*.
>
> A README is a set of promises. It says install with `requirements.txt`, run
> `scripts/run_experiments.sh`, see `configs/default.yaml`. Nothing checks them.
> A reviewer reads fluent, confident prose and forms an impression, because
> reading prose is what a human can cheaply do.
>
> So the expensive failure is specific: a convincing README that isn't consistent
> with its own repository."

**On screen:** the LPR artifact's README, scrolling. Then the verifier output
showing *15 of 17 referenced paths do not exist.*

---

## 0:35 – 1:10 — The baseline

> "The baseline is what a reviewer does today: one prompt, the README, the ACM
> rubric, asked for a tier.
>
> It's deliberately a fair baseline — same model, same rubric, same output
> schema, same scrubbed README the solution sees. The only difference is that
> none of the claims have been checked."

**On screen:** `make baseline` running. Point out that it answers `Functional`
for 14 of 15 artifacts.

---

## 1:10 – 2:15 — One realistic execution

Run the solution on a single artifact and narrate the pipeline.

> "Step one, scrub. Four of the fifteen READMEs in this corpus announce their own
> badge. If I don't redact that, I'm not measuring judgement, I'm measuring
> reading comprehension.
>
> Step two, verify. Every path the README references is checked against the
> repository's real file tree — thirty-one thousand files here. That's ordinary
> Python, no model. It can't hallucinate, it costs nothing, and every finding is
> citable by path.
>
> Step three, judge. The model now reasons over verified facts instead of over
> prose. And when confidence is low, the artifact goes to a human reviewer
> instead of being guessed at."

**On screen:** `trajectories/product-agent__zhangxiaosa__LPR.md`, scrolling
through Steps 0 → 4.

---

## 2:15 – 3:10 — The comparison, and the honest part

> "Here's where the project changed shape.
>
> I started by scoring both systems against real ACM badges. The baseline got MAE
> 0.733. The solution got 1.000 — *worse*.
>
> Before touching anything I added a control: a constant predictor that always
> answers 'Functional', with no model and no input. It scored 0.667. **It beat
> both systems.** The baseline only looked good because it collapsed onto the
> middle class, which MAE rewards.
>
> The cause is a ground-truth mismatch. The committee badged the curated Zenodo
> deposit; I'm analysing the living GitHub mirror, where README drift is normal.
> The verifier was correct and being punished for it.
>
> So I replaced the experiment with one where I author the ground truth: falsify
> each README to reference five files that provably don't exist."

**On screen:** the constant-predictor table, then the final result:

```
                        baseline    solution
detection (mean)             0%         97%
range over 3 trials       0%-0%    90%-100%
verifier              75/75 claims, 0 false positives
```

> "The baseline is perfectly stable at zero. Across forty-five opportunities it
> never once noticed a corrupted README. That's not a tuning gap — reading only
> prose, it has no mechanism that *could* detect a fabricated path."

---

## 3:10 – 3:50 — Changelog and the biggest contributor

> "Twenty-six iterations, each tied to the evidence that prompted it.
>
> The change that contributed most wasn't a prompt or a model. It was moving
> verification *out* of the model and into deterministic code. That single move
> took detection from zero to ninety-seven percent, and it's the reason the
> verifier's own result is identical on every run while the model's varies
> between ninety and one hundred."

**On screen:** `CHANGELOG.md`, scrolling.

---

## 3:50 – 4:20 — One experiment removed

> "I removed GitHub search. Only half the artifacts had a repo link in their
> Zenodo record, so I searched GitHub by paper title to recover the rest. It
> found twenty — including a Jekyll theme matched to a patch-generation paper,
> and a LodeRunner game clone matched to 'Total Recall? How Good are Static Call
> Graphs Really?'.
>
> I hardened the matcher twice. The game still passed — its README genuinely
> contains 'total recall'. So I cut the whole thing and kept only the fifteen
> repos the authors published themselves.
>
> Smaller corpus, zero false labels. And the lesson is the project's own thesis:
> fuzzy matching produced confident, plausible, wrong answers."

---

## 4:20 – 4:45 — Hot take

> "Give an agent a control group before you give it a metric.
>
> Every real defect here was found by a control, and every one was invisible to
> the headline number. The negative control found two bugs in my verifier. The
> constant predictor invalidated my entire primary metric. A surprising
> measurement turned out to be my own truncation bug.
>
> Without those, this ships a confident, plausible, well-formatted number that
> means nothing — which is exactly the failure it was built to detect, one level
> up."

---

## Recording notes

- **Cut the setup.** Don't film `uv venv`. Start on the problem.
- **Show real terminal output**, not slides of numbers. The deterministic parts
  run in seconds with no credentials — safest thing to film live.
- **Do not film `.env`, `aws configure`, or any credential screen.**
- Pre-run the model steps and film the saved output; live model calls are slow
  and non-deterministic on camera.
- The single most persuasive shot is the LPR verifier output: *15 of 17
  referenced paths do not exist*, in a repository badged `Reusable`.
