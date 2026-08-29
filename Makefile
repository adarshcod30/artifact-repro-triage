# Every target below is verified to run. See `make verify-targets`.
#
# PYTHONPATH=src is used consistently rather than relying on an editable
# install, so the commands work in a fresh clone before `pip install -e .`
# has been run - which is exactly the situation a judge starts from.

PY := PYTHONPATH=src .venv/bin/python

.PHONY: help setup test preflight corpus baseline solution eval repro \
        discover prevalence pinning portability links report validate \
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

links:  ## Check README URLs for link rot
	$(PY) -m artifact_triage.solution.links

pinning:  ## Dependency and container base-image pinning
	$(PY) -m artifact_triage.solution.pinning

portability:  ## Hard-coded machine-specific paths and hosts
	$(PY) -m artifact_triage.solution.portability

discover:  ## Harvest research-artifact repositories from Zenodo
	$(PY) -m artifact_triage.corpus.discover

prevalence:  ## How widespread are broken README claims (376 artifacts)
	$(PY) -m artifact_triage.eval.prevalence

validate:  ## Do real users complain about what the verifier flags
	$(PY) -m artifact_triage.eval.issue_validation

report:  ## Reviewer report for one repo: make report REPO=owner/name
	@test -n "$(REPO)" || (echo "usage: make report REPO=owner/name" && exit 1)
	$(PY) -m artifact_triage.cli $(REPO)

selfcheck:  ## Run the tool on THIS repository (dogfooding)
	$(PY) -m artifact_triage.cli adarshcod30/artifact-repro-triage

dataset:  ## Export the 376-artifact measurements as CSV + JSONL + datasheet
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

falsified:  ## The primary experiment (set ARTIFACT_TRIAGE_TRIALS=3)
	$(PY) -m artifact_triage.eval.falsified_run

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
