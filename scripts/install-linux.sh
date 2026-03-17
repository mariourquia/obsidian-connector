#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector Linux installer
#
# One-command setup: creates the Python venv, installs the package,
# configures Claude Desktop (XDG), and optionally installs systemd
# timers for scheduled workflows.
#
# Usage:
#   ./scripts/install-linux.sh       # from repo root
#   bash scripts/install-linux.sh    # explicit bash
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Helpers ───────────────────────────────────────────────────────────

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
dim()   { printf '\033[2m%s\033[0m\n' "$*"; }

die() { red "ERROR: $*" >&2; exit 1; }

# ── Locate repo root ─────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

bold "obsidian-connector installer (Linux)"
dim  "repo: $REPO_ROOT"
echo ""

# ── Step 1: Check Python ─────────────────────────────────────────────

bold "[1/5] Checking Python..."

PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    die "Python 3.11+ is required but not found.
    Install via your package manager (e.g. sudo apt install python3.11) and re-run."
fi

green "  Found $PYTHON ($($PYTHON --version))"

# ── Step 2: Create venv and install ───────────────────────────────────

bold "[2/5] Setting up Python environment..."

if [ ! -d "$REPO_ROOT/.venv" ]; then
    "$PYTHON" -m venv "$REPO_ROOT/.venv"
    dim "  Created .venv"
else
    dim "  .venv already exists"
fi

"$REPO_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install --quiet -r "$REPO_ROOT/requirements-lock.txt"
"$REPO_ROOT/.venv/bin/pip" install --quiet --no-deps -e "$REPO_ROOT"

green "  Installed obsidian-connector"

# ── Step 3: Configure Claude Desktop (XDG) ───────────────────────────

bold "[3/5] Configuring Claude Desktop..."

VENV_PYTHON="$REPO_ROOT/.venv/bin/python3"

# XDG-compliant config path
CLAUDE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

