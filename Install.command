#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector installer (double-click from Finder)
#
# For non-technical users: just double-click this file.
# It will set everything up and configure Claude Desktop automatically.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────

TELEMETRY_URL="https://cre-skills-feedback-api.vercel.app/api/installer-telemetry"
PLUGIN_NAME="obsidian-connector"
INSTALLER_VERSION="0.8.1"
TOTAL_STEPS=5

# ── Timing ───────────────────────────────────────────────────────────

INSTALL_START=$(date +%s)

# ── Step tracking ────────────────────────────────────────────────────

STEP_PYTHON="pending"
STEP_VENV="pending"
STEP_PIP="pending"
STEP_REGISTER="pending"
STEP_VERIFY="pending"

PYTHON_VERSION=""
PYTHON_SOURCE=""
CLAUDE_CODE_PRESENT="false"
CLAUDE_DESKTOP_PRESENT="false"
EDGE_CASES=""
REMEDIATIONS=""
FINAL_STATUS="failure"
FAILED_STEP=""
FAILED_MSG=""

# ── Helpers ──────────────────────────────────────────────────────────

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
green()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()    { printf '\033[1;31m%s\033[0m\n' "$*"; }
dim()    { printf '\033[2m%s\033[0m\n' "$*"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }

step() {
    local n=$1; shift
    echo ""
    printf '\033[1m  [%d/%d] %s\033[0m\n' "$n" "$TOTAL_STEPS" "$*"
}

add_edge_case() {
    if [ -z "$EDGE_CASES" ]; then EDGE_CASES="$1"; else EDGE_CASES="$EDGE_CASES,$1"; fi
}

add_remediation() {
    if [ -z "$REMEDIATIONS" ]; then REMEDIATIONS="$1"; else REMEDIATIONS="$REMEDIATIONS,$1"; fi
}

press_to_exit() {
    echo ""
    bold "Press Enter to close this window."
    read -r
    exit "${1:-0}"
}

fail_step() {
    local step_name="$1"
    local msg="$2"
    FAILED_STEP="$step_name"
    FAILED_MSG="$msg"
}

# ── Install ID ───────────────────────────────────────────────────────

get_install_hash() {
    local id_file="$HOME/.obsidian-connector-install-id"
    if [ -f "$id_file" ]; then
        cat "$id_file"
    else
        local hash
        hash=$(uuidgen | tr '[:upper:]' '[:lower:]')
        mkdir -p "$(dirname "$id_file")"
        printf '%s' "$hash" > "$id_file"
        echo "$hash"
    fi
}

INSTALL_HASH=$(get_install_hash)

# ── Telemetry ────────────────────────────────────────────────────────

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ' | tr '\r' ' '
}

