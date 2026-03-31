# AGENTS.md (Repository Map)

> This file is your entry point. Read it first, follow links for detail.
> **Hard limit: ≤120 lines.** Do not add implementation details here.

## Start here (routing)

- Architecture map: [./ARCHITECTURE.md](./ARCHITECTURE.md)
- Docs catalog: [./docs/index.md](./docs/index.md)
- Security & reliability: [./docs/security/SECURITY.md](./docs/security/SECURITY.md), [./docs/reliability/RELIABILITY.md](./docs/reliability/RELIABILITY.md)
- Product specs: [./docs/product-specs/index.md](./docs/product-specs/index.md)
- Design docs: [./docs/design-docs/index.md](./docs/design-docs/index.md)
- Active execution plans: [./docs/exec-plans/active/](./docs/exec-plans/active/)
- Quality scores: [./docs/quality/QUALITY_SCORE.md](./docs/quality/QUALITY_SCORE.md)
- Tech debt tracker: [./docs/tech-debt-tracker.md](./docs/tech-debt-tracker.md)

## Operating rules

- Treat `docs/` as source-of-truth; do not invent behavior not backed by code or docs.
- For complex changes: create/extend an execution plan under `docs/exec-plans/active/`.
- When code behavior changes, update the relevant docs and bump `last_reviewed`.
- Prefer updating docs closest to ownership (domain folder) over general docs.
- If docs conflict with code, **code wins**; open a doc-fix PR immediately.

## How to navigate fast

- Use ripgrep: `rg "keyword" docs/ src/`
- Start with indexes; do not read long docs unless routed by an index.
- Prefer docs with `status: verified`. Treat `draft` as partial; treat `deprecated` as historical.

## Required artifacts by change type

- **Behavior change:** update doc(s) + add/adjust tests
- **New module/domain:** add `docs/<area>/index.md` entry + ownership metadata
- **Cross-cutting change:** update ARCHITECTURE.md and relevant QUALITY_SCORE.md

## Escalation

- If docs conflict with code, code wins; open a doc-fix PR immediately.
- Mechanical lint: enforce AGENTS.md max lines + required links exist.

## Available local commands

```
make docs-lint            # Validate docs structure (warnings + errors)
make docs-lint-strict     # Errors only (CI equivalent)
make docs-staleness       # Check git-based staleness
make docs-changed         # Lint only changed docs (fast pre-commit)
make harness-validate     # Full sandbox → journey → assertions pipeline
make ci-local             # Run everything CI runs, locally
make ci-full              # Docs lint + full harness validation
make install-deps         # Install Python dependencies for harness tools
make help                 # Show all available targets
```

## Tools & skills reference

- Docs linter: `tools/docs_lint.py`
- Sandbox lifecycle: `dev/sandbox_up.sh`, `dev/sandbox_down.sh`
- UI journeys: `skills/ui_playwright.py` + `dev/journeys/*.yaml`
- Observability queries: `skills/obs_prom_loki.py`
- Assertions: `skills/assertions.py` + `dev/assertions/*.yaml`
- Worktree isolation: `dev/worktree_env.py` + `dev/ports.py`
- Templates: `templates/` (exec-plan, design-doc, product-spec, doc-frontmatter, doc-gardener-prompt)
