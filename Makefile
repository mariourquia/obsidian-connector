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

# ─── Release Build ───────────────────────────────────────────────────────
# Produces builds/<target>/ from sources. Run before cutting a release tag.
# Output directories are gitignored; CI uploads them as release artifacts.

BUILDS_DIR := builds
VERSION ?= $(shell python3 -c "import importlib.metadata; print(importlib.metadata.version('obsidian-connector'))" 2>/dev/null || echo "0.0.0-dev")

.PHONY: build-portable
build-portable: ## Assemble portable skills bundle -> builds/portable/
	bash scripts/build-portable.sh
	@mkdir -p $(BUILDS_DIR)/portable
	@cp -r portable/. $(BUILDS_DIR)/portable/

.PHONY: build-claude-code
build-claude-code: ## Assemble Claude Code plugin bundle -> builds/claude-code/
	@echo "Assembling Claude Code plugin bundle v$(VERSION)..."
	@rm -rf $(BUILDS_DIR)/claude-code && mkdir -p $(BUILDS_DIR)/claude-code
	@cp -r obsidian_connector bin hooks skills .claude-plugin .mcp.json pyproject.toml requirements-lock.txt $(BUILDS_DIR)/claude-code/ 2>/dev/null || true
	@echo "Done: $(BUILDS_DIR)/claude-code/"

.PHONY: build-claude-desktop
build-claude-desktop: ## Assemble Claude Desktop bundle -> builds/claude-desktop/
	@echo "Assembling Claude Desktop bundle v$(VERSION)..."
	@rm -rf $(BUILDS_DIR)/claude-desktop && mkdir -p $(BUILDS_DIR)/claude-desktop
	@cp -r obsidian_connector bin pyproject.toml requirements-lock.txt $(BUILDS_DIR)/claude-desktop/ 2>/dev/null || true
	@echo "Done: $(BUILDS_DIR)/claude-desktop/"

.PHONY: build-cowork
build-cowork: ## Assemble CoWork bundle -> builds/cowork/
	@echo "Assembling CoWork bundle v$(VERSION)..."
	@rm -rf $(BUILDS_DIR)/cowork && mkdir -p $(BUILDS_DIR)/cowork
	@cp -r hooks skills .claude-plugin $(BUILDS_DIR)/cowork/ 2>/dev/null || true
	@echo "Done: $(BUILDS_DIR)/cowork/"

.PHONY: release-build
release-build: build-portable build-claude-code build-claude-desktop build-cowork ## Build all distribution targets

.PHONY: clean-builds
clean-builds: ## Remove builds/ directory
	rm -rf $(BUILDS_DIR)

# ─── MCPB Packaging ──────────────────────────────────────────────────────

.PHONY: mcpb-build
mcpb-build: ## Build MCPB package (when mcpb CLI is available)
	@echo "MCPB packaging not yet available. See docs/distribution/MCPB_RESEARCH.md"

.PHONY: mcpb-validate
mcpb-validate: ## Validate mcpb.json manifest
	$(PYTHON) -c "import json; json.load(open('mcpb.json')); print('mcpb.json: valid JSON')"

# ─── Help ────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'
