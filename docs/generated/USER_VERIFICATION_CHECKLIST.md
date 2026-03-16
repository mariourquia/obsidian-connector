---
title: "Uninstaller User Verification Checklist"
status: draft
# generated, do not edit
owner: "mariourquia"
last_reviewed: "2026-03-16"
---

# Uninstaller User Verification Checklist

Step-by-step checklist for verifying that `obsx uninstall` (v0.1.3) correctly removes all obsidian-connector artifacts. Covers CLI and MCP modes.

---

## 1. Pre-Uninstall Verification

Run a dry-run first to preview what will be removed. Nothing is deleted during this step.

### CLI dry-run

```bash
obsx uninstall --dry-run
```

Confirm the output lists each artifact category:
- [ ] `.venv/` directory (if present)
- [ ] Skills in `.claude/commands/` (morning.md, evening.md, idea.md, weekly.md)
- [ ] SessionStart hook entry
- [ ] launchd plist (`~/Library/LaunchAgents/com.obsidian-connector.daily.plist`)
- [ ] Claude Desktop config entry (`mcpServers.obsidian-connector`)
- [ ] Audit logs (`~/.obsidian-connector/logs/`)
- [ ] Cache/index files

### MCP dry-run

The `uninstall` MCP tool defaults to dry-run mode (`destructiveHint=true` in ToolAnnotations). Invoke it without `--force` and confirm the returned JSON includes a `"dry_run": true` field and a `plan` object listing all detected artifacts.

### JSON output

```bash
obsx uninstall --dry-run --json
```

- [ ] Output is valid JSON
- [ ] `status` field is `"ok"`
- [ ] `dry_run` field is `true`
- [ ] `plan.files_to_remove` lists expected paths
- [ ] `plan.config_changes` shows the Claude Desktop config key to remove

---

## 2. Execute Uninstall

Choose one mode:

**Interactive (recommended for first run):**

```bash
obsx uninstall
```

Confirm each prompt. The CLI asks per-artifact whether to remove or keep.

**Force (no prompts):**

```bash
obsx uninstall --force
```

**JSON output (machine-readable):**

```bash
obsx uninstall --force --json
```

---

## 3. Post-Uninstall Verification

After running the uninstall, verify each artifact was removed.

### 3.1 Virtual environment removed

```bash
ls .venv
```

- [ ] Command returns "No such file or directory"

### 3.2 Skills removed

```bash
ls .claude/commands/morning.md .claude/commands/evening.md .claude/commands/idea.md .claude/commands/weekly.md
```

- [ ] All four files return "No such file or directory"
- [ ] Other non-obsidian-connector files in `.claude/commands/` are untouched

### 3.3 SessionStart hook removed

```bash
cat ~/.claude/settings.json
```

- [ ] No `session_start.sh` reference in the `hooks.SessionStart` array
- [ ] If obsidian-connector was the only hook, the `SessionStart` key may be absent or empty
- [ ] The rest of `settings.json` is intact (valid JSON)

### 3.4 launchd plist unloaded and removed

```bash
launchctl list | grep obsidian-connector
ls ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

- [ ] `launchctl list` shows no obsidian-connector entry
- [ ] Plist file returns "No such file or directory"

### 3.5 Claude Desktop config entry removed

```bash
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python3 -m json.tool
```

- [ ] `mcpServers` object does not contain an `obsidian-connector` key
- [ ] Other MCP server entries are untouched
- [ ] File is valid JSON (the `json.tool` command succeeds without error)

### 3.6 Config backup exists

```bash
ls ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup-*
```

- [ ] At least one timestamped backup file exists (format: `claude_desktop_config.json.backup-YYYY-MM-DD-HH-MM-SS`)
- [ ] Backup file contains the original config with the `obsidian-connector` entry still present

### 3.7 Audit log recorded the uninstall

```bash
ls ~/.obsidian-connector/logs/
cat ~/.obsidian-connector/logs/audit.log | tail -20
```

- [ ] Audit log file exists
- [ ] Recent entries show uninstall actions with timestamps

---

## 4. Recovery Steps

If something went wrong during uninstall, use these steps to restore.

### Restore Claude Desktop config from backup

```bash
# Find the most recent backup
ls -lt ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup-* | head -1

# Copy it back (replace TIMESTAMP with the actual value)
cp ~/Library/Application\ Support/Claude/claude_desktop_config.json.backup-TIMESTAMP \
   ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

Restart Claude Desktop after restoring the config.

### Restore launchd plist

If the plist was removed but the file still exists in the repo:

```bash
cp scheduling/com.obsidian-connector.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

### Restore skills

```bash
mkdir -p .claude/commands
cp skills/*.md .claude/commands/
```

### Restore SessionStart hook

Add the hook entry back to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "bash /ABSOLUTE/PATH/TO/obsidian-connector/hooks/session_start.sh",
        "timeout": 30
      }
    ]
  }
}
```

Replace `/ABSOLUTE/PATH/TO/` with the actual clone path.

---

## 5. Verify Clean State

After a complete uninstall, `obsx doctor` should fail gracefully since the venv and package are gone.

```bash
./bin/obsx doctor
```

- [ ] Command fails with a clear error (missing venv or module not found), not a crash or traceback
- [ ] No orphaned processes running (`ps aux | grep obsidian-connector` shows nothing)
- [ ] No orphaned launchd jobs (`launchctl list | grep obsidian` shows nothing)

### Idempotency check

Running uninstall again on an already-uninstalled system should be safe:

```bash
obsx uninstall --dry-run
```

- [ ] Reports no artifacts to remove (or an empty plan)
- [ ] Does not error or crash

---

## 6. Re-Install After Uninstall

To reinstall obsidian-connector from scratch:

```bash
cd /path/to/obsidian-connector
./scripts/install.sh
```

Then follow the setup guide for your preferred path (Claude Desktop, Claude CLI, or both). See `docs/setup-guide.md` for full instructions.

After reinstalling, verify the installation:

```bash
./bin/obsx doctor
./bin/obsx check-in
python3 scripts/smoke_test.py
```

- [ ] `doctor` reports healthy status
- [ ] `check-in` returns time-of-day context and suggestions
- [ ] Smoke tests pass
