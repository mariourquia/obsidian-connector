# Docs Catalog

Top-level index for all documentation.

## User-facing docs

- [Setup Guide](./setup-guide.md) -- three installation paths (Desktop, CLI, both)
- [Daily Optimization Guide](./daily-optimization.md) -- 18 recipes across 4 phases
- [Reliability / Debugging](./reliability/CLAUDE_DESKTOP_DEBUGGING.md)

## Distribution

- [Distribution docs](./distribution/index.md) -- marketplace strategy and submission checklists

## Release artifacts

- [Generated docs](./generated/) -- release notes, compatibility matrix, security review

## Planning

- [Roadmap](./plans/ROADMAP.md) -- prioritized backlog

## Implementation

- [Commitment dashboards + review surfaces](./implementation/commitment_dashboards.md) -- eight dashboards under `Dashboards/` and `Dashboards/Review/`; CLI `obsx review-dashboards`, MCP `obsidian_review_dashboards`
- [Commitment note schema](./implementation/commitment_note_schema.md)
- [Commitment commands](./implementation/commitment_commands.md)

## Architecture

- [Task 26 -- Review dashboards](./architecture/task_26_review_dashboards.md) -- ADR for the Daily/Weekly/Stale/Merge Candidates review surfaces
- [Creation Vault OS: Vault Schema](./architecture/creation-vault-schema.md) -- note types, freshness/authority frontmatter, backlog-item schema, migration
- [Creation Vault OS: Agent Session State](./architecture/creation-session-state.md) -- resumable session lifecycle, checkpoints, resume
- [Creation Vault OS: Voice-to-Backlog Pipeline](./architecture/voice-to-backlog-pipeline.md) -- capture-service reuse plus triage-to-backlog diffs
- [Creation Vault OS: /start creation work](./architecture/claude-code-start-creation-work.md) -- Claude Code flow and the freshness-gated context pack
- [Creation Vault OS: mario-agentops Boundary](./architecture/mario-agentops-boundary.md) -- event contract, hook-level shell-out, Increment A

## Root-level docs (outside docs/)

- [TOOLS_CONTRACT.md](../TOOLS_CONTRACT.md) -- canonical JSON envelope, typed errors, command reference
- [README.md](../README.md) -- installation, Claude Desktop setup, CLI usage
