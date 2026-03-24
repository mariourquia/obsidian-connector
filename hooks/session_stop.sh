#!/usr/bin/env bash
# session_stop.sh -- Auto-sync vault on Claude Code session end.
#
# Runs as a Stop hook. Debounced: only syncs if the last sync was
# more than 10 minutes ago. Runs in background to avoid blocking.
# Timeout: 30 seconds max.

set -o pipefail

VAULT_CANDIDATES=(
  "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/creation/creation"
  "$HOME/.obsidian-vaults/creation"
  "$HOME/Documents/obsidian/creation"
)

# Find the vault
VAULT=""
for candidate in "${VAULT_CANDIDATES[@]}"; do
  if [[ -d "$candidate" ]]; then
    VAULT="$candidate"
    break
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

# Check if the sync script exists
SYNC_SCRIPT="$HOME/.local/bin/sync-creation-vault"
if [[ ! -x "$SYNC_SCRIPT" ]]; then
  # Try plugin's Python sync as fallback
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"
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
  exit 0
fi

# Run sync in background with 30-second timeout
timeout 30 "$SYNC_SCRIPT" >/dev/null 2>&1 &

exit 0
