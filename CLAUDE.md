# Agent Instructions -- obsidian-connector

> Always start by reading `AGENTS.md` in the repo root. It is your map.

## Quick orientation

Python wrapper for the Obsidian desktop app CLI. Provides:
- **Python API** -- `from obsidian_connector import search_notes, read_note, ...`
- **CLI** -- `obsx search "query"` or `./bin/obsx search "query"`
- **MCP server** -- 8 tools for Claude Desktop via stdio or HTTP

This repo uses **Harness Engineering** for agent-friendly development:
1. **Knowledge Architecture** -- docs as system-of-record with mechanical enforcement
2. **Agent Operating Procedures** -- templates and evidence-driven validation

## Golden rule

**Never call the `obsidian` CLI directly.** Use the MCP tools, Python API,
or CLI wrapper. They handle vault resolution, argument escaping, error
detection, audit logging, and output parsing.

## Navigation hierarchy

Read files in this order (progressive disclosure):
1. `AGENTS.md` -- routing map (always read first)
2. `ARCHITECTURE.md` -- module/package layering
3. `TOOLS_CONTRACT.md` -- JSON envelope schema, typed errors, command reference
4. `docs/index.md` -> `docs/**/index.md` -> leaf docs (only as needed)

## Available local commands

```bash
make docs-lint              # Validate docs structure (warnings + errors)
make docs-lint-strict       # Errors only (CI equivalent)
make docs-staleness         # Check git-based staleness
make docs-changed           # Lint only changed docs (fast pre-commit)
python3 scripts/smoke_test.py    # Core function smoke tests
python3 scripts/cache_test.py    # Cache module tests
bash scripts/mcp_launch_smoke.sh # MCP server launch test
./bin/obsx doctor           # Health check (Obsidian connectivity)
```

## Rules

1. **Treat `docs/` as source-of-truth** -- do not invent behavior not backed by docs
2. **For complex changes** -- create an execution plan under `docs/exec-plans/active/`
3. **When code behavior changes** -- update TOOLS_CONTRACT.md, relevant docs, bump `last_reviewed`
4. **If docs conflict with code** -- code wins; fix docs immediately
5. **Always run `make docs-lint`** before submitting changes that touch docs/

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py` (composed)
2. Export from `__init__.py`
3. Add an argparse subcommand in `cli.py` with both human and `--json` output
4. Add a `@mcp.tool()` function in `mcp_server.py`
5. If mutating, add `--dry-run` and call `log_action()` from `audit.py`
6. Add a smoke test in `scripts/`
7. Update `TOOLS_CONTRACT.md`

## Frontmatter contract

Every doc in `docs/` must have:
```yaml
---
title: "Title"
status: draft | verified | deprecated
owner: "team-slug"
last_reviewed: "YYYY-MM-DD"
---
```
