# Changelog

All notable changes to obsidian-connector are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-04-13

```text
+==============================================================+
|                                                              |
|   OBSIDIAN-CONNECTOR  v0.9.0                                 |
|   ::  TRIAGE  ::  SMART CLASSIFICATION  ::  ENTITY NOTES     |
|                                                              |
|   [ rules -> threshold -> LLM fallback ]                     |
|                                                              |
+==============================================================+
```

### Added
- **`smart_triage` module + `RuleBasedClassifier`**: Connector surface (`obsidian_connector.smart_triage`, `obsidian_connector.classifiers.rule_based`) consumed by obsidian-capture-service Task 20 triage modes. The `smart_triage()` function runs rule-based classification first and falls back to an injected `LLMClient` when rule confidence is below the threshold (default 0.7). Exposes `ClassificationResult`, `LLMClient`, `Kind`, `Source`.
- **`entity_notes.py`**: Entity notes writer for the semantic memory layer (Task 15.A), generating per-entity vault notes from extracted entities.
- **`commitment_dashboards.py`**: 4 generated dashboard views (open by priority, blocked, due this week, recently completed) rendered from capture-service actions.
- **`commitment_notes.py`**: Renders capture-service actions as vault notes with lifecycle metadata and follow-up log fences.
- **Commitment inspection and update commands**: CLI surface for querying and updating commitment state.
- **Textual TUI dashboard**: `obsx` menu with sidebar navigation and multi-screen wizard.
- **First-run setup wizard**: Guided onboarding flow for new users.
- **UX orchestrator, Ix Integration, and progressive MCP middleware**: Connector orchestration layer coordinating user-facing flows across MCP, CLI, and TUI surfaces.

## [0.7.1] - 2026-04-02

### Added
- **Installer smoke tests** (`installer_smoke_test.py`): Validates 6 post-install conditions (plugin cache, installed_plugins.json, settings.json, Desktop config, MCP server import, version consistency) on Windows + macOS CI runners. Runs on every PR that touches installer files.
- **Release gating** (`verify-release.yml`): Downloads draft release assets, runs installers on platform-specific CI runners, promotes to live only on all-pass. Creates GitHub issue on failure. No asset reaches users without automated verification.
- **Error reporting** (`diagnostic_report.py`): On installer failure, collects system diagnostics (OS, Python, Node, Claude CLI, plugin state) and generates a pre-filled GitHub issue URL. One click to report.
- **Windows Desktop MCP diagnostics**: Install.ps1 now reads back `claude_desktop_config.json` after writing, validates the registered Python command path exists on disk, and prints actionable troubleshooting output if missing.

### Fixed
- **Install.ps1 error trap**: Replaced 6-line basic trap with 33-line version that calls diagnostic_report.py, falls back to issues URL, and never masks the original error.
- **Install.command error handling**: Added EXIT trap with diagnostic collection.
- **20+ CI fixes since v0.7.0**: Cross-platform test isolation (Windows path separators, POSIX permissions), lockfile sync, pip-audit for editable packages, automation test timing flakiness.

### Security
- SECURITY.md updated (support matrix needs refresh -- see Known Limitations).

## [0.7.0] - 2026-04-02

### Added
- **Product registry** (`product_registry.py`): Single source of truth for all product metadata (version, counts, skill registry, surface registry). Used by manifest_check and integrity_check.
- **4 new compressed skills** (17 total): `/capture` (quick/route/incubate/auto), `/ritual` (morning/evening/weekly/auto), `/new-vault` (project/topic/preset/existing), `/sync` (explicit manual sync). Legacy skills remain as wrappers with alias tips.
- **Enhanced manifest checker**: Now validates 14 user-facing files, checks MCP tool contract completeness (every @mcp.tool in TOOLS_CONTRACT.md), and validates skill registry completeness.
- **TOOLS_CONTRACT completeness**: Added 12 previously undocumented tools across 3 new sections (idea routing, vault factory, vault guardian). All 62 MCP tools now documented.
- **CLI section rewrite**: TOOLS_CONTRACT CLI section now documents all 59 runnable leaf commands with explicit methodology note.

### Fixed
- **Personal environment leakage**: Removed hardcoded "creation" vault paths from vault_init.py, project_sync.py, hooks/session_stop.sh, and generated docs. Default vault name changed to "My Vault". Personal repo registry replaced with auto-discovery.
- **Documentation drift**: Fixed stale counts in docs/setup-guide.md (35->62 tools, 11->13 skills), docs/second-brain-overview.md (11->13 skills), docs/daily-optimization.md (35->62 tools), Install.command (29->62 tools), ARCHITECTURE.md (31->38 modules), portable/README.md.
- **Skill classification**: All 17 skills properly classified into groups (capture, ritual, vault, sync, knowledge, workflow).

