# Tools Contract -- obsidian-connector

This document tells Claude Code (and other AI coding agents) how to interact
with Obsidian through this project.  Read this file before touching the vault.

## Golden rule

**Never call the `obsidian` CLI directly.**  Use the MCP tools, Python API,
or CLI wrapper instead.  They handle vault resolution, argument escaping,
error detection, audit logging, and output parsing.

## MCP tools (Claude Desktop / AI agents)

When running as an MCP server (via `claude_desktop_config.json` or `--http`),
62 tools are available to Claude and other MCP clients.  All `vault`
parameters are optional -- when omitted, the configured default vault is used.

### Core vault operations

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_search` | `query`, `vault?` | JSON array of `{file, matches[{line, text}]}` |
| `obsidian_read` | `name_or_path`, `vault?` | Raw markdown content of the note |
| `obsidian_tasks` | `status?`, `path_prefix?`, `limit?`, `vault?` | JSON array of `{text, status, file, line}` |
| `obsidian_log_daily` | `content`, `vault?` | Confirmation string |
| `obsidian_log_decision` | `project`, `summary`, `details`, `vault?` | Confirmation string |
| `obsidian_create_note` | `title`, `template`, `vault?` | Created file path |
| `obsidian_doctor` | `vault?` | JSON array of health check results |

### Research and discovery

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_find_prior_work` | `topic`, `top_n?`, `vault?` | JSON array of `{file, heading, excerpt, match_count}` |
| `obsidian_challenge_belief` | `belief`, `vault?`, `max_evidence?` | JSON `{belief, counter_evidence[], supporting_evidence[], verdict}` |
| `obsidian_emerge_ideas` | `topic`, `vault?`, `max_clusters?` | JSON `{topic, total_notes, clusters[]}` |
| `obsidian_connect_domains` | `domain_a`, `domain_b`, `vault?`, `max_connections?` | JSON `{domain_a, domain_b, connections[], domain_a_only[], domain_b_only[]}` |

### Graph intelligence

These tools read vault `.md` files directly and work without Obsidian running.

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_neighborhood` | `note_path`, `depth?`, `vault?` | JSON `{note, backlinks[], forward_links[], tags[], neighbors[]}` |
| `obsidian_vault_structure` | `vault?` | JSON `{total_notes, orphans[], dead_ends[], unresolved_links{}, tag_cloud{}, top_connected[]}` |
| `obsidian_backlinks` | `note_path`, `vault?` | JSON array of `{file, context_line, tags[]}` |
| `obsidian_rebuild_index` | `vault?` | Confirmation with note count and timing |

### Thinking tools

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_ghost` | `sample_notes?`, `question?`, `vault?` | JSON voice profile `{patterns{}, summary}` |
| `obsidian_drift` | `vault?`, `lookback_days?` | JSON `{intention, evidence[], drift_score, analysis}` |
| `obsidian_trace` | `topic`, `max_notes?`, `vault?` | JSON `{idea, timeline[], evolution_summary}` |
| `obsidian_ideas` | `vault?`, `max_ideas?` | JSON `{ideas[], graph_stats{}}` |

