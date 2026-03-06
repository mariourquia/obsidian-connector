---
title: "Daily Optimization Guide"
status: verified
owner: core
last_reviewed: "2026-03-06"
---

# Daily Optimization Guide

27 tools. Four phases. One operating system for your day.

The obsidian-connector gives Claude full access to your Obsidian vault. This
guide shows you how to combine those tools into a daily cycle that helps you
think clearer, decide better, and ship more. Each recipe is standalone -- adopt
one or run the full cycle.

The four phases form a loop:

```
Awareness --> Decision-Making --> Execution --> Reflection
    ^                                              |
    '----------------------------------------------'
```

Awareness sharpens decisions. Decisions drive execution. Execution generates
material for reflection. Reflection deepens awareness.

---

## Phase 1: Awareness

Know your current state before acting.

### Morning briefing

**When**: First thing in the morning, before opening email or Slack.

**Tools**: `obsidian_today`, `obsidian_open_loops`

**Ask Claude**:
> "Give me my morning briefing. What's on today's daily note, what tasks are
> open, and what loops am I carrying?"

**CLI**:
```bash
./bin/obsx today
./bin/obsx open-loops
```

**What happens**: Claude reads your daily note, pulls outstanding tasks, and
surfaces any `OL:` markers or `#openloop` tags from recent notes. You start
the day knowing exactly what's live instead of guessing.

---

### Full context load

**When**: Starting a deep work session where Claude needs to understand your
full situation -- a planning session, a weekly review, or a complex question.

**Tools**: `obsidian_my_world`, `obsidian_context_load`

**Ask Claude**:
> "Load my full vault context. I want to do a weekly planning session."

**CLI**:
```bash
./bin/obsx my-world
./bin/obsx context-load
```

**What happens**: Claude ingests your recent notes, tasks, open loops, and
vault context in one pass. This gives it the full picture so it can make
connections you might miss. Use this before asking Claude to help you
prioritize, plan, or synthesize.

---

### Vault health check

**When**: Weekly, or when your vault feels disorganized.

**Tools**: `obsidian_vault_structure`, `obsidian_doctor`

**Ask Claude**:
> "Run a vault health check. Show me orphan notes, dead ends, and anything
> that needs linking."

**CLI**:
```bash
./bin/obsx vault-structure
./bin/obsx doctor
```

**What happens**: `vault-structure` scans your vault's link graph and reports
orphan notes (no inbound or outbound links), dead ends (linked to but
nonexistent), unresolved links, and your most-connected hubs. `doctor` checks
that the Obsidian CLI is reachable and your vault is healthy. Together they
surface structural debt before it compounds.

---

### Know your voice

**When**: Weekly, or when you feel your writing has gone stale.

**Tools**: `obsidian_ghost`

**Ask Claude**:
> "Analyze my writing voice from the past two weeks. What patterns do you
> see?"

**CLI**:
```bash
./bin/obsx ghost --lookback-days 14
```

**What happens**: Claude reads your recent notes and builds a voice profile --
sentence patterns, recurring phrases, tone shifts, vocabulary tendencies. This
is a mirror. Use it to notice when you're writing on autopilot, when your
energy is low (shorter, flatter entries), or when you're in a creative surge.

---

## Phase 2: Decision-Making

Choose well under uncertainty.

### Decision logging

**When**: Any time you make a meaningful decision -- technical, financial,
career, personal.

**Tools**: `obsidian_log_decision`

**Ask Claude**:
> "Log a decision: project AMOS, summary 'Switched from REST to event-driven
> architecture', details 'Reduces P95 latency from 800ms to 200ms. Trade-off:
> more complex debugging. Revisit in 90 days.'"

**CLI**:
```bash
./bin/obsx log-decision \
  --project "AMOS" \
  --summary "Switched from REST to event-driven" \
  --details "Reduces P95 latency to 200ms. Trade-off: debugging complexity."
```

**What happens**: A structured decision record is appended to your daily note
with project, summary, details, and timestamp. Months later, you can search
your vault for past decisions and understand why you chose what you chose. The
compound value of decision logs grows over time -- you build a searchable
history of your own judgment.

---

### Challenge before you commit

**When**: Before making a high-stakes commitment -- an investment thesis, a
technical bet, a strategic pivot.

**Tools**: `obsidian_challenge_belief`

**Ask Claude**:
> "I believe that multifamily cap rates will compress in 2027. Challenge
> that belief against everything in my vault."

