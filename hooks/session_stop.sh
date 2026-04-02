#!/usr/bin/env bash
# session_stop.sh -- Auto-sync vault on Claude Code session end.
#
# Runs as a Stop hook. Debounced: only syncs if the last sync was
# more than 10 minutes ago. Runs in background to avoid blocking.
# Timeout: 30 seconds max.

set -o pipefail

# Resolve vault from config.json if available, then fall back to common locations.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CONFIG_VAULT=""
if [ -f "$PLUGIN_ROOT/config.json" ]; then
  CONFIG_VAULT=$(python3 -c "
import json, sys, os
try:
    with open('$PLUGIN_ROOT/config.json') as f:
        v = json.load(f).get('default_vault', '')
    if v:
        print(os.path.expanduser(v))
except Exception:
    pass
" 2>/dev/null)
fi

VAULT_CANDIDATES=()
# Config-specified vault gets priority
if [ -n "$CONFIG_VAULT" ] && [ -d "$CONFIG_VAULT" ]; then
  VAULT_CANDIDATES+=("$CONFIG_VAULT")
fi
# Platform-aware fallback candidates
VAULT_CANDIDATES+=(
  "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents"
  "$HOME/.obsidian-vaults"
  "$HOME/Documents/Obsidian"
)

# Find the vault -- if a candidate is a parent directory containing vaults,
# look for subdirectories that contain an .obsidian/ folder.
VAULT=""
for candidate in "${VAULT_CANDIDATES[@]}"; do
  if [[ -d "$candidate/.obsidian" ]]; then
    # Direct vault directory
    VAULT="$candidate"
    break
  elif [[ -d "$candidate" ]]; then
    # Parent directory -- find first child with .obsidian/
    for sub in "$candidate"/*/; do
      if [[ -d "${sub}.obsidian" ]]; then
        VAULT="${sub%/}"
        break
      fi
    done
    [[ -n "$VAULT" ]] && break
  fi
done

[[ -z "$VAULT" ]] && exit 0  # No vault found, skip silently

# Debounce: only sync if last sync was >10 minutes ago
LAST_SYNC_FILE="$VAULT/.last-sync"
if [[ -f "$LAST_SYNC_FILE" ]]; then
  last_sync_epoch=$(date -j -f "%Y-%m-%d %H:%M" "$(cat "$LAST_SYNC_FILE")" "+%s" 2>/dev/null || echo "0")
  now_epoch=$(date "+%s")
  elapsed=$(( now_epoch - last_sync_epoch ))
  if [[ $elapsed -lt 600 ]]; then
    # Less than 10 minutes since last sync, skip
    exit 0
  fi
fi

# Use the plugin's Python sync (preferred), or fall back to a user-installed
# sync script if one exists on PATH.
PYTHON="$PLUGIN_ROOT/.venv/bin/python3"
if [[ -x "$PYTHON" ]]; then
  timeout 30 "$PYTHON" -c "
from obsidian_connector.project_sync import sync_projects
try:
    sync_projects()
except Exception:
    pass
" >/dev/null 2>&1 &
  exit 0
fi

# Fallback: check for a user-installed sync script on PATH
SYNC_SCRIPT=""
if command -v obsx &>/dev/null; then
  SYNC_SCRIPT="$(command -v obsx)"
fi

if [[ -z "$SYNC_SCRIPT" ]]; then
  exit 0
fi

# Run user-installed sync script in background with 30-second timeout
timeout 30 "$SYNC_SCRIPT" sync-projects >/dev/null 2>&1 &

exit 0
