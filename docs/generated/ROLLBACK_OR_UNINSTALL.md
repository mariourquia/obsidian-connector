---
title: "Rollback and Recovery Guide: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Rollback and Recovery Guide

This guide covers uninstalling obsidian-connector, recovering from a failed
uninstall, manually cleaning up artifacts when the CLI is broken, downgrading
to a prior version, and reinstalling after removal.

## Data Safety Guarantee

The uninstaller never modifies, deletes, or touches vault notes. Your Obsidian
vault data is always safe regardless of which removal path you follow. This
applies to the CLI uninstaller, the MCP uninstall tool, and every manual
procedure documented below.

Artifacts the uninstaller does manage:

| Artifact | Location | Created by |
|----------|----------|------------|
| Python venv | `<repo>/.venv/` | `scripts/install.sh` |
| Skills | `<repo>/.claude/commands/{morning,evening,idea,weekly}.md` | `scripts/install.sh` (optional) |
| SessionStart hook | `<repo>/.claude/settings.json` (hooks entry) | `scripts/install.sh` (optional) |
| launchd plist | `~/Library/LaunchAgents/com.obsidian-connector.daily.plist` | `scripts/install.sh` (optional) |
| Claude Desktop config entry | `~/Library/Application Support/Claude/claude_desktop_config.json` | `scripts/install.sh` |
| Audit logs | `~/.obsidian-connector/logs/` | Runtime |
| Cache/index | Runtime cache files | Runtime |

## When to Use This Guide

- **Normal uninstall** -- you want to cleanly remove obsidian-connector.
- **Failed uninstall** -- the CLI crashed partway through removal and left
  artifacts behind.
- **Partial removal** -- you removed some components but not others and need to
  finish the job.
- **Reinstallation** -- you uninstalled and want to set it up again.
- **Downgrade** -- you want to roll back to an earlier version (e.g., v0.1.2).
- **Broken CLI** -- the `obsx` command itself is not working and you need to
  clean up by hand.

## 1. Full Uninstall (Normal Path)

### Interactive mode (recommended)

```bash
obsx uninstall
```

The CLI walks you through each artifact type, asking what to keep. It creates a
config backup before touching Claude Desktop's config, then removes only what
you approve. A final confirmation prompt appears before any deletion.

### Non-interactive mode

```bash
obsx uninstall --force \
  --remove-venv \
  --remove-skills \
  --remove-hook \
  --remove-plist \
  --remove-logs \
  --remove-cache
```

Each `--remove-*` flag is opt-in. Omit a flag to keep that artifact. This mode
is designed for scripted or MCP-driven uninstalls.

### Dry-run preview

```bash
obsx uninstall --dry-run
```

Shows exactly what would be removed without making any changes. Use this first
if you are unsure.

### MCP tool

The MCP `uninstall` tool defaults to `dry_run=True`. To execute a real
uninstall via MCP, set `dry_run=False` and pass the desired `remove_*`
parameters explicitly.

## 2. Recovery from a Failed Uninstall

If the uninstaller crashes or exits partway through, some artifacts may have
been removed while others remain. Follow the steps below to recover.

### 2.1 Restore Claude Desktop Config from Backup

The uninstaller creates a timestamped backup before modifying the config:

```
~/Library/Application Support/Claude/claude_desktop_config.json.backup-YYYY-MM-DD-HH-MM-SS
```

To restore:

```bash
# List available backups
ls -lt ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup-*

# Restore the most recent backup
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup-<TIMESTAMP> \
   ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

After restoring, restart Claude Desktop for the change to take effect.

### 2.2 Manually Remove Leftover Artifacts

Run a dry-run to see what the uninstaller still detects:

```bash
obsx uninstall --dry-run
```

If the dry-run shows remaining artifacts, run the uninstaller again (interactive
or `--force`) to finish the job. The uninstaller is idempotent -- re-running it
on already-removed artifacts is safe.

### 2.3 Re-load or Unload launchd Plist Manually

If the plist was partially removed (file deleted but agent still loaded, or
vice versa):

```bash
# Unload the agent (safe even if already unloaded)
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist 2>/dev/null

