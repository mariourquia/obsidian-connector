#!/usr/bin/env bash
# obsidian-connector SessionStart hook
# Checks time of day and suggests the appropriate workflow.
# Called by Claude Code at session start via hooks/hooks.json (plugin mode)
# or .claude/settings.json (standalone mode).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OBSX="$REPO_ROOT/bin/obsx"

# Bail silently if obsx isn't available
if [ ! -x "$OBSX" ]; then
    exit 0
fi

# Get check-in data as JSON (10s timeout prevents blocking session start
# if Obsidian IPC hangs; the CLI's own 30s timeout is too long for a hook)
if command -v timeout &>/dev/null; then
    CHECKIN=$(timeout 10 "$OBSX" --json check-in 2>/dev/null) || exit 0
else
    CHECKIN=$("$OBSX" --json check-in 2>/dev/null) || exit 0
fi

# Parse with python (available since we need python for the connector anyway)
python3 -c "
import json, sys

data = json.loads(sys.stdin.read())
if not data.get('ok'):
    sys.exit(0)

d = data.get('data', data)
time_of_day = d.get('time_of_day', '')
pending = d.get('pending_rituals', [])
delegations = d.get('pending_delegations', 0)
drafts = d.get('unreviewed_drafts', 0)
loops = d.get('open_loop_count', 0)

parts = []

if time_of_day == 'morning' and 'morning_briefing' in pending:
    parts.append('Morning -- briefing not yet run. Type /morning to start your day.')
elif time_of_day == 'evening' and 'evening_close' in pending:
    parts.append('Evening -- day not yet closed. Type /evening to wrap up.')

if delegations > 0:
    parts.append(f'{delegations} pending delegation(s) in your vault.')
if drafts > 0:
    parts.append(f'{drafts} agent draft(s) awaiting review.')

# Only show if there is something actionable
if parts:
    print(' '.join(parts))
" <<< "$CHECKIN" 2>/dev/null || true
