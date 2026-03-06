---
title: "Second Brain Assistant -- Agent Team Orchestration"
status: draft
owner: core
last_reviewed: "2026-03-06"
---

# Second Brain Assistant -- Agent Team Orchestration

> **Purpose**: Execution plan for implementing the Second Brain Assistant.
> Designed for parallel agent execution across multiple sessions.
>
> **Design doc**: `docs/plans/2026-03-06-second-brain-assistant-design.md`
> **Implementation plan**: `docs/plans/2026-03-06-second-brain-assistant-plan.md`
> **Branch**: `feature/second-brain-assistant`

---

## Team Charter

### Objective

Transform obsidian-connector from passive tool into proactive second brain
assistant. Deliver: 1 new MCP tool, 4 Claude Code skills, 1 SessionStart hook,
macOS scheduled automation, Claude Desktop system prompt, and full
documentation rewrite.

### Success Criteria

| # | Criterion | Verification Command |
|---|-----------|---------------------|
| 1 | `check_in()` returns structured dict with all required keys | `python3 scripts/checkin_test.py` |
| 2 | `obsidian_check_in` MCP tool works | `bash scripts/mcp_launch_smoke.sh` |
| 3 | Four skills exist and follow Claude Code format | `ls skills/*.md` (4 files, each with frontmatter) |
| 4 | SessionStart hook runs without error | `bash hooks/session_start.sh` |
| 5 | Scheduled runner completes without crash | `python3 scheduling/run_scheduled.py morning` |
| 6 | Desktop system prompt covers all workflows | Manual review of `templates/claude-desktop-persona.md` |
| 7 | README leads with "second brain" pitch | Manual review |
| 8 | All tests pass, docs lint passes | `python3 scripts/smoke_test.py && make docs-lint` |

### Constraints

- Python 3.11+, FastMCP, existing patterns (`_error_envelope`, `ToolAnnotations`, envelope format)
- Skills are `.md` files in Claude Code format (frontmatter: `name`, `description`)
- Scheduled jobs call Python API directly -- no LLM, no network
- All docs need frontmatter: `title`, `status`, `owner`, `last_reviewed`
- Do not modify existing 27 MCP tools

---

## Agent Team

### Roster

| Agent | Role | Scope | Lane Boundaries |
|-------|------|-------|-----------------|
| **Archie** | Lead Architect | API design, integration review, structural decisions | Does NOT write implementation code. Reviews, advises, approves. |
| **Builder** | Implementer | All Python code, shell scripts, test scripts | Does NOT write docs or skill content. Code and scripts only. |
| **Sage** | User Advocate | Skills, Desktop prompt, UX narrative, onboarding | Does NOT touch Python. Writes `.md` skill files and reviews user-facing text. |
| **Scribe** | Docs / Comms | README, overview, setup guide, operating manual, AGENTS.md | Does NOT touch Python or skills. Documentation only. |
| **Red** | Critic | Review at every gate, regression checks, quality enforcement | Does NOT produce deliverables. Reviews, flags, approves/blocks. |

### Communication Protocol

1. **Archie** speaks first on any structural question (API shape, module boundaries, integration)
2. **Builder** presents code at each gate for review
3. **Sage** reviews all user-facing text before gate approval
4. **Scribe** reviews all docs before gate approval
5. **Red** reviews everything at gates -- has veto power on blocking issues
6. Non-blocking feedback is logged but does not halt progress
7. Blocking issues halt the phase until resolved

---

## Dependency Graph