### Workflow OS

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_my_world` | `vault?` | JSON full vault snapshot (recent notes, tasks, loops, context) |
| `obsidian_today` | `vault?` | JSON today brief (daily note, tasks, loops) |
| `obsidian_close_day` | `vault?` | JSON end-of-day reflection prompt |
| `obsidian_open_loops` | `vault?`, `lookback_days?` | JSON array of open loop items |
| `obsidian_graduate_candidates` | `vault?`, `lookback_days?` | JSON array of promotable idea candidates |
| `obsidian_graduate_execute` | `title`, `content`, `source_file?`, `vault?`, `confirm?`, `dry_run?` | JSON created path + provenance |
| `obsidian_delegations` | `vault?`, `lookback_days?` | JSON array of delegation instructions |
| `obsidian_context_load` | `vault?` | JSON full context bundle for agent session start |
| `obsidian_check_in` | `vault?`, `timezone?` | JSON `{time_of_day, daily_note_exists, completed_rituals[], pending_rituals[], pending_delegations, unreviewed_drafts, open_loop_count, suggestion}` |

### Project sync

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_sync_projects` | `vault?`, `github_root?`, `update_todo?` | JSON `{synced, active_threads, projects_dir, dashboard, timestamp, todo_updated}` |
| `obsidian_project_status` | `project`, `vault?`, `github_root?` | JSON `{project, branch, last_commit, uncommitted, activity, modified_files[], ...}` |
| `obsidian_active_threads` | `vault?`, `github_root?` | JSON array of `{project, branch, uncommitted, last_commit, modified_files[]}` |
| `obsidian_log_session` | `projects`, `work_types?`, `completed?`, `next_steps?`, `decisions?`, `session_context?`, `vault?` | JSON `{session_file, date, projects[], appended}` |
| `obsidian_running_todo` | `vault?` | JSON `{total_open, total_completed, by_source{}, recent_completed[]}` |
| `obsidian_init_vault` | `vault_path`, `github_root?`, `use_defaults?` | JSON `{vault_path, repos_tracked, dirs_created[], files_created[], config_file, next_step}` |

### System administration

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_uninstall` | `dry_run?`, `remove_venv?`, `remove_skills?`, `remove_hook?`, `remove_plist?`, `remove_logs?`, `remove_cache?` | JSON removal plan (dry_run=true) or removal results (dry_run=false) |

### Write safety (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_rollback` | `vault?` | JSON result of restored snapshot |

### Draft management (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_list_drafts` | `vault?` | JSON array of draft info (path, age, status) |
| `obsidian_approve_draft` | `draft_path`, `target_folder`, `vault?` | JSON confirmation with new path |
| `obsidian_reject_draft` | `draft_path`, `vault?` | JSON confirmation with archive path |
| `obsidian_clean_drafts` | `max_age_days?`, `dry_run?`, `vault?` | JSON list of archived drafts |

### Vault registry (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_register_vault` | `name`, `path`, `profile?` | JSON confirmation |
| `obsidian_set_default_vault` | `name` | JSON confirmation |

### Templates (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_list_templates` | `vault?` | JSON array of template info |
| `obsidian_create_from_template` | `template_name`, `title`, `vault?`, `variables?` | JSON with created file path |

### Project intelligence (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_project_changelog` | `project_name`, `since_days?`, `vault?` | Markdown changelog string |
| `obsidian_project_health` | `vault?` | JSON array of project health scores |
| `obsidian_project_packet` | `days?`, `vault?` | Markdown weekly packet string |

### Reports (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_generate_report` | `report_type`, `vault?` | JSON with report path and summary |

### Telemetry (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_session_stats` | (none) | JSON session telemetry summary |

### Index status (v0.6.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_index_status` | `vault?` | JSON with index age and staleness flag |

### Commitment commands (v0.9.0)

