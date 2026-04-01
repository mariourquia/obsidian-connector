---
title: "Release Notes -- obsidian-connector v0.3.0"
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

                    v0.3.0 -- Project Sync, Running TODO, Vault Init
```

## Highlights

This release adds **project sync**, **structured session logging**, a **running TODO
list**, and a **vault initialization wizard** to the obsidian-connector plugin.

- **35 MCP tools** (was 29). **35 CLI commands** (was 29). **9 skills** (was 7).
- Two new Python modules: `project_sync.py` and `vault_init.py` (810 LOC combined).
- Multi-agent security review (5 parallel agents) with all blocking findings resolved.
- Cross-platform Python implementation replaces the standalone bash sync script.

## What's New

### Project Sync (`obsidian_sync_projects`)

Syncs all tracked git repositories into the Obsidian vault. Generates:
- Per-project Markdown files with branch, commits, modified files, activity labels
- `Dashboard.md` with project table and quick links
- `Active Threads` for repos with uncommitted work or feature branches
- `Running TODO.md` aggregating all open `- [ ]` items across the vault

```bash
obsx sync-projects              # sync all repos
obsx project-status site        # single project status
obsx active-threads             # repos with active work
obsx running-todo               # open TODO items
```

### Structured Session Logging (`obsidian_log_session`)

Session logs write YAML frontmatter with project tags, work type classification,
and file counts -- enabling time-series analysis via Obsidian Bases.

```yaml
---
title: "Session Log - 2026-03-23"
date: 2026-03-23
tags: [session, feature-dev, integration]
projects_touched:
  - name: obsidian-connector
    work_type: [feature-dev, integration]
    files_changed: 8
total_files_changed: 8
---
```

Work types: `feature-dev`, `bugfix`, `refactor`, `research`, `ops`, `docs`,
`testing`, `review`, `planning`, `setup`.

### Vault Initialization (`obsx init`)

Interactive wizard for new users:

```
$ obsx init

  Obsidian Connector -- Vault Setup Wizard
  ==========================================

  Vault path [~/...creation/creation]:
  GitHub projects root [~/Documents/GitHub]:

  Found 16 git repos in ~/Documents/GitHub
  Track all discovered repos? [Y/n]:

  Creating vault at: ~/...creation/creation
  Tracking 16 repos from: ~/Documents/GitHub

  Vault initialized. 8 files created.
  Next: run obsx sync-projects to populate project data.
```

Creates: `projects/`, `sessions/`, `context/`, `groups/`, `daily/`, `Inbox/`,
`Dashboard.md`, `Running TODO.md`, `sync_config.json`, group MOC files.

### Running TODO (`obsidian_running_todo`)

Canonical open-item list. Scans daily notes and project folders for `- [ ]` items,
groups by source, tracks completions with timestamps.

```
$ obsx running-todo
Open items: 12
Completed: 3

  daily/2026-03-23.md:
    - [ ] Review PR #20
    - [ ] Update vault sync schedule
  projects/site.md:
    - [ ] Fix greeksurface tabindex
```

### New Skills

| Skill | Purpose |
|-------|---------|
| `/sync-vault` | End-of-session sync with conversation-aware session logging |
| `/init-vault` | Guided vault creation for new users |

## New MCP Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `obsidian_sync_projects` | `vault?`, `github_root?`, `update_todo?` | Sync summary (count, active threads, timestamp) |
| `obsidian_project_status` | `project`, `vault?`, `github_root?` | Branch, commits, uncommitted, activity |
| `obsidian_active_threads` | `vault?`, `github_root?` | Projects with active work |
| `obsidian_log_session` | `projects`, `work_types?`, `completed?`, `next_steps?`, `decisions?`, `session_context?` | Session file path |
| `obsidian_running_todo` | `vault?` | Open/completed counts, items by source |
| `obsidian_init_vault` | `vault_path`, `github_root?`, `use_defaults?` | Created paths, repo count |

## Security

- **Path traversal protection**: `vault_subdir` resolved and contained within vault root. `dir_name` validated against `/`, `..`, null bytes.
- **Glob caps**: TODO scanning limited to 100 files per non-daily folder.
- **No I/O in renderers**: All git state captured upfront in `_extract_repo_state`. Render functions are pure formatters.
- **Multi-agent review**: 5 parallel review agents (security, architecture, testing, tech debt, feature/UX) examined all new code. All BLOCKING and MEDIUM findings resolved before merge.

## Testing

- **56 new assertions** in `scripts/project_sync_test.py`
- Covers: imports, data classes, 5 render functions, vault init scaffold, repo discovery, live git operations
- **0 regressions**: existing 8 smoke tests + import cycle test pass
- **CI**: 17 test files across 9 matrix combinations (3 OS x 3 Python versions)
- **Known gap**: `sync_projects()` and `log_session()` I/O paths not unit tested (tracked for follow-up)

## Compatibility

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Obsidian | 1.12+ (with CLI enabled) |
| OS | macOS, Linux, Windows |
| MCP | 1.0.x |
| Claude Code | Any version with plugin support |
| Claude Desktop | Any version with MCP server support |

## Breaking Changes

None. This release is purely additive.

## Known Limitations

- Session logs use separate files per session (no same-day merge). Intentional for frontmatter integrity.
- TODO scanning covers `daily/`, `Inbox/`, `projects/` folders only. Notes in other locations are not scanned.
- `discover_repos()` assigns all repos to the "standalone" group. Group assignments require `sync_config.json` or `--use-defaults`.
- No `--dry-run` on `sync-projects` yet (tracked in roadmap).
- No CLI commands for adding/removing repos from registry or viewing past sessions (tracked).

## Upgrade

```bash
git pull origin main
# or re-clone:
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector && pip install -e .
```

For DMG users: download `obsidian-connector-v0.3.0.dmg` from Releases.
The smart installer preserves your existing config and venv.

## Verification

```bash
# Verify version
python3 -c "import obsidian_connector; print(obsidian_connector.__version__)"
# Expected: 0.3.0

# Verify tools
python3 -c "from obsidian_connector.mcp_server import mcp; print(len(mcp._tool_manager.list_tools()), 'tools')"
# Expected: 35 tools

# Run tests
python3 scripts/project_sync_test.py  # 56 assertions
python3 scripts/smoke_test.py         # 8 core tests

# Check release assets (after download)
sha256sum -c obsidian-connector-v0.3.0.sha256
cosign verify-blob --signature obsidian-connector-v0.3.0.tar.gz.sig \
  --certificate obsidian-connector-v0.3.0.tar.gz.cert \
  obsidian-connector-v0.3.0.tar.gz
```

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for all changes since v0.2.1.

**[v0.2.1...v0.3.0](https://github.com/mariourquia/obsidian-connector/compare/v0.2.1...v0.3.0)**
