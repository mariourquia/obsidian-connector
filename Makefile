# obsidian-connector — Local Runner
# Every CI check has an equivalent make target.

SHELL := /bin/bash
.DEFAULT_GOAL := help
PYTHON := python3
DOCS_LINT := $(PYTHON) tools/docs_lint.py

# ─── Knowledge Architecture ──────────────────────────────────────────────

.PHONY: docs-lint
docs-lint: ## Run docs linter (warnings + errors)
	$(DOCS_LINT)

.PHONY: docs-lint-strict
docs-lint-strict: ## Run docs linter (errors only, CI-equivalent)
	$(DOCS_LINT) --severity error

.PHONY: docs-lint-json
docs-lint-json: ## Run docs linter with JSON output
	$(DOCS_LINT) --json

.PHONY: docs-staleness
docs-staleness: ## Check git-based staleness
	$(DOCS_LINT) --check-git-staleness

.PHONY: docs-changed
docs-changed: ## Lint only changed docs (pre-commit use)
	$(DOCS_LINT) --changed-only --severity error

# ─── Tests ────────────────────────────────────────────────────────────────

.PHONY: test-smoke
test-smoke: ## Run core function smoke tests (requires Obsidian running)
	$(PYTHON) scripts/smoke_test.py

.PHONY: test-cache
test-cache: ## Run cache module tests
	$(PYTHON) scripts/cache_test.py

.PHONY: test-mcp
test-mcp: ## Run MCP server launch smoke test
	bash scripts/mcp_launch_smoke.sh

.PHONY: test-all
test-all: test-smoke test-cache test-mcp ## Run all tests

.PHONY: doctor
doctor: ## Health check (Obsidian CLI connectivity)
	./bin/obsx doctor

# ─── Combined ────────────────────────────────────────────────────────────

.PHONY: ci-local
ci-local: docs-lint-strict test-cache test-mcp ## Run everything CI would run, locally

.PHONY: check
check: docs-lint test-all doctor ## Full check: docs + tests + health

# ─── Help ────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
