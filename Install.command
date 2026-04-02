#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector installer (double-click from Finder)
#
# For non-technical users: just double-click this file.
# It will set everything up and configure Claude Desktop automatically.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Error trap: generate diagnostic report on failure ────────────────
cleanup_on_error() {
    local exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        echo ""
        printf '\033[1;31m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
        printf '\033[1;31m  INSTALLATION ERROR (exit code %s)\033[0m\n' "$exit_code"
        printf '\033[1;31m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
        echo ""
        send_telemetry "unhandled_exit" "Install.command exited with code $exit_code"
        dim "  An anonymous error report was sent to help improve the installer."
        echo ""
        echo "  Submit a bug report:"
        echo "  https://github.com/mariourquia/obsidian-connector/issues/new?labels=bug,installer"
        echo ""
        printf '\033[1mPress Enter to close this window.\033[0m\n'
        read -r
    fi
}
trap cleanup_on_error EXIT

clear

# ── Helpers ───────────────────────────────────────────────────────────

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()    { printf '\033[1;31m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }

press_to_exit() {
    echo ""
    bold "Press Enter to close this window."
    read -r
    exit "${1:-0}"
}

# ── Telemetry (curl-based, no Python dependency) ───────────────────

TELEMETRY_URL="https://cre-skills-feedback-api.vercel.app/api/installer-telemetry"
PLUGIN_NAME_CONST="obsidian-connector"
INSTALLER_VERSION_CONST="0.7.2"

send_telemetry() {
    local step_failed="$1"
    local error_msg="$2"
    local prereqs_json="${3:-{}}"

    {
        local id_source
        id_source="$(hostname)-$(whoami)"
        local install_hash
        install_hash=$(printf '%s' "$id_source" | shasum -a 256 | cut -d' ' -f1)
        local event_seed
        event_seed="$step_failed-$error_msg-$(date +%s)"
        local event_id
        event_id="it_$(printf '%s' "$event_seed" | shasum -a 256 | cut -d' ' -f1 | head -c 16)"

        if [ ${#error_msg} -gt 2000 ]; then
            error_msg="${error_msg:0:2000}"
        fi

        curl -s -X POST "$TELEMETRY_URL" \
            -H "Content-Type: application/json" \
            -d "$(printf '{"id":"%s","plugin_name":"%s","plugin_version":"%s","installer_type":"command","os":"macos","os_version":"%s","arch":"%s","step_failed":"%s","error_message":"%s","prereqs":%s,"install_id_hash":"%s"}' \
                "$event_id" "$PLUGIN_NAME_CONST" "$INSTALLER_VERSION_CONST" \
                "$(sw_vers -productVersion 2>/dev/null || uname -r)" \
                "$(uname -m)" \
                "$step_failed" \
                "$error_msg" \
                "$prereqs_json" \
                "$install_hash")" \
            --connect-timeout 5 --max-time 10 2>/dev/null
    } &
}

# ── Navigate to repo root ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Verify we're in the right place
if [ ! -f "pyproject.toml" ] || [ ! -d "obsidian_connector" ]; then
    red "Could not find the obsidian-connector project files."
    echo "Make sure this file is in the obsidian-connector folder."
    press_to_exit 1
fi

echo ""
bold "  ┌─────────────────────────────────────┐"
bold "  │   obsidian-connector installer       │"
bold "  └─────────────────────────────────────┘"
echo ""
echo "  This will set up obsidian-connector and configure"
echo "  Claude Desktop to access your Obsidian vault."
echo ""

# ── Step 1: Check Python ─────────────────────────────────────────────

bold "  Checking for Python 3.11+..."

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
    yellow "  Python 3.11+ not found. Attempting to install..."

    if command -v brew &>/dev/null; then
        dim "  Installing via Homebrew..."
        brew install python@3.12 2>&1 | while read -r line; do
            printf "\r\033[2m  %s\033[0m\033[K" "$line"
        done
        printf "\r\033[K"

        for candidate in python3.12 python3 python3.14 python3.13 python3.11; do
            if command -v "$candidate" &>/dev/null; then
                version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
                major=$(echo "$version" | cut -d. -f1)
                minor=$(echo "$version" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                    PYTHON="$candidate"
                    green "  Python installed: $($candidate --version)"
                    break
                fi
            fi
        done
    fi

    if [ -z "$PYTHON" ]; then
        red "  Python 3.11+ could not be installed."
        echo ""
        echo "  Install manually:"
        dim "    brew install python@3.12"
        dim "    or: https://www.python.org/downloads/"
        echo ""
        send_telemetry "python_install" "Python 3.11+ not found and auto-install failed" \
            "{\"python\":\"missing\",\"brew\":\"$(command -v brew &>/dev/null && echo 'available' || echo 'not_installed')\"}"
        press_to_exit 1
    fi
fi

green "  Found $($PYTHON --version)"

# ── Step 2: Install ──────────────────────────────────────────────────

bold "  Installing (this may take a minute)..."
echo ""

if [ ! -d ".venv" ]; then
    "$PYTHON" -m venv .venv
fi

.venv/bin/pip install --quiet --upgrade pip 2>&1 | while read -r line; do
    printf "\r\033[2m  %s\033[0m\033[K" "$line"
done
.venv/bin/pip install --quiet -e . 2>&1 | while read -r line; do
    printf "\r\033[2m  %s\033[0m\033[K" "$line"
done
printf "\r\033[K"

green "  Installed successfully"

# ── Step 3: Configure Claude Desktop ─────────────────────────────────

bold "  Configuring Claude Desktop..."

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

mkdir -p "$CLAUDE_CONFIG_DIR"

"$SCRIPT_DIR/.venv/bin/python3" -c "
import json, sys, os

config_path = os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json')
venv_python = '$VENV_PYTHON'

server_entry = {
    'command': venv_python,
    'args': ['-u', '-m', 'obsidian_connector.mcp_server'],
    'cwd': '$SCRIPT_DIR',
    'env': {'PYTHONPATH': '$SCRIPT_DIR'}
}

try:
    with open(config_path) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

if 'mcpServers' not in cfg:
    cfg['mcpServers'] = {}

cfg['mcpServers']['obsidian-connector'] = server_entry

with open(config_path, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')

print('ok')
" 2>/dev/null && green "  Claude Desktop configured" || {
    echo ""
    dim "  Could not auto-configure Claude Desktop."
    dim "  See README.md for manual setup instructions."
    send_telemetry "desktop_config" "Python inline script failed to write claude_desktop_config.json"
}

# ── Step 4: Check Obsidian ───────────────────────────────────────────

bold "  Checking Obsidian..."

if pgrep -x "Obsidian" &>/dev/null; then
    green "  Obsidian is running"
else
    dim "  Obsidian is not running (you'll need it open to use most tools)"
fi

# ── Done ──────────────────────────────────────────────────────────────

echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
green "  Setup complete!"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  To start using it:"
echo ""
echo "    1. Make sure Obsidian is open"
echo "    2. Quit and reopen Claude Desktop"
echo "    3. Claude now has access to your vault"
echo ""
dim "  (62 tools for search, read, graph analysis,"
dim "   idea surfacing, daily workflows, and more)"
echo ""

press_to_exit 0
