.PHONY: help setup corpus baseline solution eval repro clean
help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:    ## Create venv and install pinned deps
	uv sync

spend:     ## Cumulative model spend against the $5 budget
	PYTHONPATH=src .venv/bin/python -m artifact_triage.eval.spend

test:      ## Regression tests pinning every bug the changelog claims to have fixed
	.venv/bin/python tests/test_regressions.py

preflight: ## Verify credentials and model access before spending tokens
	.venv/bin/python scripts/preflight.py

corpus:   ## Build the labeled artifact corpus (scrubbed) from cached fixtures
	uv run python -m artifact_triage.corpus.build

baseline: ## Run the single-prompt baseline over the corpus
	uv run python -m artifact_triage.baseline.run

solution: ## Run the claim-verification agent over the corpus
	uv run python -m artifact_triage.solution.run

eval:     ## Score baseline + solution against expert badge labels
	uv run python -m artifact_triage.eval.score

repro:    ## The one command judges run: corpus -> baseline -> solution -> eval
	$(MAKE) corpus && $(MAKE) baseline && $(MAKE) solution && $(MAKE) eval

discover:  ## Harvest research-artifact repos at scale from Zenodo
	PYTHONPATH=src .venv/bin/python -m artifact_triage.corpus.discover

prevalence: ## Measure how widespread broken README claims are (no model needed)
	PYTHONPATH=src .venv/bin/python -m artifact_triage.eval.prevalence

pinning:  ## Dependency pinning analysis
	PYTHONPATH=src .venv/bin/python -m artifact_triage.solution.pinning

portability:## Scan for hard-coded machine-specific values
	PYTHONPATH=src .venv/bin/python -m artifact_triage.solution.portability

links:     ## Check README URLs for link rot
	PYTHONPATH=src .venv/bin/python -m artifact_triage.solution.links

report:    ## Reviewer report for one repo: make report REPO=owner/name
	PYTHONPATH=src .venv/bin/python -m artifact_triage.cli $(REPO)

validate:  ## Do real users complain about what the verifier detects?
	PYTHONPATH=src .venv/bin/python -m artifact_triage.eval.issue_validation

trajectories: ## Export agent trajectories (product agents + build agent)
	PYTHONPATH=src .venv/bin/python -m artifact_triage.eval.export_trajectories
	.venv/bin/python scripts/export_build_trajectory.py

clean:
	rm -rf data/clones results/*.json