```
Phase 1: Core Tool
  Tasks 1-5 (sequential chain)
  Agents: Builder + Archie
  Gate: Red reviews
       |
       v
Phase 2: Orchestration Layer (3 parallel workstreams)
  +---> 2a: Skills (Tasks 6-9)        Agents: Sage + Builder(review)
  |     [parallel: 6,7,8,9 are independent]
  |
  +---> 2b: Hook + Scheduling (Tasks 10-11)  Agents: Builder
  |     [10 and 11 are independent]
  |
  +---> 2c: Desktop Prompt (Task 12)   Agent: Sage
  |
  +---> Gate: Red reviews all three workstreams
       |
       v
Phase 3: Documentation (5 parallel docs)
  +---> Task 13: AGENTS.md             Agent: Scribe
  +---> Task 14: daily-optimization.md  Agents: Scribe + Sage(review)
  +---> Task 15: second-brain-overview  Agent: Scribe
  +---> Task 16: setup-guide.md        Agent: Scribe
  +---> Task 17: README.md             Agents: Scribe + Sage(review)
  |
  +---> Gate: Red reviews all docs
       |
       v
Phase 4: Integration
  Task 18: install.sh update           Agent: Builder
  Task 19: Full verification           Agent: Red
  Final gate: All success criteria met
```

### Task-Level Dependencies

```
T1 (check_in fn)
 ├── T2 (export __init__)
 ├── T3 (MCP tool) ──── T5 (TOOLS_CONTRACT)
 ├── T4 (CLI cmd) ──── T10 (hook uses `obsx check-in`)
 └── T11 (scheduling uses check_in Python API)

T6 (skill: morning)  ── independent
T7 (skill: evening)  ── independent
T8 (skill: idea)     ── independent
T9 (skill: weekly)   ── independent
T12 (Desktop prompt) ── independent

T13 (AGENTS.md)              ── depends on T1-T12 (describes what exists)
T14 (daily-optimization.md)  ── depends on T1-T12
T15 (overview doc)           ── depends on T1-T12
T16 (setup guide)            ── depends on T1-T12
T17 (README.md)              ── depends on T1-T12

T18 (install.sh)             ── depends on T6-T12
T19 (verification)           ── depends on T1-T18
```

### Parallelism Map

Use this to dispatch parallel agents. Each row is a set of tasks that can
run simultaneously.

| Wave | Tasks | Agents | Prereqs |
|------|-------|--------|---------|
| Wave 1 | T1 -> T2 -> T3 -> T4 -> T5 | Builder + Archie | None |
| Wave 2a | T6, T7, T8, T9 | Sage | Wave 1 |
| Wave 2b | T10, T11 | Builder | Wave 1 |
| Wave 2c | T12 | Sage | Wave 1 |
| Wave 3 | T13, T14, T15, T16, T17 | Scribe + Sage | Wave 2 |
| Wave 4 | T18 | Builder | Wave 2 + Wave 3 |
| Wave 5 | T19 | Red | All |

**Maximum parallelism**: Wave 2 runs 3 workstreams simultaneously (2a, 2b, 2c).
Wave 3 runs 5 docs simultaneously.

---

## Phase Details

### Phase 1: Core Tool

**Objective**: `check_in()` function, export, MCP tool, CLI command,
TOOLS_CONTRACT update, test.

**Owner**: Builder (code), Archie (review)

**Tasks**:

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T1 | Write `check_in()` in workflows.py + test | `obsidian_connector/workflows.py`, `scripts/checkin_test.py` | `python3 scripts/checkin_test.py` passes |
| T2 | Export from `__init__.py` | `obsidian_connector/__init__.py` | `python3 -c "from obsidian_connector import check_in"` |
| T3 | Add `obsidian_check_in` MCP tool | `obsidian_connector/mcp_server.py` | `bash scripts/mcp_launch_smoke.sh` |
| T4 | Add `check-in` CLI subcommand | `obsidian_connector/cli.py` | `./bin/obsx check-in` and `./bin/obsx --json check-in` |
| T5 | Update TOOLS_CONTRACT.md | `TOOLS_CONTRACT.md` | Manual review: check_in listed, counts updated |

**Handoff to Phase 2**: All 5 tasks complete, Red approves at gate.

**Gate 1 checklist (Red)**:
- [ ] `python3 scripts/checkin_test.py` -- all pass
- [ ] `bash scripts/mcp_launch_smoke.sh` -- passes
- [ ] `./bin/obsx check-in` -- returns output with time_of_day and suggestion
- [ ] `./bin/obsx --json check-in` -- valid JSON with all keys from design
- [ ] check_in return shape matches design doc exactly
- [ ] No regressions: `python3 scripts/smoke_test.py` still passes
- [ ] TOOLS_CONTRACT.md has correct tool spec and updated counts

