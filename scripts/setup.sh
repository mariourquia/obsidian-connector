#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# obsidian-connector plugin setup
#
# Creates the Python venv and installs dependencies.
# Run this after installing the plugin via `claude plugin install`.
#
# Usage:
#   bash <plugin-dir>/scripts/setup.sh
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
dim()   { printf '\033[2m%s\033[0m\n' "$*"; }
die()   { red "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

bold "obsidian-connector plugin setup"
dim  "plugin root: $PLUGIN_ROOT"
echo ""

# ── Check Python ────────────────────────────────────────────────────
bold "[1/3] Checking Python..."

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
    die "Python 3.11+ is required. Install from https://www.python.org/downloads/"
fi
green "  Found $PYTHON ($($PYTHON --version))"

# ── Create venv ─────────────────────────────────────────────────────
bold "[2/3] Setting up Python environment..."

if [ ! -d "$PLUGIN_ROOT/.venv" ]; then
    "$PYTHON" -m venv "$PLUGIN_ROOT/.venv"
    dim "  Created .venv"
else
    dim "  .venv already exists"
fi

"$PLUGIN_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$PLUGIN_ROOT/.venv/bin/pip" install --quiet -e "${PLUGIN_ROOT}[tui]"

green "  Installed obsidian-connector + dashboard dependencies"

# ── Verify ──────────────────────────────────────────────────────────
bold "[3/3] Verifying..."

if "$PLUGIN_ROOT/.venv/bin/python3" -c "import obsidian_connector; print('  Package OK')" 2>/dev/null; then
    green "  Setup complete!"
else
    die "Package import failed."
fi

echo ""
bold "Next steps:"
echo "  1. Make sure Obsidian is running"
echo "  2. Restart Claude Code"
echo "  3. The obsidian-connector MCP tools and skills will be available"
echo ""
dim "Health check: $PLUGIN_ROOT/bin/obsx doctor"
