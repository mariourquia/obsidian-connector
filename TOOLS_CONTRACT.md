# Tools Contract -- obsidian-connector

This document tells Claude Code (and other AI coding agents) how to interact
with Obsidian through this project.  Read this file before touching the vault.

## Golden rule

**Never call the `obsidian` CLI directly.**  Use the MCP tools, Python API,
or CLI wrapper instead.  They handle vault resolution, argument escaping,
error detection, audit logging, and output parsing.

## MCP tools (Claude Desktop / AI agents)

When running as an MCP server (via `claude_desktop_config.json` or `--http`),
these tools are available to Claude and other MCP clients:

| MCP Tool | Parameters | Returns |
|---|---|---|
| `obsidian_search` | `query`, `vault?` | JSON array of `{file, matches[{line, text}]}` |
| `obsidian_read` | `name_or_path`, `vault?` | Raw markdown content of the note |
| `obsidian_tasks` | `status?`, `path_prefix?`, `limit?`, `vault?` | JSON array of `{text, status, file, line}` |
| `obsidian_log_daily` | `content`, `vault?` | Confirmation string |
| `obsidian_log_decision` | `project`, `summary`, `details`, `vault?` | Confirmation string |
| `obsidian_find_prior_work` | `topic`, `top_n?`, `vault?` | JSON array of `{file, heading, excerpt, match_count}` |
| `obsidian_create_note` | `title`, `template`, `vault?` | Created file path |
| `obsidian_challenge_belief` | `belief`, `vault?`, `max_evidence?` | JSON `{belief, counter_evidence[], supporting_evidence[], verdict}` |
| `obsidian_emerge_ideas` | `topic`, `vault?`, `max_clusters?` | JSON `{topic, total_notes, clusters[]}` |
| `obsidian_connect_domains` | `domain_a`, `domain_b`, `vault?`, `max_connections?` | JSON `{domain_a, domain_b, connections[], domain_a_only[], domain_b_only[]}` |
| `obsidian_doctor` | `vault?` | JSON array of health check results |

All `vault` parameters are optional.  When omitted, the configured default
vault is used (env var `OBSIDIAN_VAULT` or `config.json`).

**Recommended pattern:** Use the MCP tools for all vault interaction.  Do not
shell out to `obsidian` or `python main.py` from within an MCP-connected session.

## CLI wrapper

The tool is installable as `obsx` via `pip install -e .`, or use `./bin/obsx`
from the repo root (no venv activation required).

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

## Commands

### log-daily

Append text to today's daily note.

```bash
python main.py log-daily "Reviewed PR #42 -- approved with minor nits"
python main.py --vault "Work" log-daily "Standup: blocked on API key rotation"
python main.py --json log-daily "test entry"
python main.py log-daily "preview only" --dry-run
```

### search

Full-text search across the vault.  Returns file paths and matching lines.

```bash
python main.py search "deal pipeline"
python main.py --json search "CMBS spreads"
python main.py search "vol surface" --max-results 5 --context-lines 2
python main.py search "duplicates" --dedupe
```

### read

Read a note by wikilink-style name or vault-relative path.

```bash
python main.py read "Project Alpha"
python main.py --json read "Cards/Project Alpha.md"
```

### tasks

List tasks, optionally filtered by status, path prefix, or limit.

```bash
python main.py tasks --status todo
python main.py --json tasks --status done --limit 20
python main.py tasks --path-prefix "Cards/AMOS" --status todo
```

### log-decision

Append a structured decision record (heading, timestamp, summary, details)
to today's daily note.

```bash
python main.py log-decision \
  --project "AMOS" \
  --summary "Moved ingestion to event-driven" \
  --details "Reduces deal-update latency from 2s to 200ms."
python main.py log-decision --project "test" --summary "s" --details "d" --dry-run
```

### create-research-note

Create a new note from a named template and open it in Obsidian.

```bash
python main.py create-research-note \
  --title "CMBS Spread Analysis Q3" \
  --template "Template, Note"
python main.py create-research-note --title "Test" --template "Template, Note" --dry-run
```

### find-prior-work

Search for existing notes on a topic, read the top N hits, and return
structured summaries (heading + first paragraph).

```bash
python main.py find-prior-work "machine learning" --top-n 5
python main.py --json find-prior-work "underwriting" --top-n 3
```

### challenge

Challenge a belief by searching the vault for counter-evidence and
supporting evidence.  Read-only.

```bash
python main.py challenge "note-taking improves memory"
python main.py --json challenge "all tech stocks outperform" --max-evidence 5
```

### emerge

Cluster related notes into idea groups around a topic.  Groups by folder
path and returns summaries.  Read-only.

```bash
python main.py emerge "project"
python main.py --json emerge "finance" --max-clusters 3
```

### connect

Find connections between two domains by searching for notes that mention
both.  Read-only.

```bash
python main.py connect "health" "productivity"
python main.py --json connect "real estate" "machine learning" --max-connections 5
```

### doctor

Run health checks on Obsidian CLI connectivity, vault resolution, and
reachability.  Use this first when debugging failures.

