#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector installer
#
# One-command setup: creates the Python venv, installs the package,
# and configures Claude Desktop to use the MCP server.
#
# Usage:
#   ./scripts/install.sh          # from repo root
#   bash scripts/install.sh       # explicit bash
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── OS dispatch ──────────────────────────────────────────────────────

SCRIPT_DIR_EARLY="$(cd "$(dirname "$0")" && pwd)"
case "$(uname -s)" in
    Linux)
        exec "$SCRIPT_DIR_EARLY/install-linux.sh" "$@"
        ;;
    CYGWIN*|MINGW*|MSYS*)
        echo "Windows detected. Use scripts/install.ps1 instead."
        exit 1
        ;;
esac
# macOS continues below

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

bold "obsidian-connector installer"
dim  "repo: $REPO_ROOT"
echo ""

# ── Step 1: Check Python ─────────────────────────────────────────────

bold "[1/4] Checking Python..."

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
    Install from https://www.python.org/downloads/ and re-run this script."
fi

green "  Found $PYTHON ($($PYTHON --version))"

# ── Step 2: Create venv and install ───────────────────────────────────

bold "[2/4] Setting up Python environment..."

if [ ! -d "$REPO_ROOT/.venv" ]; then
    "$PYTHON" -m venv "$REPO_ROOT/.venv"
    dim "  Created .venv"
else
    dim "  .venv already exists"
fi

"$REPO_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_ROOT/.venv/bin/pip" install --quiet -e "$REPO_ROOT"

green "  Installed obsidian-connector"

# ── Step 3: Configure Claude Desktop ─────────────────────────────────

bold "[3/4] Configuring Claude Desktop..."

VENV_PYTHON="$REPO_ROOT/.venv/bin/python3"

# Resolve Claude Desktop config path (cross-platform)
case "$(uname -s)" in
    Darwin*)
        CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
        ;;
    Linux*)
        CLAUDE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Claude"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        CLAUDE_CONFIG_DIR="${APPDATA:-$HOME/AppData/Roaming}/Claude"
        ;;
    *)
        CLAUDE_CONFIG_DIR="$HOME/.config/Claude"
        ;;
esac
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

# ── Step 4: Verify ───────────────────────────────────────────────────

bold "[4/4] Verifying installation..."

if "$REPO_ROOT/.venv/bin/python3" -c "import obsidian_connector; print('  Package OK')" 2>/dev/null; then
    green "  Installation verified"
else
    die "Package import failed. Check the output above for errors."
fi

# ── Done ──────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
green "  Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$CLAUDE_CONFIGURED" = true ]; then
    bold "Next steps:"
    echo "  1. Make sure Obsidian is running"
    echo "  2. Restart Claude Desktop"
    echo "  3. The Obsidian tools will appear automatically"
else
    bold "Almost done -- manual step needed:"
    echo ""
    echo "  Add this to: ~/Library/Application Support/Claude/claude_desktop_config.json"
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

# ── Plugin mode detection ────────────────────────────────────────
# If installed as a Claude Code plugin, skills and hooks are handled
# by the plugin system. Only offer manual setup for standalone installs.

PLUGIN_MODE=false
if [ -f "$REPO_ROOT/.claude-plugin/plugin.json" ] && \
   [ -f "$REPO_ROOT/hooks/hooks.json" ] && \
   [ -d "$REPO_ROOT/skills/morning" ]; then
    bold "Plugin mode available"
    dim  "Skills and hooks can be loaded via the Claude Code plugin system."
    dim  "  Plugin install: claude --plugin-dir $REPO_ROOT"
    dim  "  Or install from marketplace: claude plugin install obsidian-connector"
    echo ""
    read -rp "  Use plugin mode (recommended) instead of manual setup? [Y/n] " USE_PLUGIN
    if [[ "${USE_PLUGIN:-y}" =~ ^[Yy]$ ]] || [ -z "$USE_PLUGIN" ]; then
        PLUGIN_MODE=true
        green "  Plugin mode selected. Skills and hooks handled by plugin system."
    fi
fi

# ── Skills ──────────────────────────────────────────────────────────

if [ "$PLUGIN_MODE" = false ]; then
read -rp "  Install Claude Code skills (/morning, /evening, /idea, /weekly)? [y/N] " INSTALL_SKILLS
if [[ "${INSTALL_SKILLS:-n}" =~ ^[Yy]$ ]]; then
    COMMANDS_DIR="$REPO_ROOT/.claude/commands"
    mkdir -p "$COMMANDS_DIR"
    copied=0
    # Support both flat (skills/*.md) and nested (skills/*/SKILL.md) layouts
    for skill in "$REPO_ROOT"/skills/*/SKILL.md "$REPO_ROOT"/skills/*.md; do
        [ -f "$skill" ] || continue
        skill_name=$(basename "$(dirname "$skill")")
        if [ "$skill_name" = "skills" ]; then
            # Flat layout: skills/morning.md
            cp "$skill" "$COMMANDS_DIR/"
        else
            # Nested layout: skills/morning/SKILL.md -> commands/morning.md
            cp "$skill" "$COMMANDS_DIR/${skill_name}.md"
        fi
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
fi

# ── SessionStart Hook ──────────────────────────────────────────────

if [ "$PLUGIN_MODE" = false ]; then
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
already = any(
    hook_entry.get('matcher') == '' and
    any(h.get('command') == hook_cmd for h in hook_entry.get('hooks', []))
    for hook_entry in session_hooks
)
if not already:
    session_hooks.append({
        'matcher': '',
        'hooks': [{
            'type': 'command',
            'command': hook_cmd
        }]
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
fi

# ── Scheduled Automation ───────────────────────────────────────────

read -rp "  Install scheduled daily briefing (macOS launchd)? [y/N] " INSTALL_SCHEDULE
if [[ "${INSTALL_SCHEDULE:-n}" =~ ^[Yy]$ ]]; then
    PLIST_SRC="$REPO_ROOT/scheduling/com.obsidian-connector.daily.plist"
    PLIST_DST="$HOME/Library/LaunchAgents/com.obsidian-connector.daily.plist"

    if [ ! -f "$PLIST_SRC" ]; then
        dim "  Plist template not found at $PLIST_SRC"
    else
        # Generate plist via Python to avoid sed issues with & and \ in paths
        "$REPO_ROOT/.venv/bin/python3" -c "
import sys
src = sys.argv[1]
dst = sys.argv[2]
repo = sys.argv[3]
venv_py = sys.argv[4]
with open(src) as f:
    content = f.read()
# Replace __REPO_ROOT__ placeholder
content = content.replace('__REPO_ROOT__', repo)
# Replace /usr/bin/env + python3 with venv python directly
content = content.replace('<string>/usr/bin/env</string>\n        <string>python3</string>', '<string>' + venv_py + '</string>')
with open(dst, 'w') as f:
    f.write(content)
" "$PLIST_SRC" "$PLIST_DST" "$REPO_ROOT" "$REPO_ROOT/.venv/bin/python3"

        # Load the agent
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        if launchctl load "$PLIST_DST" 2>/dev/null; then
            green "  Scheduled daily briefing installed and loaded"
            dim "  Runs at 08:00 daily. Edit scheduling/config.yaml to customize."
            dim "  Uninstall: launchctl unload $PLIST_DST && rm $PLIST_DST"
        else
            dim "  Plist written to $PLIST_DST but launchctl load failed."
            dim "  Try: launchctl load $PLIST_DST"
        fi
    fi
else
    dim "  Skipped scheduling"
fi

echo ""
