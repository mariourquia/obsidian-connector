---
title: "Creation Vault OS: Design and Phased Plan"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/cli.py"
  - "obsidian_connector/mcp_server.py"
  - "obsidian_connector/workflows.py"
  - "obsidian_connector/project_sync.py"
  - "obsidian_connector/write_manager.py"
related_docs:
  - "../architecture/creation-vault-schema.md"
  - "../architecture/creation-session-state.md"
  - "../architecture/voice-to-backlog-pipeline.md"
  - "../architecture/claude-code-start-creation-work.md"
  - "../architecture/mario-agentops-boundary.md"
tags: ["creation-vault-os", "design", "plan", "backlog", "freshness", "agentops"]
---

# Creation Vault OS: Design and Phased Plan

## Thesis

The Creation Vault OS is not a new application. It is a `creation` layer added to
obsidian-connector's existing shared core that turns the Obsidian "creation" vault into
the durable, local-first working memory for Mario's AI-assisted work: backlog, session
continuity, context packs, decisions, and next actions across all active repos. It
**projects from** reality (git repos, the capture service, mario-agentops) rather than
owning capture or orchestration. Writes flow through an append-only event log; the
human-readable markdown notes are materialized views that can be rebuilt. That
event-sourced shape is what structurally prevents stale memory from corrupting current
state.

The single most important property: the vault is authoritative only because it is
continuously re-derived from git and other primary sources. Old notes and old memories
are hints, never authority, until revalidated.

## Locked decisions (2026-06-18)

1. **Vault location: hybrid.** Canonical markdown stays in the iCloud `creation` vault
   (Obsidian-native, mobile-visible). The append-only event log and derived indexes live
   outside iCloud at `~/.obsidian-connector/creation/<vault-id>/`, beside the existing
   audit log, so a hot-append file never races iCloud sync.
2. **Freshness gate: hybrid.** Label and warn on every context-pack fact and backlog
   claim; hard-block only `done` and `PR merged` claims that lack `source_commit` or
   `source_pr` evidence.
3. **First PR: freshness spine + session lifecycle.** Schema, event log, freshness guard,
   `creation status`, `creation sync start|checkpoint|end`, `creation freshness-audit`.
   No TUI, voice, MCP parity, or agentops wiring in PR 1.
4. **mario-agentops coupling: hook-level shell-out.** `obsx creation sync ...` calls are
   embedded directly into agentops hooks (fail-open, debounced, backgrounded). See the
   boundary doc and "Increment A" below.

## Current state (grounded)

- obsidian-connector is a projection and control surface, not the capture engine. CLI
  (`cli.py`) and MCP server (`mcp_server.py`) are parallel thin wrappers over a shared
  core (`workflows.py`, `client_fallback.py`, `project_sync.py`, `thinking.py`,
  `commitment_ops.py`). Add a function to the core once, expose it in both. ~115 CLI
  invocations and ~113 MCP tools, near 1:1, enforced by `TOOLS_CONTRACT.md`.
- Canonical JSON envelope `{ok, command, vault, duration_ms, data|error}` (`envelope.py`).
  `--dry-run` on mutating CLI commands. Append-only audit JSONL at
  `~/.obsidian-connector/logs/`. Atomic writes plus snapshots and `rollback`
  (`write_manager.py`), AST-audited by `tests/test_hardening.py`.
- Reusable primitives already present: `context-load` (read-only bundle), `log-session`
  (append-only session log), `sync-projects` (git to dashboards), `schedule fire --event`
  (event firing), `run` (YAML recipe engine), thinking tools, idea routing.
- Capture already exists in siblings: `obsidian-capture-service` (Mac FastAPI: Wispr Flow
  transcripts, extraction, triage, dedupe, action lifecycle) and
  `obsidian-capture-service-api` (Vercel/Neon offline queue). `local-research-os` is a
  third local-first system with checkpoints, resume, a typed wiki, and a bounded agent
  worker.
- The existing vault is automation-managed with a `type:` discriminator
  (project/session/daily/card/idea/group/plan/commitment), a dual-ownership convention
  (`index.md`/`todo.md` user-curated and never clobbered; `sync.md`/dashboards
  regenerated), and service-managed fences (`<!-- service:...:begin/end -->`) as the
  safe-write pattern.
- mario-agentops is a governance plugin (hooks, gates, autonomy, loops, checkpoints,
  memory). It had no durable lifecycle-event log; integration is added as fail-open
  shell-outs (Increment A).

## Gaps (ranked)

1. **No backlog primitive** (the top functional gap). Work items are scattered across
   `commitments`, `open-loops`, `running-todo`, `due-soon`, `unrouted-actions`, and
   `delegations`. This is task aggregation, not backlog management.
