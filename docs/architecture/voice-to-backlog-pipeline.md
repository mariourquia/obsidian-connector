---
title: "Creation Vault OS: Voice-to-Backlog Pipeline"
status: draft
owner: mariourquia
last_reviewed: "2026-06-18"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/smart_triage.py"
  - "obsidian_connector/commitment_ops.py"
related_docs:
  - "../plans/2026-06-18-creation-vault-os.md"
  - "./creation-vault-schema.md"
tags: ["creation-vault-os", "voice", "backlog", "triage"]
---

# Creation Vault OS: Voice-to-Backlog Pipeline

Transcription, extraction, entity linking, and triage already exist in the sibling
`obsidian-capture-service` (Wispr Flow -> extraction -> `smart_triage` -> SQLite + vault
note) with an offline queue in `obsidian-capture-service-api`. This design does NOT
re-implement any of that. The new, connector-side layer is **triage-to-backlog**: turning
a transcribed capture into a reviewed, deduplicated change to the canonical backlog rather
than a dumped note.

## Boundary

- Capture service owns: audio capture, transcription, action extraction, entity linking,
  duplicate-candidate scoring, action lifecycle.
- Creation Vault OS owns: matching captures to canonical backlog items, proposing diffs,
  the human review surface, applying accepted changes via events, reprioritization, and
  the freshness audit afterward.

## Pipeline

1. **Pull** recent captures (`find-commitments` / the vault `voice-capture` notes).
2. **Detect** projects/repos, decisions, open loops, blockers, priority and time signals
   from the cleaned transcript and the service's extracted entities.
3. **Match** against canonical backlog items: content-hash plus title Jaccard, reusing the
   capture service's `duplicate-candidates` scoring. Above the strong threshold, treat as
   an update to the existing item; below the candidate threshold, treat as new.
4. **Propose** a diff, never a blind mutation: new item, or field-level updates
   (priority change, new acceptance criterion, new blocker, status change, decision
   candidate).
5. **Review** in the TUI voice inbox or via `AskUserQuestion`: accept / reject / edit per
   proposed change.
6. **Apply** accepted changes through the event log (so concurrent edits never conflict),
   linking the capture as `source_voice_captures`.
7. **Reprioritize** affected items and **run a freshness audit**.
8. **Summarize**: emit a "what changed because of this voice note" report.

## Worked example

Voice note: "the Obsidian commands still aren't helping me organize what to do next across
repos; maybe a start creation work command with a TUI and agent handoff."

Result: matches the existing `obsidian-connector` "Creation Vault OS" backlog item (no
duplicate created); raises its priority; attaches a decision candidate (TUI-first vs
command-first); adds acceptance criteria (`/start creation work`, TUI selector, agentops
handoff); links the capture; sets a next action. The change summary names each edit and the
new score.

## Safety

All proposals are read-only until accepted. Accepted writes go through events plus
`write_manager.atomic_write`. Dry-run shows the diff without applying. No capture ever
mutates a higher-authority field (e.g. a `repo_grounded` completion) without explicit
confirmation.

## Tests

Transcript-to-candidate extraction, dedupe matching (new vs update thresholds),
propose-not-mutate, accept-applies-via-events, reprioritization, the freshness audit run,
and idempotency on re-ingesting the same capture (content-hash dedupe).
