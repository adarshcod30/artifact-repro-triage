# Every target below is verified to run. See `make verify-targets`.
#
# PYTHONPATH=src is used consistently rather than relying on an editable
# install, so the commands work in a fresh clone before `pip install -e .`
# has been run - which is exactly the situation a judge starts from.

PY := PYTHONPATH=src .venv/bin/python

.PHONY: help setup test preflight corpus baseline solution eval repro \
        discover prevalence linkgap resolution pinning portability links report validate falsified-llama \
        falsified-model falsified-cheap \
        trajectories dashboard spend verify-targets selfcheck clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup ----
setup:  ## Create the venv and install dependencies
	uv venv
	uv pip install -e .

# ------------------------------------------------- free: no credentials ----
test:  ## Regression tests pinning every bug the changelog claims to have fixed
	.venv/bin/python tests/test_regressions.py

corpus:  ## Rebuild artifact fact sheets from cached API responses
	$(PY) -m artifact_triage.corpus.fetch

verify:  ## Deterministic claim verification over the labelled corpus
	$(PY) -m artifact_triage.solution.verify

control:  ## Negative control - 75 injected false claims
	$(PY) -m artifact_triage.eval.negative_control

ablation:  ## Does the strict path extractor earn its complexity?
	$(PY) -m artifact_triage.eval.ablation

subtle:  ## Harder control: mutate real paths into near-misses
	$(PY) -m artifact_triage.eval.subtle_control

links:  ## Check README URLs for link rot
	$(PY) -m artifact_triage.solution.links

pinning:  ## Dependency and container base-image pinning
	$(PY) -m artifact_triage.solution.pinning

portability:  ## Hard-coded machine-specific paths and hosts
	$(PY) -m artifact_triage.solution.portability

discover:  ## Harvest research-artifact repositories from Zenodo (ARGS=--stratified to extend)
	$(PY) -m artifact_triage.corpus.discover $(ARGS)

resolution:  ## Audit HOW claims resolve - this project's own leniency
	$(PY) -m artifact_triage.eval.resolution_audit

linkgap:  ## What an existing Markdown link checker would already catch
	$(PY) -m artifact_triage.eval.linkchecker_gap

prevalence:  ## How widespread are broken README claims (742 artifacts)
	$(PY) -m artifact_triage.eval.prevalence

validate:  ## Do real users complain about what the verifier flags
	$(PY) -m artifact_triage.eval.issue_validation

report:  ## Reviewer report for one repo: make report REPO=owner/name
	@test -n "$(REPO)" || (echo "usage: make report REPO=owner/name" && exit 1)
	$(PY) -m artifact_triage.cli $(REPO)

selfcheck:  ## Run the tool on THIS repository (dogfooding)
	$(PY) -m artifact_triage.cli adarshcod30/artifact-repro-triage

dataset:  ## Export the 742-artifact measurements as CSV + JSONL + datasheet
	$(PY) -m artifact_triage.eval.export_dataset

dashboard:  ## Render every result into one self-contained HTML page
	$(PY) -m artifact_triage.eval.dashboard

spend:  ## Cumulative model spend against the $5 budget
	$(PY) -m artifact_triage.eval.spend

trajectories:  ## Export agent trajectories (product agents + build agent)
	$(PY) -m artifact_triage.eval.export_trajectories
	.venv/bin/python scripts/export_build_trajectory.py

# ------------------------------------------- needs a model provider --------
preflight:  ## Verify credentials and model access before spending tokens
	.venv/bin/python scripts/preflight.py

baseline:  ## One direct prompt over the README
	$(PY) -m artifact_triage.baseline.run

solution:  ## Verified facts plus the README
	$(PY) -m artifact_triage.solution.run

eval:  ## Score baseline and solution with the shared scorer
	$(PY) -m artifact_triage.eval.compare

adversarial:  ## Two tests designed to break the central claim
	$(PY) -m artifact_triage.eval.adversarial

falsified:  ## The primary experiment (set ARTIFACT_TRIAGE_TRIALS=3)
	$(PY) -m artifact_triage.eval.falsified_run

falsified-model:  ## Cross-model run: make falsified-model MODEL=<id> OUT=<file>
	@# falsified_run.py writes one fixed path, so the primary result is saved and
	@# restored around this run. Without that, a cross-model check silently
	@# destroys the primary result and restoring it costs another paid run.
	@test -n "$(MODEL)" -a -n "$(OUT)" || \
		(echo "usage: make falsified-model MODEL=<bedrock-id> OUT=results/x.json" && exit 1)
	@cp results/falsified_run.json results/.falsified_primary.bak 2>/dev/null || true
	ARTIFACT_TRIAGE_PROVIDER=bedrock ARTIFACT_TRIAGE_MODEL=$(MODEL) \
	$(PY) -m artifact_triage.eval.falsified_run
	cp results/falsified_run.json $(OUT)
	@cp results/.falsified_primary.bak results/falsified_run.json 2>/dev/null || true
	@rm -f results/.falsified_primary.bak
	@echo "-> $(OUT) (primary result restored)"

falsified-llama:  ## Cross-model check on Llama 3.3 70B
	$(MAKE) falsified-model MODEL=us.meta.llama3-3-70b-instruct-v1:0 \
		OUT=results/falsified_llama.json

falsified-cheap:  ## Cross-TIER check: a 13x cheaper model, same experiment
	$(MAKE) falsified-model MODEL=us.amazon.nova-2-lite-v1:0 \
		OUT=results/falsified_nova2lite.json

repro:  ## The one command judges run
	$(MAKE) test
	$(MAKE) corpus
	$(MAKE) control
	$(MAKE) baseline
	$(MAKE) solution
	$(MAKE) eval
	$(MAKE) dashboard

# --------------------------------------------------------------- checks ----
check-claims:  ## Verify every number in the docs matches results/*.json
	.venv/bin/python scripts/check_claims.py

verify-targets:  ## Prove every credential-free target actually runs
	.venv/bin/python scripts/verify_targets.py

clean:
	rm -rf data/clones results/*.local.*