Commands operate on `Commitments/Open/` and `Commitments/Done/` in the vault.
Mutating commands optionally sync status to `obsidian-capture-service` via
`OBSIDIAN_CAPTURE_SERVICE_URL` + `OBSIDIAN_CAPTURE_SERVICE_TOKEN`.

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_commitments` | `status?`, `project?`, `priority?`, `vault?` | JSON `{ok, count, commitments[{action_id, title, status, priority, project, due_at, postponed_until, requires_ack, path}]}` |
| `obsidian_commitment_status` | `action_id`, `vault?` | JSON `{ok, commitment{...}}` or `{ok: false, error: {type: "NotFound"}}` |
| `obsidian_mark_done` | `action_id`, `completed_at?`, `vault?` | JSON `{ok, action_id, previous_status, status, completed_at, path, moved_from, service_sync?}` |
| `obsidian_postpone` | `action_id`, `until`, `vault?` | JSON `{ok, action_id, status, postponed_until, path, service_sync?}` |
| `obsidian_add_reason` | `action_id`, `reason`, `vault?` | JSON `{ok, action_id, reason_added, timestamp, path, status}` |
| `obsidian_due_soon` | `within_days?`, `vault?` | JSON `{ok, count, commitments[...+overdue]}` sorted earliest-due first |
| `obsidian_sync_commitments` | `service_url?`, `vault?` | JSON `{ok, synced, errors[], source_url}` or `{ok: false, error}` |
| `obsidian_review_dashboards` | `stale_days?`, `merge_window_days?`, `merge_jaccard?`, `now?`, `vault?` | JSON `{ok, count, dashboards[{path, written}]}` -- refreshes Daily, Weekly, Stale, Merge Candidates under `Dashboards/Review/` |
| `obsidian_find_commitments` | `status?`, `lifecycle_stage?`, `project?`, `person?`, `area?`, `urgency?`, `priority?`, `source_app?`, `due_before?`, `due_after?`, `limit?`, `cursor?`, `service_url?` | JSON envelope `{ok, status_code, data: {ok, items[...], next_cursor}}` -- thin wrapper over `GET /api/v1/actions` on the capture service. Task 28. |
| `obsidian_commitment_detail` | `action_id`, `service_url?` | JSON envelope `{ok, status_code, data: {ok, action{...}}}` -- thin wrapper over `GET /api/v1/actions/{id}`. Includes delivery summary, entity buckets, `next_follow_up_at`. Task 28. |
| `obsidian_commitment_stats` | `service_url?` | JSON envelope `{ok, status_code, data: {ok, total, by_status, by_lifecycle_stage, by_priority, by_source_app}}`. Task 28. |

### Idea routing (v0.5.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_float_idea` | `idea`, `project?`, `vault?` | JSON `{file, project, idea, timestamp}` |
| `obsidian_incubate_project` | `name`, `description`, `why?`, `tags?`, `related_projects?`, `vault?` | JSON `{file, name, description}` |
| `obsidian_incubating` | `vault?` | JSON array of project inception cards |
| `obsidian_idea_files` | `vault?` | JSON array of `{file, project, idea_count}` |

### Vault factory (v0.5.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_create_vault` | `name`, `description?`, `seed_topics?`, `vault_root?`, `preset?` | JSON `{vault_path, name, preset, seed_topics}` |
| `obsidian_seed_vault` | `vault_path`, `title`, `content`, `tags?`, `folder?` | JSON `{file, title, folder}` |
| `obsidian_vault_presets` | *(none)* | JSON `{presets[], count}` |
| `obsidian_list_vaults` | *(none)* | JSON `{vaults[], count}` |
| `obsidian_discard_vault` | `vault_path`, `confirm?` | JSON `{vault_path, status}` |

