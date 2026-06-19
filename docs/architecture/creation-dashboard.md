---
title: "Creation Vault OS: Creation Dashboard (Operating Console)"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/project_sync.py"
  - "obsidian_connector/ui_dashboard.py"
  - "obsidian_connector/cli.py"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-vault-schema.md"
  - "./creation-session-state.md"
tags: ["creation-vault-os", "dashboard", "project", "repo", "next-action"]
---

# Creation Vault OS: Creation Dashboard (Operating Console)

The Creation Dashboard is the **main operating console** for the Creation Vault OS, not a
passive report. It is where Mario sees every project and repo, understands current state,
and drives the next action. The same model renders across the TUI, CLI, MCP JSON, generated
Obsidian markdown, project one-pagers, and agent startup context packs. It is a core
requirement: the vault does not feel like a working brain until one dashboard answers what
exists, why it matters, where it lives, what state it is in, what is stale, what is blocked,
and what should happen next.

## Model: a project contains repos

A **Project** is a program that groups one or more repos. MCMC is a project of nine repos;
CRE Skills is a project of five. This formalizes the existing `group` field in the sync
registry into a first-class entity with a one-pager and a dashboard.

```
Project (program; was: group)
  -> Repos (per-repo status; was: the per-repo project hub)
       -> Backlog items, agent sessions, checkpoints
```

Naming note and migration: the current vault uses `type: project` for the per-repo hub at
`projects/{slug}/index.md`. This design promotes `group` to the Project entity and renames
the per-repo hub to a **repo** view. Migration moves `projects/{slug}/` under
`Projects/{Project}/Repos/{slug}.md` and creates the project one-pager, dashboard, and
backlog. The repo's `group` determines its parent Project. Migration is fence-preserving
and reversible (a mapping note records the moves); the flat layout keeps working until the
move is run.

## Target vault shape

```
Creation Vault/
  Dashboard.md                 # global operating console (generated)
  Projects.md                  # index of all projects (generated)
  Next Actions.md              # ranked cross-project recommendations (generated)
  Stale Context.md             # everything flagged stale/conflicting (generated)
  Pending Decisions.md         # open decisions needing Mario (generated)
  Active Sessions.md           # in-flight + recent agent sessions (generated)
  Projects/
    MCMC/
      Project One-Pager.md
      Project Dashboard.md
      Backlog.md
      Repos/
        mcmc-erp.md  mcmc-ehr.md  mcmc-erp-web.md  ... (per-repo status)
    CRE Skills Pro/
      Project One-Pager.md  Project Dashboard.md  Backlog.md
      Repos/ cre-skills-pro.md
```

Generated dashboards are materialized views (rebuildable from the event log + git);
hand-written intent (the one-pager prose) lives behind `<!-- service:...-notes -->` fences
and is never clobbered.

## 1. Global dashboard

`Dashboard.md` / `obsx creation dashboard` shows every active project. Per project:
name, type, product goal, product intent, current status, current phase, priority, active
repos, blocked/unblocked, stale-state warnings, active and recent agent sessions, latest
verified sync, pending decisions, top risks, next recommended action, and links to the
project one-pager, project dashboard, canonical backlog, relevant local folders, and
Obsidian notes. Supports global overview and drilldown.

## 2. Project drilldown

`Projects/{Project}/Project Dashboard.md` / `obsx creation project show <Project>` answers:
what is this project, why it matters, product goal, product intent, target users,
architecture, which repos, current state, current phase, latest verified state, roadmap,
what is next, what is blocked, what is stale, pending decisions, what context an agent
should load, and the relevant local folders, repo paths, docs, and notes.

The **project one-pager** (`Project One-Pager.md`) is the canonical narrative: short
description, product goal, product intent, target users, why it matters, architecture
summary, repo map, local directories, deployed surfaces, data flows, agent workflows,
roadmap, top priorities, blockers, key decisions, links, related notes, latest verified
status, and next best action. Prose fields are user-authored (behind fences); state fields
are generated.

## 3. Repo drilldown

`Projects/{Project}/Repos/{repo}.md` / `obsx creation repo show <repo>` tracks: repo name,
project, local path, GitHub URL, current branch, HEAD SHA, dirty/clean tree, untracked
files, recent commits, open PRs, merged PRs since last sync, test commands, last test
result, build status, deploy status, package/app version, linked backlog items, current
implementation phase, next repo-specific action, blockers, stale notes, related docs/plans,
related agent sessions, and owner / suggested agent workflow.

It classifies the repo into an obvious state: clean-and-ready, mid-implementation,
waiting-on-PR-review, blocked-by-tests, blocked-by-Mario-decision, stale-relative-to-vault,
ahead-of-vault, behind-vault, needs-sync, or ready-for-next-agent-session. The classifier
is git-grounded (a `repo_grounded` authority claim).

## 4. Interactive console behavior

From the TUI, Mario can: view all projects; filter by priority/status/staleness/blockers;
drill into a project or repo; view top next actions; reprioritize a project or backlog
item; mark a decision answered; mark an item blocked/unblocked; assign or change the
suggested agent workflow; generate a context pack; generate a frontier-agent prompt; start
or resume a session; accept/reject voice-note backlog updates; run a freshness audit; run
repo sync; copy a startup command; and open a local folder path or Obsidian note path.

