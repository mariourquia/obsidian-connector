---
title: "Second Brain Assistant Design"
status: deprecated
replaced_by: main
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Design: Second Brain Assistant

**Date**: 2026-03-06

## Problem

The obsidian-connector is a powerful execution layer (27 MCP tools) but it's
passive -- users must remember to invoke each tool. The daily optimization guide
documents workflows but doesn't drive them. Users experience the connector as a
toolkit, not an assistant.

## Vision

Transform the connector from "Obsidian power tools" to "your second brain
assistant." Claude proactively drives daily workflows, captures ideas in real
time, and surfaces connections -- all through conversation. The connector
becomes invisible plumbing; users talk to Claude, Claude drives Obsidian.

## Target environments

- **Claude CLI**: Skills, hooks, scheduled automation (full experience)
- **Claude Desktop**: MCP tools + system prompt template (equivalent capability)
- Both environments share the same execution layer (MCP tools / Python API)

## Architecture: Three layers

```
Layer 3: Proactive (hooks, scheduling, system prompt)
   |
Layer 2: Orchestration (skills for CLI, natural language for Desktop)
   |
Layer 1: Execution (MCP tools, Python API -- existing 27 tools + check_in)
```

---

## Layer 1: The check_in tool

One new MCP tool added to the connector.

### Purpose

Time-aware "what should I do now?" -- the universal proactive element that
works in both CLI and Desktop.

### Input

None required. Optional: `timezone` override (string, e.g. "America/New_York").

### Logic

1. Detect current time of day: `morning` (<11am), `midday` (11am-4pm),
   `evening` (4pm-8pm), `night` (>8pm)
2. Read today's daily note
3. Check for sentinel markers (`## Morning Briefing`, `## Day Close`) to
   determine which rituals have run
4. Count open `@claude:` / `@agent:` delegations
5. Check `Inbox/Agent Drafts/` for unreviewed drafts
6. Count open loops

### Output

```json
{
  "time_of_day": "morning",
  "daily_note_exists": true,
  "completed_rituals": ["morning_briefing"],
  "pending_rituals": ["evening_close"],
  "pending_delegations": 2,
  "unreviewed_drafts": 1,
  "open_loop_count": 5,
  "suggestion": "You have 2 unprocessed delegation instructions and 5 open loops. Consider triaging your open loops."
}
```

### Location

- Function: `workflows.py::check_in()`
- MCP tool: `mcp_server.py::obsidian_check_in()`
- CLI: `obsx check-in` (human + `--json` output)

---

## Layer 2: Claude Code Skills

Four skills in `skills/` directory, installable to `.claude/commands/`.

### /morning

**Flow**:
1. Call `obsidian_check_in` -- if briefing already done, say so, offer re-run
2. Call `obsidian_today` -- daily note contents
3. Call `obsidian_open_loops` -- open loops
4. Call `obsidian_delegations` -- pending @claude: tasks
5. Synthesize conversational briefing
6. Write `## Morning Briefing` section to daily note via `obsidian_log_daily`
7. Ask user: "Anything to triage, capture, or change before starting?"
8. Respond to follow-up conversationally (defer tasks, log ideas, etc.)

### /evening

**Flow**:
1. Call `obsidian_check_in` -- if close already done, say so
2. Call `obsidian_close_day` -- day's activity summary
3. Call `obsidian_graduate_candidates` -- ideas worth promoting
4. Synthesize reflection: done, still open, carry forward
5. Write `## Day Close` section to daily note
6. If graduate candidates found, offer to promote them

### /idea

**Flow**:
1. Parse argument as idea text
2. Call `obsidian_log_daily` with formatted entry: `- [timestamp]: {text}`
3. If idea mentions a project/topic, call `obsidian_search` for related context
4. Confirm with related notes if found

Fastest path: two seconds from thought to vault.

### /weekly

**Flow**:
1. Call `obsidian_drift` with configured intentions
2. Call `obsidian_graduate_candidates` (7-day lookback)
3. Call `obsidian_vault_structure` -- orphans, dead ends
4. Synthesize weekly review
5. Write to daily note or dedicated review note
6. Present findings, ask for triage