---

### Phase 2: Orchestration Layer

**Objective**: Skills, hook, scheduling, Desktop system prompt.

**Three parallel workstreams**:

#### 2a: Skills (Sage)

| Task | Description | File | Verification |
|------|-------------|------|--------------|
| T6 | `/morning` skill | `skills/morning.md` | Has frontmatter, references correct MCP tools |
| T7 | `/evening` skill | `skills/evening.md` | Has frontmatter, references correct MCP tools |
| T8 | `/idea` skill | `skills/idea.md` | Has frontmatter, fast-path design |
| T9 | `/weekly` skill | `skills/weekly.md` | Has frontmatter, references drift + graduate + vault-structure |

**Sage guidelines for skills**:
- Each skill must have YAML frontmatter with `name` and `description`
- Step-by-step instructions that Claude Code can follow exactly
- Reference MCP tools by their exact names (e.g. `obsidian_check_in`, not `check-in`)
- Include decision points ("if X, ask user; if Y, proceed")
- `/idea` must be the fastest -- minimize steps, maximize speed
- `/morning` and `/evening` must write sentinel headings (`## Morning Briefing`, `## Day Close`) so check_in can detect them

#### 2b: Hook + Scheduling (Builder)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T10 | SessionStart hook | `hooks/session_start.sh` | `bash hooks/session_start.sh` exits 0 |
| T11 | Scheduled automation | `scheduling/config.yaml`, `scheduling/run_scheduled.py`, `scheduling/com.obsidian-connector.daily.plist`, `scheduling/README.md` | `python3 scheduling/run_scheduled.py morning` completes |

**Builder guidelines for scheduling**:
- `run_scheduled.py` must import from `obsidian_connector` Python API, never shell out to `obsx`
- Must handle missing vault gracefully (print error, exit 1, no crash)
- Config loading: check `~/.config/obsidian-connector/schedule.yaml` first, fall back to `scheduling/config.yaml`
- `pyyaml` is an optional dependency -- if not installed, use built-in config defaults
- Plist uses `__REPO_ROOT__` placeholder -- installer replaces with actual path

#### 2c: Desktop Prompt (Sage)

| Task | Description | File | Verification |
|------|-------------|------|--------------|
| T12 | Claude Desktop system prompt | `templates/claude-desktop-persona.md` | Covers all 4 workflows, calls check_in at start |

**Sage guidelines for Desktop prompt**:
- Must teach Claude to call `obsidian_check_in` at every conversation start
- Natural language trigger patterns for each workflow
- "Always write back" principle -- never just tell, always persist to vault
- Keep under 2000 words -- Desktop custom instructions have limits

**Handoff to Phase 3**: All three workstreams complete, Red approves at gate.

**Gate 2 checklist (Red)**:
- [ ] 4 skill files exist in `skills/` with valid frontmatter
- [ ] Skills reference correct MCP tool names
- [ ] Skills write sentinel headings that match `_RITUAL_SENTINELS` in workflows.py
- [ ] `bash hooks/session_start.sh` exits 0 (may produce output or be silent)
- [ ] Hook does not crash when vault is unavailable
- [ ] `python3 scheduling/run_scheduled.py morning` completes (may error on missing vault, must not crash)
- [ ] Desktop prompt covers: check_in at start, morning, evening, idea, weekly
- [ ] Desktop prompt is under 2000 words
- [ ] No regressions: `python3 scripts/smoke_test.py` still passes

---

### Phase 3: Documentation

**Objective**: AGENTS.md update, daily-optimization rewrite, new overview doc,
setup guide, README rewrite.

**Owner**: Scribe (all docs), Sage (narrative review on T14 and T17)

| Task | Description | File | Verification |
|------|-------------|------|--------------|
| T13 | Update AGENTS.md | `AGENTS.md` | Module map includes skills/, hooks/, scheduling/, templates/ |
| T14 | Rewrite daily-optimization.md | `docs/daily-optimization.md` | Framed as "what your assistant does", not "tools you invoke" |
| T15 | New: second-brain-overview.md | `docs/second-brain-overview.md` | Valid frontmatter, explains three-layer architecture |
| T16 | New: setup-guide.md | `docs/setup-guide.md` | Three paths: Desktop, CLI, Both. Valid frontmatter. |
| T17 | Rewrite README.md | `README.md` | Opens with "second brain" pitch, not "Python wrapper" |

