---
title: "Second Brain Operating Manual"
status: verified
owner: core
last_reviewed: "2026-03-06"
---

# Second Brain Operating Manual

35 tools. Four phases. One assistant running your day.

Your second brain assistant lives inside Claude. It reads your Obsidian vault,
tracks your open loops, surfaces forgotten ideas, and drives daily rituals --
all through conversation. You talk to Claude. Claude drives Obsidian. The
connector is invisible.

The four phases form a loop:

```
Awareness --> Decision-Making --> Execution --> Reflection
    ^                                              |
    '----------------------------------------------'
```

Awareness sharpens decisions. Decisions drive execution. Execution generates
material for reflection. Reflection deepens awareness. Your assistant manages
the machinery. You focus on thinking.

---

## How It Works

Your assistant operates across three layers, from fully automatic to fully
interactive.

**Layer 1 -- Scheduled.** A macOS LaunchAgent runs your morning briefing and
evening close automatically, writing structured sections to your daily note
whether or not you open Claude. When you do open Claude, the briefing is
already waiting.

**Layer 2 -- Check-in.** The `obsidian_check_in` tool detects the time of day,
reads your daily note, checks which rituals have already run, counts open
loops and pending delegations, and suggests what to do next. Your assistant
calls this at the start of every session.

**Layer 3 -- Interactive.** Skills (`/morning`, `/evening`, `/idea`, `/weekly`)
and natural conversation let you drive workflows on demand. Say "close my day"
or type `/evening` and your assistant orchestrates the right tools, writes back
to your vault, and offers follow-up actions.

The layers reinforce each other. Scheduled automation ensures nothing is missed.
Check-in keeps your assistant context-aware. Interactive skills let you go
deeper whenever you want.

---

## Getting Started

You do not need to adopt everything at once.

**Day 1.** Tell your assistant "give me my morning briefing" and "close my day"
at end of day. Two conversations. Your assistant handles the rest.

**Week 1.** Add idea capture throughout the day -- say "log this idea" or use
`/idea` in Claude Code. Let your assistant run a weekly review on Sunday
(`/weekly`). Start noticing how your daily note becomes a running record.

**Month 1.** Enable scheduled automation so briefings write themselves. Let
your assistant challenge beliefs before big decisions, graduate ideas from
daily notes to standalone research, and run drift checks against your stated
intentions. By now the system is self-reinforcing -- your vault feeds your
assistant, your assistant feeds your vault.

---

## Phase 1: Awareness

Know your current state before acting.

### Morning briefing

**When**: First thing in the morning, before opening email or Slack.

Your assistant calls `obsidian_check_in`, `obsidian_today`, and
`obsidian_open_loops` to build your briefing. The `/morning` skill or
scheduled automation handles this automatically -- just open Claude and your
assistant knows what to tell you.

**Say**:
> "What's on my plate today?"

**CLI**:
```bash
./bin/obsx today
./bin/obsx open-loops
```

**What happens**: Your assistant reads your daily note, pulls outstanding
tasks, and surfaces any `OL:` markers or `#openloop` tags from recent notes.
You start the day knowing exactly what's live instead of guessing.

---

### Full context load

**When**: Starting a deep work session where your assistant needs to understand
your full situation -- a planning session, a weekly review, or a complex
question.

Your assistant calls `obsidian_my_world` and `obsidian_context_load`.

**Say**:
> "Load my full vault context. I want to do a weekly planning session."

**CLI**:
```bash
./bin/obsx my-world
./bin/obsx context-load
```

**What happens**: Your assistant ingests your recent notes, tasks, open loops,
and vault context in one pass. This gives it the full picture so it can make
connections you might miss. Use this before asking your assistant to help you
prioritize, plan, or synthesize.

---

### Vault health check

**When**: Weekly, or when your vault feels disorganized.

Your assistant calls `obsidian_vault_structure` and `obsidian_doctor`.

**Say**:
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

Your assistant calls `obsidian_ghost`.

**Say**:
> "Analyze my writing voice from the past two weeks. What patterns do you
> see?"

**CLI**:
```bash
./bin/obsx ghost --lookback-days 14
```

