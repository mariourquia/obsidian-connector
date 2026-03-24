---
title: "Uninstaller Design"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Uninstaller Design -- obsidian-connector

## Overview

A two-mode uninstaller (`obsx uninstall`) that safely removes all installation artifacts with interactive confirmation in CLI and non-interactive dry-run flow for MCP/Claude Desktop context.

## Problem Statement

Users need an easy, safe way to completely remove obsidian-connector when they no longer need it. The installer touches multiple system locations:
- Python venv at repo root
- Claude Desktop MCP server config
- Claude Code skills and hooks
- macOS scheduled automation (launchd)

Manual removal is error-prone and can corrupt Claude config or leave orphaned files.

## Design

### Core Architecture

**New Module**: `obsidian_connector/uninstall.py`
- `UninstallPlan`: Data class tracking artifacts to remove
- `generate_uninstall_plan()`: Scan system, detect what's installed
- `execute_uninstall()`: Apply removals with backups and validation
- `dry_run_uninstall()`: Preview-only (JSON output)

**Entry Points**:
1. CLI: `obsx uninstall` (interactive)
2. MCP tool: `uninstall` (dry-run + force pattern)

### CLI Flow (Interactive)

```
1. Scan system (what's actually installed?)
2. Ask user what to keep:
   - Keep .venv? [y/N]
   - Keep Claude config entry? [y/N]
   - Keep skills from .claude/commands/? [y/N]
   - Keep SessionStart hook? [y/N]
   - Keep launchd plist? [y/N]
3. Ask user about auxiliary cleanup:
   - Remove logs? [y/N]
   - Remove cache/index files? [y/N]
4. Show removal plan in detail (files, config keys, etc.)
5. Confirm: "Remove these artifacts? [y/N]"
6. Execute with backups (claude_desktop_config.json.backup-TIMESTAMP)
7. Verify each step succeeded
8. Report what was removed
```

### MCP Flow (Non-Interactive)

For Claude Desktop context where interactive prompts aren't available:

```
1. obsx uninstall --dry-run
   → Outputs JSON with removal plan
   → User reviews in Claude Desktop context
2. obsx uninstall --force --remove-venv --remove-skills --remove-hook --remove-plist --remove-logs --remove-cache
   → Executes with all confirmations pre-answered
   → Still creates backups
   → Outputs JSON result
```

### Safety Mechanisms

1. **Backups**: Before modifying any config file, create timestamped backup (e.g., `claude_desktop_config.json.backup-2026-03-06-14-30-45`)
2. **Validation**: After removing config entries, validate JSON is still valid before writing back
3. **Dry-run**: Always show what will be removed before asking for confirmation
4. **Audit log**: Log removal actions to audit trail (reversible via backup)
5. **Idempotent**: Safe to run multiple times (if artifact already gone, skip it)
6. **Explicit confirmation**: No silent removals; all destructive actions require user approval

### What Gets Removed

| Item | Location | Behavior |
|------|----------|----------|
| **venv** | `.venv/` | Ask user (interactive) |
| **Claude MCP entry** | `~/Library/Application Support/Claude/claude_desktop_config.json` | Backup + remove `obsidian-connector` entry |
| **Skills** | `~/.claude/commands/` | Ask user (interactive) |
| **SessionStart hook** | `~/.claude/settings.json` | Ask user (interactive) |
| **Launchd plist** | `~/Library/LaunchAgents/com.obsidian-connector.daily.plist` | Ask user (interactive) |
| **Logs** | `obsidian_connector/audit.log` (if present) | Ask user (interactive) |
| **Cache/Index** | TBD (persistent index store location) | Ask user (interactive) |

### Output Examples

**CLI (success)**:
```
✓ Removed launchd plist
✓ Removed SessionStart hook from .claude/settings.json
✓ Removed obsidian-connector from Claude Desktop config
✓ Uninstall complete!

Backup created: ~/Library/Application Support/Claude/claude_desktop_config.json.backup-2026-03-06-14-30-45
```

**MCP (dry-run)**:
```json
{
  "status": "ok",
  "dry_run": true,
  "plan": {
    "files_to_remove": ["~/.claude/commands/morning.md", ...],
    "config_changes": {
      "claude_desktop_config.json": {
        "action": "remove_key",
        "path": ["mcpServers", "obsidian-connector"]
      }
    },
    "plist": "unload",
    "summary": "Will remove 5 files, 1 config entry"
  }
}
```

## Implementation Approach

1. **Detection**: Scan standard locations to determine what's installed
2. **Planning**: Build UninstallPlan with user input (CLI) or flags (MCP)
3. **Execution**: Remove in safe order (config backups first, then files)
4. **Validation**: Verify each removal succeeded
5. **Reporting**: Show summary of what was removed

## Testing Strategy

- Unit tests: UninstallPlan generation, config parsing/validation
- Integration tests: Full uninstall flow (CLI + MCP), backup/restore, partial uninstalls
- Smoke tests: Verify no corrupted config after uninstall
- Edge cases: Missing files, corrupted config, partial installs, multiple runs

## Success Criteria

- ✓ User can fully remove obsidian-connector in one command
- ✓ Config backups prevent data loss
- ✓ Works in both CLI and MCP contexts
- ✓ Safe to run multiple times (idempotent)
- ✓ Clear feedback on what was removed
- ✓ Audit trail for all removals
