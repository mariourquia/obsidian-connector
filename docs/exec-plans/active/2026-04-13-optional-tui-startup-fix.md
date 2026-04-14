---
title: "Optional TUI Startup Fix"
status: draft
owner: core
last_reviewed: "2026-04-13"
---

# Optional TUI Startup Fix

## Scope

- Move first-run marker logic out of `ui_dashboard.py` into a non-UI startup module.
- Make the CLI lazy-load the Textual dashboard only for `menu`, `setup-wizard`, and first-run onboarding.
- Treat `textual` as an optional `tui` extra in packaging and user-facing install guidance.
- Add regression coverage for non-UI startup, graceful missing-dependency failures, and packaging consistency.

## Validation

- `pytest` for CLI/TUI regression coverage.
- Relevant build/install docs updated to match the new dependency boundary.
