---
title: "Compatibility Matrix: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Compatibility Matrix: obsidian-connector v0.2.0

> Last updated: 2026-03-16

## Runtime Requirements

| Requirement      | Minimum | Recommended | Tested With         |
|------------------|---------|-------------|---------------------|
| Python           | 3.11    | 3.13        | 3.11, 3.12, 3.13   |
| Obsidian desktop | 1.4     | latest      | 1.4+ (CLI plugin)   |
| mcp package      | 1.0.0   | 1.26.0      | 1.26.0 (locked)     |

## Operating System Support

| OS              | Version    | Architecture     | Status   | Installer              |
|-----------------|------------|------------------|----------|------------------------|
| macOS           | 12+        | arm64, x86_64    | Tested   | .dmg, install.sh       |
| Ubuntu          | 22.04+     | x86_64           | Tested   | install-linux.sh       |
| Windows         | 10+        | x86_64           | Tested   | Install.ps1            |
| Linux (other)   | varies     | x86_64           | Untested | Manual install         |
| ARM64 Linux     | varies     | aarch64          | Untested | Manual install         |

CI matrix: macOS-latest + ubuntu-latest + windows-latest x Python 3.11, 3.12, 3.13 (9 configurations).

## Feature Availability by OS

| Feature                      | macOS    | Linux       | Windows      |
|------------------------------|----------|-------------|--------------|
| Core Python API              | Yes      | Yes         | Yes          |
| CLI (`obsx`)                 | Yes      | Yes         | Yes          |
| MCP server (`obsx-mcp`)     | Yes      | Yes         | Yes          |
| Obsidian CLI IPC             | Yes      | Yes         | Yes          |
| Graph tools (vault indexing) | Yes      | Yes         | Yes          |
| Thinking tools               | Yes      | Yes         | Yes          |
| Cache / index                | Yes      | Yes         | Yes          |
| Audit logging                | Yes      | Yes         | Yes          |
| Notifications                | Yes (osascript) | Yes (notify-send) | Yes (PowerShell toast) |
| Scheduling                   | launchd  | systemd     | Task Scheduler |
| Uninstaller                  | Full     | Full        | Full         |
| Doctor / health check        | Full     | Full        | Full         |

## Claude Desktop / MCP Client Compatibility

| Client         | Transport | Compatible | Notes                                    |
|----------------|-----------|------------|------------------------------------------|
| Claude Desktop | stdio     | Yes        | Primary target. Configure in config JSON |
| Claude Code    | stdio     | Yes        | Configure in Claude Code MCP settings    |
| Any MCP host   | stdio     | Yes        | Standard MCP stdio via `obsx-mcp`        |
| Any MCP host   | HTTP/SSE  | Yes        | Alternate transport supported by FastMCP |

35 MCP tools. Typed JSON envelope responses per `TOOLS_CONTRACT.md`.

## Dependency Compatibility

| Dependency  | Required Version   | Type     | License | Purpose                    |
|-------------|--------------------|----------|---------|----------------------------|
| mcp         | >=1.0.0, <2.0.0 (locked at 1.26.0) | Required | MIT     | FastMCP server framework   |
| pyyaml      | >=6.0, <7.0        | Optional | MIT     | Schedule config parsing    |
| hatchling   | (build-time only)  | Build    | MIT     | PEP 517 build backend      |

All other imports are Python standard library. A `requirements-lock.txt` pins mcp and all 21 transitive dependencies with SHA256 hashes (generated via `pip-compile --generate-hashes`).

## Breaking Changes from v0.1.x

| Change                                         | Impact                              | Migration                                 |
|------------------------------------------------|-------------------------------------|-------------------------------------------|
| `uninstall` MCP tool renamed to `obsidian_uninstall` | MCP callers using old tool name | Update tool name in prompts               |
| Config search order reversed (CWD no longer priority) | Users with `config.json` in CWD  | Move config.json to package directory     |
| Exception types narrowed in workflows/thinking | Code catching `Exception` from these modules | Catch specific types listed in CHANGELOG |

## Deprecated Features

No features deprecated in v0.2.0.

## Version History

| Version | Date       | Compatibility Changes                                           |
|---------|------------|-----------------------------------------------------------------|
| 0.1.0   | 2026-03-06 | Initial release. macOS only, Python 3.11+, Obsidian 1.12+      |
| 0.1.1   | 2026-03-06 | CI added, CONTRIBUTING/SECURITY/SBOM                            |
| 0.1.2   | 2026-03-06 | PYTHONPATH fix for Claude Desktop subprocess isolation           |
| 0.1.3   | 2026-03-16 | Uninstaller added, test suite expanded                          |
| 0.2.0   | 2026-03-16 | Cross-platform (macOS+Linux+Windows), 8 security fixes, 23 test files |