**What happens**: Your assistant reads your recent notes and builds a voice
profile -- sentence patterns, recurring phrases, tone shifts, vocabulary
tendencies. This is a mirror. Use it to notice when you're writing on
autopilot, when your energy is low (shorter, flatter entries), or when you're
in a creative surge.

---

## Phase 2: Decision-Making

Choose well under uncertainty.

### Decision logging

**When**: Any time you make a meaningful decision -- technical, financial,
career, personal.

Your assistant calls `obsidian_log_decision`.

**Say**:
> "Log a decision: project MyProject, summary 'Switched from REST to event-driven
> architecture', details 'Reduces P95 latency from 800ms to 200ms. Trade-off:
> more complex debugging. Revisit in 90 days.'"

**CLI**:
```bash
./bin/obsx log-decision \
  --project "MyProject" \
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

Your assistant calls `obsidian_challenge_belief`.

**Say**:
> "I believe that multifamily cap rates will compress in 2027. Challenge
> that belief against everything in my vault."

**CLI**:
```bash
./bin/obsx challenge "multifamily cap rates will compress in 2027"
```

**What happens**: Your assistant searches your vault for counter-evidence and
supporting evidence, then delivers a verdict. This forces you to confront
what your own notes say rather than relying on recency bias or gut feel.
Particularly valuable for investment decisions, career moves, and technical
bets where confirmation bias is expensive.

---

### Prior art search

**When**: Before starting a new project, writing a new note, or building
something from scratch.

Your assistant calls `obsidian_find_prior_work`.

**Say**:
> "Before I start researching CMBS structures, check what I've already
> written about it."

**CLI**:
```bash
./bin/obsx find-prior-work "CMBS structures" --top-n 5
```

**What happens**: Your assistant searches your vault, ranks the top matches,
and summarizes what you've already captured. This prevents you from
reinventing your own work and helps you build on existing thinking. Knowledge
compounds when you connect new work to old.

---

### Cross-domain insight

**When**: When you suspect two areas of your work or life might connect but
you're not sure how.

Your assistant calls `obsidian_connect_domains`.

**Say**:
> "Find connections between my real estate notes and my machine learning
> notes."

**CLI**:
```bash
./bin/obsx connect "real estate" "machine learning"
```

**What happens**: Your assistant searches both domains independently, then
finds notes that bridge them -- shared concepts, overlapping ideas, notes that
reference both. The best insights often live at the intersection of domains
you don't usually think about together.

---

## Phase 3: Execution

Close loops and ship.

### Open loop triage

**When**: When you feel scattered, overwhelmed, or unsure what to work on
next.

Your assistant calls `obsidian_open_loops` and `obsidian_tasks`.

**Say**:
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

Your assistant calls `obsidian_log_daily`.

**Say**:
> "Log this: Finished the CMBS analysis draft. Key finding: subordination
> levels are tighter than 2019 vintage."

**CLI**:
```bash
./bin/obsx log-daily "Finished CMBS analysis draft. Subordination tighter than 2019."
```

**What happens**: Your text is appended to today's daily note with a
timestamp. No context switching, no opening Obsidian, no finding the right
file. The daily note becomes a running log that feeds every other workflow --
morning briefings, open loop detection, idea graduation, drift analysis.

---

### Idea graduation

**When**: During a weekly review, or when you sense a daily-note entry
deserves its own standalone note.

Your assistant calls `obsidian_graduate_candidates` and
`obsidian_graduate_execute`.

**Say**:
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

**When**: When you want your assistant to pick up tasks you've left in your
notes.

Your assistant calls `obsidian_delegations`.

**Say**:
> "Check my recent notes for any delegation instructions I've left."

**CLI**:
```bash
./bin/obsx delegations --lookback-days 7
```

**What happens**: Your assistant scans for `@agent:` and `@claude:` markers
in your notes -- inline instructions you've left for future sessions. This
turns your vault into an async task queue. Write `@claude: summarize this
week's CRE research` in a note today, and your next session picks it up
automatically.

---

### Research note creation

**When**: An idea or topic deserves its own structured note right now.

Your assistant calls `obsidian_create_note`.

**Say**:
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

Your assistant calls `obsidian_check_in` and `obsidian_close_day`. The
`/evening` skill or scheduled automation handles this automatically --
say "close my day" and your assistant takes it from there.

**Say**:
> "Close my day. What did I accomplish, what's still open, and what should
> I carry into tomorrow?"