**CLI**:
```bash
./bin/obsx challenge "multifamily cap rates will compress in 2027"
```

**What happens**: Claude searches your vault for counter-evidence and
supporting evidence, then delivers a verdict. This forces you to confront
what your own notes say rather than relying on recency bias or gut feel.
Particularly valuable for investment decisions, career moves, and technical
bets where confirmation bias is expensive.

---

### Prior art search

**When**: Before starting a new project, writing a new note, or building
something from scratch.

**Tools**: `obsidian_find_prior_work`

**Ask Claude**:
> "Before I start researching CMBS structures, check what I've already
> written about it."

**CLI**:
```bash
./bin/obsx find-prior-work "CMBS structures" --top-n 5
```

**What happens**: Claude searches your vault, ranks the top matches, and
summarizes what you've already captured. This prevents you from reinventing
your own work and helps you build on existing thinking. Knowledge compounds
when you connect new work to old.

---

### Cross-domain insight

**When**: When you suspect two areas of your work or life might connect but
you're not sure how.

**Tools**: `obsidian_connect_domains`

**Ask Claude**:
> "Find connections between my real estate notes and my machine learning
> notes."

**CLI**:
```bash
./bin/obsx connect "real estate" "machine learning"
```

**What happens**: Claude searches both domains independently, then finds
notes that bridge them -- shared concepts, overlapping ideas, notes that
reference both. The best insights often live at the intersection of domains
you don't usually think about together.

---

## Phase 3: Execution

Close loops and ship.

### Open loop triage

**When**: When you feel scattered, overwhelmed, or unsure what to work on
next.

**Tools**: `obsidian_open_loops`, `obsidian_tasks`

**Ask Claude**:
> "Show me all my open loops and outstanding tasks. Help me triage -- what
> should I close, defer, or delegate?"

**CLI**:
```bash
./bin/obsx open-loops
./bin/obsx tasks --status todo
```

**What happens**: `open-loops` surfaces every `OL:` marker and `#openloop`
tag in your recent notes. `tasks` lists your outstanding to-dos. Together,
they give you a complete inventory of commitments. Open loops consume mental
energy even when you're not actively thinking about them. Getting them out
of your head and into a triage list is the first step to clearing them.

---

### Daily logging

**When**: Throughout the day, whenever something is worth recording.

**Tools**: `obsidian_log_daily`

**Ask Claude**:
> "Log to daily: Finished the CMBS analysis draft. Key finding: subordination
> levels are tighter than 2019 vintage."

**CLI**:
```bash
./bin/obsx log-daily "Finished CMBS analysis draft. Subordination tighter than 2019."
```

**What happens**: Your text is appended to today's daily note with a
timestamp. No context switching, no opening Obsidian, no finding the right
file. The daily note becomes a running log that feeds every other tool in
this guide -- morning briefings, open loop detection, idea graduation, drift
analysis.

---

### Idea graduation

**When**: During a weekly review, or when you sense a daily-note entry
deserves its own standalone note.

**Tools**: `obsidian_graduate_candidates`, `obsidian_graduate_execute`

**Ask Claude**:
> "Scan my daily notes from the past week for ideas worth promoting to
> standalone notes."

**CLI**:
```bash
./bin/obsx graduate list --lookback-days 7
./bin/obsx graduate execute --title "Factor Model v2" --content "..." --confirm
```

**What happens**: `graduate_candidates` scans recent daily notes for
entries substantial enough to become their own note -- recurring themes,
detailed analyses, ideas that keep coming back. `graduate_execute` creates
an agent draft in `Inbox/Agent Drafts/` with provenance metadata. You
review and promote. This is how fleeting notes become permanent knowledge.

---

### Delegation scan

**When**: When you want Claude to pick up tasks you've left in your notes.

**Tools**: `obsidian_delegations`

**Ask Claude**:
> "Check my recent notes for any delegation instructions I've left."

**CLI**:
```bash
./bin/obsx delegations --lookback-days 7
```

**What happens**: Claude scans for `@agent:` and `@claude:` markers in your
notes -- inline instructions you've left for future AI sessions. This turns
your vault into an async task queue. Write `@claude: summarize this week's
CRE research` in a note today, and your next Claude session can pick it up.

---

### Research note creation

**When**: An idea or topic deserves its own structured note right now.

**Tools**: `obsidian_create_note`

**Ask Claude**:
> "Create a new research note titled 'CMBS Subordination Analysis' using
> my Note template."

