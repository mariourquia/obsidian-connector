```
 ___  _         _    _ _               ___                       _
/ _ \| |__  ___(_) _| (_) __ _ _ __   / __\___  _ __  _ __   ___| |_ ___  _ __
| | | | '_ \/ __| |/ _` | |/ _` | '_ \ / /  / _ \| '_ \| '_ \ / _ \ __/ _ \| '__|
| |_| | |_) \__ \ | (_| | | (_| | | | / /__| (_) | | | | | | |  __/ || (_) | |
 \___/|_.__/|___/_|\__,_|_|\__,_|_| |_\____/\___/|_| |_|_| |_|\___|\__\___/|_|

                          v0.1.0 -- Second Brain Assistant
                    Turn Claude into your second brain.
```

## Highlights

- **Your second brain, not a tool.** Morning briefings, evening reflections,
  idea capture, weekly reviews -- all driven by your Obsidian vault.
- **Works everywhere.** Claude Desktop (MCP tools + system prompt), Claude
  Code (skills + hooks), headless scheduling (launchd).
- **100% local.** Your vault never leaves your machine. No network calls,
  no cloud sync, no telemetry.
- **28 MCP tools, 27 CLI commands, 4 skills.** From full-text search to
  drift analysis, graph intelligence to idea graduation.

## What's New

### Core

| Feature | Description | Environment |
|---------|-------------|-------------|
| `obsidian_check_in` | Time-aware situational awareness -- what should you do right now? | CLI + Desktop |
| `obsidian_today` | Today's daily note, tasks, and context at a glance | CLI + Desktop |
| `obsidian_close_day` | End-of-day reflection prompts | CLI + Desktop |
| `obsidian_open_loops` | Surface unfinished threads from recent notes | CLI + Desktop |
| `obsidian_my_world` | Full vault snapshot for deep context | CLI + Desktop |

### Research & Discovery

| Feature | Description | Environment |
|---------|-------------|-------------|
| `obsidian_find_prior_work` | Search + rank top matching notes for a topic | CLI + Desktop |
| `obsidian_challenge_belief` | Test a belief against vault evidence | CLI + Desktop |
| `obsidian_emerge_ideas` | Cluster notes into idea groups | CLI + Desktop |
| `obsidian_connect_domains` | Find connections between two knowledge domains | CLI + Desktop |

### Graph Intelligence

| Feature | Description | Environment |
|---------|-------------|-------------|
| `obsidian_neighborhood` | Explore link neighborhood of any note | CLI + Desktop |
| `obsidian_vault_structure` | Topology overview: orphans, dead ends, tag cloud | CLI + Desktop |
| `obsidian_backlinks` | All notes linking to a given note | CLI + Desktop |
| `obsidian_ideas` | Surface latent ideas from graph structure | CLI + Desktop |

### Thinking Tools

| Feature | Description | Environment |
|---------|-------------|-------------|
| `obsidian_ghost` | Analyze your writing voice patterns | CLI + Desktop |
| `obsidian_drift` | Detect intention vs behavior drift | CLI + Desktop |
| `obsidian_trace` | Trace how an idea evolved over time | CLI + Desktop |

### Skills (Claude Code)

| Skill | What it does |
|-------|-------------|
| `/morning` | Run morning briefing, surface loops and delegations, write to vault |
| `/evening` | Close your day, review progress, offer idea graduation |
| `/idea` | Two-second idea capture to daily note |
| `/weekly` | Drift check, idea graduation, vault health audit |

### Orchestration

| Feature | Description |
|---------|-------------|
| SessionStart hook | Greets you with context at every Claude Code session start |
| Scheduled automation | macOS launchd runs morning briefing at 08:00 (configurable) |
| Desktop system prompt | Teaches Claude Desktop to drive all four workflows |
| One-click installer | `./scripts/install.sh` with opt-in skills, hooks, scheduling |

