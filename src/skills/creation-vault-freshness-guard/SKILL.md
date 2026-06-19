---
name: creation-vault-freshness-guard
description: Use whenever loading vault context, writing to the vault, ingesting captures, or starting a work session. Detects stale/conflicting notes, downgrades unverified old information, and annotates context with freshness labels. Guarded mode: warns and labels, never blocks (except completion claims lacking repo evidence).
---

# Creation Vault Freshness Guard

Run `obsx creation freshness-audit --json` and `obsx creation status --json` before
relying on any vault fact. For each fact, attach its `authority_level`. Treat memory or
notes older than 7 days, or any item whose `source_commit` no longer matches repo HEAD, as
`stale_needs_review` and verify against git before acting. Refuse to mark a backlog item
`done` without `source_commit` or `source_pr` evidence. Emit a "Stale context warnings"
section in every startup context pack. Guarded mode: warn and label; do not block work
(the only hard block is unverified completion).

## When to invoke

- At the start of any agent session (SessionStart hook).
- Before writing or updating any vault note that references a repo state.
- After a `git pull` or branch switch that may advance `repo_head`.
- When loading the context pack for a planning or implementation session.

## Authority hierarchy (highest to lowest)

1. `fresh_user_instruction` -- Mario said it explicitly in the current session.
2. `repo_grounded` -- derived from a git commit/PR in the session.
3. `verified_current` -- independently confirmed by the agent during the session.
4. `agent_reported_unverified` -- agent asserted without verification.
5. `stale_needs_review` -- age or commit drift triggered downgrade.
6. `conflicting` -- two sources disagree; requires explicit resolution.
7. `deprecated` -- superseded by a newer record.

## Freshness rules

| Policy | Stale when |
|--------|-----------|
| `repo-commit` | `source_commit` differs from current `repo_head` |
| `ttl` | `now_iso > valid_until` |
| `manual` | Never auto-stale (requires explicit label change) |

## Completion hard-gate

A backlog item claiming `done` or `pr_merged` status **must** supply
`source_commit` or `source_pr` evidence. Without it, `can_complete()` returns
`(False, "completion requires repo evidence")` and the claim is rejected.

## CLI commands

```bash
# Read-only status (active session, event count, stale warnings)
obsx creation status --json

# Full freshness audit of Backlog/**/*.md
obsx creation freshness-audit --json

# Start a session (dry-run by default)
obsx creation sync start --repo mcmc-erp --branch main [--allow-write]

# Checkpoint a session (dry-run by default)
obsx creation sync checkpoint --session-id ses_XXX --summary "..." [--allow-write]

# End a session (dry-run by default)
obsx creation sync end --session-id ses_XXX --report "..." [--allow-write]
```

## Output format

All commands return the canonical JSON envelope:

```json
{
  "ok": true,
  "command": "creation status",
  "vault": "/path/to/vault",
  "duration_ms": 12,
  "data": { ... }
}
```
