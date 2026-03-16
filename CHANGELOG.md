# Changelog

All notable changes to obsidian-connector are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

- **Uninstaller** (`obsx uninstall`): Two-mode safe uninstaller that cleanly removes all installation artifacts. Interactive CLI mode with per-artifact confirmation, and non-interactive `--force` mode for MCP/scripted contexts. Includes `--dry-run` preview, timestamped config backups, JSON validation after config edits, and idempotent operation.
- **Uninstall MCP tool**: `uninstall` tool with `ToolAnnotations` (`destructiveHint=true`) for Claude Desktop. Defaults to dry-run for safety; explicit flags required for each artifact type.
- **Comprehensive test suite**: 52 tests covering unit (Tasks 1-6), integration (Task 9), and edge cases (Task 11) for the uninstaller module.

### Security

- Config file backups created before any modification (`claude_desktop_config.json.backup-TIMESTAMP`)
- JSON validation after config edits prevents writing corrupted config
- Launchd plist properly unloaded before removal
- All uninstall actions logged to audit trail

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