2. **No freshness/authority/conflict layer** (the top architectural gap). No provenance
   beyond date-only `last_reviewed`, no staleness policy, no `supersedes`/`superseded_by`,
   no `confidence`/`authority_level`, no conflict records, no event-log-plus-materialized
   model, no repo-evidence gating on completion.
3. **No session object model or resume.** `log-session` is append-only and retrospective;
   `context-load` is read-only. No `start`/`checkpoint`/`resume`/`end` state machine, no
   active-session marker, no resume pointer, no handoff package.
4. **No context-pack save or freshness-gated pack.**
5. **Missing verbs**: `next`, `handoff`, `reprioritize`, `voice-review`, `session-resume`,
   context-pack save.
6. **No repo-reality verification** of a backlog or session claim.
7. **No uniform MCP write-safety** (`dry_run`) to match the CLI.

## Architecture

Layers:

- **L0 Sources of truth:** git repos under `~/dev`, capture-service SQLite, agentops
  events and checkpoints, the user's newest instruction, the Claude memory store.
- **L1 Event spine (new):** `creation_events.jsonl`, append-only and immutable, at
  `~/.obsidian-connector/creation/<vault-id>/events/` (outside iCloud). Every state change
  is an event first.
- **L2 Canonical materialized notes:** backlog items, agent sessions, context packs,
  decisions, plus extended project hubs, in the vault as markdown + frontmatter. Rebuilt
  from L1 by `obsx creation rebuild`. Auto-regions behind service fences.
- **L3 Freshness/authority spine (new, cross-cutting):** every canonical note carries a
  provenance + freshness block; an authority hierarchy resolves conflicts; a
  `creation-vault-freshness-guard` runs on read, write, ingest, and session start.
- **L4 Surfaces:** CLI `obsx creation *`, MCP `obsidian_creation_*`, the Textual TUI, and
  the Claude Code `/start creation work` flow.
- **L5 Integration:** the mario-agentops event contract (hook-level shell-out).

### Source-of-truth hierarchy (deterministic conflict resolution)

Highest to lowest: fresh explicit user instruction (this session) > live repo state (git
HEAD, branch, dirty tree, merged PRs, tests) > agentops harness events (verified
gate/commit/PR facts) > latest approved backlog item or decision > canonical
project/session notes > unstructured daily/inbox notes > old memories and old session
summaries (hints only, never authoritative until revalidated).

### Status labels

Every context-pack fact and backlog claim carries one of: `verified_current`,
`fresh_user_instruction`, `repo_grounded`, `agent_reported_unverified`,
`stale_needs_review`, `deprecated`, `conflicting`.

### Track A: freshness, authority, and conflict resolution (first-class)

This is not a late phase. The event spine plus the freshness/authority frontmatter is the
foundation built in Phases 1 and 2 and threaded through every later phase. It is how each
failure mode is defeated:

| Failure mode | Defense |
|---|---|
| Old note treated as current | `staleness_policy` + `valid_until`; guard downgrades to `stale_needs_review` past TTL |
| Agent starts on stale context | context-pack freshness gate: refresh, ask, or mark blocked (never silent) |
| Voice note creates a duplicate backlog item | `voice-review` matches canonical backlog (content-hash + title Jaccard, reusing capture-service dedupe), proposes update not create |
| Session state not written back | session state machine writes at every lifecycle hook; SessionEnd writeback mandatory |
| Repo diverges from vault | repo-reality sync marks each claim `repo_grounded` or `stale_needs_review`; drift auditor reports |
| Concurrent agents overlap | append events first (never conflict), materialize second, detect conflicting status changes, keep both with timestamps |
| User/model memory conflicts vault | authority hierarchy: fresh user instruction and repo state beat `agent_reported` and old memory |
| Vault says done but repo disproves | completion gate refuses `done`/`merged` without `source_commit`/`source_pr` |

## Command surface

Namespace `obsx creation <verb>` with MCP mirror `obsidian_creation_*`. All return the
canonical envelope; all writes take `--dry-run` and `--allow-write`; new MCP write tools
get a uniform `dry_run` parameter (closing the current parity gap). Full specification in
the schema and session-state docs.

- Read: `status`, `next`, `backlog list|show`, `decisions`, `context-load <backlog-id>`
  (extends the existing `context-load` to a freshness-gated pack), `voice-review`,
  `freshness-audit`.
- Write: `start [--backlog-id]`, `tui`, `ingest`, `reprioritize`, `handoff <backlog-id>`,
  `backlog add|update`, `decisions record|resolve`, `sync-repos`, `rebuild`.
