---
title: "Release Notes -- obsidian-connector v0.6.0"
# generated, do not edit
status: verified
owner: mariourquia
---

```
  ___  _         _    _ _                ___
 / _ \| |__  ___(_) _| (_) __ _ _ __    / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

   v0.6.0 -- Live Retrieval, Safe Writes, Multi-Vault Workflows
                    Turn Claude into your second brain.
```

## At a Glance

| Metric           | v0.5.0 | v0.6.0 |
|------------------|--------|--------|
| MCP tools        | 47     | 62     |
| CLI commands     | 36     | 62     |
| Skills           | 13     | 13     |
| Vault presets    | 13     | 13     |
| Python modules   | 20     | 31     |
| Test assertions  | ~100   | 441+   |

## What Changed

The connector had breadth. Now it has trust, freshness, and scale.

### Milestone A -- Trust and Freshness

**Write safety.** Every mutation now routes through `write_manager.py`:
atomic write-then-rename, pre-write snapshots in `.obsidian-connector/snapshots/`,
rollback to any snapshot, diff preview via `--preview`, file-level locking,
protected-folder policies, and `generated_by` metadata on all agent-created files.

**Live indexing.** `watcher.py` monitors the vault for `.md` changes and triggers
incremental re-index within seconds. Uses `watchdog` when installed, polls when not.
Every CLI/MCP response includes `index_age_seconds` when the index is stale.

**Draft lifecycle.** Agent drafts no longer accumulate forever.
`draft_manager.py` provides list/approve/reject/auto-archive with configurable
retention. Stale drafts (default 14 days) get moved to `Archive/Stale Drafts/`.

### Milestone B -- Smarter Retrieval and Vault Scale

**Hybrid search.** `retrieval.py` combines four signals: BM25-style lexical
scoring, local semantic embeddings (optional `sentence-transformers`), graph
centrality from backlinks, and exponential recency decay. Four profiles tune the
mix: `journal` (recency-heavy), `project` (graph-heavy), `research`
(semantic-heavy), `review` (balanced). `--explain` shows why each result ranked.

**Multi-vault.** `vault_registry.py` maintains a named vault registry at
`~/.config/obsidian-connector/vaults.json` with profiles (`personal`, `work`,
`research`, `creative`) and per-vault policies. Cross-vault search via
`--vaults=all`.

### Milestone C -- Daily Operating System

**Templates.** `template_engine.py` loads templates from `_templates/` with
`{{variable}}` substitution and template inheritance. Five built-ins: daily-note,
meeting-note, research-note, decision-log, project-idea. Configurable daily note
path, format, and sentinel headings via `config.json`.

**Scheduler.** `scheduler.py` manages morning/evening/weekly schedules with
workflow chaining (run a sequence of tools), active-hours windows, missed-run
detection, and event triggers (`after_sync`, `after_note_create`,
`after_session_end`).

**Reports.** `reports.py` generates weekly review, monthly review, vault health
(orphans, stale notes, index coverage, tag distribution), and project status
reports as Markdown in `Reports/`.

**Project intelligence.** `project_intelligence.py` computes per-project health
scores (0-100), generates changelogs from session logs, detects stale projects,
suggests idea-to-project graduations, and produces weekly project packets.

**Telemetry.** `telemetry.py` tracks notes read/written, tools called, retrieval
misses, and write-risk events. Local JSONL storage, auto-rotation, zero network.

### Milestone D -- Polish

**Manifest validation.** `scripts/manifest_check.py` validates tool/skill/preset/
command counts across README, CLAUDE.md, TOOLS_CONTRACT.md, marketplace.json,
and mcpb.json. Exits non-zero on mismatch. CI-ready.

**Compatibility matrix.** `scripts/generate_compat_matrix.py` produces
`docs/references/compatibility-matrix.md` showing which features are available
on which surface (MCP, CLI, Python API, portable).

**Release checklist.** `templates/release-checklist.md` standardizes the release
process.

## New CLI Commands

```
obsx rollback [--last | --snapshot DIR]
obsx drafts list | approve PATH --target DIR | reject PATH | clean [--dry-run]
obsx vaults list | add NAME PATH | remove NAME | default NAME
obsx templates list | init | check
obsx schedule list | preview NAME | status | run NAME | fire EVENT | tools
obsx report weekly | monthly | vault-health | project-status
obsx stats [--weekly]
obsx project health | changelog NAME | packet
obsx index-status
obsx search --profile journal --explain "query"
```

## New MCP Tools