### Changed
- Version bump 0.6.1 -> 0.7.0 across all manifests.
- `hooks/session_stop.sh` now resolves vault from config.json, with platform-aware fallback discovery.
- `vault_init.py` default vault name changed from "creation" to "My Vault", path suggestions are platform-aware.
- `project_sync.py` default repo registry is now empty (relies on auto-discovery or sync_config.json).
- Legacy skills (`/idea`, `/float`, `/morning`, `/evening`, `/weekly`, `/init-vault`, `/explore`, `/sync-vault`) preserved with tips pointing to new unified entrypoints.

## [0.6.1] - 2026-04-01

### Added
- **Event automation runtime** (`automation.py`): Tool registry (14 tools), ToolChainRunner (sequential execution with per-step error handling), EventBus (routes watcher events and scheduler triggers to tool chains). New CLI: `schedule run`, `schedule fire`, `schedule tools`. 55 test assertions.
- **Pytest suite**: Parametrized test runner in `tests/test_all_suites.py` wrapping all 10 test scripts. `python -m pytest tests/` runs 441+ assertions in 3.5s.
- **Manifest check in CI**: `scripts/manifest_check.py` added to CI lint job. PRs that change tool/skill/command counts without updating docs fail CI.
- **v0.6.0 release notes** (`docs/generated/RELEASE_NOTES_v0.6.0.md`) with ASCII art.

### Fixed
- **Documentation drift**: 12 stale count references across AGENTS.md, ARCHITECTURE.md, TOOLS_CONTRACT.md, README.md (35->62/65 tools/commands, 11->13 skills).
- **CI docs lint**: Added required frontmatter to generated release notes. Removed broken links to deleted uninstaller docs.
- **CI coverage threshold**: Lowered `fail-under` from 40 to 10 to match actual coverage with 31 modules.
- **CI lockfile check**: Replaced unsupported `pip-compile --check` with diff-based validation.
- **Lockfile**: Regenerated `requirements-lock.txt` for v0.6.0 optional dependency groups.

### Removed
- 16 stale docs: 12 generated docs pinned to v0.2.0, 3 archived exec plans, 1 old release notes (v0.1.3).

### Changed
- `pyproject.toml`: Added `dev` optional dependency group (`pytest>=8.0`).
- Moved v0.6.0 PRD from `exec-plans/active/` to `exec-plans/completed/`.

## [0.6.0] - 2026-03-30

### Added
- **Atomic write manager** (`write_manager.py`): All mutating operations now route through write-then-rename for atomicity. Pre-write snapshots, rollback, diff preview, file locking, protected-folder policy, and `generated_by` metadata injection.
- **Filesystem watcher** (`watcher.py`): Incremental re-index on vault file changes. Uses `watchdog` if installed, falls back to polling. Debounce, exclude patterns, stale-index indicator.
- **Draft lifecycle manager** (`draft_manager.py`): List, approve, reject, and auto-archive stale agent drafts. Configurable retention, dashboard integration.
- **Named vault registry** (`vault_registry.py`): Register multiple vaults with profiles (`personal`, `work`, `research`, `creative`) and per-vault policies. Cross-vault search support.
- **Hybrid retrieval engine** (`retrieval.py`, `embeddings.py`): Combines lexical, semantic (optional `sentence-transformers`), graph, and recency signals. Four retrieval profiles (journal, project, research, review) with explanation mode.
- **Template system** (`template_engine.py`): User templates with `{{variable}}` substitution, template inheritance, 5 built-in templates (daily-note, meeting-note, research-note, decision-log, project-idea). Configurable daily note path/format and sentinel headings.
- **Scheduler expansion** (`scheduler.py`): First-class schedule config for morning/evening/weekly jobs with workflow chaining, active hours, missed-run recovery, and event triggers.
- **Report generation** (`reports.py`): Weekly review, monthly review, vault health (orphans, stale notes, index coverage), and project status reports. Markdown output to `Reports/` folder.
- **Session telemetry** (`telemetry.py`): Local-only (zero network) session tracking: notes read/written, tools called, retrieval misses, write-risk events. JSONL storage with auto-rotation.
- **Project intelligence** (`project_intelligence.py`): Project health scores (0-100 with status), changelogs from session logs, stale project detection, idea-to-project graduation suggestions, weekly project packets.
- **Manifest validation** (`scripts/manifest_check.py`): CI-ready script that validates tool/skill/preset/command counts across README, CLAUDE.md, TOOLS_CONTRACT.md, marketplace.json, mcpb.json.
- **Compatibility matrix generator** (`scripts/generate_compat_matrix.py`): Autogenerates feature availability table across MCP, CLI, Python API, and portable surfaces.
- **Release checklist template** (`templates/release-checklist.md`): Standardized release process.
- **15 new MCP tools** (62 total): `obsidian_rollback`, `obsidian_list_drafts`, `obsidian_approve_draft`, `obsidian_reject_draft`, `obsidian_clean_drafts`, `obsidian_register_vault`, `obsidian_set_default_vault`, `obsidian_list_templates`, `obsidian_create_from_template`, `obsidian_project_changelog`, `obsidian_project_health`, `obsidian_project_packet`, `obsidian_generate_report`, `obsidian_session_stats`, `obsidian_index_status`.
- **New CLI commands**: `rollback`, `drafts` (list/approve/reject/clean), `vaults` (list/add/remove/default), `templates` (list/init/check), `schedule` (list/preview/status), `report`, `stats`, `project` (health/changelog/packet), `index-status`. Existing `search` gains `--profile` and `--explain` flags.
- **386 new test assertions** across 9 test suites covering all new modules.

