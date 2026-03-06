---
title: "Architecture Map"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-05"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/"
---

# Architecture Map -- obsidian-connector

**Primary language:** Python 3.11+
**Runtime dependency:** Obsidian desktop app (v1.12+) with CLI enabled

## How it works

obsidian-connector wraps the Obsidian desktop app's CLI, which communicates
with the running Electron app via IPC. Every vault operation is a subprocess
call to the `obsidian` binary. The connector adds: vault resolution, argument
escaping, error detection, audit logging, caching, and output parsing.

## Top-level directory map

| Directory | Purpose |
|-----------|---------|
| `obsidian_connector/` | Core Python package (client, CLI, MCP server, cache, config, errors) |
| `bin/` | Shell wrappers (`obsx`, `obsx-mcp`) that work without venv activation |
| `scripts/` | Smoke tests and integration tests |
| `docs/` | Knowledge base (harness engineering, frontmatter-enforced) |
| `tools/` | Mechanical enforcement (docs linter) |
| `templates/` | Reusable doc templates (exec-plan, design-doc, product-spec) |

## Package modules

| Module | Purpose |
|--------|---------|
| `client.py` | Core CLI wrapper: `run_obsidian()`, `search_notes()`, `read_note()`, `list_tasks()`, `log_to_daily()` |
| `cli.py` | CLI entry point (`obsx`): argparse subcommands, `--json` / `--vault` / `--dry-run` flags |
| `mcp_server.py` | MCP server (FastMCP): 8 tools for Claude Desktop (stdio + HTTP transports) |
| `workflows.py` | Higher-level workflows: `log_decision()`, `create_research_note()`, `find_prior_work()` |
| `cache.py` | In-memory TTL cache for read-only CLI calls, thread-safe, mutation-aware |
| `config.py` | Layered config loading (CLI flags > env vars > config.json) |
| `audit.py` | Append-only JSONL audit log for mutating commands |
| `doctor.py` | Health-check diagnostics (binary, version, vault, reachability) |
| `envelope.py` | Canonical JSON envelope builder for `--json` output |
| `errors.py` | Typed exception hierarchy (ObsidianNotFound, VaultNotFound, etc.) |
| `search.py` | Search result enrichment and deduplication |

## Dependency flow

```
bin/obsx ──> cli.py ──> client.py ──> subprocess (obsidian CLI) ──> Obsidian app (IPC)
                    ──> workflows.py ──> client.py
                    ──> envelope.py, audit.py
bin/obsx-mcp ──> mcp_server.py ──> client.py + workflows.py + doctor.py

client.py uses: config.py, cache.py, errors.py
cli.py uses: client.py, workflows.py, doctor.py, envelope.py, audit.py
```

## Key entry points

- **Agent starts here:** `AGENTS.md`
- **Agent tools contract:** `TOOLS_CONTRACT.md`
- **Docs catalog:** `docs/index.md`
- **Local dev:** `Makefile`
- **CLI:** `bin/obsx` or `python3 main.py`
- **MCP server:** `bin/obsx-mcp`