**Scribe guidelines**:
- All new docs need frontmatter: `title`, `status: draft`, `owner: core`, `last_reviewed: "2026-03-06"`
- daily-optimization.md: preserve all existing recipe content, reframe language
- daily-optimization.md: add "How It Works" section (3 layers), "Getting Started" (Day 1/Week 1/Month 1)
- README: lead with experience, tools under "What's Under the Hood"
- setup-guide.md: exact commands for each path, not just descriptions
- Run `make docs-lint` after writing -- fix any errors before marking complete

**Sage review criteria for T14 and T17**:
- Does it feel like describing an assistant, not a toolkit?
- Would a new user understand what this does in 30 seconds?
- Is the "Getting Started" path approachable?

**Handoff to Phase 4**: All docs complete, Red approves at gate.

**Gate 3 checklist (Red)**:
- [ ] `make docs-lint` passes
- [ ] All new docs have valid frontmatter
- [ ] AGENTS.md module map includes new directories, counts updated
- [ ] README first paragraph says "second brain" or equivalent, not "wrapper" or "toolkit"
- [ ] daily-optimization.md has "How It Works" and "Getting Started" sections
- [ ] setup-guide.md has three paths with exact commands
- [ ] second-brain-overview.md explains three layers clearly
- [ ] No dead links in docs

---

### Phase 4: Integration

**Objective**: Installer update, full verification against all success criteria.

**Owner**: Builder (T18), Red (T19)

| Task | Description | Files | Verification |
|------|-------------|-------|--------------|
| T18 | Extend install.sh | `scripts/install.sh` | Offers skill, hook, scheduling setup |
| T19 | Full verification | All | All 8 success criteria pass |

**Builder guidelines for T18**:
- Skill install: copy/symlink `skills/*.md` to project `.claude/commands/`
- Hook install: add hook config to `.claude/settings.json` (ask user first)
- Scheduling install: generate plists with correct paths, `launchctl load`
- All three are opt-in (prompted, not automatic)
- Must not break existing install flow

**Gate 4 / Final checklist (Red)**:
- [ ] Success criterion 1: `python3 scripts/checkin_test.py` passes
- [ ] Success criterion 2: `bash scripts/mcp_launch_smoke.sh` passes
- [ ] Success criterion 3: `ls skills/*.md` shows 4 files with frontmatter
- [ ] Success criterion 4: `bash hooks/session_start.sh` exits 0
- [ ] Success criterion 5: `python3 scheduling/run_scheduled.py morning` completes
- [ ] Success criterion 6: Desktop prompt covers all workflows
- [ ] Success criterion 7: README leads with second brain pitch
- [ ] Success criterion 8: `python3 scripts/smoke_test.py && make docs-lint` passes
- [ ] No regressions in any existing test script
- [ ] All commits follow project conventions (GPG signed, branch PR flow)

---

## Agent Prompts

### Archie (Lead Architect)

```
You are Archie, the Lead Architect for the Second Brain Assistant feature
on obsidian-connector.

GOAL: Ensure the check_in tool, skills, hook, scheduling, and Desktop
prompt integrate cleanly into the existing architecture.

YOUR RESPONSIBILITIES:
1. Review the check_in() API shape before Builder implements it. Ensure
   it matches the design doc at docs/plans/2026-03-06-second-brain-assistant-design.md.
2. Verify that skills reference MCP tools by correct names and the
   skill-tool contract is clean (skills orchestrate, tools execute).
3. Ensure the three layers (execution, orchestration, proactive) don't
   leak abstractions -- scheduled jobs should never need an LLM.
4. Review Builder's code at gates for architectural fit with existing
   patterns (_error_envelope, ToolAnnotations, envelope format).
5. Resolve any structural disagreements between agents.

FILES YOU OWN (review, not write):
- obsidian_connector/workflows.py (check_in function shape)
- obsidian_connector/mcp_server.py (tool registration pattern)
- ARCHITECTURE.md (if it needs updating)

YOU MUST NOT: Write implementation code. You review and advise.

EXISTING PATTERNS TO ENFORCE:
- MCP tools use _error_envelope() for error handling
- MCP tools have ToolAnnotations (readOnlyHint, destructiveHint, etc.)
- CLI commands have a _fmt_* formatter + parser entry in build_parser()
- Workflows functions live in workflows.py, are imported in __init__.py
- Tests are custom scripts in scripts/, not pytest
```

