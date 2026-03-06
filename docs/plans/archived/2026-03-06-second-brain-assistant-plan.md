---
title: "Second Brain Assistant Implementation Plan"
status: deprecated
replaced_by: main
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Second Brain Assistant Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform obsidian-connector from passive tool into proactive second brain assistant with check_in tool, 4 skills, SessionStart hook, scheduled automation, Desktop system prompt, and documentation rewrite.

**Architecture:** Three layers -- execution (1 new MCP tool), orchestration (4 Claude Code skills), proactive (hook + launchd + Desktop system prompt). The check_in tool is the universal brain that works in both CLI and Desktop environments. Scheduled jobs call Python directly (no LLM). Skills orchestrate MCP tools for interactive workflows.

**Tech Stack:** Python 3.11+, FastMCP, argparse, launchd (macOS), osascript (notifications)

---

### Task 1: check_in function in workflows.py

**Files:**
- Modify: `obsidian_connector/workflows.py` (append after existing workflows, ~line 500+)
- Test: `scripts/checkin_test.py`

**Step 1: Write the test**

Create `scripts/checkin_test.py`:

```python
#!/usr/bin/env python3
"""check_in workflow tests."""

from __future__ import annotations

import sys
import traceback

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from obsidian_connector.workflows import check_in

PASS = 0
FAIL = 0


def assert_eq(label, actual, expected):
    global PASS, FAIL
    if actual == expected:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: expected {expected!r}, got {actual!r}")
        FAIL += 1


def assert_in(label, value, container):
    global PASS, FAIL
    if value in container:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: {value!r} not in {container!r}")
        FAIL += 1


def assert_type(label, value, expected_type):
    global PASS, FAIL
    if isinstance(value, expected_type):
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}: expected {expected_type.__name__}, got {type(value).__name__}")
        FAIL += 1


def main() -> int:
    print("=" * 60)
    print("TEST: check_in returns structured result")
    print("=" * 60)

    try:
        result = check_in()
    except Exception as exc:
        print(f"  FAIL  check_in() raised {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        return 1

    # Structure checks
    assert_type("result is dict", result, dict)
    assert_in("has time_of_day", "time_of_day", result)
    assert_in("time_of_day valid", result.get("time_of_day"), ["morning", "midday", "evening", "night"])
    assert_in("has daily_note_exists", "daily_note_exists", result)
    assert_type("daily_note_exists is bool", result.get("daily_note_exists"), bool)
    assert_in("has completed_rituals", "completed_rituals", result)
    assert_type("completed_rituals is list", result.get("completed_rituals"), list)
    assert_in("has pending_rituals", "pending_rituals", result)
    assert_type("pending_rituals is list", result.get("pending_rituals"), list)
    assert_in("has pending_delegations", "pending_delegations", result)
    assert_type("pending_delegations is int", result.get("pending_delegations"), int)
    assert_in("has unreviewed_drafts", "unreviewed_drafts", result)
    assert_type("unreviewed_drafts is int", result.get("unreviewed_drafts"), int)
    assert_in("has open_loop_count", "open_loop_count", result)
    assert_type("open_loop_count is int", result.get("open_loop_count"), int)
    assert_in("has suggestion", "suggestion", result)
    assert_type("suggestion is str", result.get("suggestion"), str)

    # Ritual logic: completed + pending should cover both rituals
    all_rituals = set(result["completed_rituals"] + result["pending_rituals"])
    assert_eq("morning_briefing accounted for", "morning_briefing" in all_rituals, True)
    assert_eq("evening_close accounted for", "evening_close" in all_rituals, True)

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Run test to verify it fails**

Run: `python3 scripts/checkin_test.py`
Expected: FAIL with `ImportError: cannot import name 'check_in' from 'obsidian_connector.workflows'`

**Step 3: Write the check_in function**

Append to `obsidian_connector/workflows.py` after the existing workflow functions:

```python
# ---------------------------------------------------------------------------
# Check-in (proactive assistant brain)
# ---------------------------------------------------------------------------

_RITUAL_SENTINELS = {
    "morning_briefing": "## Morning Briefing",
    "evening_close": "## Day Close",
}