### Vault guardian (v0.5.0)

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_mark_auto_generated` | `vault?` | JSON result of files marked |
| `obsidian_detect_unorganized` | `vault?` | JSON `{suggestions[], count}` |
| `obsidian_organize_file` | `file_name`, `target_folder`, `vault?` | JSON result of file move |

**Recommended pattern:** Use the MCP tools for all vault interaction.  Do not
shell out to `obsidian` or `python main.py` from within an MCP-connected session.

## CLI wrapper

The CLI is available as `./bin/obsx` (no venv needed), `obsx` or
`obsidian-connector` (after `pip install -e .`), or `python3 main.py`.
Core CLI commands do not require Textual. The optional `menu` and
`setup-wizard` commands require `pip install 'obsidian-connector[tui]'`
(first-party installers and `scripts/setup.sh` include it).

### CLI subcommands (65 add_parser registrations, including 6 parent groups)

Parent groups (`graduate`, `drafts`, `vaults`, `templates`, `schedule`, `project`)
are not directly runnable -- they contain the sub-subcommands listed below.

| Command | Description | Mutating |
|---|---|---|
| `search` | Full-text search across the vault | no |
| `read` | Read a note by name or path | no |
| `tasks` | List tasks (filterable) | no |
| `log-daily` | Append text to today's daily note | yes |
| `log-decision` | Append a structured decision record | yes |
| `create-research-note` | Create a note from a template | yes |
| `find-prior-work` | Search + summarize top N matching notes | no |
| `challenge` | Challenge a belief against vault evidence | no |
| `emerge` | Cluster notes into idea groups | no |
| `connect` | Find connections between two domains | no |
| `neighborhood` | Graph neighborhood of a note | no |
| `vault-structure` | Vault topology overview | no |
| `backlinks` | All notes linking to a given note | no |
| `ghost` | Analyze writing voice | no |
| `drift` | Detect intention vs behavior drift | no |
| `trace` | Trace idea evolution over time | no |
| `ideas` | Surface latent ideas from graph | no |
| `my-world` | Full vault snapshot | no |
| `today` | Today brief | no |
| `close` | End-of-day reflection | no |
| `open-loops` | List open loops | no |
| `graduate list` | Scan for graduate candidates | no |
| `graduate execute` | Create an agent draft note | yes |
| `delegations` | Scan for delegation instructions | no |
| `context-load` | Load full context bundle | no |
| `check-in` | Time-aware check-in with suggestions | no |
| `rebuild-index` | Force-rebuild the vault graph index | no |
| `doctor` | Health check on CLI and vault | no |
| `uninstall` | Safely remove installation artifacts (two-mode: dry-run or force) | yes |
| `sync-projects` | Sync all tracked repos into the vault | yes |
| `project-status` | Get git status for a single project | no |
| `active-threads` | List projects with active work | no |
| `log-session` | Write a structured session log entry | yes |
| `running-todo` | Show the running TODO state | no |
| `init` | Initialize a new vault for project tracking | yes |
| `rollback` | Restore vault files from a snapshot | yes |
| `drafts list` | List all agent drafts | no |
| `drafts approve` | Move a draft to a target folder | yes |
| `drafts reject` | Archive a draft as rejected | yes |
| `drafts clean` | Auto-archive stale drafts | yes |
| `vaults list` | List all registered vaults | no |
| `vaults add` | Register a new vault | yes |
| `vaults remove` | Unregister a vault | yes |
| `vaults default` | Set a vault as the default | yes |
| `templates list` | List all templates in the vault | no |
| `templates init` | Seed _templates/ from built-in templates | yes |
| `templates check` | Show outdated templates | no |
| `schedule list` | List all configured schedules | no |
| `schedule preview` | Show what a schedule would run | no |
| `schedule status` | Show health of all schedules | no |
| `schedule run` | Execute a named schedule now | yes |
| `schedule fire` | Fire an event trigger | yes |
| `schedule tools` | List available automation tools | no |
| `report` | Generate a vault report | no |
| `stats` | Show session telemetry stats | no |
| `project health` | Show health scores for all projects | no |
| `project changelog` | Generate a project changelog | no |
| `project packet` | Generate a weekly project packet | no |
| `index-status` | Show index age and staleness | no |
| `menu` | Open the interactive configuration dashboard (`tui` extra) | no |
| `setup-wizard` | Run the interactive setup wizard (`tui` extra) | no |

## Canonical JSON envelope

> **Note:** MCP tools return raw JSON payloads, not wrapped in the canonical
> envelope. The envelope schema applies to CLI `--json` output only.

Every command supports `--json` (global flag, before the subcommand).
The response is always wrapped in a canonical envelope:

### Success

```json
{
  "ok": true,
  "command": "search",
  "vault": "Obsidian Vault",
  "duration_ms": 42,
  "data": <command-specific payload>
}
```

### Error

```json
{
  "ok": false,
  "command": "search",
  "vault": "Obsidian Vault",
  "error": {
    "type": "ObsidianCLIError",
    "message": "obsidian exited 1: ...",
    "stderr": "raw stderr",
    "exit_code": 1
  }
}
```

### Typed error types

| Type | Meaning |
|------|---------|
| `ObsidianCLIError` | Generic CLI failure (fallback) |
| `ObsidianNotFound` | Binary not on PATH |
| `ObsidianNotRunning` | App not open / IPC unavailable |
| `VaultNotFound` | Specified vault does not exist |
| `CommandTimeout` | Subprocess timed out |
| `MalformedCLIOutput` | JSON parse failure on CLI stdout |

## Output modes

| Flag | Behavior |
|------|----------|
| *(default)* | Human-readable, suitable for terminal display |
| `--json` | Canonical JSON envelope to stdout (works on ALL commands) |

The `--json` flag is global (placed before the subcommand).  When piping
output to another tool or parsing programmatically, always use `--json`.
The envelope's `ok` field tells you success/failure without parsing the message.

## Safety features

### Dry-run mode

Mutating commands (`log-daily`, `log-decision`, `create-research-note`,
`graduate execute`) support `--dry-run`.  In dry-run mode:

- No vault mutation occurs.
- The response `data` includes `"dry_run": true` and describes what would happen.
- The action is still recorded in the audit log (with `"dry_run": true`).

### Audit log

Every mutating command writes an append-only JSONL line to:

```
~/.obsidian-connector/logs/YYYY-MM-DD.jsonl
```

Each line contains:

```json
{
  "timestamp": "2026-03-06T00:32:00+00:00",
  "command": "log-daily",
  "args": {"content": "..."},
  "vault": "Obsidian Vault",
  "dry_run": false,
  "affected_path": "daily",
  "content_hash": "sha256hex..."
}
```

### Agent draft provenance

`graduate execute` writes notes to `Inbox/Agent Drafts/` with frontmatter:

```yaml
---
source: agent
status: draft
created: "2026-03-06T14:00:00"
source_file: "daily/2026-03-05.md"
---
```

This enforces the "agents read, humans write" boundary. Drafts require
human review before promotion to permanent notes.

## Cross-platform support

All platform-specific logic is centralized in `obsidian_connector/platform.py`.
No other module hardcodes OS-specific paths. The `platform.py` module provides
OS detection, path resolution, scheduling, notifications, and process detection.

### Platform support matrix

| Feature | macOS | Linux | Windows |
|---------|-------|-------|---------|
| CLI wrapper (Obsidian CLI) | Full | Full | Not available (no CLI) |
| Graph tools (direct file access) | Full | Full | Full |
| Thinking tools (direct file access) | Full | Full | Full |
| Workflow OS | Full | Full | Full |
| Scheduling | launchd (available) | systemd (available) | Task Scheduler (not implemented) |
| Notifications | osascript (available) | notify-send (if installed) | PowerShell toast (not implemented) |
| Uninstaller | Full | Full (systemd) | Partial (no scheduler cleanup) |
| Config auto-detection | `~/Library/Application Support/` | `$XDG_CONFIG_HOME/` or `~/.config/` | `%APPDATA%/` |

### Tools requiring Obsidian to be running

These tools communicate with the Obsidian desktop app via IPC and require
the app to be open:

- `obsidian_search`, `obsidian_read`, `obsidian_tasks`
- `obsidian_log_daily`, `obsidian_log_decision`, `obsidian_create_note`
- `obsidian_find_prior_work`, `obsidian_challenge_belief`, `obsidian_emerge_ideas`, `obsidian_connect_domains`

### Tools that work without Obsidian running

These tools read vault `.md` files directly via pathlib and do not need
the Obsidian desktop app or its CLI:

- Graph: `obsidian_neighborhood`, `obsidian_vault_structure`, `obsidian_backlinks`, `obsidian_rebuild_index`
- Thinking: `obsidian_ghost`, `obsidian_drift`, `obsidian_trace`, `obsidian_ideas`
- Workflow OS: `obsidian_my_world`, `obsidian_today`, `obsidian_close_day`, `obsidian_open_loops`, `obsidian_graduate_candidates`, `obsidian_graduate_execute`, `obsidian_delegations`, `obsidian_context_load`, `obsidian_check_in`
- Idea routing: `obsidian_float_idea`, `obsidian_incubate_project`, `obsidian_incubating`, `obsidian_idea_files`
- Vault factory: `obsidian_create_vault`, `obsidian_seed_vault`, `obsidian_vault_presets`, `obsidian_list_vaults`, `obsidian_discard_vault`
- Vault guardian: `obsidian_mark_auto_generated`, `obsidian_detect_unorganized`, `obsidian_organize_file`
- System: `obsidian_doctor`, `obsidian_uninstall`

### Platform-specific behavior notes

**Scheduling backend:** The scheduling backend varies by OS. On macOS,
`install_schedule()` writes launchd plists to `~/Library/LaunchAgents/`.
On Linux, it writes systemd user units to `~/.config/systemd/user/`.
Windows Task Scheduler support is planned for v0.3.0.

**Config paths:** Vault auto-detection reads `obsidian.json` from the
platform-appropriate config directory. On Linux, `XDG_CONFIG_HOME` is
respected (falls back to `~/.config`). On Windows, `%APPDATA%` is used.

**File backend fallback:** On platforms where the Obsidian CLI is not
available (e.g., Windows, headless Linux), graph tools, thinking tools,
and workflow OS tools still function because they read vault files directly
via pathlib. Only CLI-dependent operations (search, read, tasks, mutations
via the Obsidian CLI) require the desktop app.

**Doctor diagnostics:** The `doctor` command reports platform-specific
information including detected OS, scheduler type and availability,
Claude Desktop config path, Obsidian process status, and a feature
availability summary.

## Vault targeting

Resolution order (highest priority wins):

1. `--vault <name>` flag on the command
2. `OBSIDIAN_VAULT_PATH` environment variable (directory path)
3. `OBSIDIAN_VAULT` environment variable (vault name)
4. `vault_path` in `config.json`
5. `default_vault` in `config.json`
6. Auto-detected from platform-specific `obsidian.json` (macOS: `~/Library/Application Support/obsidian/obsidian.json`, Linux: `~/.config/obsidian/obsidian.json`, Windows: `%APPDATA%/obsidian/obsidian.json`)

## Failure modes and recovery

### Step 1: run doctor

```bash
./bin/obsx --json doctor
```

This checks binary presence, version, vault resolution, and reachability.
If any check fails, the `detail` field explains why.

### Obsidian not running

The CLI communicates with the running Obsidian desktop app via IPC.  If
Obsidian is not open, CLI-based commands fail with `ObsidianNotRunning`.

Graph tools (`neighborhood`, `vault-structure`, `backlinks`, `rebuild-index`,
`ghost`, `drift`, `trace`, `ideas`) read vault files directly and work
without Obsidian running, as long as the vault path can be resolved.

### Timeout

Commands time out after 30 seconds by default.  Override with:

```bash
export OBSIDIAN_TIMEOUT=60
```

### In-memory cache

Read-only CLI commands (`search`, `read`, `tasks`) can be cached in-memory.
The cache is disabled by default.

```bash
export OBSIDIAN_CACHE_TTL=30   # seconds
```

Mutations bypass the cache and invalidate all entries.

## File layout

```
obsidian-connector/
  scripts/install.sh               One-command installer
  main.py                          Thin wrapper (backward compat)
  config.json                      Project-level defaults
  pyproject.toml                   Package metadata (console scripts: obsx)
  TOOLS_CONTRACT.md                This file
  obsidian_connector/              Core Python package
    __init__.py                    Public API re-exports
    __main__.py                    Module entry point
    cli.py                         CLI entry point (65 subcommands)
    startup.py                     First-run marker + shared startup helpers
    mcp_server.py                  MCP server (62 tools for Claude Desktop)
    client.py                      Core CLI wrapper + batch reads
    client_fallback.py             Adapter: auto file_backend fallback when CLI unavailable
    file_backend.py                CLI-less vault access via direct file reads
    workflows.py                   Workflow OS: daily ops, loops, graduate, delegations, context
    thinking.py                    Thinking tools: ghost, drift, trace, ideas
    graph.py                       Graph indexing: links, tags, frontmatter, NoteIndex
    index_store.py                 SQLite-backed persistent index (incremental updates)
    write_manager.py               Atomic writes, snapshots, rollback, file locks
    watcher.py                     Filesystem watcher for incremental re-index
    draft_manager.py               Draft lifecycle: list, approve, reject, auto-archive
    vault_registry.py              Named vault registry with profiles and policies
    vault_factory.py               Vault discovery, creation, research topic seeding
    vault_presets.py               13 vault preset templates
    vault_guardian.py              Auto-generated file marking, unorganized note detection
    vault_init.py                  Vault initialization wizard
    idea_router.py                 Idea routing to project idea files
    retrieval.py                   Hybrid search: lexical + semantic + graph + recency
    embeddings.py                  Local embedding index (sentence-transformers, optional)
    template_engine.py             Template loading, variable substitution, inheritance
    scheduler.py                   Schedule config, workflow chaining, event triggers
    automation.py                  Event-triggered automation: tool registry, chain runner
    reports.py                     Report generation: weekly, monthly, vault health
    telemetry.py                   Local-only session telemetry (zero network calls)
    project_intelligence.py        Project health scores, changelogs, weekly packets
    project_sync.py                Project sync engine: git state, dashboard, TODO, sessions
    uninstall.py                   Safe two-mode uninstaller (CLI + MCP)
    audit.py                       Append-only audit log
    cache.py                       In-memory TTL cache
    config.py                      Layered config + vault path resolution
    doctor.py                      Health-check diagnostics (cross-platform)
    envelope.py                    Canonical JSON envelope builder
    errors.py                      Typed exception hierarchy
    platform.py                    Platform abstraction (OS detection, paths, scheduling)
    search.py                      Search result enrichment
  scripts/
    install.sh                     One-command installer
    smoke_test.py                  Core function smoke tests
    workflow_test.py               Workflow function smoke tests
    thinking_tools_test.py         Thinking tools smoke tests
    thinking_deep_test.py          Deep thinking module tests (56 assertions)
    graduate_test.py               Graduate pipeline tests
    delegation_test.py             Delegation detection tests
    perf_test.py                   Performance and batch read tests
    audit_test.py                  Audit log tests
    cache_test.py                  Cache module tests
    checkin_test.py                Check-in workflow tests
    escaping_test.py               Content escaping edge-case tests
    graph_test.py                  Graph module tests
    index_test.py                  Index store tests
    platform_test.py               Platform abstraction tests (OS, paths, scheduling, doctor)
    mcp_launch_smoke.sh            MCP server launch smoke test
  bin/
    obsx                           CLI wrapper (no venv activation needed)
    obsx-mcp                       MCP server wrapper
```

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py`
   (composed from existing functions).
2. Export from `__init__.py`.
3. Add an argparse subcommand in `cli.py` with both human and `--json`
   output paths (use the envelope functions).
3b. Add a `@mcp.tool()` function in `mcp_server.py` with `ToolAnnotations`.
4. If mutating, add `--dry-run` and call `log_action()` from `audit.py`.
5. Add a smoke test in `scripts/`.
6. Update this contract and `README.md`.
