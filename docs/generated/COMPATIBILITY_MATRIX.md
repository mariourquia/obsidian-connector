---
title: "Compatibility Matrix"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Compatibility Matrix

obsidian-connector v0.1.3

## Python Version Support

| Python | CI Tested | Supported | Notes |
|--------|-----------|-----------|-------|
| 3.11   | Yes       | Yes       | Minimum required version (`requires-python = ">=3.11"`) |
| 3.12   | Yes       | Yes       | |
| 3.13   | Yes       | Yes       | |
| 3.14   | No        | Yes       | Listed in classifiers; not yet in CI matrix |
| < 3.11 | No        | No        | Will not work; f-string, `match`, `Path`, and `|` union syntax depend on 3.11+ |

CI runs on GitHub Actions with `macos-latest` across Python 3.11, 3.12, and 3.13. Docs lint runs on `ubuntu-latest` with Python 3.11 (no Obsidian dependency required for linting).

## Operating System Support

| OS             | Version      | Status       | Target Release | Notes |
|----------------|--------------|--------------|----------------|-------|
| macOS          | 12 Monterey  | Supported    | v0.1.0         | Minimum supported; not CI-tested |
| macOS          | 13 Ventura   | Supported    | v0.1.0         | Not CI-tested directly |
| macOS          | 14 Sonoma    | Supported    | v0.1.0         | `macos-latest` in CI may resolve to this |
| macOS          | 15 Sequoia   | Supported    | v0.1.0         | `macos-latest` in CI may resolve to this |
| Linux (x86_64) | Ubuntu 22.04+| Planned      | v0.2.0         | See blockers below |
| Windows        | 10/11        | Planned      | v0.3.0         | See blockers below |

## Obsidian Version Compatibility

| Obsidian Version | Compatible | Notes |
|------------------|------------|-------|
| < 1.12           | No         | CLI interface not available |
| 1.12+            | Yes        | Requires CLI to be enabled in Settings > Community plugins |
| Insider builds   | Untested   | May work but not guaranteed |

The `obsidian` CLI must be available on `PATH`. On macOS this is typically installed to `/usr/local/bin/obsidian` when enabled in the Obsidian app settings.

## Claude Desktop / Claude Code Compatibility

| Client        | Transport | Compatible | Notes |
|---------------|-----------|------------|-------|
| Claude Desktop| stdio     | Yes        | Primary target. Configure in `claude_desktop_config.json` |
| Claude Code   | stdio     | Yes        | Configure in Claude Code MCP settings |
| Any MCP host  | stdio     | Yes        | Standard MCP stdio transport via `obsx-mcp` |
| Any MCP host  | HTTP/SSE  | Yes        | Alternate transport supported by FastMCP |

Requires `mcp >= 1.0.0, < 2.0.0` (FastMCP). The MCP server exposes 27 tools and responds with typed JSON envelopes per `TOOLS_CONTRACT.md`.

## Dependency Compatibility

| Dependency  | Required Version  | Type     | Purpose |
|-------------|-------------------|----------|---------|
| mcp         | >= 1.0.0, < 2.0.0| Required | FastMCP server framework, tool annotations |
| pyyaml      | >= 6.0, < 7.0     | Optional | Scheduling features (`pip install obsidian-connector[scheduling]`) |
| hatchling   | (build-time only) | Build    | PEP 517 build backend |

All other imports (`subprocess`, `json`, `pathlib`, `dataclasses`, `argparse`, `sqlite3`, `logging`, `shutil`) are Python standard library.

## Feature Availability by OS

| Feature                     | macOS | Linux (planned) | Windows (planned) |
|-----------------------------|-------|------------------|--------------------|
| Core Python API             | Yes   | Yes              | Yes                |
| CLI (`obsx`)                | Yes   | Yes              | Yes                |
| MCP server (`obsx-mcp`)     | Yes   | Yes              | Yes                |
| Obsidian CLI IPC            | Yes   | Blocked          | Blocked            |
| Graph tools (vault indexing)| Yes   | Yes              | Yes                |
| Thinking tools              | Yes   | Yes              | Yes                |
| Cache / index               | Yes   | Yes              | Yes                |
| Audit logging               | Yes   | Yes              | Yes                |
| Daily scheduling (launchd)  | Yes   | No               | No                 |
| Uninstaller (full)          | Yes   | Partial          | Partial            |
| Doctor / health check       | Yes   | Partial          | Partial            |

**Graph tools** read `.md` files directly from the vault directory using `pathlib`. They do not call the Obsidian CLI and will work on any OS where the vault path is accessible.

**Uninstaller** uses `pathlib` for file removal (cross-platform) but calls `launchctl unload` for plist cleanup (macOS-only). On Linux/Windows, plist removal would be skipped.

## Blockers for Linux and Windows Support

### Linux (target: v0.2.0)

| Blocker | Description | Mitigation Path |
|---------|-------------|-----------------|
| Obsidian CLI | Obsidian desktop on Linux does not expose the same CLI interface as macOS. AppImage/Snap/Flatpak packaging complicates `PATH` discovery. | Abstract CLI discovery behind a platform adapter; fall back to direct vault file access where possible. |
| Scheduling | `launchd` is macOS-only. Linux uses `systemd` timers or `cron`. | Add a `systemd` timer generator alongside the existing plist generator. |
| Config paths | Config currently hardcodes `~/Library/Application Support/obsidian/obsidian.json` for vault discovery. | Use `XDG_CONFIG_HOME` on Linux (`~/.config/obsidian/obsidian.json`). |
| Uninstaller | `launchctl unload` is macOS-only. | Add `systemctl --user disable` path for systemd timers. |

### Windows (target: v0.3.0)

| Blocker | Description | Mitigation Path |
|---------|-------------|-----------------|
| Obsidian CLI | Windows Obsidian does not provide a CLI in the same way. URI protocol (`obsidian://`) exists but is not equivalent. | Investigate Obsidian URI protocol or direct vault file I/O as fallback. |
| Scheduling | No `launchd` or `systemd`. Windows uses Task Scheduler. | Add `schtasks` or `Register-ScheduledTask` support. |
| Config paths | `~/Library/` does not exist on Windows. Obsidian stores config in `%APPDATA%/obsidian/obsidian.json`. | Use `Path(os.environ["APPDATA"]) / "obsidian"` on Windows. |
| Path separators | Some string-based path handling may assume `/`. | Already using `pathlib.Path` throughout; minimal risk. |
| Subprocess calls | `subprocess.run(["obsidian", ...])` assumes Unix-style binary lookup. | Use `shutil.which("obsidian")` for portable binary discovery. |

## Version History

| Version | Date       | Compatibility Changes |
|---------|------------|-----------------------|
| 0.1.0   | 2025-12    | Initial release. macOS only, Python 3.11+, Obsidian 1.12+ |
| 0.1.3   | 2026-03    | Added uninstaller, Python 3.14 classifier, mcp 1.x dependency |
