---
title: "Second Brain Overview"
status: draft
owner: core
last_reviewed: "2026-03-06"
---

# Second Brain Overview

Your second brain assistant. Claude proactively drives daily workflows
through your Obsidian vault -- morning briefings, idea capture, evening
reflections, weekly reviews. You talk to Claude; Claude drives Obsidian.

---

## Three-layer architecture

```
Layer 3: Proactive
  SessionStart hook, launchd scheduling, Desktop system prompt
  Claude acts before you ask.
         |
Layer 2: Orchestration
  4 Claude Code skills (/morning, /evening, /idea, /weekly)
  Compose tools into multi-step workflows.
         |
Layer 1: Execution
  28 MCP tools / Python API
  Search, read, write, graph, thinking, workflows, check-in.
```

### Layer 1: Execution

The foundation. 28 MCP tools and a full Python API that handle every vault
operation: search, read, write, graph analysis, thinking tools, workflow
management, and time-aware check-in. Every tool returns a typed JSON
envelope with structured errors. See [TOOLS_CONTRACT.md](../TOOLS_CONTRACT.md).

### Layer 2: Orchestration

Four Claude Code skills compose execution tools into workflows:

| Skill | What it does |
|-------|-------------|
| `/morning` | Reads daily note, surfaces open loops and delegations, writes a briefing |
| `/evening` | Reviews accomplishments, suggests carry-forward items, writes a reflection |
| `/idea` | Captures a thought to your vault, surfaces related notes and connections |
| `/weekly` | Checks drift between intentions and actions, graduates ideas, audits health |

Each skill calls `check_in` first to understand context, then sequences
the right tools for the workflow.

### Layer 3: Proactive

The layer that makes Claude act before you ask:

- **SessionStart hook** -- runs at every Claude CLI session start, calls
  `check_in`, and offers the right workflow for the time of day
- **launchd scheduling** -- macOS daemon writes morning briefings at 8am
  and evening reflections at 6pm, even when you are not at the keyboard
- **Desktop system prompt** -- template that instructs Claude Desktop to
  call `obsidian_check_in` at every conversation start

## Two environments, same brain

| | Claude CLI | Claude Desktop |
|--|-----------|---------------|
| Execution | MCP tools / Python API | MCP tools |
| Orchestration | Skills (/morning, /evening, /idea, /weekly) | Natural language (user asks, Claude sequences tools) |
| Proactive | SessionStart hook + launchd scheduling | System prompt (calls check_in automatically) |

Both environments share the same execution layer. The orchestration and
proactive layers differ by environment but produce equivalent outcomes.

---

## A day with your assistant

**8:00 AM** -- launchd fires `run_scheduled.py morning`. Claude reads your
daily note, scans open loops and delegations, writes a Morning Briefing
section. By the time you sit down, it is waiting.

**8:15 AM** -- you open Claude CLI. The SessionStart hook runs `check_in`,
sees the briefing exists, and says: "Morning briefing is ready. Want me to
walk you through it?" You say yes; Claude reads the briefing aloud,
highlights three open loops, and asks which to tackle first.

**11:30 AM** -- reading an article sparks an idea. You type `/idea` and
describe it in two sentences. Claude captures it to your daily note,
searches your vault for related notes, and surfaces a connection you
missed.

**5:45 PM** -- launchd fires `run_scheduled.py evening`. Claude reviews
what you accomplished, lists incomplete tasks, suggests what to carry
forward, writes a Day Close section.

**6:00 PM** -- you open Claude. The hook sees the Day Close is ready and
offers to walk you through it. You review, add a thought, done.

**Sunday morning** -- you run `/weekly`. Claude checks drift between your
stated intentions and actual behavior over the past 7 days. Scans daily
notes for ideas worth graduating to standalone notes. Audits vault health
(orphans, stale notes, unresolved links). Writes a Weekly Review section.

---

## Links

- **Setup**: [Setup Guide](setup-guide.md) -- three installation paths
- **Operating manual**: [Daily Optimization Guide](daily-optimization.md) -- 18 recipes across 4 phases
- **Tools contract**: [TOOLS_CONTRACT.md](../TOOLS_CONTRACT.md) -- JSON envelope schema, typed errors, command reference
- **Architecture**: [ARCHITECTURE.md](../ARCHITECTURE.md) -- module and package layering