# If the plist file still exists, remove it
rm -f ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

To re-load a plist that was unloaded but not deleted:

```bash
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

## 3. Manual Cleanup (CLI Is Broken)

If the `obsx` command itself is not functional, remove each artifact by hand.

### 3.1 Remove the Python venv

```bash
rm -rf /path/to/obsidian-connector/.venv
```

Replace `/path/to/obsidian-connector` with the actual repo location (e.g.,
`~/Documents/GitHub/obsidian-connector`).

### 3.2 Remove Skills

```bash
rm -f /path/to/obsidian-connector/.claude/commands/morning.md
rm -f /path/to/obsidian-connector/.claude/commands/evening.md
rm -f /path/to/obsidian-connector/.claude/commands/idea.md
rm -f /path/to/obsidian-connector/.claude/commands/weekly.md
```

### 3.3 Remove SessionStart Hook

Edit `.claude/settings.json` in the repo root. Find and remove the hook entry
that references `hooks/session_start.sh`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "bash /path/to/obsidian-connector/hooks/session_start.sh"
      }
    ]
  }
}
```

Remove the object from the `SessionStart` array. If it is the only entry,
remove the entire `SessionStart` key or the `hooks` key.

### 3.4 Edit Claude Desktop Config by Hand

Open the config file:

```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Or edit in a terminal editor:

```bash
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Find the `"obsidian-connector"` key inside `"mcpServers"` and delete the entire
block:

```json
{
  "mcpServers": {
    "obsidian-connector": {
      "command": "...",
      "args": ["..."],
      "cwd": "...",
      "env": { "PYTHONPATH": "..." }
    }
  }
}
```

Make sure the resulting JSON is valid (no trailing commas). Restart Claude
Desktop afterward.

### 3.5 Unload and Remove launchd Plist

```bash
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

### 3.6 Remove Audit Logs and Cache

```bash
rm -rf ~/.obsidian-connector/logs/
```

## 4. Downgrade to v0.1.2

To roll back to a previous version while preserving your vault and config:

```bash
cd /path/to/obsidian-connector

# 1. Unload the launchd agent if running
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist 2>/dev/null

# 2. Check out the target version
git fetch --tags
git checkout v0.1.2

# 3. Recreate the venv against the older code
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

# 4. Verify
.venv/bin/python3 -c "import obsidian_connector; print('OK')"
```

The Claude Desktop config entry does not need to change -- the `command` path
points to `.venv/bin/python3` which will now run the older version.

If the older version does not include features you had installed (skills,
hook, plist), remove those artifacts manually using Section 3 above, since the
older CLI will not have the `uninstall` subcommand.

Restart Claude Desktop after downgrading.

## 5. Complete Removal (Nuke Everything)

To remove all traces of obsidian-connector from your system, including the
repository clone:

```bash
# 1. Unload launchd agent
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.obsidian-connector.daily.plist

# 2. Remove audit logs and cache
rm -rf ~/.obsidian-connector/

# 3. Remove the obsidian-connector entry from Claude Desktop config
#    (edit the file manually -- see Section 3.4)

# 4. Delete the entire repository clone
rm -rf /path/to/obsidian-connector
```

This removes skills, the hook, the venv, and all code in one step since they
all live inside the repo directory. The only artifacts outside the repo are the
launchd plist, the Claude Desktop config entry, and the `~/.obsidian-connector/`
directory -- handle those first.

Your Obsidian vault is untouched.

## 6. Re-installation After Uninstall

To reinstall after a full or partial uninstall:

```bash
cd /path/to/obsidian-connector

# If the repo was deleted, clone it first
# git clone https://github.com/mariourquia/obsidian-connector.git
# cd obsidian-connector

# Run the installer
bash scripts/install.sh
```

The installer will:
1. Create a fresh `.venv` and install the package as editable (`pip install -e .`).
2. Add or update the `obsidian-connector` entry in Claude Desktop's config.
3. Prompt to optionally install skills, the SessionStart hook, and the launchd
   scheduled briefing.

After installation, restart Claude Desktop and verify with:

```bash
./bin/obsx doctor
```