**CLI**:
```bash
./bin/obsx close
```

**What happens**: Your assistant generates a structured reflection based on
your day's activity -- notes written, tasks completed, loops opened and
closed. This is the bookend to the morning briefing. Closing the day with
intention prevents yesterday's unfinished work from ambushing tomorrow.

---

### Intention vs. reality

**When**: Weekly or monthly, when you want an honest check on whether your
actions match your stated priorities.

Your assistant calls `obsidian_drift`. The `/weekly` skill includes this
as part of the weekly review.

**Say**:
> "I said I'd write daily notes and do weekly CRE research. Check my vault
> for the last 30 days -- did I actually do it?"

**CLI**:
```bash
./bin/obsx drift --intention "write daily notes and do weekly CRE research" --lookback-days 30
```

**What happens**: Your assistant compares your stated intention against the
evidence in your vault -- note frequency, topics covered, gaps in the record.
It returns a drift score and analysis. This is the most uncomfortable tool
in the kit and the most valuable. You cannot improve what you do not measure.

---

### Idea archaeology

**When**: When you want to understand how a concept or project evolved in
your thinking over time.

Your assistant calls `obsidian_trace`.

**Say**:
> "Trace how my thinking about factor models has evolved across my vault."

**CLI**:
```bash
./bin/obsx trace "factor model"
```

**What happens**: Your assistant finds every mention of the idea across your
vault, orders them chronologically, and summarizes the evolution -- when it
first appeared, how it changed, what influenced the shifts. This reveals
patterns in your thinking that you can't see in the moment.

---

### Latent idea surfacing

**When**: When you want new ideas without new input -- mining what you
already have.

Your assistant calls `obsidian_ideas`.

**Say**:
> "What ideas are hiding in my vault's graph structure that I haven't
> explicitly written about?"

**CLI**:
```bash
./bin/obsx ideas
```

**What happens**: Your assistant analyzes your vault's link graph -- orphan
clusters, densely connected neighborhoods, notes that bridge otherwise
separate areas -- and surfaces ideas implied by the structure but never stated
explicitly. Your vault knows things you don't.

---

### Idea clustering

**When**: When a topic feels scattered across too many notes and you want
to see the shape of it.

Your assistant calls `obsidian_emerge`.

**Say**:
> "Cluster all my notes related to 'project management' into thematic
> groups."

**CLI**:
```bash
./bin/obsx emerge "project management"
```

**What happens**: Your assistant searches for all notes matching the topic,
then groups them into clusters based on content similarity. This shows you
the sub-themes within a broad topic and reveals which areas are well-developed
and which are thin.

---

## Utility tools

These are building blocks your assistant uses behind the scenes. You rarely
invoke them directly, but they power every recipe above:

| Tool | What your assistant uses it for |
|---|---|
| `obsidian_search` | Full-text search across all notes |
| `obsidian_read` | Reading a specific note by name or path |
| `obsidian_neighborhood` | Exploring a note's graph neighborhood -- backlinks, forward links, shared tags |
| `obsidian_backlinks` | Listing every note that links to a given note with context |
| `obsidian_rebuild_index` | Force-rebuilding the vault graph index (runs automatically if graph results seem stale) |
| `obsidian_check_in` | Detecting time of day, completed rituals, and pending actions to stay proactive |

---

## The full cycle

You don't need to run every recipe yourself. Your assistant manages the cycle.
Here is the minimal daily rhythm:

1. **Morning**: Your assistant runs a briefing (scheduled or via `/morning`) -- you know what's live
2. **Throughout the day**: Say "log this" -- your assistant captures as you go
3. **Before decisions**: Say "challenge this" or "what have I written about X" -- your assistant checks you
4. **End of day**: Your assistant runs a close (scheduled or via `/evening`) -- reflect and set up tomorrow

Layer in weekly workflows as habits form:
- **Weekly**: `/weekly` review -- drift check (are you doing what you said?), idea graduation (promote notes), vault health (clean up)
- **Monthly**: Voice analysis (writing mirror), latent ideas (mine the graph), cross-domain connections (cross-pollinate)

The system works best when your daily note is your default capture surface.
Write there freely. Your assistant handles the rest -- surfacing, connecting,
graduating, and reflecting on what you've captured.
