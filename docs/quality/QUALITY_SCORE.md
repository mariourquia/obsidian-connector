---
title: "Quality Score"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-05"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/"
  - "scripts/"
---

# Quality Score

## Scoring rubric

| Grade | Meaning |
|-------|---------|
| A | Docs verified, tests >80%, no known debt |
| B | Docs verified, tests >60%, minor debt |
| C | Docs draft or stale, tests >40%, moderate debt |
| D | Docs missing or stale, tests <40%, significant debt |
| F | No docs, no tests, critical debt |

## Domain scores

| Domain | Docs | Tests | Tech Debt | Grade |
|--------|------|-------|-----------|-------|
| client (core CLI wrapper) | TOOLS_CONTRACT.md (verified) | smoke_test.py (8 tests) | low | B |
| cache | TOOLS_CONTRACT.md + cache plan (verified) | cache_test.py (16 tests) | none | A |
| MCP server | README + TOOLS_CONTRACT.md (verified) | mcp_launch_smoke.sh (3 checks) | none | B |
| CLI | TOOLS_CONTRACT.md (verified) | smoke_test.py (shared) | none | B |

## Coverage gaps

- No unit tests for `audit.py`, `envelope.py`, `errors.py` (low risk, simple modules)
- No integration test for `--dry-run` on all mutating commands