### Builder (Implementer)

```
You are Builder, the Implementer for the Second Brain Assistant feature
on obsidian-connector.

GOAL: Write all Python code, shell scripts, and test scripts for the
Second Brain Assistant.

YOUR RESPONSIBILITIES:
1. Implement check_in() in workflows.py following the spec in
   docs/plans/2026-03-06-second-brain-assistant-plan.md (Task 1).
2. Wire it up: __init__.py export (T2), MCP tool (T3), CLI command (T4).
3. Write the SessionStart hook script (T10).
4. Write the scheduling infrastructure (T11): config, runner, plist.
5. Extend install.sh for skills/hooks/scheduling (T18).

FILES YOU OWN:
- obsidian_connector/workflows.py (append check_in function)
- obsidian_connector/__init__.py (add export)
- obsidian_connector/mcp_server.py (add MCP tool)
- obsidian_connector/cli.py (add subcommand + formatter)
- scripts/checkin_test.py (new)
- hooks/session_start.sh (new)
- scheduling/* (new)
- scripts/install.sh (extend)

YOU MUST NOT: Write documentation (.md docs in docs/) or skill files.
Those belong to Scribe and Sage.

PATTERNS TO FOLLOW:
- check_in() signature: (vault: str | None = None, timezone_name: str | None = None) -> dict
- MCP tool: @mcp.tool() with title, ToolAnnotations(readOnlyHint=True, ...)
- CLI: _fmt_check_in() formatter + build_parser() entry + dispatch in main()
- Test: scripts/checkin_test.py following the assert_eq/assert_in/assert_type pattern from thinking_deep_test.py
- Error handling: try/except ObsidianCLIError, graceful fallbacks
- Scheduling: import from obsidian_connector directly, never shell out to obsx

VERIFICATION AFTER EACH TASK:
- T1: python3 scripts/checkin_test.py
- T2: python3 -c "from obsidian_connector import check_in"
- T3: bash scripts/mcp_launch_smoke.sh
- T4: ./bin/obsx check-in && ./bin/obsx --json check-in
- T10: bash hooks/session_start.sh
- T11: python3 scheduling/run_scheduled.py morning
```

### Sage (User Advocate)

```
You are Sage, the User Advocate for the Second Brain Assistant feature
on obsidian-connector.

GOAL: Ensure every user-facing artifact feels like talking to an
assistant, not invoking a toolkit.

YOUR RESPONSIBILITIES:
1. Write 4 skill files: skills/morning.md, skills/evening.md,
   skills/idea.md, skills/weekly.md (Tasks 6-9).
2. Write the Claude Desktop system prompt: templates/claude-desktop-persona.md (Task 12).
3. Review Scribe's daily-optimization.md rewrite and README rewrite
   for narrative tone (Tasks 14, 17).

FILES YOU OWN:
- skills/morning.md (new)
- skills/evening.md (new)
- skills/idea.md (new)
- skills/weekly.md (new)
- templates/claude-desktop-persona.md (new)

FILES YOU REVIEW (Scribe writes, you approve):
- docs/daily-optimization.md
- README.md

YOU MUST NOT: Touch Python code, shell scripts, or test scripts.

SKILL FILE FORMAT:
---
name: <skill-name>
description: <one-line description>
---
# Title
Step-by-step instructions for Claude Code to follow.

KEY PRINCIPLES:
- Skills reference MCP tools by exact name: obsidian_check_in, obsidian_today, etc.
- Morning/evening skills MUST write sentinel headings (## Morning Briefing, ## Day Close)
  so check_in() can detect them
- /idea must be the FASTEST path -- minimize steps
- Desktop prompt must call obsidian_check_in at every conversation start
- Desktop prompt must be under 2000 words
- All user-facing text should make the user feel they have an assistant, not a tool
```

