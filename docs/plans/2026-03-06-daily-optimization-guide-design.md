# Design: Daily Optimization Guide

**Date**: 2026-03-06
**Status**: approved

## Purpose

Create a user-facing doc (`docs/daily-optimization.md`) that shows how to
combine the connector's 27 tools into a daily operating system for thinking
clearer, deciding better, and shipping more. Linked from README.

## Audience

Both new users and existing Obsidian power users. Starts with a quick hook,
then organizes by operational phase with standalone recipes.

## Format

Recipe collection. Each recipe is self-contained: trigger condition, tools,
example prompt or CLI command, expected result. Users can adopt one recipe
or the full cycle.

## Framework: The Daily Operating System (MECE, cycle-based)

Four phases, each feeding the next:

1. **Awareness** -- know your current state before acting
2. **Decision-Making** -- choose well under uncertainty
3. **Execution** -- close loops and ship
4. **Reflection** -- learn from experience

## Recipe inventory

### Phase 1: Awareness (4 recipes)
- Morning briefing: `today`, `open_loops`
- Full context load: `my_world`, `context_load`
- Vault health check: `vault_structure`, `doctor`
- Know your voice: `ghost`

### Phase 2: Decision-Making (4 recipes)
- Decision logging: `log_decision`
- Challenge before you commit: `challenge_belief`
- Prior art search: `find_prior_work`
- Cross-domain insight: `connect_domains`

### Phase 3: Execution (5 recipes)
- Open loop triage: `open_loops`, `tasks`
- Daily logging: `log_daily`
- Idea graduation: `graduate_candidates`, `graduate_execute`
- Delegation scan: `delegations`
- Research note creation: `create_note`

### Phase 4: Reflection (5 recipes)
- End-of-day close: `close_day`
- Intention vs. reality: `drift`
- Idea archaeology: `trace`
- Latent idea surfacing: `ideas`
- Idea clustering: `emerge`

### Utility tools (brief note)
`search`, `read`, `neighborhood`, `backlinks`, `rebuild_index` -- building
blocks referenced within recipes.

## Recipe format

```
### Recipe name
**When**: one-line trigger condition
**Tools**: list
**Example prompt** or **CLI command**
**What happens**: 2-3 sentences
```

## File placement
- Guide: `docs/daily-optimization.md` with standard frontmatter
- README: new section after "AI agent integration" with link
- Design doc: this file (`docs/plans/2026-03-06-daily-optimization-guide-design.md`)