`obsidian_rollback`, `obsidian_list_drafts`, `obsidian_approve_draft`,
`obsidian_reject_draft`, `obsidian_clean_drafts`, `obsidian_register_vault`,
`obsidian_set_default_vault`, `obsidian_list_templates`,
`obsidian_create_from_template`, `obsidian_project_changelog`,
`obsidian_project_health`, `obsidian_project_packet`,
`obsidian_generate_report`, `obsidian_session_stats`, `obsidian_index_status`.

## New Optional Dependencies

| Package | Install | What it enables |
|---------|---------|-----------------|
| `watchdog` | `pip install obsidian-connector[live]` | Filesystem watcher (vs polling fallback) |
| `sentence-transformers` | `pip install obsidian-connector[semantic]` | Semantic similarity in hybrid search |

Both are optional. All features work without them (degraded mode).

## New Modules

| Module | LOC | Purpose |
|--------|-----|---------|
| `write_manager.py` | 602 | Atomic writes, snapshots, rollback, locks |
| `watcher.py` | 370 | Filesystem watcher, debounce, polling fallback |
| `draft_manager.py` | 384 | Draft lifecycle (approve/reject/auto-archive) |
| `vault_registry.py` | 338 | Named vault registry with policies |
| `retrieval.py` | 531 | Hybrid search engine |
| `embeddings.py` | 342 | Local embedding index (optional) |
| `template_engine.py` | 608 | Template loading, inheritance, variable substitution |
| `scheduler.py` | 389 | Schedule config, chaining, event triggers |
| `reports.py` | 512 | Report generation engine |
| `telemetry.py` | 246 | Local-only session telemetry |
| `project_intelligence.py` | 582 | Health scores, changelogs, weekly packets |

## Testing

441+ assertions across 10 test suites. pytest discovery via `python -m pytest tests/`.

| Suite | Assertions | Status |
|-------|-----------|--------|
| write_manager | 26 | pass |
| watcher | 29 | pass |
| draft_manager | 30 | pass |
| vault_registry | 36 | pass |
| template_engine | 49 | pass |
| retrieval | 78 | pass |
| scheduler | 22 | pass |
| reports + telemetry | 54 | pass |
| project_intelligence | 62 | pass |
| automation | 55 | pass |

Existing test suites (import cycle, CLI parse, MCP contract) unaffected.
Smoke tests require Obsidian desktop running (expected, unchanged).

## Security

- All new mutating operations route through `write_manager.py` with path traversal
  protection (`_resolve_and_validate` checks resolved path stays within vault root).
- File locks prevent concurrent writes from iCloud/Obsidian Sync conflicts.
- `telemetry.py` has zero network imports (no urllib, socket, requests, http.client).
  Verified by AST inspection in the test suite.
- New error types (`ProtectedFolderError`, `WriteLockError`, `RollbackError`) added
  to `errors.py` and mapped in MCP error envelope.
- No new dependencies required. `watchdog` and `sentence-transformers` are optional.

## Verification

```bash
# Run all v0.6.0 tests
python -m pytest tests/ -v

# Validate documentation counts match code
python3 scripts/manifest_check.py

# Check import integrity
python3 scripts/import_cycle_test.py

# Health check (requires Obsidian running)
./bin/obsx doctor --json
```

## Known Limitations

- `sentence-transformers` pulls ~500MB of model data on first use.
- File watcher polling fallback checks every 2 seconds (vs ~instant with watchdog).
- Multi-vault cross-vault search is sequential (no parallel index queries yet).
- Template inheritance only supports `## Heading` section-level override, not
  arbitrary nesting.
- Scheduler does not have a persistent daemon yet -- schedules run via launchd/cron
  or manual `obsx schedule run NAME`.

## Compatibility

| Platform | Status |
|----------|--------|
| macOS (Apple Silicon + Intel) | Tested, primary |
| Ubuntu 22.04+ | CI-tested |
| Windows 10+ | Supported (not CI-tested for v0.6.0 new modules) |
| Python 3.11 | Supported |
| Python 3.12 | Supported |
| Python 3.13 | Supported |
| Python 3.14 | Tested (development machine) |
| Obsidian 1.12+ | Required for CLI-based tools |

## Upgrade

```bash
cd /path/to/obsidian-connector
git pull origin main
pip install -e .                    # core
pip install -e .[live]              # + filesystem watcher
pip install -e .[semantic]          # + semantic search
pip install -e .[live,semantic]     # both
```

No breaking changes. All v0.5.0 tools, commands, and APIs continue to work unchanged.

## Full PRD

`docs/exec-plans/completed/v0.6.0-prd.md` -- 35 issues, acceptance criteria,
architecture notes, and risk analysis.