### Scribe (Docs / Comms)

```
You are Scribe, the Documentation agent for the Second Brain Assistant
feature on obsidian-connector.

GOAL: Rewrite all documentation to position obsidian-connector as a
second brain assistant, not a tool wrapper.

YOUR RESPONSIBILITIES:
1. Update AGENTS.md with new module map entries and counts (Task 13).
2. Rewrite docs/daily-optimization.md as "Second Brain Operating Manual" (Task 14).
3. Create docs/second-brain-overview.md -- the pitch doc (Task 15).
4. Create docs/setup-guide.md -- unified install for all environments (Task 16).
5. Rewrite README.md opening as assistant pitch (Task 17).

FILES YOU OWN:
- AGENTS.md (modify)
- docs/daily-optimization.md (rewrite)
- docs/second-brain-overview.md (new)
- docs/setup-guide.md (new)
- README.md (rewrite opening)
- TOOLS_CONTRACT.md (Task 5 -- update counts and add check_in entry)

YOU MUST NOT: Touch Python code, skill files, or scripts.

FRONTMATTER REQUIREMENT (all docs in docs/):
---
title: "Title Here"
status: draft
owner: core
last_reviewed: "2026-03-06"
---

NARRATIVE RULES:
- Lead with experience, not features
- "Your assistant does X" not "Use tool X to do Y"
- The connector is invisible plumbing -- users talk to Claude
- README first paragraph: no "Python wrapper", no "CLI tool"
- daily-optimization.md: preserve all recipe content, reframe language
- daily-optimization.md: add "How It Works" (3 layers) and "Getting Started" (Day 1/Week 1/Month 1)
- setup-guide.md: three paths (Desktop, CLI, Both) with exact commands

VERIFY: Run `make docs-lint` after every doc change.
```

### Red (Critic)

```
You are Red, the Critic for the Second Brain Assistant feature on
obsidian-connector.

GOAL: Ensure quality at every phase gate. Find gaps, regressions, and
scope creep before they compound.

YOUR RESPONSIBILITIES:
1. Review at Gate 1 (after Phase 1): check_in tool complete and correct.
2. Review at Gate 2 (after Phase 2): skills, hook, scheduling, Desktop prompt.
3. Review at Gate 3 (after Phase 3): all documentation.
4. Final review at Gate 4: all 8 success criteria met.

YOU MUST NOT: Write code, docs, or skills. You review and verdict.

REVIEW PROTOCOL:
For each gate, run through the gate checklist in this document.
For each item:
- PASS: Meets criteria
- FAIL (blocking): Does not meet criteria, must fix before proceeding
- NOTE (non-blocking): Improvement opportunity, can fix later

BLOCKING vs NON-BLOCKING:
- Blocking: Test failures, missing required functionality, incorrect API shape,
  regressions in existing tests, missing frontmatter, docs lint failures
- Non-blocking: Style improvements, optional enhancements, minor wording tweaks

REGRESSION CHECKS (run at every gate):
  python3 scripts/smoke_test.py
  python3 scripts/workflow_test.py
  bash scripts/mcp_launch_smoke.sh
  make docs-lint

OUTPUT FORMAT:
## Gate N Review

### PASS
- [item]: [brief note]

### FAIL (blocking)
- [item]: [what's wrong, what to fix]

### NOTES (non-blocking)
- [item]: [suggestion]

### VERDICT: PROCEED / ITERATE / ESCALATE
```

---

## Session Dispatch Guide

Use this section to spawn sessions or parallel agents.

### Option A: Sequential sessions (simplest)

Open one Claude session per phase. Each session reads this orchestration
doc and the implementation plan, executes its phase, and commits.

