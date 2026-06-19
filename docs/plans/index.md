---
title: "Planning Docs"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-17"
---

# Planning Docs

Feature designs, implementation plans, and product roadmap.

## Active

- [Plugin Marketplace Plan](./2026-03-17-plugin-marketplace-plan.md) -- Claude Code plugin structure for Anthropic marketplace submission (v0.2.1, executed)
- [Creation Vault OS: Design and Phased Plan](./2026-06-18-creation-vault-os.md) -- turns the creation vault into the durable backlog/session/context brain; freshness-authority spine; mario-agentops boundary (draft; Increment A shipped)
- [Creation Spine v0 Implementation Plan](./2026-06-18-creation-spine-v0-plan.md) -- TDD task-by-task plan for the first PR: schema + event log + freshness guard + session lifecycle + obsx creation status|sync|freshness-audit
- [Creation Backlog Engine v0 Implementation Plan](./2026-06-18-creation-backlog-engine-plan.md) -- TDD plan for the backlog primitive (Gap #1): events-as-truth backlog engine, materialized fence-preserving notes, hybrid completion gate, obsx creation backlog add|update|list|show + rebuild + MCP parity (draft)
- [Creation Dashboard (Phase 4 read layer) Implementation Plan](./2026-06-19-creation-dashboard-plan.md) -- Project entity + git/PR/test classifier + explainable next-action engine + reversible migration + hybrid/drilldown/rollup generators + CLI/MCP (read layer; TUI deferred to Phase 6)

## Roadmap

- [Roadmap](./ROADMAP.md) -- prioritized v0.3.0+ backlog (v0.2.0 and v0.2.1 shipped)
