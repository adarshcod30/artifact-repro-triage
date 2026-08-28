.PHONY: help setup corpus baseline solution eval repro clean
help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:    ## Create venv and install pinned deps
	uv sync

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

clean:
	rm -rf data/clones results/*.json