- Sync family (callable by hooks, agentops, CLI, MCP, TUI):
  `creation sync start|checkpoint|plan|spec|files|tests|commit|pr|end|freshness-audit|resolve-conflicts`,
  each supporting `--dry-run --json --vault --project --repo --session-id --backlog-id
  --evidence --allow-write`.

## Vault schema (summary)

New and extended note types built on the existing `type:` discriminator and fence
convention: `backlog-item` (new), `agent-session` (extends `session`), `context-pack`
(new), `decision` (new typed), `checkpoint` (new), `voice-capture` (extended). Every
canonical note carries a freshness block (`id`, `authority_level`, `confidence`,
`last_verified_at`, `last_verified_by`, `verification_source`, `source_repo`,
`source_branch`, `source_commit`, `source_pr`, `source_session`, `staleness_policy`,
`valid_until`, `supersedes`, `superseded_by`). Backlog items carry the full field set
(project, repos, priority, status, type, owner, source notes, acceptance criteria,
blockers, dependencies, recommended context pack, suggested workflow, prompt path, last
session, next action, last touched, confidence/urgency/impact, ready_for_agent,
needs_decision). Migration extends existing notes in place via additive fences and
backfills backlog items as `stale_needs_review`. Full detail:
[creation-vault-schema.md](../architecture/creation-vault-schema.md).

## Session state model (summary)

A resumable `agent-session` note plus an active-session marker, written at SessionStart,
PlanCreated, ImplementationStarted, CheckpointCreated, UserQuestionAsked/Answered,
FilesChanged, TestsRun, CommitCreated, PRCreated/Merged, Blocked, SessionEnd, and
ContextWindowLow. Resume consumes the latest checkpoint plus agentops's
`.agentops/session-checkpoint.json`. Full detail:
[creation-session-state.md](../architecture/creation-session-state.md).

## Voice-to-backlog (summary)

Reuse the capture service for transcription, extraction, entity linking, and triage. The
new connector-side layer is triage-to-backlog: match against canonical backlog (dedupe),
propose updates as a diff (never blind-create), review in the TUI or via AskUserQuestion,
accept via events, reprioritize, freshness-audit, and emit a "what changed" summary. Full
detail: [voice-to-backlog-pipeline.md](../architecture/voice-to-backlog-pipeline.md).

## /start creation work (summary)

A Claude Code skill that runs the freshness guard, presents projects and recommended
backlog items, generates a freshness-gated context pack (with the mandatory header:
generated-at, vault and repo snapshots, stale warnings, conflicts, assumptions to verify,
pending decisions, canonical item and session used), starts the session, checkpoints
periodically, and writes back at SessionEnd. Local-first and robust with no external
service. Full detail:
[claude-code-start-creation-work.md](../architecture/claude-code-start-creation-work.md).

## mario-agentops boundary (summary)

A contract, not coupling. agentops owns orchestration, gates, approvals, loops, autonomy,
and checkpoints. obsidian-connector owns vault schema, backlog, context packs, voice
triage, the TUI, and the human-readable brain. Hook-level shell-out: agentops hooks call
`obsx creation sync ...` (fail-open, debounced, backgrounded) at lifecycle points. Neither
system requires the other. Full detail:
[mario-agentops-boundary.md](../architecture/mario-agentops-boundary.md).

## Phased plan

Track A (freshness/authority/sync) is foundational, built in Phases 1 and 2 and threaded
through later phases, not deferred.

- **Phase 0: repo audit + current-state map.** This document; reconcile the
  `~/Documents/GitHub` to `~/dev` path drift; refresh the repo registry; add
  obsidian-connector to `~/dev/CLAUDE.md`. (Largely done; see Increment A.)
- **Phase 1: schema + freshness spine + migration.** `creation_schema.py`,
  `creation_freshness.py`, templates, a creation/engineering vault preset. Tests:
  frontmatter round-trip, freshness-block parse, ID assignment, fence-preserving
  migration. Acceptance: existing notes carry freshness blocks without losing user
  content. Risk: vault mutation; mitigate with `--dry-run` defaults and snapshots.
- **Phase 2: event spine + backlog/state engine.** `creation_events.py` (append-only,
  outside iCloud), `creation_backlog.py`, `creation_session.py`, `creation rebuild`.
  Tests: append-then-materialize, rebuild idempotency, concurrent-append conflict
  detection. Acceptance: Flow D (stale note never overwrites higher-authority state).
- **Phase 3: voice-ingestion intelligence.** Reuse capture-service; add
  `creation_voice_triage.py`. Acceptance: Flow C.