def check_in(
    vault: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    """Time-aware check-in: what should the user do now?

    Reads the daily note, checks which rituals have run, counts open
    loops and pending delegations, and returns a structured suggestion.

    Parameters
    ----------
    vault:
        Target vault name.
    timezone_name:
        IANA timezone (e.g. "America/New_York"). Falls back to local time.

    Returns
    -------
    dict
        Keys: time_of_day, daily_note_exists, completed_rituals,
        pending_rituals, pending_delegations, unreviewed_drafts,
        open_loop_count, suggestion.
    """
    from zoneinfo import ZoneInfo

    # -- Determine time of day ------------------------------------------------
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
        except (KeyError, Exception):
            tz = None
    else:
        tz = None

    now = datetime.now(tz or timezone.utc)
    if tz is None:
        now = datetime.now()  # naive local time
    hour = now.hour

    if hour < 11:
        time_of_day = "morning"
    elif hour < 16:
        time_of_day = "midday"
    elif hour < 20:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    # -- Read today's daily note ----------------------------------------------
    daily_content = ""
    daily_note_exists = False
    try:
        brief = today_brief(vault=vault)
        daily_content = brief.get("daily_note", "") or ""
        daily_note_exists = bool(daily_content)
    except ObsidianCLIError:
        pass

    # -- Check completed rituals via sentinel headings ------------------------
    completed_rituals: list[str] = []
    pending_rituals: list[str] = []
    for ritual, sentinel in _RITUAL_SENTINELS.items():
        if sentinel in daily_content:
            completed_rituals.append(ritual)
        else:
            pending_rituals.append(ritual)

    # -- Count open loops -----------------------------------------------------
    open_loop_count = 0
    try:
        loops = list_open_loops(vault=vault)
        open_loop_count = len(loops)
    except ObsidianCLIError:
        pass

    # -- Count pending delegations --------------------------------------------
    pending_delegations = 0
    try:
        delegations = detect_delegations(vault=vault)
        pending_delegations = len([d for d in delegations if d.get("status") != "done"])
    except ObsidianCLIError:
        pass

    # -- Count unreviewed agent drafts ----------------------------------------
    unreviewed_drafts = 0
    try:
        cfg = load_config()
        vault_path = resolve_vault_path(vault)
        if vault_path:
            drafts_dir = os.path.join(vault_path, "Inbox", "Agent Drafts")
            if os.path.isdir(drafts_dir):
                unreviewed_drafts = len([
                    f for f in os.listdir(drafts_dir)
                    if f.endswith(".md")
                ])
    except Exception:
        pass

    # -- Build suggestion -----------------------------------------------------
    parts: list[str] = []

    if time_of_day == "morning" and "morning_briefing" in pending_rituals:
        parts.append("Morning briefing hasn't run yet.")
    if time_of_day == "evening" and "evening_close" in pending_rituals:
        parts.append("Evening close hasn't run yet.")
    if pending_delegations > 0:
        parts.append(f"{pending_delegations} pending delegation{'s' if pending_delegations != 1 else ''}.")
    if unreviewed_drafts > 0:
        parts.append(f"{unreviewed_drafts} unreviewed agent draft{'s' if unreviewed_drafts != 1 else ''}.")
    if open_loop_count > 5:
        parts.append(f"{open_loop_count} open loops -- consider triaging.")
    elif open_loop_count > 0:
        parts.append(f"{open_loop_count} open loop{'s' if open_loop_count != 1 else ''}.")

    if not parts:
        parts.append("All caught up.")

    suggestion = " ".join(parts)

    return {
        "time_of_day": time_of_day,
        "daily_note_exists": daily_note_exists,
        "completed_rituals": completed_rituals,
        "pending_rituals": pending_rituals,
        "pending_delegations": pending_delegations,
        "unreviewed_drafts": unreviewed_drafts,
        "open_loop_count": open_loop_count,
        "suggestion": suggestion,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 scripts/checkin_test.py`
Expected: All assertions PASS

**Step 5: Commit**

```bash
git add obsidian_connector/workflows.py scripts/checkin_test.py
git commit -m "feat: add check_in workflow function

Time-aware function that reads daily note, checks ritual completion,
counts open loops/delegations/drafts, returns structured suggestion."
```

---

### Task 2: Export check_in from __init__.py

**Files:**
- Modify: `obsidian_connector/__init__.py`

**Step 1: Add check_in to imports and __all__**

In the imports from workflows (line 40-55), add `check_in`:
```python
from obsidian_connector.workflows import (
    challenge_belief,
    check_in,           # <-- add
    close_day_reflection,
    ...
)
```

In `__all__` (line 57-103), add `"check_in"` in alphabetical position:
```python
__all__ = [
    ...
    "challenge_belief",
    "check_in",         # <-- add
    "close_day_reflection",
    ...
]
```

**Step 2: Verify import works**

Run: `python3 -c "from obsidian_connector import check_in; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add obsidian_connector/__init__.py
git commit -m "feat: export check_in from package"
```

---

### Task 3: Add check_in MCP tool

**Files:**
- Modify: `obsidian_connector/mcp_server.py` (add after last @mcp.tool, ~line 1017+)

**Step 1: Add import**

In the imports from workflows (line 35-50), add `check_in`:
```python
from obsidian_connector.workflows import (
    challenge_belief,
    check_in,           # <-- add
    close_day_reflection,
    ...
)
```

**Step 2: Add the MCP tool**

Append after the last existing `@mcp.tool()` function:

```python
@mcp.tool(
    title="Check In",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_check_in(
    vault: str | None = None,
    timezone: str | None = None,
) -> str:
    """Time-aware check-in: what should you do now?

    Call this at the start of a conversation. Returns what time of day
    it is, which daily rituals have already run, how many open loops and
    delegations are pending, and a suggested next action.

    Use the suggestion to proactively offer the user their morning
    briefing, evening close, or other relevant workflow.
    """
    try:
        result = check_in(vault=vault, timezone_name=timezone)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
```

**Step 3: Test MCP server launches**

Run: `bash scripts/mcp_launch_smoke.sh`
Expected: Server launches without import errors

**Step 4: Commit**

```bash
git add obsidian_connector/mcp_server.py
git commit -m "feat: add obsidian_check_in MCP tool

Time-aware tool for proactive assistant behavior. Returns ritual
status, open loops, delegations, and suggested next action."
```

---

### Task 4: Add check-in CLI command

**Files:**
- Modify: `obsidian_connector/cli.py`

**Step 1: Add import**

In the imports from workflows (line 35-50), add `check_in`:
```python
from obsidian_connector.workflows import (
    challenge_belief,
    check_in,           # <-- add
    close_day_reflection,
    ...
)
```

**Step 2: Add human-readable formatter**

Add after existing formatters (~line 670):

```python
def _fmt_check_in(data: dict) -> str:
    """Human-readable check-in output."""
    lines: list[str] = []
    lines.append(f"Time: {data.get('time_of_day', '?')}")
    lines.append(f"Daily note: {'exists' if data.get('daily_note_exists') else 'not found'}")

    completed = data.get("completed_rituals", [])
    if completed:
        lines.append(f"Completed: {', '.join(completed)}")

    pending = data.get("pending_rituals", [])
    if pending:
        lines.append(f"Pending: {', '.join(pending)}")

    loops = data.get("open_loop_count", 0)
    if loops:
        lines.append(f"Open loops: {loops}")

    delegations = data.get("pending_delegations", 0)
    if delegations:
        lines.append(f"Pending delegations: {delegations}")

    drafts = data.get("unreviewed_drafts", 0)
    if drafts:
        lines.append(f"Unreviewed drafts: {drafts}")

    suggestion = data.get("suggestion", "")
    if suggestion:
        lines.append(f"\n{suggestion}")

    return "\n".join(lines)
```

**Step 3: Add subcommand parser**

Add in `build_parser()` after the last existing subcommand:

```python
    # -- check-in ----------------------------------------------------------
    p = sub.add_parser("check-in", help="Time-aware check-in: what should you do now?")
    p.add_argument("--timezone", default=None, help="IANA timezone (e.g. America/New_York).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")
```

**Step 4: Add command handler**

Add in the `main()` function's command dispatch (follow existing pattern):

```python
    elif args.command == "check-in":
        t0 = time.time()
        data = check_in(vault=vault, timezone_name=args.timezone)
        elapsed = int((time.time() - t0) * 1000)
        if as_json:
            print(format_output(success_envelope("check-in", data, vault, elapsed), True))
        else:
            print(_fmt_check_in(data))
```

**Step 5: Test CLI**

Run: `./bin/obsx check-in`
Expected: Human-readable check-in output with time of day and suggestion

Run: `./bin/obsx --json check-in`
Expected: JSON envelope with full structured data

**Step 6: Commit**

```bash
git add obsidian_connector/cli.py
git commit -m "feat: add check-in CLI command (obsx check-in)

Human-readable and JSON output modes. Supports --timezone override."
```

---

### Task 5: Update TOOLS_CONTRACT.md

**Files:**
- Modify: `TOOLS_CONTRACT.md`

**Step 1: Add check_in to Workflow OS table**

In the "Workflow OS" section (~line 61), add a new row:

```markdown
| `obsidian_check_in` | `vault?`, `timezone?` | JSON `{time_of_day, daily_note_exists, completed_rituals[], pending_rituals[], pending_delegations, unreviewed_drafts, open_loop_count, suggestion}` |
```

**Step 2: Add check-in to CLI commands table**

In the CLI commands section (~line 82), add:

```markdown
| `check-in` | Time-aware check-in with suggestions | no |
```

**Step 3: Update tool/command counts**

Update "27 tools" to "28 tools" in the MCP section header and "26 total" to "27 total" in the CLI section header.

**Step 4: Commit**

```bash
git add TOOLS_CONTRACT.md
git commit -m "docs: add check_in to TOOLS_CONTRACT.md"
```

---

### Task 6: Create /morning skill

**Files:**
- Create: `skills/morning.md`

**Step 1: Create skills directory**

Run: `mkdir -p skills`

**Step 2: Write the skill file**

Create `skills/morning.md`:

```markdown
---
name: morning
description: Run your morning briefing. Reads daily note, surfaces open loops and delegations, writes a briefing to your vault.
---

# Morning Briefing

You are running the user's morning briefing workflow. Follow these steps exactly.

## Step 1: Check in

Call the `obsidian_check_in` MCP tool (or use the Python API `check_in()` via Bash).

- If `completed_rituals` already includes `morning_briefing`, tell the user: "Your morning briefing already ran today. Want me to run it again?" If they say no, stop.
- Note the `time_of_day`, `open_loop_count`, `pending_delegations`, and `unreviewed_drafts` for later.

## Step 2: Read today's state

Call these tools (in parallel if possible):
1. `obsidian_today` -- get the daily note content and open tasks
2. `obsidian_open_loops` -- get all open loops
3. `obsidian_delegations` -- get pending @claude: instructions

## Step 3: Synthesize the briefing

Compose a conversational briefing covering:
- **Date and time context** (e.g. "It's Tuesday morning")
- **Daily note summary** -- what's already on today's note
- **Open tasks** -- count and top 5 most important
- **Open loops** -- count and the ones that seem most urgent
- **Pending delegations** -- any @claude: instructions to act on
- **Unreviewed drafts** -- any agent drafts waiting for review

Keep it concise. Lead with the most actionable items.

## Step 4: Write to vault

Call `obsidian_log_daily` with the briefing formatted as:

```
## Morning Briefing
**Generated:** {timestamp}

{briefing content}
```

This sentinel heading (`## Morning Briefing`) is how the system knows the briefing has run.

## Step 5: Offer interaction

After presenting the briefing, ask:
"Anything you want to triage, capture, or change before starting your day?"

If the user responds:
- **Defer a task**: Log a note about deferral to the daily note
- **Log an idea**: Call `obsidian_log_daily` with the idea
- **Act on a delegation**: Execute the delegation instruction
- **Create a note**: Call `obsidian_create_note`
- **Nothing**: Wish them a good day and end
```

**Step 3: Commit**

```bash
git add skills/morning.md
git commit -m "feat: add /morning skill for daily briefing workflow"
```

---

### Task 7: Create /evening skill

**Files:**
- Create: `skills/evening.md`

**Step 1: Write the skill file**

Create `skills/evening.md`:

```markdown
---
name: evening
description: Close your day. Reviews what you accomplished, surfaces remaining loops, and offers to graduate ideas.
---

# Evening Close

You are running the user's evening close workflow. Follow these steps exactly.

## Step 1: Check in

Call `obsidian_check_in`.

- If `completed_rituals` already includes `evening_close`, tell the user: "Your evening close already ran today. Want me to run it again?" If they say no, stop.

## Step 2: Review the day

Call these tools (in parallel if possible):
1. `obsidian_close_day` -- get day's activity, completed/remaining tasks, reflection prompts
2. `obsidian_graduate_candidates` with `lookback_days=1` -- ideas from today worth promoting

## Step 3: Synthesize the close

Compose a reflection covering:
- **What got done** -- completed tasks and key daily note entries
- **What's still open** -- remaining tasks and open loops
- **What to carry forward** -- suggest 1-3 items for tomorrow
- **Reflection prompts** -- present the reflection prompts from close_day
- **Graduate candidates** -- if any ideas are worth promoting, list them

## Step 4: Write to vault

Call `obsidian_log_daily` with the close formatted as:

```
## Day Close
**Generated:** {timestamp}

{close content}
```

## Step 5: Offer graduation

If graduate candidates were found:
"These ideas from today look worth promoting to standalone notes: {list}. Want me to graduate any of them?"

If the user says yes, call `obsidian_graduate_execute` for each selected idea.

## Step 6: End

"Day closed. Rest well."
```

**Step 2: Commit**

```bash
git add skills/evening.md
git commit -m "feat: add /evening skill for end-of-day close workflow"
```

---

### Task 8: Create /idea skill

**Files:**
- Create: `skills/idea.md`

**Step 1: Write the skill file**

Create `skills/idea.md`:

```markdown
---
name: idea
description: Quickly capture an idea to your daily note. Surfaces related context if found.
---

# Quick Idea Capture

You are capturing an idea for the user. This should be fast -- two seconds from thought to vault.

## Step 1: Parse the idea

The user's argument is the idea text. If no argument was provided, ask: "What's the idea?"

## Step 2: Log to daily note

Call `obsidian_log_daily` with:

```
- {HH:MM} {idea text}
```

Use the current time (24h format). Keep the format simple and scannable.

## Step 3: Surface related context (optional, fast)

If the idea mentions a recognizable topic (a project name, a domain, a person):
- Call `obsidian_search` with the most distinctive keyword from the idea
- If results come back, briefly mention: "Related: {note1}, {note2}. Want me to expand this into a research note?"

If no clear topic, skip this step. Speed matters more than completeness.

## Step 4: Confirm

"Logged." (Keep it brief. The user is in flow.)

If you surfaced related notes and the user wants to expand:
- Call `obsidian_create_note` with an appropriate template
- Or call `obsidian_log_daily` with a more detailed entry
```

**Step 2: Commit**

```bash
git add skills/idea.md
git commit -m "feat: add /idea skill for quick idea capture"
```

---

### Task 9: Create /weekly skill

**Files:**
- Create: `skills/weekly.md`

**Step 1: Write the skill file**

Create `skills/weekly.md`:

```markdown
---
name: weekly
description: Run your weekly review. Checks drift, graduates ideas, audits vault health.
---

# Weekly Review

You are running the user's weekly review. This is a longer, more reflective workflow.

## Step 1: Context load

Call `obsidian_check_in` to get current state.

## Step 2: Drift analysis

Call `obsidian_drift` with:
- `lookback_days=7`
- For the `intention` parameter, check if the user has stated intentions in their vault. Search for "intention" or "goal" or "commitment" in recent notes. If found, use those. If not, ask the user: "What were your intentions for this week?"

Present the drift analysis: coverage percentage, gaps, surprises.

## Step 3: Idea graduation

Call `obsidian_graduate_candidates` with `lookback_days=7`.

If candidates found, present them and ask which to promote.
For each approved candidate, call `obsidian_graduate_execute`.

## Step 4: Vault health

Call `obsidian_vault_structure`.

Report:
- Orphan count (notes with no links in or out)
- Dead ends (linked but nonexistent notes)
- Top connected hubs

If orphan count is high, suggest linking strategies.

## Step 5: Write weekly summary

Call `obsidian_log_daily` with a summary section:

```
## Weekly Review
**Week of:** {date range}

### Drift
{drift summary}

### Graduated Ideas
{list of graduated notes, or "None this week"}

### Vault Health
{orphan count, dead ends, action items}

### Intentions for Next Week
{ask user or carry forward}
```

## Step 6: Set next week's intentions

Ask: "What are your intentions for next week?"

Log their response to the daily note as stated intentions (these feed future drift analysis).
```

**Step 2: Commit**

```bash
git add skills/weekly.md
git commit -m "feat: add /weekly skill for weekly review workflow"
```

---

### Task 10: Create SessionStart hook

**Files:**
- Create: `hooks/session_start.sh`

**Step 1: Create hooks directory**

Run: `mkdir -p hooks`

**Step 2: Write the hook script**

Create `hooks/session_start.sh`:

```bash
#!/usr/bin/env bash
# obsidian-connector SessionStart hook
# Checks time of day and suggests the appropriate workflow.
# Called by Claude Code at session start via settings.json hook config.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OBSX="$REPO_ROOT/bin/obsx"

# Bail silently if obsx isn't available
if [ ! -x "$OBSX" ]; then
    exit 0
fi

# Get check-in data as JSON
CHECKIN=$("$OBSX" --json check-in 2>/dev/null) || exit 0

# Parse with python (available since we need python for the connector anyway)
python3 -c "
import json, sys

data = json.loads('''$CHECKIN''')
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

# Only show if there's something actionable
if parts:
    print(' '.join(parts))
" 2>/dev/null || true
```

**Step 3: Make executable**

Run: `chmod +x hooks/session_start.sh`

**Step 4: Test the hook**

Run: `bash hooks/session_start.sh`
Expected: Either a suggestion line or silent exit (depending on vault state)

**Step 5: Commit**

```bash
git add hooks/session_start.sh
git commit -m "feat: add SessionStart hook for proactive workflow suggestions

Checks time of day and vault state, suggests /morning or /evening
when appropriate. Silent when everything is caught up."
```

---

### Task 11: Create scheduled automation

**Files:**
- Create: `scheduling/config.yaml`
- Create: `scheduling/run_scheduled.py`
- Create: `scheduling/com.obsidian-connector.daily.plist`
- Create: `scheduling/README.md`

**Step 1: Create scheduling directory**

Run: `mkdir -p scheduling`

**Step 2: Write config.yaml**

Create `scheduling/config.yaml`:

```yaml
# obsidian-connector scheduling configuration
# Copy to ~/.config/obsidian-connector/schedule.yaml and customize.

timezone: America/New_York

morning:
  enabled: true
  time: "08:00"

evening:
  enabled: true
  time: "18:00"

weekly:
  enabled: true
  day: sunday
  time: "09:00"

notification:
  enabled: true
  method: osascript        # osascript (built-in) or terminal-notifier
  open_on_click: obsidian  # obsidian or claude
```

**Step 3: Write run_scheduled.py**

Create `scheduling/run_scheduled.py`:

```python
#!/usr/bin/env python3
"""Headless scheduled runner for obsidian-connector.

Calls Python API directly (no LLM needed). Writes structured output
to the daily note and sends a macOS notification.

Usage:
    python3 scheduling/run_scheduled.py morning
    python3 scheduling/run_scheduled.py evening
    python3 scheduling/run_scheduled.py weekly
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.client import ObsidianCLIError, log_to_daily
from obsidian_connector.workflows import (
    check_in,
    close_day_reflection,
    detect_delegations,
    graduate_candidates,
    list_open_loops,
    today_brief,
)


def load_config() -> dict:
    """Load schedule config from default locations."""
    import yaml

    candidates = [
        Path.home() / ".config" / "obsidian-connector" / "schedule.yaml",
        Path(__file__).resolve().parent / "config.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


def notify(title: str, message: str, config: dict) -> None:
    """Send a macOS notification."""
    notif_config = config.get("notification", {})
    if not notif_config.get("enabled", True):
        return

    method = notif_config.get("method", "osascript")
    if method == "osascript":
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
    elif method == "terminal-notifier":
        subprocess.run(
            ["terminal-notifier", "-title", title, "-message", message],
            capture_output=True,
        )


def run_morning(config: dict) -> None:
    """Generate and write morning briefing to daily note."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        brief = today_brief()
    except ObsidianCLIError:
        brief = {}

    try:
        loops = list_open_loops()
    except ObsidianCLIError:
        loops = []

    try:
        delegations = detect_delegations()
        pending = [d for d in delegations if d.get("status") != "done"]
    except ObsidianCLIError:
        pending = []

    # Build briefing
    parts = [f"## Morning Briefing", f"**Generated:** {ts}", ""]

    tasks = brief.get("open_tasks", [])
    if tasks:
        parts.append(f"**Open tasks:** {len(tasks)}")
        for t in tasks[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        if len(tasks) > 5:
            parts.append(f"- ... and {len(tasks) - 5} more")
        parts.append("")

    if loops:
        parts.append(f"**Open loops:** {len(loops)}")
        for loop in loops[:5]:
            parts.append(f"- {loop.get('text', '').strip()}")
        if len(loops) > 5:
            parts.append(f"- ... and {len(loops) - 5} more")
        parts.append("")

    if pending:
        parts.append(f"**Pending delegations:** {len(pending)}")
        for d in pending[:3]:
            parts.append(f"- {d.get('instruction', '').strip()}")
        parts.append("")

    if not tasks and not loops and not pending:
        parts.append("Clean slate. Nothing carried over.")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        notify("Morning Briefing", f"{len(tasks)} tasks, {len(loops)} loops", config)
        print(f"Morning briefing written ({len(tasks)} tasks, {len(loops)} loops)")
    except ObsidianCLIError as exc:
        print(f"Error writing briefing: {exc}", file=sys.stderr)
        sys.exit(1)


def run_evening(config: dict) -> None:
    """Generate and write evening close to daily note."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        close = close_day_reflection()
    except ObsidianCLIError:
        close = {}

    parts = [f"## Day Close", f"**Generated:** {ts}", ""]

    done = close.get("completed_tasks", [])
    if done:
        parts.append(f"**Completed:** {len(done)} tasks")
        for t in done[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        parts.append("")

    remaining = close.get("remaining_tasks", [])
    if remaining:
        parts.append(f"**Remaining:** {len(remaining)} tasks")
        for t in remaining[:5]:
            parts.append(f"- {t.get('text', '').strip()}")
        parts.append("")

    prompts = close.get("reflection_prompts", [])
    if prompts:
        parts.append("**Reflect:**")
        for p in prompts:
            parts.append(f"- {p}")
        parts.append("")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        notify("Day Closed", f"{len(done)} done, {len(remaining)} remaining", config)
        print(f"Evening close written ({len(done)} done, {len(remaining)} remaining)")
    except ObsidianCLIError as exc:
        print(f"Error writing close: {exc}", file=sys.stderr)
        sys.exit(1)


def run_weekly(config: dict) -> None:
    """Generate and write weekly review to daily note."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        candidates = graduate_candidates(lookback_days=7)
    except ObsidianCLIError:
        candidates = []

    try:
        loops = list_open_loops()
    except ObsidianCLIError:
        loops = []

    parts = [f"## Weekly Review", f"**Generated:** {ts}", ""]

    if candidates:
        parts.append(f"**Graduate candidates:** {len(candidates)} ideas worth promoting")
        for c in candidates:
            parts.append(f"- {c.get('title', '?')}")
        parts.append("")

    if loops:
        parts.append(f"**Open loops:** {len(loops)} total")
        parts.append("")

    content = "\n".join(parts)

    try:
        log_to_daily(content)
        notify("Weekly Review", f"{len(candidates)} ideas, {len(loops)} loops", config)
        print(f"Weekly review written ({len(candidates)} candidates, {len(loops)} loops)")
    except ObsidianCLIError as exc:
        print(f"Error writing review: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="obsidian-connector scheduled runner")
    parser.add_argument("workflow", choices=["morning", "evening", "weekly"])
    args = parser.parse_args()

    config = load_config()

    if args.workflow == "morning":
        run_morning(config)
    elif args.workflow == "evening":
        run_evening(config)
    elif args.workflow == "weekly":
        run_weekly(config)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Write launchd plist**

Create `scheduling/com.obsidian-connector.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obsidian-connector.daily</string>

    <key>ProgramArguments</key>
    <array>
        <!-- Updated by install.sh to use the correct python path -->
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>__REPO_ROOT__/scheduling/run_scheduled.py</string>
        <string>morning</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <!-- Morning briefing at 08:00 -->
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>/tmp/obsidian-connector-morning.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/obsidian-connector-morning.err</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Note: The install script will generate separate plists for morning, evening, and weekly with correct paths. This is the template.

**Step 5: Write scheduling README**

Create `scheduling/README.md`:

```markdown
# Scheduled Automation

The obsidian-connector can run morning briefings, evening closes, and weekly
reviews automatically using macOS launchd.

## How it works

1. A launchd agent fires at configured times (default: 8am, 6pm, Sunday 9am)
2. `run_scheduled.py` calls the Python API directly (no LLM, no API calls)
3. A structured summary is written to your daily note
4. A macOS notification tells you it ran

## Setup

Run the installer with scheduling enabled:

```bash
./scripts/install.sh --with-scheduling
```

Or manually:

1. Copy `config.yaml` to `~/.config/obsidian-connector/schedule.yaml`
2. Edit times and timezone
3. Install the launchd agents:

```bash
# Morning
cp scheduling/com.obsidian-connector.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```

## Configuration

Edit `~/.config/obsidian-connector/schedule.yaml`:

```yaml
timezone: America/New_York
morning:
  enabled: true
  time: "08:00"
evening:
  enabled: true
  time: "18:00"
weekly:
  enabled: true
  day: sunday
  time: "09:00"
notification:
  enabled: true
  method: osascript
  open_on_click: obsidian
```

## Manual testing

```bash
python3 scheduling/run_scheduled.py morning
python3 scheduling/run_scheduled.py evening
python3 scheduling/run_scheduled.py weekly
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
rm ~/Library/LaunchAgents/com.obsidian-connector.daily.plist
```
```

**Step 6: Commit**

```bash
git add scheduling/
git commit -m "feat: add scheduled automation (launchd + headless runner)

Morning briefing, evening close, and weekly review run on schedule.
Calls Python API directly (no LLM). macOS notifications on completion."
```

---

### Task 12: Create Claude Desktop system prompt

**Files:**
- Create: `templates/claude-desktop-persona.md`

**Step 1: Write the system prompt**

Create `templates/claude-desktop-persona.md`:

```markdown
# Obsidian Second Brain Assistant

You are the user's second brain assistant. You have full access to their
Obsidian vault through MCP tools. You don't just answer questions -- you
proactively drive their daily workflows and help them think better.

## On every conversation start

Call `obsidian_check_in` FIRST. Use its output to greet the user with
context:

- If morning and briefing hasn't run: "Good morning. Your briefing hasn't
  run yet -- want me to start your day?"
- If evening and close hasn't run: "It's evening. Ready to close your day?"
- If there are pending delegations: "You have N delegation instructions
  waiting in your vault."
- If everything is caught up: "All caught up. What would you like to work on?"

## Workflows you drive

### Morning briefing
Trigger: user says "morning", "start my day", "briefing", or check_in shows
morning + no briefing.

1. Call `obsidian_today`
2. Call `obsidian_open_loops`
3. Call `obsidian_delegations`
4. Synthesize a conversational briefing
5. Write `## Morning Briefing` section to daily note via `obsidian_log_daily`
6. Ask what to triage

### Evening close
Trigger: user says "evening", "close my day", "wrap up", or check_in shows
evening + no close.

1. Call `obsidian_close_day`
2. Call `obsidian_graduate_candidates` (lookback 1 day)
3. Synthesize a reflection
4. Write `## Day Close` section to daily note
5. Offer to graduate promising ideas

### Quick idea capture
Trigger: user says "idea:", "thought:", "log this", or "capture".

1. Call `obsidian_log_daily` with formatted entry: `- {HH:MM} {text}`
2. If topic is recognizable, call `obsidian_search` for related notes
3. Confirm briefly

### Weekly review
Trigger: user says "weekly review", "weekly", or it's Sunday/Monday.

1. Call `obsidian_drift` with 7-day lookback
2. Call `obsidian_graduate_candidates` with 7-day lookback
3. Call `obsidian_vault_structure`
4. Synthesize weekly review
5. Write `## Weekly Review` to daily note

## Principles

- **The vault is truth.** Always read before advising. Never guess what's in
  a note -- read it.
- **Always write back.** If you generate a summary, briefing, or reflection,
  persist it to the daily note via `obsidian_log_daily`.
- **Be proactive.** If check_in shows pending work, mention it. Don't wait
  to be asked.
- **The daily note is the capture surface.** Append to it freely. The user's
  other tools (morning briefing, graduation, drift) all read from it.
- **Speed for ideas.** When the user is capturing an idea, be fast. Log
  first, elaborate later.
- **Depth for reviews.** When the user is reviewing (morning, evening,
  weekly), be thorough. Read multiple notes, surface connections, offer
  analysis.
```

**Step 2: Commit**

```bash
git add templates/claude-desktop-persona.md
git commit -m "feat: add Claude Desktop system prompt for second brain behavior

Teaches Claude to call check_in at conversation start, drive daily
workflows, and always write back to the vault."
```

---

### Task 13: Update AGENTS.md

**Files:**
- Modify: `AGENTS.md`

**Step 1: Update module map**

Add to the module map table:

```markdown
| `skills/` | 4 Claude Code skills (morning, evening, idea, weekly) |
| `hooks/` | SessionStart hook for proactive suggestions |
| `scheduling/` | launchd automation + headless runner |
| `templates/` | Claude Desktop system prompt, exec-plan templates |
```

**Step 2: Update tool/command counts**

Change "26 commands" to "27 commands" and "27 tools" to "28 tools" where referenced.

**Step 3: Update "What this repo does" section**

Update to mention the assistant layer:
```markdown
Python wrapper for the Obsidian desktop app. Exposes vault operations
(search, read, write, graph analysis, thinking tools, workflow management)
as a Python API, CLI (`obsx` -- 27 commands), and MCP server (28 tools)
for Claude Desktop. Includes skills, hooks, and scheduled automation that
turn Claude into a proactive second brain assistant.
```

**Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with skills, hooks, scheduling layers"
```

---

### Task 14: Rewrite docs/daily-optimization.md as Second Brain Operating Manual

**Files:**
- Modify: `docs/daily-optimization.md`

**Step 1: Read current file** (already read above)

**Step 2: Rewrite with new framing**

The full content is extensive. Key structural changes:

1. **New title**: "Second Brain Operating Manual"
2. **New opening**: Lead with "your assistant drives this" not "here are tools you invoke"
3. **New section**: "How It Works" explaining three layers (scheduled → check_in → interactive)
4. **New section**: "Getting Started" with Day 1 / Week 1 / Month 1 path
5. **Reframed phases**: Same Awareness → Decision → Execution → Reflection structure, but recipes written as "what your assistant does" not "tools you can call"
6. **Updated frontmatter**: bump `last_reviewed`

This is the largest single task. The implementer should preserve all existing recipe content but reframe the language throughout.

**Step 3: Commit**

```bash
git add docs/daily-optimization.md
git commit -m "docs: reframe daily optimization as Second Brain Operating Manual

Shifts from 'tools you invoke' to 'your assistant drives this'.
Adds how-it-works section, getting-started path, three-layer explanation."
```

---

### Task 15: Create docs/second-brain-overview.md

**Files:**
- Create: `docs/second-brain-overview.md`

**Step 1: Write the overview doc**

This is the pitch doc. Covers:
- What the connector is (your second brain assistant)
- The three-layer architecture (execution, orchestration, proactive)
- How it works in Claude CLI vs Claude Desktop
- What a typical day looks like with the assistant
- Link to setup guide and operating manual

Must include standard frontmatter:
```yaml
---
title: "Second Brain Overview"
status: draft
owner: core
last_reviewed: "2026-03-06"
---
```

**Step 2: Commit**

```bash
git add docs/second-brain-overview.md
git commit -m "docs: add second brain overview (pitch doc)"
```

---

### Task 16: Create docs/setup-guide.md

**Files:**
- Create: `docs/setup-guide.md`

**Step 1: Write unified setup guide**

Three paths:
1. **Claude Desktop only**: Install connector, paste system prompt, done
2. **Claude CLI only**: Install connector, install skills, enable hook, optionally enable scheduling
3. **Both**: Full setup

Each path has numbered steps with exact commands.

Must include standard frontmatter.

**Step 2: Commit**

```bash
git add docs/setup-guide.md
git commit -m "docs: add unified setup guide for all three environments"
```

---

### Task 17: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Read current README**

**Step 2: Rewrite opening**

Replace tool-centric opening with assistant-centric pitch:
- Lead: "Turn Claude into your second brain."
- One paragraph on what it does (drives daily workflows, captures ideas, surfaces connections)
- Quick start section with three paths
- "What's under the hood" section with tool count and architecture
- Link to Second Brain Overview, Setup Guide, Operating Manual

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README as second brain assistant pitch

Leads with experience, not tool count. Three quick-start paths
for Desktop, CLI, and both environments."
```

---

### Task 18: Update install.sh for skills + hooks + scheduling

**Files:**
- Modify: `scripts/install.sh`

**Step 1: Add skill installation step**

After the existing venv/package install steps, add:
- Copy skills to project-local `.claude/commands/` or symlink
- Ask user if they want to enable the SessionStart hook
- Ask user if they want to enable scheduled automation
- If scheduling: generate plists with correct paths, install to `~/Library/LaunchAgents/`

**Step 2: Test**

Run: `./scripts/install.sh` (in a test scenario)
Expected: Installer offers skill, hook, and scheduling setup

**Step 3: Commit**

```bash
git add scripts/install.sh
git commit -m "feat: extend installer with skills, hooks, and scheduling setup

Offers opt-in installation of Claude Code skills, SessionStart hook,
and macOS launchd scheduling."
```

---

### Task 19: Run full test suite and verify

**Step 1: Run all existing tests**

```bash
python3 scripts/smoke_test.py
python3 scripts/workflow_test.py
python3 scripts/checkin_test.py
bash scripts/mcp_launch_smoke.sh
```

**Step 2: Run docs lint**

```bash
make docs-lint
```

**Step 3: Fix any failures**

**Step 4: Final commit**

```bash
git commit -m "chore: fix any test/lint issues from second brain integration"
```

---

## Task dependency graph

```
Task 1 (check_in function)
  → Task 2 (export from __init__)
  → Task 3 (MCP tool) → Task 5 (TOOLS_CONTRACT)
  → Task 4 (CLI command) → Task 10 (hook, uses CLI)
  → Task 11 (scheduling, uses Python API)

Tasks 6-9 (skills) -- independent of each other, depend on Task 3

Task 12 (Desktop prompt) -- independent

Tasks 13-17 (docs) -- depend on Tasks 1-12 being done

Task 18 (installer) -- depends on Tasks 6-12

Task 19 (final verification) -- last
```

**Parallelizable groups:**
- Group A: Tasks 1-5 (sequential -- each builds on previous)
- Group B: Tasks 6, 7, 8, 9 (parallel -- independent skills)
- Group C: Task 10, 11, 12 (parallel -- independent layers)
- Group D: Tasks 13, 14, 15, 16, 17 (parallel -- independent docs)
- Group E: Task 18 (depends on B + C)
- Group F: Task 19 (final)
