---
title: "Architecture Map"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-30"
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
| `obsidian_connector/` | Core Python package (31 modules) |
| `bin/` | Shell wrappers (`obsx`, `obsx-mcp`) that work without venv activation |
| `scripts/` | Install script, smoke tests, and integration tests |
| `docs/` | User-facing documentation, release artifacts, distribution guides |
| `skills/` | Claude Code skill definitions (13 skills: 8 workflow + 5 knowledge) |
| `portable/` | Portable skills bundle for Codex CLI, OpenCode, Gemini CLI (5 skills) |
| `scheduling/` | launchd/cron configs for scheduled automation |

## Package modules

| Module | Purpose |
|--------|---------|
| `client.py` | Core CLI wrapper: `run_obsidian()`, `search_notes()`, `read_note()`, `list_tasks()`, `log_to_daily()`, `batch_read_notes()` |
| `cli.py` | CLI entry point (`obsx`): 62 argparse subcommands, `--json` / `--vault` / `--dry-run` flags |
| `mcp_server.py` | MCP server (FastMCP): 62 tools for Claude Desktop (stdio + HTTP transports) |
| `platform.py` | Cross-platform OS abstraction (path resolution, scheduling, notifications, process detection for macOS/Linux/Windows) |
| `uninstall.py` | Artifact discovery and removal (venv, skills, hooks, plist/systemd/schtasks, Claude Desktop config, audit logs) |
| `write_manager.py` | Atomic writes, pre-write snapshots, rollback, file locks, diff preview, protected folders |
| `watcher.py` | Filesystem watcher for incremental re-index on vault changes (watchdog or polling fallback) |
| `draft_manager.py` | Draft lifecycle: list, approve, reject, auto-archive stale agent drafts |
| `vault_registry.py` | Named vault registry with profiles and per-vault policies |
| `retrieval.py` | Hybrid search: lexical + semantic + graph + recency scoring with profiles and explanations |
| `embeddings.py` | Local embedding index via sentence-transformers (optional) |
| `template_engine.py` | Template loading, variable substitution, inheritance, configurable daily notes and sentinels |
| `scheduler.py` | Schedule config, workflow chaining, active hours, missed-run recovery, event triggers |
| `reports.py` | Report generation: weekly, monthly, vault health, project status |
| `telemetry.py` | Local-only session telemetry (zero network calls) |
| `project_intelligence.py` | Project health scores, changelogs, stale detection, graduation suggestions, weekly packets |
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
| `client_fallback.py` | Adapter layer: wraps client.py with automatic file_backend fallback when Obsidian CLI is unavailable |
| `file_backend.py` | CLI-less vault access via direct file reads (search, read, tasks, daily log, note creation with path traversal protection) |
| `search.py` | Search result enrichment and deduplication |
| `project_sync.py` | Project sync engine: git state extraction, dashboard/threads/todo/session rendering, configurable repo registry |
| `vault_init.py` | Vault initialization wizard: interactive setup, auto-discovery, scaffold generation |

## Dependency flow

```
bin/obsx ──> cli.py ──> client.py ──> subprocess (obsidian CLI) ──> Obsidian app (IPC)
                    ──> workflows.py ──> client_fallback.py + graph.py
                    ──> thinking.py ──> client_fallback.py + graph.py + index_store.py
                    ──> project_sync.py ──> config.py + audit.py + vault_init.py
                    ──> vault_init.py ──> project_sync.py (data types) + audit.py
                    ──> envelope.py, audit.py

bin/obsx-mcp ──> mcp_server.py ──> client_fallback.py + workflows.py + thinking.py + graph.py + doctor.py

client.py uses: config.py, cache.py, errors.py
client_fallback.py uses: client.py, file_backend.py, config.py, errors.py
graph.py uses: config.py (vault path resolution)
index_store.py uses: graph.py, config.py
workflows.py uses: client_fallback.py, graph.py, index_store.py, config.py, audit.py
thinking.py uses: client_fallback.py, graph.py, index_store.py, config.py
platform.py uses: (no internal deps -- foundation layer)
file_backend.py uses: (no internal deps -- standalone file access)
uninstall.py uses: platform.py, config.py
```

## Key entry points

- **Tools contract:** `TOOLS_CONTRACT.md`
- **Docs catalog:** `docs/index.md`
- **Install:** `scripts/install.sh`
- **CLI:** `bin/obsx`
- **MCP server:** `python3 -m obsidian_connector.mcp_server`
