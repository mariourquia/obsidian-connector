---
title: "Exec Plan: obsidian-connector vNext"
status: deprecated
owner: "mariourquia"
last_reviewed: "2026-03-06"
sources_of_truth:
  - "obsidian_connector/"
  - "scripts/"
  - "bin/"
---

## Goal

Make obsidian-connector a polished, distributable Obsidian+Claude integration:
- High-level workflow tools (my-world, today, close-day, open-loops)
- Thinking tools (challenge-belief, emerge-ideas, connect-domains)
- MCPB packaging for one-click Claude Desktop install
- Marketplace publishing strategy (Claude Code plugins + Anthropic directory)
- Reliability hardening for Desktop-first usage

## Non-goals

- Building a web UI or dashboard
- Real-time sync / file watching
- Multi-vault simultaneous access
- Plugin system within obsidian-connector itself

## Fix-first (before new features)

- [x] Fix MCP config: bypass bash wrapper for macOS sandbox (commit 892394c)
- [ ] Verify Claude Desktop loads tools after restart (user action: restart Desktop)

## Epics

### Epic 1: Reliability & UX Hardening (Agent 5) -- FIRST

Owner: Agent 5
Priority: P0 (blocking -- must land before new tools)

- [ ] **T5.1** Add explicit timeouts to all subprocess calls in client.py
- [ ] **T5.2** Improve error mapping: ensure all error types propagate to MCP as structured envelopes
- [ ] **T5.3** Enhance doctor --json: add actionable steps field per check
- [ ] **T5.4** Create docs/reliability/CLAUDE_DESKTOP_DEBUGGING.md (log locations, common failures, manual reproduction)
- [ ] **T5.5** Verify: mcp_launch_smoke.sh passes, wrong vault produces typed error, MCP starts cleanly

Acceptance tests:
- scripts/mcp_launch_smoke.sh passes
- `./bin/obsx --json --vault "NONEXISTENT" search "test"` returns typed VaultNotFound error
- MCP server starts and lists tools
- docs/reliability/CLAUDE_DESKTOP_DEBUGGING.md exists and is indexed

### Epic 2: Workflow OS Tools (Agent 1)

Owner: Agent 1
Priority: P1

- [ ] **T1.1** Implement `my_world_snapshot()` in workflows.py
- [ ] **T1.2** Implement `today_brief()` in workflows.py
- [ ] **T1.3** Implement `close_day_reflection()` in workflows.py (read-only unless confirm)
- [ ] **T1.4** Implement `list_open_loops()` in workflows.py
- [ ] **T1.5** Add CLI subcommands: my-world, today, close, open-loops
- [ ] **T1.6** Add MCP tools: obsidian_my_world, obsidian_today, obsidian_close_day, obsidian_open_loops
- [ ] **T1.7** Update TOOLS_CONTRACT.md with new tools
- [ ] **T1.8** Add scripts/workflow_os_test.py

Acceptance tests:
- `./bin/obsx my-world --json` returns JSON envelope with recent notes, tasks, open loops
- `./bin/obsx today --json` returns today's brief
- `./bin/obsx close --json` returns reflection (no write without --confirm)
- `./bin/obsx open-loops --json` returns open loop items
- scripts/workflow_os_test.py passes

### Epic 3: Thinking Tools (Agent 2)

Owner: Agent 2
Priority: P1

- [ ] **T2.1** Implement `challenge_belief()` in workflows.py
- [ ] **T2.2** Implement `emerge_ideas()` in workflows.py
- [ ] **T2.3** Implement `connect_domains()` in workflows.py
- [ ] **T2.4** Add CLI subcommands: challenge, emerge, connect
- [ ] **T2.5** Add MCP tools: obsidian_challenge_belief, obsidian_emerge_ideas, obsidian_connect_domains
- [ ] **T2.6** Update TOOLS_CONTRACT.md
- [ ] **T2.7** Add scripts/thinking_tools_test.py

Acceptance tests:
- `./bin/obsx challenge "CMBS spreads mean-revert" --json` returns structured results with citations
- `./bin/obsx emerge "liquidity risk" --json` returns idea clusters
- `./bin/obsx connect "real estate" "structured credit" --json` returns connections
- scripts/thinking_tools_test.py passes

### Epic 4: MCPB Packaging + Directory Compliance (Agent 3)

Owner: Agent 3
Priority: P2

- [ ] **T3.1** Research MCPB CLI workflow and document findings
- [ ] **T3.2** Add tool annotations/hints (readOnlyHint, destructiveHint, title) to mcp_server.py
- [ ] **T3.3** Add privacy policy to README and as standalone file
- [ ] **T3.4** Create manifest.json or mcpb config for packaging
- [ ] **T3.5** Add Makefile targets for mcpb build
- [ ] **T3.6** Add Distribution section to README
- [ ] **T3.7** Create directory submission checklist

Acceptance tests:
- Tool annotations present on all MCP tools
- Privacy policy accessible in README
- Distribution section in README covers: manual, MCPB, directory submission
- Packaging steps documented and reproducible

### Epic 5: Marketplace Publishing Strategy (Agent 4)

Owner: Agent 4
Priority: P2

- [ ] **T4.1** Research Claude Code plugin marketplace (marketplace.json feed)
- [ ] **T4.2** Research Anthropic directory submission for MCP connectors
- [ ] **T4.3** Create docs/distribution/MARKETPLACE_STRATEGY.md
- [ ] **T4.4** Document difference: Claude Code plugins vs Anthropic MCP directory
- [ ] **T4.5** Create submission-ready checklist with required artifacts
- [ ] **T4.6** If feasible: scaffold marketplace.json for Claude Code plugin feed

Acceptance tests:
- docs/distribution/MARKETPLACE_STRATEGY.md exists and is comprehensive
- Submission checklist covers both distribution paths
- Any marketplace.json validates structurally

## Integration order

1. Epic 1 (Reliability) -- blocking
2. Epic 2 (Workflow OS)
3. Epic 3 (Thinking Tools)
4. Epic 4 (MCPB Packaging)
5. Epic 5 (Marketplace Strategy)

## Verification after each integration

```bash
python3 -m compileall obsidian_connector/ main.py scripts/
python3 scripts/smoke_test.py
python3 scripts/cache_test.py
bash scripts/mcp_launch_smoke.sh
./bin/obsx doctor
./bin/obsx --json doctor
make docs-lint
```

## Progress log

- 2026-03-06: Plan created. Phase 0 reality check complete. Fix-first (MCP config) already committed.
- 2026-03-06: Epic 1 (Reliability) completed -- commit d92146e
- 2026-03-06: Epic 2 (Workflow OS) completed -- commit ebfb97e
- 2026-03-06: Epic 3 (Thinking Tools) completed -- commit ed0792f
- 2026-03-06: Epic 4 (MCPB Packaging) completed -- commit 111d9e9
- 2026-03-06: Epic 5 (Marketplace Strategy) completed -- commit d7bf1e8
- 2026-03-06: All 5 epics complete. Final verification: 15/15 tests pass, 16 MCP tools, 4/4 doctor checks pass, docs-lint clean.