Every mutation: supports `--dry-run`, shows a diff, writes an audit event (to the event
log), preserves prior state (the supersedes chain), never does a silent destructive update,
and respects the freshness/authority layer (e.g. cannot mark a repo `done` without
`source_commit`/`source_pr` evidence).

## 5. "What should I do next?" engine

The next-action engine ranks recommendations at three levels, each with explainable
reasoning (no black-box ranking):

- **Global:** what should Mario work on next across projects; what should agents work on;
  what is most urgent; most valuable; blocked; stale and needs cleanup; safe to advance;
  needs Mario's decision.
- **Project:** the next best action; which repo to touch first; which backlog item unlocks
  the most; which agent workflow to run; what context to load.
- **Repo:** the next safe technical action; tests failing; open PR; dirty tree; waiting on
  docs/spec/planning; implementation in progress; resume vs start fresh.

Recommendation shape:

```yaml
recommendation:
  scope: project            # global | project | repo
  project: MCMC
  repo: mcmc-docs
  backlog_id: BL-2026-06-18-004
  action: "Update canonical platform backlog and docs IA after latest UAT findings"
  reason:
    - "High user urgency"
    - "Blocks multiple downstream implementation agents"
    - "Docs are stale relative to recent repo changes"
    - "Voice notes mention this repeatedly"
  confidence: 0.82
  requires_mario_decision: false
  suggested_workflow: "docs-architect + repo-grounding-agent + backlog-steward"
  context_pack: "Context Packs/MCMC/docs-backlog-refresh.md"
```

Reasoning draws on the prioritization scoring in the schema doc (urgency, impact,
dependency-unlock, stale age, user emphasis, deadline, unfinished session, repo readiness)
and always names the top contributing factors.

## 6. Command surface

Added to the `obsx creation` surface (each with human output, `--json`, MCP parity, a TUI
equivalent, `--dry-run` on writes, tests, and documented failure modes):

```
obsx creation dashboard                     # global console
obsx creation dashboard --project MCMC      # project console
obsx creation dashboard --repo mcmc-ehr     # repo console
obsx creation projects                      # list projects
obsx creation project show MCMC
obsx creation project refresh MCMC          # re-derive project state (write; dry-run)
obsx creation repo show mcmc-ehr
obsx creation repo sync mcmc-ehr            # git-ground a single repo (write; dry-run)
obsx creation next [--project MCMC] [--repo mcmc-ehr]
obsx creation reprioritize [--project MCMC] # write; dry-run
obsx creation context-pack --project MCMC
obsx creation context-pack --backlog-id BL-...
obsx creation start --project MCMC
```

## 7. Obsidian-native markdown dashboards

Generate and maintain readable markdown (useful without the TUI), with natural
wikilinks/backlinks: `Dashboard.md`, `Projects.md`, `Next Actions.md`, `Stale Context.md`,
`Pending Decisions.md`, `Active Sessions.md`, `Projects/{Project}/Project Dashboard.md`, and
`Projects/{Project}/Repos/{repo}.md`. These extend the existing generated `Dashboard.md`,
`Running TODO.md`, `context/active-threads.md`, and the `groups/{Group}.md` MOCs that
`sync-creation-vault` already produces.

## 8. Agent startup behavior

A new agent session starts from the dashboard, not from stale notes or model assumptions:
load the global dashboard summary; identify the highest-priority project or ask Mario to
choose; load the project one-pager and dashboard; load the relevant repo drilldown; load the
canonical backlog item; load freshness warnings; load recent session state; generate or use
a context pack. If asked where to start, use the next-action engine, never loose memory.
See [claude-code-start-creation-work.md](./claude-code-start-creation-work.md).

## 9. Acceptance criteria

- A. `obsx creation dashboard` or the TUI shows all active projects with status, priority,
  blockers, stale warnings, and next action; Mario can drill into any project.
- B. The MCMC project dashboard shows all MCMC repos, product goal/intent/architecture,
  current repo states, top backlog items and blockers, and what to do next.
- C. `obsx creation next` returns ranked, reasoned recommendations across projects; stale
  and conflicting items are flagged; Mario can accept, reprioritize, or generate a prompt.
- D. An agent loads the dashboard and one-pager, does not rely on stale memory, selects or
  asks for the highest-value backlog item, loads the correct context pack, and writes
  session state back.
- E. Mario reprioritizes in the TUI; the canonical backlog updates; an audit event is
  written; next-action recommendations update; agent startup sees the new priority.

## Build-on-existing

This layer extends, not replaces: `project_sync.py` already produces `Dashboard.md`, active
threads, running TODO, and per-repo `sync.md` with git state; `ui_dashboard.py` is the
Textual surface to extend; the `groups/{Group}.md` MOCs are proto project dashboards. The
work is to add the Project entity, the enriched repo status, the next-action engine, the
interactive mutations (event-sourced, freshness-respecting), and the project one-pager and
dashboard generators.