**CLI**:
```bash
./bin/obsx create-research-note --title "CMBS Subordination Analysis" --template "Template, Note"
```

**What happens**: A new note is created from your specified template with
the title pre-filled. Templates enforce consistent structure so your notes
are searchable, linkable, and compatible with your other workflows.

---

## Phase 4: Reflection

Learn from experience.

### End-of-day close

**When**: Last thing in your workday.

**Tools**: `obsidian_close_day`

**Ask Claude**:
> "Close my day. What did I accomplish, what's still open, and what should
> I carry into tomorrow?"

**CLI**:
```bash
./bin/obsx close
```

**What happens**: Claude generates a structured reflection prompt based on
your day's activity -- notes written, tasks completed, loops opened and
closed. This is the bookend to the morning briefing. Closing the day with
intention prevents yesterday's unfinished work from ambushing tomorrow.

---

### Intention vs. reality

**When**: Weekly or monthly, when you want an honest check on whether your
actions match your stated priorities.

**Tools**: `obsidian_drift`

**Ask Claude**:
> "I said I'd write daily notes and do weekly CRE research. Check my vault
> for the last 30 days -- did I actually do it?"

**CLI**:
```bash
./bin/obsx drift --intention "write daily notes and do weekly CRE research" --lookback-days 30
```

**What happens**: Claude compares your stated intention against the evidence
in your vault -- note frequency, topics covered, gaps in the record. It
returns a drift score and analysis. This is the most uncomfortable tool in
the kit and the most valuable. You cannot improve what you do not measure.

---

### Idea archaeology

**When**: When you want to understand how a concept or project evolved in
your thinking over time.

**Tools**: `obsidian_trace`

**Ask Claude**:
> "Trace how my thinking about factor models has evolved across my vault."

**CLI**:
```bash
./bin/obsx trace "factor model"
```

**What happens**: Claude finds every mention of the idea across your vault,
orders them chronologically, and summarizes the evolution -- when it first
appeared, how it changed, what influenced the shifts. This reveals patterns
in your thinking that you can't see in the moment.

---

### Latent idea surfacing

**When**: When you want new ideas without new input -- mining what you
already have.

**Tools**: `obsidian_ideas`

**Ask Claude**:
> "What ideas are hiding in my vault's graph structure that I haven't
> explicitly written about?"

**CLI**:
```bash
./bin/obsx ideas
```

**What happens**: Claude analyzes your vault's link graph -- orphan clusters,
densely connected neighborhoods, notes that bridge otherwise separate areas --
and surfaces ideas implied by the structure but never stated explicitly. Your
vault knows things you don't.

---

### Idea clustering

**When**: When a topic feels scattered across too many notes and you want
to see the shape of it.

**Tools**: `obsidian_emerge`

**Ask Claude**:
> "Cluster all my notes related to 'project management' into thematic
> groups."

**CLI**:
```bash
./bin/obsx emerge "project management"
```

**What happens**: Claude searches for all notes matching the topic, then
groups them into clusters based on content similarity. This shows you the
sub-themes within a broad topic and reveals which areas are well-developed
and which are thin.

---

## Utility tools

These tools are building blocks used within the recipes above. They don't
have their own rituals but you'll use them constantly:

| Tool | What it does |
|---|---|
| `obsidian_search` | Full-text search across all notes |
| `obsidian_read` | Read a specific note by name or path |
| `obsidian_neighborhood` | Explore a note's graph neighborhood -- backlinks, forward links, shared tags |
| `obsidian_backlinks` | List every note that links to a given note with context |
| `obsidian_rebuild_index` | Force-rebuild the vault graph index (run if graph results seem stale) |

---

## The full cycle

You don't need to run every recipe every day. Here's a minimal daily rhythm
using four tools:

1. **Morning**: `today` -- know what's live
2. **Throughout the day**: `log_daily` -- capture as you go
3. **Before decisions**: `challenge_belief` or `find_prior_work` -- check yourself
4. **End of day**: `close_day` -- reflect and set up tomorrow

Layer in weekly recipes as habits form:
- **Weekly**: `drift` (are you doing what you said?), `graduate list` (promote ideas), `vault-structure` (clean up)
- **Monthly**: `ghost` (voice check), `ideas` (mine the graph), `connect` (cross-pollinate domains)

The tools work best when your daily note is your default capture surface.
Write there freely. The tools handle the rest -- surfacing, connecting,
graduating, and reflecting on what you've captured.
