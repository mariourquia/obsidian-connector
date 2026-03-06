# Changelog

All notable changes to obsidian-connector are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.2]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mariourquia/obsidian-connector/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mariourquia/obsidian-connector/releases/tag/v0.1.0
