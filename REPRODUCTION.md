# Reproduction Guide

Written for someone starting from a clean machine with nothing installed.

---

## 1. What you need

| | |
|---|---|
| OS | macOS or Linux (developed on macOS 15, Apple Silicon) |
| Python | 3.11 or newer |
| Disk | ~120 MB (37 MB clone + venv; no repositories are cloned) |
| Network | Only for the model calls. Corpus rebuild is optional and cached. |
| Credentials | One model provider (see step 3) |

**No Docker. No GPU. No repository clones.** Artifact fact sheets are committed as
JSON fixtures, so the corpus does not need rebuilding and no rate limit applies.

## 2. Setup

```bash
git clone --depth 1 https://github.com/adarshcod30/artifact-repro-triage.git
cd artifact-repro-triage
pip install uv          # if you don't have it
uv venv
uv pip install -e .
```

**Use `--depth 1`.** Measured on a clean machine: shallow clone **37 MB in 3
seconds**; full clone 91 MB in 32 seconds. The history carries API-cache files
that were later removed, and nothing needs them.

Install takes roughly 30 seconds (`boto3`, `botocore[crt]`, `certifi`).

### Verified from a clean clone

This was run end to end on a fresh shallow clone. All ten credential-free
targets pass with no API key, no AWS account and no configuration:

```
test  verify  control  subtle  ablation  pinning  portability
dataset  dashboard  check-claims
```

`make verify-targets` re-runs that check and fails loudly if any documented
command does not work.

> `certifi` is not optional on macOS: python.org builds ship without a CA bundle,
> and every HTTPS call fails with `CERTIFICATE_VERIFY_FAILED` without it.

## 3. Credentials

Copy the template and fill in **one** provider:

```bash
cp .env.example .env    # then edit .env
```

**AWS Bedrock (what the reported results used):**

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
ARTIFACT_TRIAGE_PROVIDER=bedrock
ARTIFACT_TRIAGE_MODEL=us.amazon.nova-pro-v1:0
```

The IAM principal needs `bedrock:InvokeModel` on the model, and the model must be
enabled under Bedrock → Model access. `aws bedrock list-foundation-models` shows
the *catalogue*, not what your account has enabled — verify with step 4.

**Any other provider** — `anthropic`, `gemini`, or `grok` — set the matching key
and `ARTIFACT_TRIAGE_PROVIDER`. Both systems always read the same value, so they
can never be run against different models.

## 4. Verify before spending anything

```bash
make preflight
```

Confirms the credential is present, makes one live round trip, and prints the
estimated cost of a full comparison. It never prints a secret — only whether one
is set and how long it is.

## 5. Run

```bash
make repro
```

Runs, in order: corpus → baseline → solution → evaluation.

Individually:

```bash
make corpus      # rebuild fact sheets from cached API responses (offline)
make baseline    # one direct prompt over the README
make solution    # verified facts + README
make eval        # score both with the shared scorer
```

Everything that needs **no credentials and costs nothing**:

```bash
make test          # 82 regression tests, ~2s
make report REPO=owner/name   # reviewer report for any repository
make prevalence    # broken-claim prevalence across the harvested corpus
make links         # link-rot scan
make pinning       # dependency + container pinning
make portability   # hard-coded machine-specific values
make dashboard     # render all results to one self-contained HTML page
make spend         # model spend against the $5 budget
```

The two headline experiments:

```bash
# Deterministic. No model, no credentials, no network. Runs in ~2 seconds.
PYTHONPATH=src python -m artifact_triage.solution.verify
PYTHONPATH=src python -m artifact_triage.eval.negative_control

# The primary experiment. Needs a provider.
ARTIFACT_TRIAGE_TRIALS=3 PYTHONPATH=src python -m artifact_triage.eval.falsified_run
```

## 6. What you should see

**`negative_control`** — fully deterministic, identical on every machine:

```
injected false claims  : 75
detected by verifier   : 75   (100.0%)
false positives        : 0
```

If this differs, something is wrong with the install, not with the model.

**`falsified_run`** — the measured comparison. The baseline detection rate is
stable at 0%. The solution's rate varies between trials (see step 7).

**`verify`** — a table of every artifact, its badge, and its broken README path
claims.

## 7. On determinism — read this before comparing numbers

| Component | Deterministic? |
|---|---|
| Corpus build, scrubber, verifier, negative control | **Yes** — byte-identical every run |
| Anything involving a model | **No** |

The models are not deterministic even at `temperature: 0`. Observed across
repeated identical runs: solution detection moved between 90% and 100%. The
baseline was 0% on every run.

**This is why the reported figure is a mean over 3 trials with its range, not a
single number.** A single run of this experiment is not a reportable result, and
your numbers will differ slightly from ours. Re-run with
`ARTIFACT_TRIAGE_TRIALS=3` and compare the *interval*.

## 8. Runtime and cost

Measured on the reported configuration (`us.amazon.nova-pro-v1:0`):

| Step | Calls | Time | Cost |
|---|---|---|---|
| `corpus` | 0 | ~5 s | $0 |
| `verify` + `negative_control` | 0 | ~3 s | $0 |
| `baseline` | 15 | ~40 s | $0.033 |
| `solution` | 15 | ~45 s | $0.036 |
| `falsified_run`, 1 trial | 60 | ~2 min | $0.14 |
| `falsified_run`, 3 trials | 180 | ~6 min | $0.42 |

Full reproduction of every reported number: **under 10 minutes and under $0.50.**

Other providers scale from this. Claude Opus 5 is roughly 6× the cost;
Amazon Nova Lite roughly 1/13th.

## 9. Rebuilding the corpus from scratch (optional)

Not needed to reproduce any result — the fixtures are committed. To rebuild:

```bash
PYTHONPATH=src python -m artifact_triage.corpus.sources   # scrape badge labels
PYTHONPATH=src python -m artifact_triage.corpus.zenodo    # resolve to deposits
PYTHONPATH=src python -m artifact_triage.corpus.fetch     # build fact sheets
```

This hits the ISSTA 2024 site, the Zenodo API and the GitHub API. Zenodo
rate-limits aggressively (429s); the resolver backs off exponentially, so allow
several minutes. Cached responses under `data/cache/` make re-runs instant.

Two caveats if you rebuild:

- Repositories move. Artifacts are pinned to commit SHAs recorded in each
  fixture, but a deleted or renamed repository will drop out of the corpus.
- GitHub anonymous access allows 60 requests/hour. Set `GITHUB_TOKEN`, or let
  the tool reuse `gh auth token`, for 5000/hour.

## 10. Data provenance

| Data | Source | Licence / terms |
|---|---|---|
| Badge labels | ISSTA 2024 Artifact Evaluation results page | Public conference programme |
| Artifact metadata | Zenodo public API | Open access |
| Repository file trees | GitHub public API | Public repositories only |
| Falsified twins | Generated by this project, seeded | — |

No private data, no credentials, and no personal information are used or stored.
Every artifact analysed is public and was published by its authors for exactly
this kind of inspection.
