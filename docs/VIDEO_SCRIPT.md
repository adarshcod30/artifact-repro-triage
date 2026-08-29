# Solution Video — Script (target 4:30, hard cap 5:00)

The brief requires, in order: the problem and the simple baseline → one realistic
execution start to finish → the final comparison → the changelog briefly → the
change that contributed most → one experiment you removed.

This script covers all six. Timings are cumulative.

---

## 0:00 – 0:40 — The problem, and how big it is

> "A research paper's README is a set of promises. Install with
> `requirements.txt`. Run `scripts/run_experiments.sh`. See
> `configs/default.yaml`. Nothing checks whether those files exist.
>
> I checked. Across seven hundred and thirty-two research artifacts harvested
> from Zenodo — six thousand six hundred documented file references — **almost
> twenty-two percent point at nothing at all**. Sixty-four percent of artifacts
> have at least one.
>
> And here is the part I didn't expect. The literature says artifacts *decay* —
> dependencies drift, environments rot. So older artifacts should be worse. They
> aren't. The rate is flat across four years: point two-six under three months,
> point two-five for artifacts last touched almost four years ago.
>
> **These artifacts shipped broken.** A reviewer could have caught every one of
> them on day one, in about five seconds, for free. Nobody did, because nobody
> had a tool that looks."

**On screen:** the prevalence table, then the age-bucket table showing the flat
line. Then the LPR verifier output: *15 of 17 referenced paths do not exist* — in
an artifact badged **Reusable**.

---

## 0:40 – 1:10 — The baseline

> "The baseline is what a reviewer does today: one prompt, the README, the ACM
> rubric, asked for a tier.
>
> It's deliberately a fair baseline — same model, same rubric, same output
> schema, same scrubbed README the solution sees. The only difference is that
> none of the claims have been checked."

**On screen:** `make baseline` running. Point out that it answers `Functional`
for 13 of 15 artifacts.

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
> I started by scoring both systems against real ACM badges. Baseline MAE 0.733.
> Solution 0.800 — and those numbers move between runs, because the model isn't
> deterministic. That's the point: neither is anywhere near good.
>
> Before touching anything I added a control: a constant predictor that always
> answers 'Functional', with no model and no input. It scored 0.667. **It beat
> both systems.** It wins by collapsing onto the middle class, which MAE rewards
> — and the baseline does nearly the same thing, answering 'Functional' 13 times
> out of 15.
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
detection (mean)             0%        100%
range over 3 trials       0%-0%   100%-100%
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
> took detection from zero to a hundred percent — and it's why the verifier's
> own result is byte-identical on every run.
>
> The second-biggest change was realising the model was only being shown *one*
> of the five checks I'd built. Feeding it all five took detection from
> ninety-seven percent with variance to a flat hundred."

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

## 4:20 – 4:50 — Hot take

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

## If there is time (cut first if over 5:00)

> "Two other checks fell out of the same idea. Fifty-three percent of these
> artifacts have no dependency manifest at all. Twenty-seven percent hard-code a
> path into the author's own machine — one artifact that **passed Functional
> review** has twelve paths pointing into `/root/upbeat/`, and another reads a
> CSV off the author's Desktop."

**On screen:** `artifact-triage NWU-NISL-Fuzzing/upbeat` running live — it takes
about five seconds and needs no API key.

## Recording notes

- **Cut the setup.** Don't film `uv venv`. Start on the problem.
- **Show real terminal output**, not slides of numbers. The deterministic parts
  run in seconds with no credentials — safest thing to film live.
- **Do not film `.env`, `aws configure`, or any credential screen.**
- Pre-run the model steps and film the saved output; live model calls are slow
  and non-deterministic on camera.
- The single most persuasive shot is the LPR verifier output: *15 of 17
  referenced paths do not exist*, in a repository badged `Reusable`.
- Second most persuasive: the flat age-bucket table. It is the finding that
  turns "a tool I built" into "a thing nobody knew about this ecosystem".
- `results/dashboard.html` opens offline and shows every number on one page —
  useful for the comparison beat if screen space is tight.
