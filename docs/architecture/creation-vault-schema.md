---
title: "Creation Vault OS: Vault Schema"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/vault_init.py"
  - "obsidian_connector/vault_presets.py"
  - "obsidian_connector/commitment_notes.py"
  - "obsidian_connector/write_manager.py"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-session-state.md"
tags: ["creation-vault-os", "schema", "freshness", "backlog"]
---

# Creation Vault OS: Vault Schema

Builds on the existing vault conventions: a `type:` frontmatter discriminator, the
dual-ownership rule (user-curated files never clobbered), and service-managed fences
(`<!-- service:<name>:begin/end -->`) that protect auto-generated regions while preserving
hand-written content. New machine-generated regions MUST use the same fence pattern. All
writes go through `write_manager.atomic_write` (snapshotted, audited).

## Note type catalog

| type | location | lifecycle status | ownership |
|---|---|---|---|
| `project` (extended) | `projects/{slug}/index.md` | active / paused / shipped / dormant | user-curated; add freshness + backlog rollup behind a fence |
| `agent-session` (extends `session`) | `sessions/{id}.md` + `sessions/_active.md` | active / checkpointed / blocked / closed | machine |
| `backlog-item` (new) | `Backlog/{project}/{id}.md` | idea / ready / in_progress / blocked / in_review / done / archived | machine summary + user-editable fence |
| `context-pack` (new) | `context/packs/{id}.md` | current / stale / superseded | machine |
| `decision` (new typed) | `Decisions/{project}/{id}.md` | pending / accepted / rejected / superseded | machine summary + user notes fence |
| `checkpoint` (new) | `sessions/{session}/checkpoints/{ts}.md` | n/a | machine |
| `voice-capture` (extended) | `inbox/voice-captures/...` | inbox / triaged / linked | machine (capture service) |

## Freshness block (on every canonical note)

```yaml
id: bkl_01J...                  # ULID; new for projects/sessions/ideas that lacked IDs
authority_level: repo_grounded  # verified_current | fresh_user_instruction | repo_grounded
                                #  | agent_reported_unverified | stale_needs_review
                                #  | deprecated | conflicting
confidence: 0.8                 # 0..1
last_verified_at: 2026-06-18T16:39:00-04:00
last_verified_by: obsx-creation-sync@0.12.0
verification_source: git        # git | capture-service | agentops | user | manual
source_repo: obsidian-connector
source_branch: feat/creation-vault-os
source_commit: abc1234
source_pr: null
source_session: ses_01J...
staleness_policy: repo-commit   # repo-commit | ttl | manual ; what invalidates this note
valid_until: 2026-06-25         # for ttl policy
supersedes: []                  # ids this note replaces
superseded_by: null             # id that replaced this note
```

Field semantics:

- `authority_level` is the resolved label from the source-of-truth hierarchy (see the
  plan). It is recomputed by the freshness guard on read; the stored value is the last
  computed one.
- `staleness_policy: repo-commit` means the note is stale once `source_commit` is no longer
  the repo HEAD for `source_branch`. `ttl` uses `valid_until`. `manual` never auto-stales.
- `supersedes` / `superseded_by` form an immutable version chain so a corrected note never
  silently overwrites the prior claim.

## Backlog item schema

```yaml
id: bkl_01J...
type: backlog-item
project: mcmc-erp
repos: [mcmc-erp, mcmc-erp-web]
priority: P1                    # P0..P3
status: ready                   # idea | ready | in_progress | blocked | in_review | done | archived
work_type: feature-dev          # feature-dev | bugfix | refactor | research | ops | docs | testing | review | planning | release | architecture
owner: mario                    # or an agent role
ready_for_agent: true
needs_decision: false
acceptance_criteria:
  - "JWKS rotation endpoint returns 200 with the new key"
blockers: []
dependencies: [bkl_01H...]      # other backlog item ids
source_notes: ["inbox/voice-captures/2026/06/..."]
source_voice_captures: [cap_01K...]
recommended_context_pack: ctxp_01J...
suggested_workflow: mcmc-cross-repo-implementation
prompt_path: prompts/mcmc-jwks-rotation.md
last_session: ses_01J...
next_action: "Wire the rotation cron and add the dual-key validation test"
last_touched: 2026-06-18T16:39:00-04:00
confidence: 0.7
urgency: 8                      # 0..10
impact: 9                       # 0..10
# plus the full freshness block above
```

The machine-managed summary (status, scores, next_action, freshness) is regenerated from
events; a `<!-- service:backlog-user-notes:begin/end -->` fence holds free-form user notes
that survive regeneration. The human-readable body renders acceptance criteria, blockers,
and the linked session and context pack as wikilinks.

## Prioritization scoring (explainable)

`next` and `reprioritize` compute a transparent score and always show the inputs:

```
score = w_urgency*urgency + w_impact*impact + w_unblock*dependency_unlock
      + w_stale*stale_age_penalty + w_user*user_emphasis + w_demo*deadline_proximity
      + w_resume*unfinished_session + w_repo*repo_readiness
```

Weights live in vault config and are user-editable. Output names the top contributing
factors per item. No black-box ranking.

## Folder layout (additions)

```
creation/
  Backlog/{project}/{id}.md
  Decisions/{project}/{id}.md
  context/packs/{id}.md
  sessions/{id}.md
  sessions/_active.md
  sessions/{session}/checkpoints/{ts}.md
# event log + indexes live OUTSIDE iCloud:
~/.obsidian-connector/creation/<vault-id>/
  events/creation_events.jsonl
  index/backlog.json   index/sessions.json
```

## Machine IDs

ULID-style ids per type prefix (`bkl_`, `ses_`, `ctxp_`, `dec_`, `chk_`), assigned on
creation and stable across rebuilds. Existing notes lacking ids get one during migration,
written into frontmatter without disturbing the body.

## Migration (extend, do not replace)

1. Add the freshness block to existing project hubs and session logs via additive fences;
   never rewrite user bodies.
2. Generate `backlog-item` notes from `running-todo` + `Commitments/Open` +
   `unrouted-actions` + `open-loops`, all `authority_level: stale_needs_review` until first
   verification.
3. Assign machine ids to notes that lack them.
4. Reconcile orphaned project folders (e.g. the archived AMOS repos) into `Archive/`.

## Validation and tests

Frontmatter round-trip, freshness-block parse and defaulting, id assignment idempotency,
fence-preserving migration (AST-level, mirroring `tests/test_hardening.py`), malformed-note
tolerance, and schema-version compatibility for older notes.
