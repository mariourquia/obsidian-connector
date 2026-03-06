---
title: "MCPB Research"
status: draft
owner: "mariourquia"
last_reviewed: "2026-03-06"
---

# MCPB Research

## What is MCPB?

MCPB (MCP Builder) is a CLI tool for packaging MCP servers as `.mcpb` artifacts. These artifacts enable one-click installation into Claude Desktop, removing the need for users to manually clone repos, create virtual environments, or edit `claude_desktop_config.json`.

## Expected Workflow

1. **Manifest** -- Author an `mcpb.json` file at the repo root describing the server: name, entry point, environment variables, dependencies, and category tags.
2. **Build** -- Run `mcpb build` to produce a self-contained `.mcpb` package from the manifest plus source tree.
3. **Publish** -- Run `mcpb publish` to upload the package to the Anthropic MCP directory, making it discoverable and installable from Claude Desktop's UI.

## Current Status

The MCPB CLI is **not yet publicly available**. Anthropic has described the concept as part of the MCP ecosystem roadmap, but no public binary, npm package, or PyPI distribution exists as of March 2026.

## What We Have Prepared

- `mcpb.json` at the repo root -- a manifest file following the expected schema. It declares the server name, entry point (`python3 -m obsidian_connector.mcp_server`), environment variables, requirements, and category tags.
- `PRIVACY.md` at the repo root -- linked from the manifest, documenting that the connector runs entirely locally with no telemetry.
- Tool annotations on all 16 MCP tools -- `readOnlyHint`, `destructiveHint`, and `title` set per tool, ready for directory listing.
- Makefile targets `mcpb-build` and `mcpb-validate` -- placeholder build and manifest validation commands.

## Open Questions

- Will MCPB support Python venv creation automatically, or must we bundle a pre-built venv?
- What is the `.mcpb` archive format (zip, tar, custom)?
- Does the directory submission require a review process or is it self-service?
- Will there be a `mcpb test` command for local validation before publishing?

## References

- [MCP Specification](https://modelcontextprotocol.io)
- [Claude Desktop MCP Configuration](https://docs.anthropic.com/en/docs/claude-desktop/mcp)
