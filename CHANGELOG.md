# Changelog

All notable changes to obsidian-connector are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-23

### Added
- **Project sync engine** (`project_sync.py`, 530 LOC): Syncs git repository state into the vault. Generates per-project Markdown files, Dashboard, Active Threads, and Running TODO. Replaces the standalone `sync-creation-vault` bash script with cross-platform Python.
- **Vault initialization wizard** (`vault_init.py`, 280 LOC): Interactive `obsx init` command walks users through vault creation, repo discovery, and scaffold setup. Also available as `obsidian_init_vault` MCP tool.
- **Structured session logging**: `obsidian_log_session` writes YAML frontmatter with `projects_touched`, `work_type` tags, and `files_changed` counts per project. Queryable via Obsidian Bases for time-series analysis.
- **Running TODO**: `Running TODO.md` aggregates all open `- [ ]` items across the vault with source attribution. Completed items tracked with timestamps. Updated on each sync.
- **6 new MCP tools** (35 total): `obsidian_sync_projects`, `obsidian_project_status`, `obsidian_active_threads`, `obsidian_log_session`, `obsidian_running_todo`, `obsidian_init_vault`.
- **6 new CLI commands** (35 total): `sync-projects`, `project-status`, `active-threads`, `log-session`, `running-todo`, `init`.
- **2 new skills** (9 total): `/sync-vault` (end-of-session sync with session logging), `/init-vault` (guided vault creation).
- **Auto-discovery**: `discover_repos()` finds all git repos in a directory. Fallback when no `sync_config.json` exists.
- **56 new test assertions** in `scripts/project_sync_test.py` covering data classes, rendering, vault init, repo discovery, and live git operations.

### Fixed
- **Path traversal**: Containment checks for `vault_subdir` and `dir_name` from `sync_config.json`.
- **Session log integrity**: Each session writes a separate file (prevents frontmatter corruption on same-day multi-session writes).
- **Render I/O**: Removed git subprocess calls from `_render_project_file` and `_render_active_threads`. All git state is now captured in `_extract_repo_state` and stored on `RepoState`.
- **TODO detection**: `_DONE_RE` now accepts uppercase `[X]` for Obsidian compatibility.
- **mcpb.json version**: Updated from 0.2.0 to 0.3.0 (was out of sync since v0.2.1).

### Changed
- Shared symbols made public: `GROUP_DISPLAY`, `group_display()`, `default_repos()`, `SYNC_CONFIG_FILENAME`. Eliminates cross-module use of `_`-prefixed names.
- `RepoEntry` exported from `__init__.py` (part of public API for `init_vault(repos=[...])`).
- Completed execution plan archived to `docs/exec-plans/completed/`.
- 5 completed plan docs archived to `docs/plans/archived/`.
- Finder-created duplicate files removed.

### Security
- Path containment: `vault_subdir` resolved and verified to stay within vault root.
- Directory name validation: `dir_name` values with `/`, `..`, or null bytes rejected during config parsing.
- Glob caps: `_scan_vault_todos` limited to 100 files per non-daily folder.
- Multi-agent security review: 5 parallel agents (security, architecture, testing, tech debt, feature/UX) reviewed all new code. All blocking findings resolved.

## [0.2.1] - 2026-03-17

### Added
- **Smart DMG upgrades**: Auto-Installer detects installed version vs DMG version, shows "Upgrade v0.2.0 -> v0.2.1" dialog, preserves `.venv` and `.claude/` config during upgrade (rsync with excludes instead of rm+cp).
- **Claude Code plugin structure**: Full plugin-compliant directory layout for official marketplace submission. Skills restructured to `skills/<name>/SKILL.md` format, `hooks/hooks.json` for plugin hook registration, updated `.mcp.json` with `cwd` and `PYTHONPATH`.
- **Plugin setup script**: `scripts/setup.sh` for post-install Python venv bootstrap when installed via `claude plugin install`.
- **Plugin mode in installer**: Both `install.sh` and `install-linux.sh` detect plugin structure and offer plugin mode instead of manual skill/hook setup.

### Fixed
- Duplicate SessionStart hook in `.claude/settings.json` (removed absolute-path duplicate).
- Installer skill glob updated to support both flat (`skills/*.md`) and nested (`skills/*/SKILL.md`) layouts.

### Changed
- Skills moved from `skills/morning.md` to `skills/morning/SKILL.md` (plugin directory convention).
- Duplicate skill files removed from `.claude/commands/` (plugin namespace handles routing).
- `hooks/session_start.sh` comment updated to reflect dual-mode operation (plugin + standalone).

## [0.2.0] - 2026-03-16

### Added
- **Cross-platform support**: New `platform.py` module with `PlatformPaths` dataclass resolving Obsidian, Claude Desktop, and scheduling paths for macOS, Linux, and Windows. Includes scheduling abstraction (`install_schedule`, `uninstall_schedule`), notification dispatch, and Obsidian binary candidates per OS.
- **MCP tool contract tests**: Verifies tool count, error envelope format, typed error mapping, and narrowed exception behavior.
- **CLI argument parsing tests**: `--help` on all subcommands, `--json` flag acceptance, unknown command rejection.
- **Audit log permission tests**: Validates 0o700 directory mode for both new and pre-existing audit log directories.
- **Import cycle regression tests**: Ensures `errors.py` and `client.py` import cleanly with no circular dependency.
- **Platform detection tests**: Covers macOS, Linux, and Windows path resolution, scheduling config, and binary candidates.
- Ubuntu added to CI test matrix (15 test files, up from 8).