configure_claude() {
    mkdir -p "$CLAUDE_CONFIG_DIR"

    # Build the MCP server entry
    local server_json
    server_json=$(cat <<ENTRY
{
  "command": "$VENV_PYTHON",
  "args": ["-u", "-m", "obsidian_connector.mcp_server"],
  "cwd": "$REPO_ROOT",
  "env": {
    "PYTHONPATH": "$REPO_ROOT"
  }
}
ENTRY
)

    if [ ! -f "$CLAUDE_CONFIG" ]; then
        # No config file yet -- create one
        cat > "$CLAUDE_CONFIG" <<CONF
{
  "mcpServers": {
    "obsidian-connector": $server_json
  }
}
CONF
        green "  Created $CLAUDE_CONFIG"
        return 0
    fi

    # Config exists -- update or add obsidian-connector entry
    # Pass paths via environment variables to prevent shell injection
    if VENV_PYTHON="$VENV_PYTHON" REPO_ROOT="$REPO_ROOT" CLAUDE_CONFIG="$CLAUDE_CONFIG" \
    "$REPO_ROOT/.venv/bin/python3" -c "
import json, os
venv_python = os.environ['VENV_PYTHON']
repo_root = os.environ['REPO_ROOT']
config_path = os.environ['CLAUDE_CONFIG']
with open(config_path) as f:
    cfg = json.load(f)
servers = cfg.get('mcpServers', {})
if 'obsidian-connector' in servers:
    servers['obsidian-connector']['command'] = venv_python
    servers['obsidian-connector']['args'] = ['-u', '-m', 'obsidian_connector.mcp_server']
    servers['obsidian-connector']['cwd'] = repo_root
    servers['obsidian-connector']['env'] = {'PYTHONPATH': repo_root}
    with open(config_path, 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    print('updated')
else:
    servers['obsidian-connector'] = {
        'command': venv_python,
        'args': ['-u', '-m', 'obsidian_connector.mcp_server'],
        'cwd': repo_root,
        'env': {'PYTHONPATH': repo_root}
    }
    cfg['mcpServers'] = servers
    with open(config_path, 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    print('added')
" 2>/dev/null; then
        local result
        result=$(CLAUDE_CONFIG="$CLAUDE_CONFIG" "$REPO_ROOT/.venv/bin/python3" -c "
import json, os
config_path = os.environ['CLAUDE_CONFIG']
with open(config_path) as f:
    cfg = json.load(f)
print('present' if 'obsidian-connector' in cfg.get('mcpServers', {}) else 'missing')
" 2>/dev/null)
        if [ "$result" = "present" ]; then
            green "  Claude Desktop configured"
            return 0
        fi
    fi

    dim "  Could not auto-configure. See manual instructions below."
    return 1
}

CLAUDE_CONFIGURED=true
configure_claude || CLAUDE_CONFIGURED=false

# ── Step 4: Check dependencies ───────────────────────────────────────

bold "[4/5] Checking system dependencies..."

# Check for notify-send (used for desktop notifications)
if command -v notify-send &>/dev/null; then
    green "  notify-send found (desktop notifications enabled)"
else
    dim "  notify-send not found -- install libnotify for notifications"
    dim "  e.g.: sudo apt install libnotify-bin"
fi

# Check for Obsidian
if command -v obsidian &>/dev/null; then
    green "  Obsidian CLI found"
elif [ -f "$HOME/.local/bin/obsidian" ]; then
    green "  Obsidian found at ~/.local/bin/obsidian"
elif command -v flatpak &>/dev/null && flatpak list 2>/dev/null | grep -q "md.obsidian.Obsidian"; then
    green "  Obsidian found (Flatpak)"
elif [ -d "/snap/obsidian" ]; then
    green "  Obsidian found (Snap)"
else
    dim "  Obsidian not detected -- install from https://obsidian.md"
fi

# ── Step 5: Verify ───────────────────────────────────────────────────

bold "[5/5] Verifying installation..."

if "$REPO_ROOT/.venv/bin/python3" -c "import obsidian_connector; print('  Package OK')" 2>/dev/null; then
    green "  Installation verified"
else
    die "Package import failed. Check the output above for errors."
fi

# ── Done ──────────────────────────────────────────────────────────────

echo ""
echo "-------------------------------------------------------------------"
green "  Installation complete!"
echo "-------------------------------------------------------------------"
echo ""

if [ "$CLAUDE_CONFIGURED" = true ]; then
    bold "Next steps:"
    echo "  1. Make sure Obsidian is running"
    echo "  2. Restart Claude Desktop"
    echo "  3. The Obsidian tools will appear automatically"
else
    bold "Almost done -- manual step needed:"
    echo ""
    echo "  Add this to: $CLAUDE_CONFIG"
    echo ""
    echo "  {"
    echo "    \"mcpServers\": {"
    echo "      \"obsidian-connector\": {"
    echo "        \"command\": \"$VENV_PYTHON\","
    echo "        \"args\": [\"-u\", \"-m\", \"obsidian_connector.mcp_server\"],"
    echo "        \"cwd\": \"$REPO_ROOT\","
    echo "        \"env\": {"
    echo "          \"PYTHONPATH\": \"$REPO_ROOT\""
    echo "        }"
    echo "      }"
    echo "    }"
    echo "  }"
    echo ""
    bold "Then:"
    echo "  1. Make sure Obsidian is running"
    echo "  2. Restart Claude Desktop"
    echo "  3. The Obsidian tools will appear automatically"
fi

echo ""
dim "CLI available at: $REPO_ROOT/bin/obsx"
dim "Health check:     $REPO_ROOT/bin/obsx doctor"

# ── Optional: Second Brain Assistant ────────────────────────────────

echo ""
bold "Optional: Second Brain Assistant"
dim  "These features turn Claude into a proactive second brain."
dim  "Each is independent -- install any combination."
echo ""

# ── Skills ──────────────────────────────────────────────────────────

read -rp "  Install Claude Code skills (/morning, /evening, /idea, /weekly)? [y/N] " INSTALL_SKILLS
if [[ "${INSTALL_SKILLS:-n}" =~ ^[Yy]$ ]]; then
    COMMANDS_DIR="$REPO_ROOT/.claude/commands"
    mkdir -p "$COMMANDS_DIR"
    copied=0
    for skill in "$REPO_ROOT"/skills/*.md; do
        [ -f "$skill" ] || continue
        cp "$skill" "$COMMANDS_DIR/"
        copied=$((copied + 1))
    done
    if [ "$copied" -gt 0 ]; then
        green "  Installed $copied skill(s) to .claude/commands/"
    else
        dim "  No skill files found in skills/"
    fi
else
    dim "  Skipped skills"
fi

# ── SessionStart Hook ──────────────────────────────────────────────

read -rp "  Install SessionStart hook (shows suggestions at session start)? [y/N] " INSTALL_HOOK
if [[ "${INSTALL_HOOK:-n}" =~ ^[Yy]$ ]]; then
    SETTINGS_FILE="$REPO_ROOT/.claude/settings.json"
    HOOK_CMD="bash $REPO_ROOT/hooks/session_start.sh"

    # Pass paths via environment variables to prevent shell injection
    SETTINGS_FILE="$SETTINGS_FILE" HOOK_CMD="$HOOK_CMD" \
    "$REPO_ROOT/.venv/bin/python3" -c "
import json, os, sys

path = os.environ['SETTINGS_FILE']
hook_cmd = os.environ['HOOK_CMD']

# Load existing or start fresh
cfg = {}
if os.path.isfile(path):
    with open(path) as f:
        cfg = json.load(f)

hooks = cfg.setdefault('hooks', {})
session_hooks = hooks.setdefault('SessionStart', [])

# Check if already installed
already = any(h.get('command') == hook_cmd for h in session_hooks)
if not already:
    session_hooks.append({
        'type': 'command',
        'command': hook_cmd
    })

os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')

print('present' if already else 'added')
" 2>/dev/null
    result=$?
    if [ $result -eq 0 ]; then
        green "  SessionStart hook configured in .claude/settings.json"
    else
        dim "  Could not configure hook. Add manually to .claude/settings.json"
    fi
else
    dim "  Skipped hook"
fi

# ── Scheduled Automation (systemd) ───────────────────────────────

read -rp "  Install scheduled daily briefing (systemd user timer)? [y/N] " INSTALL_SCHEDULE
if [[ "${INSTALL_SCHEDULE:-n}" =~ ^[Yy]$ ]]; then
    # Use platform.py to install systemd timer
    result=$("$REPO_ROOT/.venv/bin/python3" -c "
import sys
sys.path.insert(0, '$REPO_ROOT')
from obsidian_connector.platform import install_schedule
from pathlib import Path
result = install_schedule(
    repo_root=Path('$REPO_ROOT'),
    python_path=Path('$VENV_PYTHON'),
    workflow='morning',
    time='08:00',
)
print('installed' if result.get('installed') else 'failed')
" 2>/dev/null)
    if [ "$result" = "installed" ]; then
        green "  Scheduled daily briefing installed via systemd"
        dim "  Runs at 08:00 daily. Edit scheduling/config.yaml to customize."
        dim "  Timer: ~/.config/systemd/user/obsidian-connector-morning.timer"
        dim "  Uninstall: systemctl --user disable --now obsidian-connector-morning.timer"
    else
        dim "  Could not install systemd timer."
        dim "  Try manually: systemctl --user enable --now obsidian-connector-morning.timer"
    fi
else
    dim "  Skipped scheduling"
fi

echo ""
