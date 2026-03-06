---
title: "Architecture Map"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-06"
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

For graph-aware features (backlinks, neighborhood, vault structure), the
connector reads `.md` files directly from the vault directory. This is
read-only and does not require Obsidian to be running. The graph index is
persisted to SQLite for fast incremental updates.

## Top-level directory map

| Directory | Purpose |
|-----------|---------|
| `obsidian_connector/` | Core Python package (14 modules) |
| `bin/` | Shell wrappers (`obsx`, `obsx-mcp`) that work without venv activation |
| `scripts/` | Install script, smoke tests, and integration tests |
| `docs/` | Knowledge base (harness engineering, frontmatter-enforced) |
| `tools/` | Mechanical enforcement (docs linter) |
| `templates/` | Reusable doc templates (exec-plan, design-doc, product-spec) |

## Package modules

| Module | Purpose |
|--------|---------|
| `client.py` | Core CLI wrapper: `run_obsidian()`, `search_notes()`, `read_note()`, `list_tasks()`, `log_to_daily()`, `batch_read_notes()` |
| `cli.py` | CLI entry point (`obsx`): 26 argparse subcommands, `--json` / `--vault` / `--dry-run` flags |
| `mcp_server.py` | MCP server (FastMCP): 27 tools for Claude Desktop (stdio + HTTP transports) |
| `workflows.py` | Higher-level workflows: daily ops, open loops, graduate pipeline, delegation detection, context loader |
| `thinking.py` | Thinking tools: ghost (voice), drift (intention vs behavior), trace (idea evolution), ideas (graph analysis) |
| `graph.py` | Graph-aware vault indexing: parse links, tags, frontmatter from `.md` files, build `NoteIndex` |
| `index_store.py` | SQLite-backed persistent index with mtime-based incremental updates |
| `cache.py` | In-memory TTL cache for read-only CLI calls, thread-safe, mutation-aware |
| `config.py` | Layered config loading (CLI flags > env vars > config.json), vault path resolution |
| `audit.py` | Append-only JSONL audit log for mutating commands |
| `doctor.py` | Health-check diagnostics (binary, version, vault, reachability) |
| `envelope.py` | Canonical JSON envelope builder for `--json` output |
| `errors.py` | Typed exception hierarchy (ObsidianNotFound, VaultNotFound, etc.) |
| `search.py` | Search result enrichment and deduplication |

## Dependency flow

```
bin/obsx ──> cli.py ──> client.py ──> subprocess (obsidian CLI) ──> Obsidian app (IPC)
                    ──> workflows.py ──> client.py + graph.py
                    ──> thinking.py ──> client.py + graph.py + index_store.py
                    ──> envelope.py, audit.py

bin/obsx-mcp ──> mcp_server.py ──> client.py + workflows.py + thinking.py + graph.py + doctor.py

client.py uses: config.py, cache.py, errors.py
graph.py uses: config.py (vault path resolution)
index_store.py uses: graph.py, config.py
workflows.py uses: client.py, graph.py, index_store.py, config.py, audit.py
thinking.py uses: client.py, graph.py, index_store.py, config.py
```

## Key entry points

- **Agent starts here:** `AGENTS.md`
- **Agent tools contract:** `TOOLS_CONTRACT.md`
- **Docs catalog:** `docs/index.md`
- **Install:** `scripts/install.sh`
- **CLI:** `bin/obsx` or `python3 main.py`
- **MCP server:** `python3 -m obsidian_connector.mcp_server`