### Fixed
- **Version sync**: All version sources (`pyproject.toml`, `__init__.py`, `plugin.json`) now read `0.2.0`.
- **Audit log security**: Directory created with `0o700` (owner-only). Explicit `chmod` hardens pre-existing directories on upgrade.
- **Circular dependency**: `ObsidianCLIError` moved to `errors.py` as canonical location. `client.py` no longer defines exceptions or uses late imports.
- **Error handling**: Uninstall MCP tool and 7 graph/thinking tools tightened from `except Exception` to specific types (`OSError`, `ValueError`, `KeyError`, `TypeError`, `json.JSONDecodeError`). Unexpected exceptions now propagate instead of being silently swallowed.
- **README accuracy**: MCP tool count (29) and CLI command count (29) corrected. Uninstall tool and command documented. Requirements updated for cross-platform.
- **Installer**: `scripts/install.sh` now resolves Claude Desktop config path per OS instead of hardcoding macOS path.

### Changed
- `_load_or_build_index()` deduplicated: removed from `mcp_server.py`, `thinking.py`, `workflows.py`; all use `index_store.load_or_build_index` directly.
- `config.py` and `uninstall.py` use `platform.py` for path resolution instead of hardcoded macOS paths.
- CI matrix expanded from macOS-only to macOS + Ubuntu, 8 to 15 test files.

### Documentation
- Tech debt tracker populated with deferred v0.2.0 review findings.
- ROADMAP updated with completed items.
- README cross-platform manual setup paths.

## [0.1.3] - 2026-03-16

### Added

- **Uninstaller** (`obsx uninstall`): Two-mode safe uninstaller that cleanly removes core installation artifacts created by the installer (CLI entrypoint, launchd plist, and Claude Desktop MCP config). Interactive CLI mode with per-artifact confirmation, and non-interactive `--force` mode for MCP/scripted contexts. Includes `--dry-run` preview, timestamped config backups, JSON validation after config edits, and idempotent operation.
- **Uninstall MCP tool**: `uninstall` tool with `ToolAnnotations` (`destructiveHint=true`) for Claude Desktop. Defaults to dry-run for safety; explicit flags required for each supported artifact type.
- **Comprehensive test suite**: 52 tests covering unit (Tasks 1-6), integration (Task 9), and edge cases (Task 11) for the uninstaller module.

### Security

- Config file backups created before any modification (`claude_desktop_config.json.backup-TIMESTAMP`)
- JSON validation after config edits prevents writing corrupted config
- Launchd plist properly unloaded before removal
- Interactive CLI uninstall actions logged to audit trail

## [0.1.2] - 2026-03-06

### Fixed

- **Claude Desktop subprocess isolation**: Added `PYTHONPATH` and `cwd` to MCP server configuration. The installer and manual setup now correctly pass environment variables so Python finds the editable package install. Resolves "ModuleNotFoundError: No module named 'obsidian_connector'" when running in Claude Desktop.
- **Setup documentation**: Added troubleshooting section for PYTHONPATH configuration issues and clarified that Obsidian must be running for CLI-based tools.

## [0.1.1] - 2026-03-06

### Added

- **GitHub Actions CI**: Lint, test (Python 3.11-3.13), and MCP launch smoke on every PR
- **CONTRIBUTING.md**: Development workflow, testing guide, tool addition checklist
- **SECURITY.md**: Vulnerability reporting policy and security model documentation
- **`pyyaml` optional dependency**: `pip install obsidian-connector[scheduling]` for custom schedule config
- **SBOM.md**: Software bill of materials with dependency inventory and license audit
- **ROADMAP.md**: Prioritized backlog with 23 items for community contribution

## [0.1.0] - 2026-03-06

First public release.

### Added

- **Core vault operations**: search, read, tasks, log-daily, log-decision, create-note, doctor (7 MCP tools, 7 CLI commands)
- **Research and discovery**: find-prior-work, challenge-belief, emerge-ideas, connect-domains (4 MCP tools)
- **Graph intelligence**: neighborhood, vault-structure, backlinks, rebuild-index (4 MCP tools). Work without Obsidian running.
- **Thinking tools**: ghost (voice analysis), drift (intention vs behavior), trace (idea evolution), ideas (latent idea surfacing) (4 MCP tools)
- **Workflow OS**: my-world, today, close-day, open-loops, graduate-candidates, graduate-execute, delegations, context-load, check-in (9 MCP tools)
- **check_in MCP tool**: Time-aware situational awareness with ritual tracking, loop counting, and actionable suggestions
- **4 Claude Code skills**: /morning, /evening, /idea, /weekly
- **SessionStart hook**: Automatic context display at Claude Code session start
- **Scheduled automation**: macOS launchd runner for morning briefings (configurable for evening/weekly)
- **Claude Desktop system prompt**: Natural language workflow orchestration template
- **One-click installer**: `scripts/install.sh` with opt-in skills, hooks, and scheduling
- **Audit log**: Append-only JSONL logging for all mutations
- **Dry-run mode**: Preview mutations without writing
- **Agent draft provenance**: Frontmatter tagging for agent-generated notes
- **SQLite-backed index**: Incremental vault graph index with change detection
- **Path traversal protection**: Validated confinement for graduate_execute writes
- **osascript escaping**: Safe notification string interpolation

### Security

- Subprocess calls use list-based args (no shell=True)
- SQLite queries use parameterized placeholders exclusively
- graduate_execute validates title and target_folder against path traversal
- obsidian_bin config rejects shell metacharacters
- context_files entries skip paths with ".." components
- Notification strings escaped before osascript interpolation
- No secrets stored, transmitted, or hardcoded
- No network calls (100% local)

[0.2.0]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mariourquia/obsidian-connector/releases/tag/v0.1.0
