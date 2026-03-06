# Tools Contract -- obsidian-connector

This document tells Claude Code (and other AI coding agents) how to interact
with Obsidian through this project.  Read this file before touching the vault.

## Golden rule

**Never call the `obsidian` CLI directly.**  Use the MCP tools, Python API,
or CLI wrapper instead.  They handle vault resolution, argument escaping,
error detection, audit logging, and output parsing.

## MCP tools (Claude Desktop / AI agents)

When running as an MCP server (via `claude_desktop_config.json` or `--http`),
28 tools are available to Claude and other MCP clients.  All `vault`
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

**Recommended pattern:** Use the MCP tools for all vault interaction.  Do not
shell out to `obsidian` or `python main.py` from within an MCP-connected session.

## CLI wrapper

The CLI is available as `./bin/obsx` (no venv needed), `obsx` or
`obsidian-connector` (after `pip install -e .`), or `python3 main.py`.

### Commands (27 total)

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

## Canonical JSON envelope

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

## Vault targeting

Resolution order (highest priority wins):

1. `--vault <name>` flag on the command
2. `OBSIDIAN_VAULT_PATH` environment variable (directory path)
3. `OBSIDIAN_VAULT` environment variable (vault name)
4. `vault_path` in `config.json`
5. `default_vault` in `config.json`
6. Auto-detected from `~/Library/Application Support/obsidian/obsidian.json`

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
  obsidian_connector/
    __init__.py                    Public API re-exports (45 symbols)
    cli.py                         CLI entry point (27 subcommands)
    mcp_server.py                  MCP server (28 tools for Claude Desktop)
    workflows.py                   Workflow OS: daily ops, loops, graduate, delegations, context
    thinking.py                    Thinking tools: ghost, drift, trace, ideas
    graph.py                       Graph indexing: links, tags, frontmatter, NoteIndex
    index_store.py                 SQLite-backed persistent index (incremental updates)
    audit.py                       Append-only audit log
    cache.py                       In-memory TTL cache
    client.py                      Core CLI wrapper + batch reads
    config.py                      Layered config + vault path resolution
    doctor.py                      Health-check diagnostics
    envelope.py                    Canonical JSON envelope builder
    errors.py                      Typed exception hierarchy
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