## Installation

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh
```

```
+---------------------------------------------------+
|                  Install Flow                     |
+---------------------------------------------------+
|                                                   |
|  [1/4] Check Python 3.11+                        |
|  [2/4] Create venv + pip install                  |
|  [3/4] Configure Claude Desktop MCP              |
|  [4/4] Verify package import                     |
|                                                   |
|  Optional:                                        |
|  [y/N] Install Claude Code skills                 |
|  [y/N] Install SessionStart hook                  |
|  [y/N] Install scheduled automation               |
|                                                   |
+---------------------------------------------------+
```

See the [Setup Guide](docs/setup-guide.md) for detailed instructions
for Desktop-only, CLI-only, or combined setups.

## Requirements

```
+---------------------+---------+
| Requirement         | Version |
+---------------------+---------+
| Python              | 3.11+   |
| Obsidian            | 1.12+   |
| Obsidian CLI        | enabled |
| macOS               | 13+     |
| Claude Desktop      | latest  |
| Claude Code (opt.)  | latest  |
+---------------------+---------+
```

## Security

### Review Summary

```
+-------------------------------+--------+
| Area                          | Status |
+-------------------------------+--------+
| Input validation (CLI/MCP)    | PASS   |
| Shell execution (subprocess)  | PASS   |
| File system (path traversal)  | PASS   |
| SQLite (injection)            | PASS   |
| Audit log (log injection)     | PASS   |
| Notification (osascript)      | PASS   |
| Secrets / credentials         | PASS   |
| Dependencies                  | PASS   |
+-------------------------------+--------+
```

**Details:**

- **Subprocess calls** use list-based args (no `shell=True`). User input
  is never interpolated into shell strings.
- **SQLite queries** use parameterized placeholders (`?`) exclusively.
  No dynamic SQL construction.
- **File system access** is bounded to the resolved vault directory.
  `os.walk` starts from the vault root; no user-controlled path joins
  escape the vault.
- **Audit log** uses `json.dumps()` for serialization -- no raw string
  concatenation that could corrupt JSONL.
- **osascript notifications** escape `\` and `"` before interpolation
  into AppleScript literals.
- **No secrets** are stored, transmitted, or hardcoded. No API keys,
  no tokens, no credentials.
- **No network calls.** Everything runs locally via Obsidian's IPC
  protocol and direct file reads.

### Permissions Model

```
+-------------------+-------------------------------------------+
| Permission        | Scope                                     |
+-------------------+-------------------------------------------+
| Read              | Vault .md files, Obsidian IPC, config     |
| Write             | Daily note (append), Agent Drafts folder  |
|                   | Audit log (~/.obsidian-connector/logs/)   |
|                   | SQLite index (~/.obsidian-connector/)     |
| Execute           | Obsidian CLI binary, osascript (notif.)   |
| Network           | None                                      |
| Credentials       | None stored or transmitted                |
+-------------------+-------------------------------------------+
```

### Guardrails

- **Audit log**: Every mutating command writes an append-only JSONL record
  with timestamp, command, args, vault, and content hash. Nothing is deleted.
- **Dry-run mode**: All mutating commands (`log-daily`, `log-decision`,
  `create-research-note`, `graduate execute`) support `--dry-run` in CLI.
- **Agent draft provenance**: Notes created by agents go to
  `Inbox/Agent Drafts/` with `source: agent`, `status: draft` frontmatter.
  Human review is required before promotion.
- **Read-only defaults**: 23 of 28 MCP tools are read-only. Mutating tools
  are clearly annotated with `destructiveHint` in their `ToolAnnotations`.
- **Timeout protection**: All subprocess calls have a 30-second default
  timeout (configurable via `OBSIDIAN_TIMEOUT`).
- **No auto-commit**: The installer and scheduled automation never commit
  to git or push to remotes.

## Known Limitations

