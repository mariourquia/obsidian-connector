---
title: "Release Notes -- obsidian-connector v0.1.3"
status: draft
owner: mariourquia
last_reviewed: "2026-03-16"
---

# obsidian-connector v0.1.3

**Release date**: 2026-03-16
**Package**: obsidian-connector
**License**: MIT
**Author**: Mario Urquia
**Python**: 3.11+
**Platform**: macOS (Linux/Windows planned)

---

## Summary

v0.1.3 adds a safe, two-mode uninstaller for cleanly removing all obsidian-connector installation artifacts. The uninstaller is available as both a CLI subcommand (`obsx uninstall`) and an MCP tool (`uninstall`) for Claude Desktop, backed by 52 new tests.

---

## What's New

### Uninstaller

A complete uninstaller that removes all artifacts created by `scripts/install.sh` or manual setup. Two modes of operation cover both human and agent workflows:

**Interactive CLI** -- `obsx uninstall`

Prompts for confirmation on each artifact before removal. Supports `--dry-run` to preview what would be removed without touching the filesystem, and `--force` for non-interactive scripted contexts. Output available in human-readable or `--json` format.

**MCP tool** -- `uninstall`

Registered with `ToolAnnotations` (`destructiveHint=true`) so Claude Desktop surfaces appropriate warnings. Defaults to dry-run for safety; callers must pass explicit flags for each artifact type:

- `remove_venv` -- virtual environment
- `remove_skills` -- Claude Code skill files
- `remove_hook` -- SessionStart hook
- `remove_plist` -- macOS launchd plist
- `remove_logs` -- audit log files
- `remove_cache` -- cache directory

### Safety Features

- **Dry-run preview**: `--dry-run` shows every artifact that would be removed, with no side effects.
- **Timestamped config backups**: Before modifying `claude_desktop_config.json`, a backup is written to `claude_desktop_config.json.backup-TIMESTAMP`.
- **JSON validation**: Config file is re-validated after edits to prevent writing corrupted JSON.
- **Idempotent operation**: Running uninstall on an already-clean system is a no-op with clear reporting.
- **Audit logging**: All uninstall actions are recorded in the append-only audit trail.

### Test Coverage

52 new tests across three categories:

- **Unit tests** (Tasks 1--6): Individual artifact removal functions, dry-run behavior, config backup/restore, JSON validation.
- **Integration tests** (Task 9): End-to-end uninstall workflows covering full removal, partial removal, and dry-run sequences.
- **Edge case tests** (Task 11): Missing files, permission errors, corrupted config, concurrent access, re-entrant uninstall.

---

## Security Highlights

- Config file backup created before any modification.
- JSON structure validated after every config edit; corrupted writes are rejected.
- macOS launchd plist is unloaded via `launchctl` before file removal.
- All uninstall actions logged to the audit trail for traceability.

---

## Breaking Changes

None.

---

## Known Limitations

- **macOS only**. Linux and Windows support is planned for v0.2.0+.
- The uninstaller removes artifacts it knows about (venv, skills, hook, plist, logs, cache, Claude Desktop config entry). Custom modifications outside these paths are not touched.

---

## Upgrade Instructions

From an existing editable install:

```bash
pip install -e .
```

Or re-run the installer:

```bash
bash scripts/install.sh
```

No configuration changes are required. Existing installations continue to work without modification.

---

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for the complete change history across all versions.

Compare with previous release: [v0.1.2...v0.1.3](https://github.com/mariourquia/obsidian-connector/compare/v0.1.2...v0.1.3)