```bash
python main.py doctor
python main.py --json doctor
```

## Output modes

| Flag | Behavior |
|------|----------|
| *(default)* | Human-readable, suitable for terminal display |
| `--json` | Canonical JSON envelope to stdout (works on ALL commands) |

The `--json` flag is global (placed before the subcommand).  Per-subcommand
`--json` aliases also work for backward compatibility on `search`, `tasks`,
and `find-prior-work`.

When piping output to another tool or parsing programmatically, always use
`--json`.  The envelope's `ok` field tells you success/failure without
parsing the message.

## Safety features

### Dry-run mode

Mutating commands (`log-daily`, `log-decision`, `create-research-note`)
support `--dry-run`.  In dry-run mode:

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

This enables auditing what was written to the vault and when, even across
sessions.

## Vault targeting

Resolution order (highest priority wins):

1. `--vault <name>` flag on the command
2. `OBSIDIAN_VAULT` environment variable
3. `default_vault` in `config.json`
4. Omitted (Obsidian uses whichever vault is active)

## Failure modes and recovery

### Step 1: run doctor

```bash
python main.py --json doctor
```

This checks binary presence, version, vault resolution, and reachability.
If any check fails, the `detail` field explains why.

### Command errors (non-zero exit or CLI soft error)

With `--json`, errors are returned as structured envelopes with
`error.type`, `error.message`, `error.stderr`, and `error.exit_code`.

Without `--json`, errors print to stderr.

### Wrong vault

If commands return unexpected results or "file not found":

1. Run `python main.py doctor` to check vault resolution.
2. Set the vault explicitly: `python main.py --vault "Exact Vault Name" search "test"`
3. Or export: `export OBSIDIAN_VAULT="Exact Vault Name"`

### Obsidian not running

The CLI communicates with the running Obsidian desktop app via IPC.  If
Obsidian is not open, all commands will fail with `ObsidianNotRunning`.

### Timeout

Commands time out after 30 seconds by default.  Override with:

```bash
export OBSIDIAN_TIMEOUT=60
```

### Content escaping limitation

The Obsidian CLI interprets `\n` as newline and `\t` as tab in content
values.  There is no escape sequence for a literal backslash followed by
`n` or `t`.  Content containing literal `\n` or `\t` sequences will have
those interpreted as whitespace characters.

### In-memory cache

Read-only commands (`search`, `read`, `tasks`) can be cached in-memory to
avoid redundant subprocess calls.  The cache is **disabled by default**.

Enable via environment variable:

```bash
export OBSIDIAN_CACHE_TTL=30   # seconds
```

Or in `config.json`:

```json
{ "cache_ttl": 30 }
```

Mutations (`log-daily`, `create-research-note`) bypass the cache and
invalidate all entries.  The cache is per-process and not persisted to disk.

### Search returns 0 results unexpectedly

The Obsidian CLI `search` indexes **note content only**, not file or folder
names.  If a term only appears in a path (e.g. `Cards/CMBS/`), search will
not find it.  Use `run_obsidian(["files", "folder=Cards/CMBS"])` for
path-based lookups.

## File layout

```
obsidian-connector/
  main.py                          Thin wrapper (backward compat for python main.py)
  config.json                      Project-level defaults
  pyproject.toml                   Package metadata (console scripts: obsx)
  TOOLS_CONTRACT.md                This file
  obsidian_connector/
    __init__.py                    Public API re-exports
    cli.py                         CLI entry point (obsx / obsidian-connector)
    mcp_server.py                  MCP server (16 tools for Claude Desktop)
    audit.py                       Append-only audit log
    cache.py                       In-memory TTL cache
    client.py                      Core CLI wrapper + 4 functions
    config.py                      Layered config loading
    doctor.py                      Health-check diagnostics
    envelope.py                    Canonical JSON envelope builder
    errors.py                      Typed exception hierarchy
    search.py                      Search result enrichment
    workflows.py                   Higher-level workflows + thinking tools
  scripts/
    smoke_test.py                  Core function smoke tests
    workflow_test.py               Workflow function smoke tests
    thinking_tools_test.py         Thinking tools smoke tests
    audit_test.py                  Audit log tests
    cache_test.py                  Cache module and integration tests
    escaping_test.py               Content escaping edge-case tests
    mcp_launch_smoke.sh            MCP server launch smoke test
  bin/
    obsx                           CLI wrapper (no venv activation needed)
    obsx-mcp                       MCP server wrapper (used by Desktop config)
```

## Adding new commands

1. Add the Obsidian CLI call in `client.py` (low-level) or `workflows.py`
   (composed from existing functions).
2. Export from `__init__.py`.
3. Add an argparse subcommand in `cli.py` with both human and `--json`
   output paths (use the envelope functions).
3b. Add a `@mcp.tool()` function in `mcp_server.py`.
4. If mutating, add `--dry-run` and call `log_action()` from `audit.py`.
5. Add a smoke test in `scripts/`.
6. Update this contract and `README.md`.
