---
title: "Docs Catalog"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-05"
review_cycle_days: 30
---

# Docs Catalog

Top-level index for all documentation. Every doc in `docs/` must be listed
here or in a sub-index linked from here.

## Sub-indexes

- [Design Docs](./design-docs/index.md)
- [Distribution](./distribution/index.md)
- [Quality Scores](./quality/QUALITY_SCORE.md)
- [Reliability](./reliability/CLAUDE_DESKTOP_DEBUGGING.md)

## Standalone docs

- [Tech Debt Tracker](./tech-debt-tracker.md)

## Execution plans

- [Active Plans](./exec-plans/active/) -- in-progress agent/human work
- [Completed Plans](./exec-plans/completed/) -- archived plans
- [Cache Layer Plan](./plans/2026-03-05-cache-layer.md) -- in-memory TTL cache (completed)

## Root-level docs (outside docs/)

- [TOOLS_CONTRACT.md](../TOOLS_CONTRACT.md) -- canonical JSON envelope, typed errors, command reference
- [README.md](../README.md) -- installation, Claude Desktop setup, CLI usage