send_telemetry() {
    local status="$1"
    local step_failed="${2:-}"
    local error_msg="${3:-}"

    {
        local elapsed=$(( $(date +%s) - INSTALL_START ))

        local event_seed="$status-$step_failed-$(date +%s)"
        local event_id="it_$(printf '%s' "$event_seed" | shasum -a 256 | cut -d' ' -f1 | head -c 16)"

        if [ ${#error_msg} -gt 2000 ]; then
            error_msg="${error_msg:0:2000}"
        fi
        error_msg=$(json_escape "$error_msg")
        local escaped_edge=$(json_escape "$EDGE_CASES")
        local escaped_remed=$(json_escape "$REMEDIATIONS")

        curl -s -X POST "$TELEMETRY_URL" \
            -H "Content-Type: application/json" \
            -d "$(cat <<ENDJSON
{
  "id":"$event_id",
  "plugin_name":"$PLUGIN_NAME",
  "plugin_version":"$INSTALLER_VERSION",
  "installer_type":"command",
  "os":"macos",
  "os_version":"$(sw_vers -productVersion 2>/dev/null || uname -r)",
  "arch":"$(uname -m)",
  "status":"$status",
  "install_id_hash":"$INSTALL_HASH",
  "python_version":"$PYTHON_VERSION",
  "python_source":"$PYTHON_SOURCE",
  "claude_code_present":$CLAUDE_CODE_PRESENT,
  "claude_desktop_present":$CLAUDE_DESKTOP_PRESENT,
  "step_results":{
    "python":"$STEP_PYTHON",
    "venv":"$STEP_VENV",
    "pip":"$STEP_PIP",
    "register":"$STEP_REGISTER",
    "verify":"$STEP_VERIFY"
  },
  "edge_cases":"$escaped_edge",
  "remediations":"$escaped_remed",
  "total_duration_s":$elapsed,
  "step_failed":"$step_failed",
  "error_message":"$error_msg"
}
ENDJSON
)" \
            --connect-timeout 5 --max-time 10 2>/dev/null
    } &
}

# ── Error trap ───────────────────────────────────────────────────────

cleanup_on_error() {
    local exit_code=$?
    if [ "$exit_code" -ne 0 ] && [ "$FINAL_STATUS" != "success" ]; then
        echo ""
        printf '\033[1;31m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
        printf '\033[1;31m  INSTALLATION ERROR (exit code %s)\033[0m\n' "$exit_code"
        printf '\033[1;31m  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n'
        echo ""
        local fail_step="${FAILED_STEP:-unhandled_exit}"
        local fail_msg="${FAILED_MSG:-Install.command exited with code $exit_code}"
        send_telemetry "failure" "$fail_step" "$fail_msg"
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

# ── Navigate to repo root ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "pyproject.toml" ] || [ ! -d "obsidian_connector" ]; then
    red "Could not find the obsidian-connector project files."
    echo "Make sure this file is in the obsidian-connector folder."
    press_to_exit 1
fi

echo ""
bold "  ┌─────────────────────────────────────┐"
bold "  │   obsidian-connector installer       │"
bold "  │   v$INSTALLER_VERSION                            │"
bold "  └─────────────────────────────────────┘"
echo ""
echo "  This will set up obsidian-connector and configure"
echo "  Claude Desktop to access your Obsidian vault."

# ── Pre-flight edge case detection ───────────────────────────────────

if [[ "$SCRIPT_DIR" == *" "* ]]; then
    add_edge_case "spaces_in_path"
    yellow "  Note: install path contains spaces -- this usually works fine"
fi

if printf '%s' "$HOME" | LC_ALL=C grep -q '[^[:print:]]' 2>/dev/null; then
    add_edge_case "non_ascii_username"
fi

if ! touch "$SCRIPT_DIR/.install_write_test" 2>/dev/null; then
    add_edge_case "read_only_filesystem"
    red "  Error: cannot write to install directory"
    dim "  Path: $SCRIPT_DIR"
    fail_step "preflight" "Read-only filesystem at $SCRIPT_DIR"
    press_to_exit 1
else
    rm -f "$SCRIPT_DIR/.install_write_test"
fi

# ── Step 1/5: Check Python ──────────────────────────────────────────

step 1 "Checking Python..."

PYTHON=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || echo "0.0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            PYTHON_VERSION="$version"
            # Determine source
            python_path=$(command -v "$candidate")
            if [[ "$python_path" == */homebrew/* ]] || [[ "$python_path" == */opt/homebrew/* ]] || [[ "$python_path" == */Cellar/* ]]; then
                PYTHON_SOURCE="brew"
            elif [[ "$python_path" == */Library/Frameworks/* ]]; then
                PYTHON_SOURCE="python.org"
            elif [[ "$python_path" == */macports/* ]]; then
                PYTHON_SOURCE="macports"
            else
                PYTHON_SOURCE="system"
            fi
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
                version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || echo "0.0.0")
                major=$(echo "$version" | cut -d. -f1)
                minor=$(echo "$version" | cut -d. -f2)
                if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                    PYTHON="$candidate"
                    PYTHON_VERSION="$version"
                    PYTHON_SOURCE="brew"
                    green "  Installed: Python $version (Homebrew)"
                    add_remediation "brew_install"
                    break
                fi
            fi
        done
    fi

    if [ -z "$PYTHON" ]; then
        STEP_PYTHON="fail"
        red "  Python 3.11+ could not be installed."
        echo ""
        echo "  Install manually:"
        dim "    brew install python@3.12"
        dim "    or: https://www.python.org/downloads/"
        echo ""
        fail_step "python_check" "Python 3.11+ not found; brew=$(command -v brew &>/dev/null && echo 'yes' || echo 'no')"
        press_to_exit 1
    fi
fi

STEP_PYTHON="ok"
green "  Found Python $PYTHON_VERSION ($PYTHON_SOURCE)"

# ── Step 2/5: Create virtual environment ─────────────────────────────

step 2 "Creating virtual environment..."

VENV_CREATED=false
if [ -d ".venv" ]; then
    # Verify existing venv is functional
    if [ -x ".venv/bin/python3" ]; then
        green "  Virtual environment already exists"
        VENV_CREATED=true
    else
        add_edge_case "corrupt_venv"
        yellow "  Existing venv is broken, recreating..."
        rm -rf .venv
    fi
fi

if [ "$VENV_CREATED" = false ]; then
    if "$PYTHON" -m venv .venv 2>/dev/null; then
        VENV_CREATED=true
        green "  Virtual environment created"
    else
        add_edge_case "venv_module_failed"
        yellow "  venv module failed, trying virtualenv..."

        if "$PYTHON" -m pip install --user virtualenv 2>/dev/null; then
            if "$PYTHON" -m virtualenv .venv 2>/dev/null; then
                VENV_CREATED=true
                add_remediation "virtualenv_fallback"
                green "  Created with virtualenv"
            fi
        fi
    fi
fi

if [ "$VENV_CREATED" = false ]; then
    STEP_VENV="fail"
    red "  Failed to create virtual environment"
    dim "  Tried: python -m venv, virtualenv"
    fail_step "venv_create" "Both venv and virtualenv failed"
    press_to_exit 1
fi

STEP_VENV="ok"

# ── Step 3/5: Installing packages ────────────────────────────────────

step 3 "Installing packages..."
echo ""

dim "  Upgrading pip..."
.venv/bin/pip install --upgrade pip 2>&1 | while read -r line; do
    printf "\r\033[2m  %s\033[0m\033[K" "$line"
done
printf "\r\033[K"

dim "  Installing obsidian-connector..."
PIP_OK=false

# Attempt 1: normal install (show progress)
if .venv/bin/pip install -e . 2>&1 | while read -r line; do
    printf "\r\033[2m  %s\033[0m\033[K" "$line"
done; then
    printf "\r\033[K"
    PIP_OK=true
fi

# Attempt 2: retry with --no-cache-dir (proxy/cache corruption)
if [ "$PIP_OK" = false ]; then
    add_edge_case "pip_failed_first_attempt"
    yellow "  Retrying with --no-cache-dir..."
    if .venv/bin/pip install --no-cache-dir -e . 2>&1 | while read -r line; do
        printf "\r\033[2m  %s\033[0m\033[K" "$line"
    done; then
        printf "\r\033[K"
        PIP_OK=true
        add_remediation "pip_no_cache_retry"
    fi
fi

# Attempt 3: check if it's a proxy issue
if [ "$PIP_OK" = false ]; then
    if [ -n "${HTTP_PROXY:-}" ] || [ -n "${HTTPS_PROXY:-}" ] || [ -n "${http_proxy:-}" ] || [ -n "${https_proxy:-}" ]; then
        add_edge_case "corporate_proxy"
    fi
    # Try trusted-host flags for corporate SSL inspection
    yellow "  Retrying with trusted hosts..."
    if .venv/bin/pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -e . 2>&1 | while read -r line; do
        printf "\r\033[2m  %s\033[0m\033[K" "$line"
    done; then
        printf "\r\033[K"
        PIP_OK=true
        add_remediation "pip_trusted_host_retry"
    fi
fi

if [ "$PIP_OK" = false ]; then
    STEP_PIP="fail"
    printf "\r\033[K"
    red "  Package installation failed"
    echo ""
    dim "  Try manually: .venv/bin/pip install -e ."
    fail_step "pip_install" "All pip install attempts failed"
    press_to_exit 1
fi

STEP_PIP="ok"
green "  Packages installed"

# ── Step 4/5: Registering with Claude ────────────────────────────────

step 4 "Registering with Claude..."

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

# Detect Claude Code
if command -v claude &>/dev/null; then
    CLAUDE_CODE_PRESENT="true"
    dim "  Claude Code CLI found"
fi

# Detect Claude Desktop
CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

if [ -d "$CLAUDE_CONFIG_DIR" ]; then
    CLAUDE_DESKTOP_PRESENT="true"
    dim "  Claude Desktop found"
fi

if [ "$CLAUDE_CODE_PRESENT" = "false" ] && [ "$CLAUDE_DESKTOP_PRESENT" = "false" ]; then
    STEP_REGISTER="skipped"
    yellow "  Neither Claude Code nor Claude Desktop found"
    dim "  Install Claude Desktop: https://claude.ai/download"
    dim "  After installing, re-run this installer."
else
    REGISTER_OK=false

    if [ "$CLAUDE_DESKTOP_PRESENT" = "true" ]; then
        mkdir -p "$CLAUDE_CONFIG_DIR"

        # Check config write permission
        if ! touch "$CLAUDE_CONFIG_DIR/.write_test" 2>/dev/null; then
            add_edge_case "config_dir_no_write"
            yellow "  Cannot write to Claude config directory"
            dim "  Path: $CLAUDE_CONFIG_DIR"
        else
            rm -f "$CLAUDE_CONFIG_DIR/.write_test"
        fi

        if "$VENV_PYTHON" -c "
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
" 2>/dev/null; then
            green "  Claude Desktop MCP server configured"
            REGISTER_OK=true
        else
            add_edge_case "desktop_config_write_failed"
            yellow "  Could not auto-configure Claude Desktop"

            # Try alternate config location
            ALT_CONFIG="$HOME/.config/claude/claude_desktop_config.json"
            if [ -d "$(dirname "$ALT_CONFIG")" ]; then
                add_remediation "alt_config_location"
                dim "  Trying alternate config location..."
            fi

            dim "  See README.md for manual setup instructions"
        fi
    fi

    if [ "$CLAUDE_CODE_PRESENT" = "true" ]; then
        REGISTER_OK=true
        dim "  Claude Code will auto-detect plugin on next launch"
    fi

    if [ "$REGISTER_OK" = true ]; then
        STEP_REGISTER="ok"
    else
        STEP_REGISTER="fail"
        fail_step "register" "Could not register with Claude Code or Desktop"
    fi
fi

# ── Step 5/5: Verifying installation ─────────────────────────────────

step 5 "Verifying installation..."

verify_fails=0

# Check venv python
if [ -x ".venv/bin/python3" ]; then
    green "  Venv python: OK"
else
    red "  Venv python missing"
    verify_fails=$((verify_fails + 1))
fi

# Check package import
if .venv/bin/python3 -c "import obsidian_connector; print('OK')" 2>/dev/null | grep -q OK; then
    green "  Package import: OK"
else
    red "  Package import failed"
    verify_fails=$((verify_fails + 1))
fi

# Check Obsidian
if pgrep -x "Obsidian" &>/dev/null; then
    green "  Obsidian: running"
else
    dim "  Obsidian: not running (needed to use most tools)"
fi

# Check Desktop config
if [ "$CLAUDE_DESKTOP_PRESENT" = "true" ] && [ -f "$CLAUDE_CONFIG" ]; then
    if .venv/bin/python3 -c "
import json, os
with open(os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json')) as f:
    cfg = json.load(f)
entry = cfg.get('mcpServers', {}).get('obsidian-connector', {})
cmd = entry.get('command', '')
if cmd and os.path.exists(cmd):
    print('OK')
else:
    print('MISSING: ' + cmd)
" 2>/dev/null | grep -q OK; then
        green "  MCP config: OK"
    else
        yellow "  MCP config: command path may not exist"
        verify_fails=$((verify_fails + 1))
    fi
fi

if [ "$verify_fails" -gt 0 ]; then
    STEP_VERIFY="warn"
    yellow "  $verify_fails verification check(s) need attention"
else
    STEP_VERIFY="ok"
fi

# ── Success telemetry ────────────────────────────────────────────────

FINAL_STATUS="success"
send_telemetry "success"

# ── Done ─────────────────────────────────────────────────────────────

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

if [ -n "$EDGE_CASES" ]; then
    echo ""
    dim "  Edge cases detected: $EDGE_CASES"
fi
if [ -n "$REMEDIATIONS" ]; then
    dim "  Auto-fixes applied: $REMEDIATIONS"
fi

elapsed=$(( $(date +%s) - INSTALL_START ))
dim "  Completed in ${elapsed}s"
echo ""

press_to_exit 0
