---
title: "Tech Debt Tracker"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-16"
review_cycle_days: 30
---

# Tech Debt Tracker

Tracked items from the v0.2.0 hardening review. Items are prioritized for
future releases.

## Deferred to v0.2.1

| # | Finding | Description | Impact |
|---|---------|-------------|--------|
| 6 | Module size | `cli.py` (1,598 LOC) and `workflows.py` (1,603 LOC) should be split | Hard to navigate, test, review |
| 13 | Parameter naming | Inconsistent: `name_or_path` vs `note_path`, `top_n` vs `max_ideas` vs `limit` | LLM confusion when calling tools |
| 14 | Long functions | 4 functions >150 LOC: `ghost_voice_profile`, `deep_ideas`, `drift_analysis`, `graduate_execute` | Hard to test individual paths |
| 15 | Error heuristic fragility | `client.py` keyword-scans stderr to classify errors | Breaks if Obsidian CLI changes messages |

## Backlog

| # | Finding | Description | Impact |
|---|---------|-------------|--------|
| 16 | No config.py tests | Env var precedence, missing config, malformed JSON untested | Silent misconfiguration |
| 17 | doctor.py gaps | No Obsidian version validation, no config.json syntax check | Incomplete health assessment |
| 25 | No retry logic | Transient timeouts in client.py not retried | Flaky under load |
| 19 | README narrative | Missing 2-3 sentence emotional hook at top | Visitors close tab |