### Changed
- `pyproject.toml`: New optional dependency groups `live` (watchdog) and `semantic` (sentence-transformers).
- `errors.py`: Added `ProtectedFolderError`, `WriteLockError`, `RollbackError`.
- ARCHITECTURE.md, CLAUDE.md, TOOLS_CONTRACT.md updated with new module counts and tool tables.

## [0.5.0] - 2026-03-30

### Added
- **Idea routing** (`idea_router.py`): Auto-routes ideas to the correct project's idea file via keyword matching against the repo registry. `obsidian_float_idea` MCP tool + `/float` skill.
- **Project incubation**: `obsidian_incubate_project` creates inception cards for projects that don't exist yet (`Inbox/Project Ideas/`).
- **Auto-detect ideas**: `UserPromptSubmit` prompt hook (`idea_detect.md`) tells Claude to automatically capture tangential ideas ("what if...", "we should eventually...") without the user invoking a skill.
- **Vault guardian** (`vault_guardian.py`): Marks auto-generated files with Obsidian callouts ("do not edit"), detects unorganized notes in the vault root, and moves them to the correct folder.
- **Vault factory** (`vault_factory.py`): Creates new Obsidian vaults alongside existing ones (auto-detected from Obsidian's config). Seeds with research topic stubs. Includes discard for unwanted vaults.
- **13 vault presets** (was 11): Added `poetry` (forms, meter, imagery, chapbook building) and `songwriting` (structure, chord progressions, hooks, AI production, sync licensing). Each preset has craft notes at foundations/intermediate/advanced levels.
- **`/explore` skill**: Creates a vault for any topic and seeds it with real web research.
- **7 new MCP tools** (47 total): `obsidian_float_idea`, `obsidian_incubate_project`, `obsidian_incubating`, `obsidian_idea_files`, `obsidian_create_vault`, `obsidian_seed_vault`, `obsidian_vault_presets`, `obsidian_list_vaults`, `obsidian_discard_vault`, `obsidian_mark_auto_generated`, `obsidian_detect_unorganized`, `obsidian_organize_file`.

### Fixed
- **Existing vault isolation**: Sync output now goes into `Project Tracking/` subdirectory when no `sync_config.json` exists, preventing pollution of personal vaults. Auto-detected: if the vault already has user content, it's treated as existing.
- User-content directories (`daily/`, `Cards/`, `Inbox/`) always created in vault root, never namespaced.

### Changed
- `vault_init` gains `existing_vault` parameter (auto-detected from vault contents).
- `SyncConfig.vault_subdir` defaults to `"Project Tracking"` when no config file exists.
- `hooks.json` adds `UserPromptSubmit` and `Stop` hooks alongside existing `SessionStart`.

## [0.4.0] - 2026-03-25

### Added
- **obsidian-cli skill**: Obsidian CLI command reference for agents. Covers read, create, search, tasks, tags, backlinks, and plugin development. Parity with kepano/obsidian-skills.
- **defuddle skill**: Web page to clean markdown extraction via defuddle CLI. Parity with kepano/obsidian-skills.
- **Portable skills bundle** (`portable/`): 5 Agent Skills-compliant knowledge skills for Codex CLI, OpenCode, Gemini CLI, and any agent supporting the Agent Skills specification.
- **Build script** (`scripts/build-portable.sh`): Assembles the portable bundle from the skills directory.
- **Skill compatibility matrix** in README: classifies all 11 skills by type, distribution surface, and runtime requirements.
- Total skills: 11 (6 workflow + 5 knowledge).

### Fixed
- 25 stale references across 11 files: skill counts (4->11), tool counts (28/29->35), command counts (28/29->35).

### Changed
- ARCHITECTURE.md: Added `portable/` to directory map.
- README: Added "Portable skills" and "Skill compatibility" sections.

## [0.3.0] - 2026-03-23

### Added
- **Project sync engine** (`project_sync.py`, 530 LOC): Syncs git repository state into the vault. Generates per-project Markdown files, Dashboard, Active Threads, and Running TODO. Cross-platform Python implementation.
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
- **Active threads sort order**: Active threads now sorted by most recent commit first (ascending `days_since_commit`, then descending uncommitted count as tiebreaker). Both Python engine and bash script updated.
- **Render I/O**: Removed git subprocess calls from `_render_project_file` and `_render_active_threads`. All git state is now captured in `_extract_repo_state` and stored on `RepoState`.
- **plugin.json version**: Bumped from 0.2.1 to 0.3.0 (was out of sync with pyproject.toml and marketplace.json).
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