- **Phase 4: `obsx creation ...` command surface.** Acceptance: Flow A from CLI.
- **Phase 5: MCP parity.** Mirror every verb with a uniform `dry_run`; update
  `TOOLS_CONTRACT.md`. Acceptance: Flow A from MCP.
- **Phase 6: TUI.** Extend `ui_dashboard.py`; visual-companion design pass first.
- **Phase 7: `/start creation work` flow.** New skill plus the freshness guard.
  Acceptance: Flow A end-to-end with the freshness header.
- **Phase 8: session save/resume + checkpointing.** SessionStart hydration, emergency
  checkpoint, `session-resume`. Acceptance: Flows B and E.
- **Phase 9: mario-agentops boundary.** Hook-level shell-out at all lifecycle points
  (started in Increment A: SessionStart/SessionEnd + git-mutation; extend to
  plan/spec/files/tests/pr/blocked).
- **Phase 10: autonomous backlog execution (later, behind agentops gates only).** Not
  until Phases 1 to 9 are proven.

## Acceptance flows

- A. New session starts from accurate, freshness-labeled context.
- B. An agent session updates the vault while working; another agent can resume from the
  context-window-low checkpoint.
- C. A voice note updates the canonical backlog without creating duplicates, then
  reprioritizes and freshness-audits.
- D. A stale note conflicting with repo reality is marked stale/conflicting, the context
  pack warns, and canonical state is not overwritten.
- E. Session end creates a durable handoff: report, backlog status, explicit next action,
  repo evidence, open decisions and blockers.

## Risks and open decisions

- local-research-os relationship: borrow its checkpoint and typed-wiki patterns, or
  integrate? Lean: borrow, do not merge yet.
- Canonicalize the two sync engines: the bash `sync-creation-vault` versus the connector's
  Python `sync_projects()`. Lean: fold the registry-driven sync into obsidian-connector
  over time; keep the bash script working in the interim.
- Capture-service as required vs optional: optional; the brain must work without it.
- The prior `creation/specs/2026-04-12-vault-hub-redesign-design.md` is the predecessor
  that created the folder-per-project structure; this builds on it.

## First PR scope ("Creation spine v0")

Smallest slice that proves the anti-stale foundation and that everything downstream depends
on: `creation_schema.py` (freshness block, machine IDs, backlog-item type),
`creation_events.py` (append-only log outside iCloud), `creation_freshness.py` (authority
hierarchy, 7 labels, staleness), `creation_session.py` (`start`/`checkpoint`/`end`); CLI
`obsx creation status`, `obsx creation sync start|checkpoint|end`, `obsx creation
freshness-audit` (all with `--json` and `--dry-run`); the `creation-vault-freshness-guard`
skill (guarded mode); migration backfilling backlog items as `stale_needs_review`; tests
mirroring `tests/`; `TOOLS_CONTRACT.md` updated; obsidian-connector added to
`~/dev/CLAUDE.md`. Explicitly out of PR 1: TUI, voice, MCP parity, full agentops wiring,
`next`/`handoff`/`reprioritize`.

## Increment A (shipped 2026-06-18, ahead of the spine)

A precondition fix and the first slice of the agentops boundary, done because the vault was
authoritatively wrong (the sync read a dead repo root):

- **Path fix (live):** `~/.local/bin/sync-creation-vault` `GITHUB_ROOT` now defaults to
  `~/dev` (override `CREATION_VAULT_REPO_ROOT`), correcting the dead `~/Documents/GitHub`
  root that had reduced the sync to a single repo. `~/.claude/commands/load-project.md`
  repointed to `~/dev`. The nightly LaunchAgent is fixed by the same edit.
- **Registry refresh (live):** the `REPOS=(` array now tracks 38 current `~/dev` repos
  (dropped the two archived AMOS repos and `quant_portfolio`), with new `cre-skills`,
  `obsidian`, and `wine` groups. Regenerated: all 38 resolve with real git state.
- **agentops auto-sync hooks (PR open):** mario-agentops PR #17
  (`feat/vault-autosync-hooks`, v0.7.2) adds `hooks/sync-creation-vault.sh`
  (SessionStart + SessionEnd) and `hooks/sync-on-git-mutation.sh` (PostToolUse Bash),
  fail-open, debounced, recursion-guarded, with a kill switch
  (`AGENTOPS_DISABLE_VAULT_SYNC`). 281 tests plus a new 9-test suite, plugin validate, and
  validate-hooks all green. Awaiting Mario's review and merge.

Follow-ups: two orphaned archived project folders in the vault; canonicalizing the two
sync engines (tracked above).
