---
title: "Architecture Map"
status: verified
owner: "mariourquia"
last_reviewed: "2026-04-13"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/"
  - "src/"
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
| `obsidian_connector/` | Core Python package -- stays at root for PyPI |
| `src/` | Human-authored plugin content (skills, hooks, manifest, MCP config, bin wrappers) |
| `src/skills/` | 17 Claude Code skill definitions (12 workflow + 5 knowledge) |
| `src/hooks/` | hooks.json + session_start.sh, session_stop.sh, idea_detect.md |
| `src/plugin/` | Plugin manifest (plugin.json) and MCP server config (.mcp.json) |
| `src/bin/` | Shell wrappers (`obsx`, `obsx-mcp`) that work without venv activation |
| `config/targets/` | Build target profiles (claude-code, claude-desktop, portable, pypi) |
| `config/defaults/` | Skill portability classification (skill-portability.yaml) |
| `tools/` | TypeScript build pipeline (build, validate, diff, doctor, package) |
| `builds/` | Generated build output per target -- gitignored, never edit |
| `scripts/` | Install script, smoke tests, and integration tests |
| `docs/` | User-facing documentation, release artifacts, distribution guides |
| `tests/` | pytest suite including build system tests and snapshots |
| `scheduling/` | launchd/cron configs for scheduled automation |

### Backward-compatibility symlinks

These symlinks at the repo root point into `src/` so that `claude --plugin-dir .`
and existing scripts continue to work during development:

| Symlink | Target |
|---------|--------|
| `.mcp.json` | `src/plugin/.mcp.json` |
| `.claude-plugin/plugin.json` | `src/plugin/plugin.json` |

The `skills/`, `hooks/`, and `bin/` directories at root share content with
their `src/` counterparts (same underlying files).

## Package modules

| Module | Purpose |
|--------|---------|
| `client.py` | Core CLI wrapper: `run_obsidian()`, `search_notes()`, `read_note()`, `list_tasks()`, `log_to_daily()`, `batch_read_notes()` |
| `cli.py` | CLI entry point (`obsx`): 115 argparse subcommands, `--json` / `--vault` / `--dry-run` flags |
| `startup.py` | Shared first-run marker and non-UI startup helpers used by the CLI and onboarding flow |
| `ui_dashboard.py` | Optional Textual dashboard and setup wizard, loaded lazily from CLI-only paths |
| `mcp_server.py` | MCP server (FastMCP): 112 tools for Claude Desktop (stdio + HTTP transports) |
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
| `vault_factory.py` | Vault discovery, creation alongside existing vaults, research topic seeding |
| `vault_presets.py` | 13 vault preset templates (research, project-management, journal, etc.) |
| `vault_guardian.py` | Auto-generated file marking, unorganized note detection, file organization |
| `idea_router.py` | Idea routing to project idea files via keyword matching against repo registry |
| `automation.py` | Event-triggered automation: tool registry, chain runner, event bus |
| `product_registry.py` | Single source of truth for product metadata (version, counts, skill/surface registries) |
| `smart_triage.py` | Three-way rule-based classifier (action / idea / raw) with LLM fallback, used by capture-service ingest |
| `commitment_notes.py` | Idempotent commitment-note renderer (frontmatter + body), preserved user-notes fences |
| `commitment_ops.py` | HTTP client for capture-service endpoints (service-retrieval, dedup, patterns, bulk-actions, timeout knob) |
| `commitment_dashboards.py` | Vault dashboard writers: commitments + review surfaces + admin + analytics |
| `entity_notes.py` | Entity wiki note writer under `Entities/<Kind>/<slug>.md` with preserved fence + deterministic first-pass wiki body |
| `admin_ops.py` | HTTP client for `/api/v1/admin/*` and `/api/v1/mobile/*` endpoints (Task 44 + Task 42) |
| `approval_ops.py` | HTTP client for `/api/v1/deliveries/*` approval UX endpoints (Task 36) |
| `analytics_ops.py` | HTTP client + vault projection for `/api/v1/analytics/*` weekly reports (Task 39) |
| `coaching_ops.py` | HTTP client for `/api/v1/coaching/*` review recommendations (Task 40) |
| `import_tools.py` | Vault import pipeline: scan / classify / plan / execute / report (Task 43), default dry-run |
| `onboarding.py` | Pure-Python onboarding step catalog, shared between `obsx onboarding` CLI and `docs/ONBOARDING.md` |
| `recipes.py` | Preset workflow recipes for common flows |
| `vault_conflicts.py` | Shared-vault conflict-file detector (Task 37): iCloud / Dropbox / OneDrive / Obsidian Sync patterns, deterministic output, never raises |

## Dependency flow

```
bin/obsx ──> cli.py ──> client.py ──> subprocess (obsidian CLI) ──> Obsidian app (IPC)
                    ──> startup.py
                    ──> ui_dashboard.py (lazy, optional `tui` extra)
                    ──> workflows.py ──> client_fallback.py + graph.py
                    ──> thinking.py ──> client_fallback.py + graph.py + index_store.py
                    ──> project_sync.py ──> config.py + audit.py + vault_init.py
                    ──> vault_init.py ──> project_sync.py (data types) + audit.py
                    ──> envelope.py, audit.py

bin/obsx-mcp ──> mcp_server.py ──> client_fallback.py + workflows.py + thinking.py + graph.py + doctor.py

client.py uses: config.py, cache.py, errors.py
cli.py uses: startup.py; lazily imports ui_dashboard.py only for `menu` / `setup-wizard` / first-run onboarding
client_fallback.py uses: client.py, file_backend.py, config.py, errors.py
graph.py uses: config.py (vault path resolution)
index_store.py uses: graph.py, config.py
workflows.py uses: client_fallback.py, graph.py, index_store.py, config.py, audit.py
thinking.py uses: client_fallback.py, graph.py, index_store.py, config.py
platform.py uses: (no internal deps -- foundation layer)
file_backend.py uses: (no internal deps -- standalone file access)
uninstall.py uses: platform.py, config.py
```

## Build system

Plugin artifacts are authored in `src/` and built to `builds/` by the TypeScript
pipeline in `tools/`. The Python package (`obsidian_connector/`) stays at the
repo root because PyPI needs it there.

Four build targets, each defined by a YAML profile in `config/targets/`:

| Target | What ships | Build command |
|--------|-----------|---------------|
| `claude-code` | Full plugin (skills + hooks + manifest + MCP + Python pkg) | `npx tsx tools/build.ts --target claude-code` |
| `claude-desktop` | MCP server + install config | `npx tsx tools/build.ts --target claude-desktop` |
| `portable` | 5 stripped knowledge skills for Codex/OpenCode/Gemini | `npx tsx tools/build.ts --target portable` |
| `pypi` | Python package only | `npx tsx tools/build.ts --target pypi` |

Skill portability (which skills ship to the portable target) is classified in
`config/defaults/skill-portability.yaml`.

## Key entry points

- **Tools contract:** `TOOLS_CONTRACT.md`
- **Docs catalog:** `docs/index.md`
- **Install:** `scripts/install.sh`
- **CLI:** `bin/obsx`
- **MCP server:** `python3 -m obsidian_connector.mcp_server`
- **Build all targets:** `npx tsx tools/build.ts --target all`
- **Validate builds:** `npx tsx tools/validate.ts --target all`
