---
title: "Setup Guide"
status: verified
owner: core
last_reviewed: "2026-04-13"
---

# Setup Guide

Three installation paths. Pick the one that fits.

---

## Prerequisites

- [Obsidian](https://obsidian.md) desktop app v1.12+ with CLI enabled
- Python 3.11+ ([download](https://www.python.org/downloads/))
- macOS (Linux/Windows support planned)

---

## Path 1: Claude Desktop only (simplest)

Best if you primarily use Claude Desktop and want MCP tools with automatic
check-in at every conversation start.

### Steps

1. Clone the repo and run the installer:

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh
```

2. Copy the contents of `templates/claude-desktop-persona.md` into
   **Claude Desktop > Settings > Custom Instructions**.

3. Restart Claude Desktop.

4. Verify: start a new conversation. Claude should call
   `obsidian_check_in` automatically and offer a time-appropriate workflow.

### What you get

- 112 MCP tools available in every Claude Desktop conversation
- Automatic `check_in` at conversation start (via system prompt)
- No skills, hooks, or scheduling (those require Claude CLI)

---

## Path 2: Claude CLI only

Best if you use Claude Code / Claude CLI and want skills, hooks, and
scheduled automation.

### Steps

1. Clone the repo and run the installer:

```bash
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh
```

2. Install skills (copy to your project's commands directory):

```bash
mkdir -p .claude/commands
cp skills/*.md .claude/commands/
```

3. Enable the SessionStart hook. Add the following to `.claude/settings.json`:

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

4. (Optional) Enable scheduled automation:

```bash
# Edit scheduling/config.yaml to set your vault and timezone
# Then install the launchd plist:
cp scheduling/com.obsidian-connector.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

### What you get

- 17 skills: `/capture`, `/ritual`, `/new-vault`, `/sync`, `/morning`, `/evening`, `/idea`, `/weekly`, `/sync-vault`, `/init-vault`, `/float`, `/explore`, `/obsidian-markdown`, `/obsidian-bases`, `/json-canvas`, `/obsidian-cli`, `/defuddle`
- SessionStart hook: Claude checks in automatically at every session
- (Optional) Scheduled automation: briefings and reflections write themselves

---

## Path 3: Both (full experience)

Combine paths 1 and 2 for the complete second brain assistant.

### Steps

1. Follow all steps from Path 1 (Claude Desktop + system prompt)
2. Follow all steps from Path 2 (skills + hook + scheduling)

Both environments share the same MCP tools and Python API. Use whichever
interface fits the moment -- Desktop for conversational exploration, CLI
for structured workflows.

---

## Verification

Run these commands to confirm everything works:

```bash
# Health check (Obsidian connectivity)
./bin/obsx doctor

# Check-in (should return time-of-day, pending rituals, suggestion)
./bin/obsx check-in

# Smoke tests
python3 scripts/smoke_test.py
python3 scripts/checkin_test.py

# MCP server launch
bash scripts/mcp_launch_smoke.sh
```

---

## Troubleshooting

**Obsidian must be running.** The connector communicates with Obsidian via
IPC. If Obsidian is closed, CLI-based tools return `ObsidianNotRunning`.
Graph tools work without Obsidian since they read files directly.

**"ModuleNotFoundError: No module named 'obsidian_connector'" on Claude Desktop.**
When Claude Desktop runs a subprocess, it doesn't inherit the editable package
path from the shell environment. The fix: ensure `PYTHONPATH` is set in the
Claude Desktop config. Re-run `./scripts/install.sh` to regenerate the config
with the correct environment variable. Or manually add to your `claude_desktop_config.json`:

```json
"env": {
  "PYTHONPATH": "/path/to/obsidian-connector"
}
```

**Dashboard commands say Textual is missing.** Install the optional dashboard
dependency with `pip install 'obsidian-connector[tui]'` (or `pip install -e '.[tui]'`
from a local clone). The first-party installers and `scripts/setup.sh` already
include it.

**"Operation not permitted" on macOS.** Re-run `./scripts/install.sh` to
update the Claude Desktop config. The installer points directly at the
venv's python3 binary, bypassing macOS sandbox restrictions on shell
scripts.

**Skills not appearing in Claude CLI.** Verify the `.md` files exist in
`.claude/commands/` and restart your Claude session.

**SessionStart hook not firing.** Check `.claude/settings.json` for
correct JSON syntax and verify the absolute path to `session_start.sh`.

**Scheduled jobs not running.** Check `launchctl list | grep obsidian` and
review `/tmp/obsidian-connector-morning.log` and `/tmp/obsidian-connector-morning.err`
for output.

For deeper diagnostics:

```bash
./bin/obsx doctor
```

See also: [TOOLS_CONTRACT.md](../TOOLS_CONTRACT.md) for error codes and
the typed error hierarchy.
