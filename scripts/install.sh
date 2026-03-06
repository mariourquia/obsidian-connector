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
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

configure_claude() {
    mkdir -p "$CLAUDE_CONFIG_DIR"

    # Build the MCP server entry
    local server_json
    server_json=$(cat <<ENTRY
{
  "command": "$VENV_PYTHON",
  "args": ["-m", "obsidian_connector.mcp_server"]
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

    # Config exists -- check if obsidian-connector is already there
    if "$REPO_ROOT/.venv/bin/python3" -c "
import json, sys
with open('$CLAUDE_CONFIG') as f:
    cfg = json.load(f)
servers = cfg.get('mcpServers', {})
if 'obsidian-connector' in servers:
    # Update the command path in case the repo moved
    servers['obsidian-connector']['command'] = '$VENV_PYTHON'
    servers['obsidian-connector']['args'] = ['-m', 'obsidian_connector.mcp_server']
    with open('$CLAUDE_CONFIG', 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    print('updated')
else:
    servers['obsidian-connector'] = json.loads('''$server_json''')
    cfg['mcpServers'] = servers
    with open('$CLAUDE_CONFIG', 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    print('added')
" 2>/dev/null; then
        local result
        result=$("$REPO_ROOT/.venv/bin/python3" -c "
import json
with open('$CLAUDE_CONFIG') as f:
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
    echo "        \"args\": [\"-m\", \"obsidian_connector.mcp_server\"]"
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
