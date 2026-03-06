---
title: "Directory Submission Checklist"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# Anthropic MCP Directory Submission Checklist

Artifacts required for submitting obsidian-connector to the Anthropic MCP directory.

- [x] README with setup instructions
- [x] PRIVACY.md
- [x] Tool annotations on all MCP tools (readOnlyHint, destructiveHint, title)
- [x] mcpb.json manifest
- [ ] Screenshots of tools in action
- [x] Category tags (productivity, notes, knowledge-management)
- [x] Version number (0.2.0)
- [x] License file (MIT)

## Notes

- Screenshots are the only remaining TODO. Capture at least: search results, daily log append, doctor health check, and today brief in Claude Desktop.
- The mcpb.json manifest is ready but cannot be validated against the official schema until the MCPB CLI is publicly released.
- Once MCPB is available, run `mcpb build` and `mcpb publish` to submit.
