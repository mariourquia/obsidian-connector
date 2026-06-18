---
title: "Creation Vault OS: Agent Session State"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/project_sync.py"
  - "obsidian_connector/workflows.py"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-vault-schema.md"
  - "./mario-agentops-boundary.md"
tags: ["creation-vault-os", "session", "checkpoint", "resume"]
---

# Creation Vault OS: Agent Session State

Today's `log-session` is append-only and retrospective. This design adds a resumable
session object with a lifecycle, written incrementally so another agent (or a later
session) can resume from where work stopped, even after a context-window-low cutoff.

## Session lifecycle

`active -> checkpointed -> (blocked) -> closed`. An `sessions/_active.md` marker points at
the current active session id; SessionEnd clears it. Only one active session per vault is
assumed; concurrent sessions append events independently and reconcile via the event log.

## Agent-session note (machine-written)

```yaml
id: ses_01J...
type: agent-session
status: active
backlog_item: bkl_01J...
repos: [mcmc-erp]
branch: feat/jwks-rotation
working_tree: dirty             # clean | dirty
prompt_path: prompts/mcmc-jwks-rotation.md
agent_team: mcmc-cross-repo-implementation
tools: [Read, Edit, Bash, gh]
started_at: 2026-06-18T16:39:00-04:00
last_checkpoint: chk_01J...
resumability: 0.8               # 0..1, see below
# plus the freshness block
```

Body sections (regenerated from events, user-notes fence preserved): Plan, Completed
steps, Failed steps, Decisions (with links to `decision` notes), Blockers, Next action,
Final report (on close).

## Lifecycle event to write mapping

| Lifecycle point | Event | Vault write |
|---|---|---|
| SessionStart | `session.start` | create session note, mark `_active.md`, refresh repo state |
| PlanCreated | `plan.created` | write plan to backlog item + session note |
| SpecCreated | `spec.created` | link spec artifact to backlog item |
| ImplementationStarted | `impl.started` | record repo, branch, files likely touched, tree status |
| CheckpointCreated | `checkpoint.created` | append a `checkpoint` note: completed, next, blockers, confidence |
| UserQuestionAsked | `decision.pending` | record pending decision in backlog item + session |
| UserQuestionAnswered | `decision.resolved` | update decision; unblock dependents |
| FilesChanged | `files.changed` | record changed paths + inferred scope |
| TestsRun | `tests.run` | record command, result, failures, timestamp |
| CommitCreated | `commit.created` | record SHA + message; mark related claims `repo_grounded` |
| PRCreated / PRMerged | `pr.created` / `pr.merged` | update backlog + project state |
| Blocked | `session.blocked` | mark blocker with owner + next required action |
| SessionEnd | `session.end` | final report, backlog status, next action, clear `_active.md`, run freshness audit |
| ContextWindowLow | `checkpoint.emergency` | emergency checkpoint sufficient to resume |

## Checkpoint note

```yaml
id: chk_01J...
type: checkpoint
session: ses_01J...
created_at: 2026-06-18T17:10:00-04:00
emergency: false
git: {branch: feat/jwks-rotation, head: abc1234, dirty: true}
```

Body: completed work, exact next steps, current blockers, confidence. Checkpoints are
append-only; the latest is the resume point. The connector consumes mario-agentops's
`.agentops/session-checkpoint.json` (and `refs/agentops/checkpoints/<session>`) as a
higher-authority `repo_grounded` checkpoint when present, rather than inventing a parallel
mechanism.

## Resume

`obsx creation session-resume [--session-id]` finds the latest useful checkpoint (preferring
an agentops checkpoint over a vault one when both exist), reconstructs a continuation
context pack (see the start-work doc), and reports the next action. The resume context pack
is freshness-gated: if the recorded `source_commit` no longer matches repo HEAD, the
relevant claims are downgraded to `stale_needs_review` and re-verified before use.

## Resumability score

`resumability` reflects how confidently a session can be resumed: presence of a recent
checkpoint, an explicit next action, clean-or-understood tree state, and unexpired context.
Low resumability surfaces in `creation status` as "needs reorientation."

## Tests

Session start/checkpoint/end writes, emergency checkpoint on context-window-low, resume
selecting the correct (and highest-authority) checkpoint, stale-commit downgrade on resume,
and idempotent rebuild of session notes from the event log.