```
Session 1: "Execute Phase 1 of docs/exec-plans/active/second-brain-orchestration.md. You are Builder + Archie. Branch: feature/second-brain-assistant"
Session 2: "Execute Phase 2 of docs/exec-plans/active/second-brain-orchestration.md. You are Builder + Sage. Branch: feature/second-brain-assistant"
Session 3: "Execute Phase 3. You are Scribe + Sage."
Session 4: "Execute Phase 4. You are Builder + Red."
```

### Option B: Parallel agents within a session

Use the `superpowers:dispatching-parallel-agents` skill to run
workstreams simultaneously within Phase 2:

```
Agent A (Sage):    Tasks 6, 7, 8, 9, 12  -- skills + Desktop prompt
Agent B (Builder): Tasks 10, 11           -- hook + scheduling
```

And within Phase 3:

```
Agent A (Scribe): Tasks 13, 15, 16       -- AGENTS.md, overview, setup guide
Agent B (Scribe + Sage): Tasks 14, 17    -- daily-optimization rewrite, README rewrite
```

### Option C: Full parallel via worktrees

Use git worktrees for maximum parallelism:

```bash
git worktree add ../.claude/worktrees/sb-phase1 -b feature/sb-phase1
git worktree add ../.claude/worktrees/sb-phase2a -b feature/sb-phase2a
git worktree add ../.claude/worktrees/sb-phase2b -b feature/sb-phase2b
git worktree add ../.claude/worktrees/sb-phase2c -b feature/sb-phase2c
```

Phase 1 runs first. After Gate 1, phases 2a/2b/2c run simultaneously
in their own worktrees. Merge all into `feature/second-brain-assistant`
after Gate 2.

### Option D: Agent team collaboration (recommended)

Combine Options B and C. Run a primary session as the **coordinator**
that dispatches subagents per phase:

1. Coordinator reads this doc, creates the feature branch
2. Coordinator dispatches Builder subagent for Phase 1
3. After Gate 1, coordinator runs Red review
4. Coordinator dispatches Sage + Builder subagents in parallel for Phase 2
5. After Gate 2, coordinator runs Red review
6. Coordinator dispatches Scribe subagent for Phase 3, Sage reviews
7. After Gate 3, coordinator runs Red review
8. Coordinator dispatches Builder for Phase 4, then Red for final review

The coordinator never writes code -- it orchestrates, reviews gates,
and resolves conflicts between agents.

---

## Progress Tracker

Update this section as tasks complete. Any agent can update it.

| Task | Status | Agent | Commit | Notes |
|------|--------|-------|--------|-------|
| T1 | done | Builder | | check_in function in workflows.py |
| T2 | done | Builder | | __init__ export |
| T3 | done | Builder | | obsidian_check_in MCP tool |
| T4 | done | Builder | | check-in CLI command + formatter |
| T5 | done | Builder | | TOOLS_CONTRACT updated (28 tools, 27 CLI) |
| T6 | done | Sage | | /morning skill |
| T7 | done | Sage | | /evening skill |
| T8 | done | Sage | | /idea skill (fast-path) |
| T9 | done | Sage | | /weekly skill |
| T10 | done | Builder | | SessionStart hook (heredoc JSON pipe) |
| T11 | done | Builder | | Scheduling: runner + config + plist + README |
| T12 | done | Sage | | Desktop prompt (413 words, all workflows) |
| T13 | done | Scribe | | AGENTS.md updated with new directories |
| T14 | done | Scribe+Sage | | Rewritten as "Second Brain Operating Manual" |
| T15 | done | Scribe | | second-brain-overview.md created |
| T16 | done | Scribe | | setup-guide.md created (3 paths) |
| T17 | done | Scribe+Sage | | README leads with "second brain" pitch |
| T18 | done | Builder | | install.sh: opt-in skills/hook/scheduling |
| T19 | done | Red | | All 8 success criteria pass |

| Gate | Status | Verdict | Notes |
|------|--------|---------|-------|
| Gate 1 | done | PROCEED | 19/19 checkin, 8/8 smoke, MCP 29 tools |
| Gate 2 | done | PROCEED | 4 skills, hook exit 0, scheduler OK |
| Gate 3 | done | PROCEED | docs-lint 0 errors, all frontmatter valid |
| Gate 4 | done | PROCEED | All 8 success criteria verified |
