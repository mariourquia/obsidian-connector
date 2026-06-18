---
title: "Creation Vault OS: /start creation work"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/workflows.py"
  - "src/skills/sync-vault/SKILL.md"
  - "src/hooks/session_start.sh"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-session-state.md"
  - "./mario-agentops-boundary.md"
tags: ["creation-vault-os", "claude-code", "context-pack", "skill"]
---

# Creation Vault OS: /start creation work

A Claude Code skill that opens a work session from accurate, freshness-labeled context. It
is local-first and degrades to plain `obsx` calls with no external service.

## Flow

1. User runs `/start creation work`.
2. The skill runs the `creation-vault-freshness-guard`, then `obsx creation status --json`:
   refresh repo state, label freshness, surface stale warnings and conflicts.
3. Present active projects and recommended backlog items: the TUI when interactive,
   `AskUserQuestion` otherwise. The user picks or confirms an item.
4. Generate a freshness-gated context pack for the chosen item (see format below).
5. If any critical item is stale, do not silently continue: refresh from repo and vault
   automatically, or ask the user, or mark the task `blocked_by_stale_context`.
6. `obsx creation start --backlog-id <id>` writes the agent-session note and marks it
   active.
7. The session checkpoints periodically (`obsx creation sync checkpoint`).
8. At SessionEnd, write back: work performed, files/commits/PRs, next action, new blockers,
   decisions needed, backlog status changes, freshness audit.

## Freshness-gated context pack

Every generated pack carries this header (the gate), then the working content:

```
Context generated at: 2026-06-18T16:39:00-04:00
Vault snapshot: <hash>            Repo snapshot: <repo>@<branch>@<head>
Last successful sync: 2026-06-18 16:39
Relevant commits/branches: ...
Stale warnings: <list, or "none">
Conflicts: <list, or "none">
Assumptions requiring verification: ...
User decisions still pending: ...
Do NOT rely on these outdated notes: <list, or "none">
Canonical backlog item used: bkl_01J...
Canonical session state used: ses_01J...
```

Working content: project summary, repo(s) and HEAD/branch, relevant notes and recent
sessions, the backlog item, acceptance criteria, current blockers, last known state,
suggested agent team, required tools, approval gates, and the exact working prompt. Every
fact is labeled with its `authority_level`.

## Gate behavior

If a critical field is `stale_needs_review` or `conflicting`, the pack does one of: (a)
auto-refresh from repo + vault and recompute, (b) ask the user to confirm, or (c) mark the
task blocked. It never proceeds silently on stale critical context.

## Local-first fallback

With no capture service and no agentops, the skill still works: it reads the vault, runs
the git-grounded refresh, and emits the pack. The agentops handoff (suggested team,
autonomous execution) is additive, not required.

## Tests

Context-pack generation includes all header fields; the stale-critical path refuses to
continue silently; the local-first path works with services absent; SessionEnd writeback
records the required fields.
