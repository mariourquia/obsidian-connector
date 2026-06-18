---
title: "Creation Vault OS: mario-agentops Boundary"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/cli.py"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-session-state.md"
tags: ["creation-vault-os", "agentops", "integration", "boundary"]
---

# Creation Vault OS: mario-agentops Boundary

A contract, not coupling. The two systems exchange structured events; neither requires the
other to function.

## Ownership

- **mario-agentops owns:** orchestration, safety gates, approval policy, loop engineering,
  autonomous execution, agent lifecycle, and checkpoints.
- **obsidian-connector owns:** the vault schema, backlog, context packs, voice triage, the
  TUI, and the human-readable project brain.
- **Exchange:** stable lifecycle events. Decision (chosen 2026-06-18): hook-level
  shell-out. agentops hooks call `obsx creation sync ...` directly. A future option is a
  decoupled tail of an `.agentops/events/*.jsonl` stream; the CLI surface is identical
  either way.

## Contract for the shell-out

Every `obsx creation sync ...` call invoked from an agentops hook MUST be:

- **Fail-open:** exit 0 on any error; a missing `obsx`/sync binary is a silent no-op. No
  hard dependency in either direction.
- **Backgrounded and timeout-bounded:** never hold a session open (mirrors the existing
  `session-end.sh` detach pattern).
- **Debounced:** a shared marker (outside iCloud) prevents rapid session churn from
  stacking syncs.
- **Recursion-guarded:** `AGENTOPS_SESSION_HOOK_ACTIVE` so a delegated `claude -p` never
  triggers a sync. Global kill switch `AGENTOPS_DISABLE_VAULT_SYNC`.

## Lifecycle to sync mapping

| agentops hook / skill point | obsx call |
|---|---|
| SessionStart | `creation sync start` (and refresh) |
| plan skill finalized | `creation sync plan` |
| safe-implementation start | `creation sync files` |
| PostToolUse: tests run | `creation sync tests` |
| PostToolUse: git commit | `creation sync commit` |
| PostToolUse: gh pr merge | `creation sync pr` |
| PreToolUse gate deny (blocked) | `creation sync end --status blocked` |
| Stop / PreCompact checkpoint | `creation sync checkpoint` |
| SessionEnd | `creation sync end` |

Note: there is no `PostPlanMode` hook in Claude Code; the plan-finalized sync hooks into
the agentops `plan` skill's completion step (or PreToolUse detecting `ExitPlanMode`).

## Authority levels of agentops events

Commit, PR-merge, and test-run events are `repo_grounded` (high authority: they reflect
actual git/test reality). Plan and intent claims are `agent_reported_unverified` (low) until
verified against the repo. The freshness layer encodes this distinction.

## Increment A (status)

The first slice of this boundary shipped 2026-06-18 as mario-agentops PR #17
(`feat/vault-autosync-hooks`, v0.7.2): `hooks/sync-creation-vault.sh` (SessionStart +
SessionEnd) and `hooks/sync-on-git-mutation.sh` (PostToolUse Bash) calling the user's
`sync-creation-vault`, fail-open, debounced, recursion-guarded, with the
`AGENTOPS_DISABLE_VAULT_SYNC` kill switch. Awaiting review and merge. The remaining
lifecycle points (plan/spec/files/tests/pr/blocked, calling `obsx creation sync ...`) land
in Phase 9 once the `creation sync` surface exists.

## Open: canonicalize the two sync engines

Today two engines write vault project state: the standalone bash `sync-creation-vault`
(registry-driven, what Increment A wires) and the connector's Python
`project_sync.sync_projects()` (a different layout, not currently active as a plugin hook).
Phase 9 folds the registry-driven sync into obsidian-connector so there is one engine, with
the bash script kept working in the interim.

## Tests

Each hook is fail-open, debounced, recursion-guarded, and kill-switchable (covered by
`tests/test_sync_creation_vault_hook.py` in mario-agentops); the `obsx creation sync`
verbs are covered on the connector side once they exist.