```
+------------------------------------+-----------------------------------+-----------------------------+
| Limitation                         | Impact                            | Workaround                  |
+------------------------------------+-----------------------------------+-----------------------------+
| macOS only                         | Linux/Windows not supported        | CLI may work on Linux;      |
|                                    |                                   | scheduling won't            |
+------------------------------------+-----------------------------------+-----------------------------+
| Obsidian must be running           | CLI commands that use IPC fail    | Graph tools (neighborhood,  |
|                                    | when Obsidian is closed           | vault-structure, etc.) work |
|                                    |                                   | without Obsidian running    |
+------------------------------------+-----------------------------------+-----------------------------+
| Obsidian CLI required              | CLI plugin must be enabled in     | Enable in Obsidian Settings |
|                                    | Obsidian settings                 | > Community Plugins         |
+------------------------------------+-----------------------------------+-----------------------------+
| Daily note format assumed          | Expects YYYY-MM-DD.md in daily/   | Configure daily note path   |
|                                    | or root                           | in config.json              |
+------------------------------------+-----------------------------------+-----------------------------+
| No real-time sync                  | Index may lag behind live edits   | Run `obsx rebuild-index`    |
|                                    |                                   | to force refresh            |
+------------------------------------+-----------------------------------+-----------------------------+
| Newline encoding ambiguity         | Literal \n in content vs actual   | Known CLI limitation;       |
|                                    | newlines are indistinguishable    | avoid literal \n in text    |
+------------------------------------+-----------------------------------+-----------------------------+
| pyyaml optional                    | Schedule config falls back to     | pip install pyyaml for      |
|                                    | defaults if pyyaml not installed  | custom scheduling config    |
+------------------------------------+-----------------------------------+-----------------------------+
| Single vault                       | Multi-vault workflows require     | Pass --vault flag or set    |
|                                    | explicit vault targeting          | OBSIDIAN_VAULT env var      |
+------------------------------------+-----------------------------------+-----------------------------+
```

## Risks

- **Vault data integrity**: Mutating commands (`log-daily`, `graduate execute`)
  append to vault files. If Obsidian is syncing (iCloud, Obsidian Sync) during
  a write, conflicts are possible. **Mitigation**: Writes are atomic appends,
  not full file rewrites. Audit log provides recovery trail.

- **Index staleness**: The SQLite index reflects vault state at last scan.
  If many files change between scans, graph queries may return stale data.
  **Mitigation**: `rebuild-index` forces a full rescan. Incremental updates
  detect mtime changes.

- **Scheduled automation**: launchd jobs run even when you're not at your
  computer. Morning briefings append to the daily note regardless.
  **Mitigation**: Opt-in only. `launchctl unload` to disable.

- **Agent draft accumulation**: If the graduation workflow runs frequently
  without human review, `Inbox/Agent Drafts/` may accumulate many drafts.
  **Mitigation**: `check_in` counts unreviewed drafts and surfaces them.

## Testing

```
+-------------------------------+-------------+--------+
| Test Suite                    | Assertions  | Status |
+-------------------------------+-------------+--------+
| scripts/smoke_test.py         | 8           | PASS   |
| scripts/checkin_test.py       | 19          | PASS   |
| scripts/mcp_launch_smoke.sh   | 3           | PASS   |
| scripts/workflow_test.py      | varies      | PASS   |
| scripts/thinking_deep_test.py | 56          | PASS   |
| scripts/graph_test.py         | varies      | PASS   |
| scripts/index_test.py         | varies      | PASS   |
| scripts/graduate_test.py      | varies      | PASS   |
| scripts/delegation_test.py    | varies      | PASS   |
| scripts/audit_test.py         | varies      | PASS   |
| scripts/cache_test.py         | varies      | PASS   |
| scripts/escaping_test.py      | varies      | PASS   |
| make docs-lint                | 0 errors    | PASS   |
+-------------------------------+-------------+--------+
```

## Compatibility

```
+-------------------+-----------+-----------------------------------+
| Environment       | Status    | Notes                             |
+-------------------+-----------+-----------------------------------+
| macOS 13+         | Supported | Primary platform                  |
| macOS 14+         | Supported | Tested                            |
| macOS 15          | Supported | Tested (development machine)      |
| Linux             | Untested  | CLI/graph tools may work;         |
|                   |           | scheduling and notifications won't|
| Windows           | Unsupported| Obsidian CLI not available        |
+-------------------+-----------+-----------------------------------+
```

## Full Changelog

First public release.

---

```
+----------------------------------------------------------+
|                                                          |
|  Built with care in New York.                            |
|  100% local. Your vault never leaves your machine.       |
|                                                          |
|  github.com/mariourquia/obsidian-connector               |
|                                                          |
+----------------------------------------------------------+
```
