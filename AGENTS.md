# AGENTS.md (Repository Map)

> This file is your entry point. Read it first, follow links for detail.
> **Hard limit: <= 120 lines.** Do not add implementation details here.

## Start here (routing)

- Architecture map: [./ARCHITECTURE.md](./ARCHITECTURE.md)
- Tools contract (AI agents): [./TOOLS_CONTRACT.md](./TOOLS_CONTRACT.md)
- Docs catalog: [./docs/index.md](./docs/index.md)
- Design docs: [./docs/design-docs/index.md](./docs/design-docs/index.md)
- Active execution plans: [./docs/exec-plans/active/](./docs/exec-plans/active/)
- Quality scores: [./docs/quality/QUALITY_SCORE.md](./docs/quality/QUALITY_SCORE.md)
- Tech debt: [./docs/tech-debt-tracker.md](./docs/tech-debt-tracker.md)

## What this repo does

Python wrapper for the Obsidian desktop app. Exposes vault operations
(search, read, write, graph analysis, thinking tools, workflow management)
as a Python API, CLI (`obsx` -- 26 commands), and MCP server (27 tools)
for Claude Desktop.

## Module map

| Module | Purpose |
|--------|---------|
| `client.py` | Core CLI wrapper, batch reads |
| `cli.py` | 26 CLI subcommands |
| `mcp_server.py` | 27 MCP tools (FastMCP) |
| `workflows.py` | Daily ops, loops, graduate, delegations, context |
| `thinking.py` | Ghost, drift, trace, ideas |
| `graph.py` | Vault graph indexing (links, tags, backlinks) |
| `index_store.py` | SQLite persistent index |

## Operating rules

- **Never call the `obsidian` CLI directly.** Use MCP tools, Python API, or `obsx`.
- Treat `docs/` as source-of-truth; do not invent behavior not backed by code or docs.
- For complex changes: create/extend an execution plan under `docs/exec-plans/active/`.
- When code behavior changes, update TOOLS_CONTRACT.md, docs, and bump `last_reviewed`.
- If docs conflict with code, **code wins**; open a doc-fix PR immediately.

## How to navigate fast

- Use ripgrep: `rg "keyword" obsidian_connector/ docs/`
- Start with indexes; do not read long docs unless routed by an index.
- Prefer docs with `status: verified`. Treat `draft` as partial.

## Required artifacts by change type

- **New command:** client.py or workflows.py + cli.py subcommand + mcp_server.py tool + TOOLS_CONTRACT.md + smoke test
- **Behavior change:** update doc(s) + add/adjust tests
- **Cross-cutting change:** update ARCHITECTURE.md and relevant QUALITY_SCORE.md

## Escalation

- If docs conflict with code, code wins; open a doc-fix PR immediately.

## Available local commands

```
./scripts/install.sh          # One-command setup (venv + Claude Desktop config)
make docs-lint                # Validate docs structure
make docs-lint-strict         # Errors only (CI equivalent)
make docs-staleness           # Check git-based staleness
python3 scripts/smoke_test.py       # Core function smoke tests
python3 scripts/graph_test.py       # Graph module tests
python3 scripts/index_test.py       # Index store tests
python3 scripts/graduate_test.py    # Graduate pipeline tests
python3 scripts/thinking_deep_test.py  # Thinking tools tests (56 assertions)
bash scripts/mcp_launch_smoke.sh    # MCP server launch test
./bin/obsx doctor             # Health check (Obsidian connectivity)
```

## Tools & skills reference

- Installer: `scripts/install.sh`
- Docs linter: `tools/docs_lint.py`
- CLI wrapper: `bin/obsx` (no venv needed)
- MCP server: `python3 -m obsidian_connector.mcp_server`
- Templates: `templates/` (exec-plan, design-doc, frontmatter)