---

## Layer 3a: SessionStart Hook

File: `hooks/session_start.sh`

### Logic (no LLM call)

1. Get current hour
2. Call `obsx check-in --json` (fast, local)
3. Format suggestion based on results:
   - Morning, briefing not done: suggest `/morning`
   - Evening, close not done: suggest `/evening`
   - Sunday/Monday, no weekly review: suggest `/weekly`
   - Everything done: stay silent

### Output example

```
Morning -- briefing not yet run. Type /morning to start your day.
```

### Install

`install.sh` adds hook config to `.claude/settings.json` (user confirms).

---

## Layer 3b: Scheduled Automation

### Components

- `scheduling/com.obsidian-connector.daily.plist` -- macOS LaunchAgent
- `scheduling/run_scheduled.py` -- headless Python script
- `scheduling/config.yaml` -- user configuration

### Schedule

| Time | Workflow |
|------|----------|
| 08:00 | Morning briefing write |
| 18:00 | Evening close write |
| Sunday 09:00 | Weekly review write |

### Design choices

- **No LLM**: Scheduled jobs call Python API directly. Fast, free, reliable.
- **Always writes to vault**: Briefing exists whether or not user engages.
- **macOS notification**: Via `osascript` or `terminal-notifier`. Configurable.
- **Click behavior**: Opens Claude Code or Obsidian (configurable).

### Config format

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
  method: osascript
  open_on_click: claude
```

### Interaction with skills

When user opens Claude after a scheduled run, `/morning` detects the briefing
is already written and shifts to interactive mode: "Your briefing ran at 8am.
Here's what it found. Want to triage?"

---

## Layer 3c: Claude Desktop System Prompt

File: `templates/claude-desktop-persona.md`

### Purpose

For users without Claude CLI -- gives Claude Desktop the same proactive
behavior through custom instructions.

### Key behaviors encoded

1. Call `obsidian_check_in` at conversation start (equivalent to SessionStart hook)
2. React to check_in results -- offer pending rituals
3. Recognize natural language triggers ("morning", "idea:", "close my day", etc.)
4. Always write back to vault -- don't just tell, persist
5. Offer next actions after any workflow

### Install

README links to file with "copy into Claude Desktop > Settings > Custom
Instructions." Install script offers to copy to clipboard.

---

## Documentation changes

### Rewrites

- **README.md**: Lead with "second brain assistant" pitch. Experience first,
  tools second. Three Quick Start paths (Desktop, CLI, both).
- **docs/daily-optimization.md**: Reframe as "Second Brain Operating Manual."
  Written from assistant's perspective. Add onboarding path (Day 1 / Week 1 /
  Month 1).

### New docs

| File | Purpose |
|------|---------|
| `docs/second-brain-overview.md` | What this is and why -- the pitch doc |
| `docs/setup-guide.md` | Unified install for all three layers |
| `templates/claude-desktop-persona.md` | Desktop system prompt |
| `scheduling/README.md` | Scheduling config and customization |

### Updates (not rewrites)

- `TOOLS_CONTRACT.md` -- add `obsidian_check_in` spec
- `AGENTS.md` -- add skills, hooks, scheduling to module map
- `ARCHITECTURE.md` -- add orchestration layer diagram

---

## Deliverable summary

1. **1 new MCP tool**: `obsidian_check_in` (+ CLI command + Python function)
2. **4 skills**: `/morning`, `/evening`, `/idea`, `/weekly`
3. **1 SessionStart hook**: time-aware nudge
4. **Scheduled automation**: launchd plist + Python script + macOS notifications
5. **Desktop system prompt**: `templates/claude-desktop-persona.md`
6. **Documentation rewrite**: README, daily optimization, new overview + setup guide

## Narrative principle

Every doc, every README line, every tool description reinforces: **you talk to
Claude, Claude drives Obsidian.** The connector is invisible. Users never think
"let me invoke obsidian_open_loops" -- they think "let me ask my assistant
what's on my plate."
