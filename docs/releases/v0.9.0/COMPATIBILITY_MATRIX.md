# Compatibility Matrix: obsidian-connector 0.9.0

> Last updated: 2026-04-13

## Runtime Requirements

| Requirement | Minimum | Recommended | Tested With                | Notes                                      |
|-------------|---------|-------------|----------------------------|--------------------------------------------|
| Python      | 3.11    | 3.12        | 3.11, 3.12, 3.13           | 3.14 not tested; not listed in trove classifiers |
| `mcp`       | 1.0.0   | latest in `<2.0.0` | pinned via `requirements-lock.txt` | Only runtime non-stdlib direct dep besides pyyaml |
| `pyyaml`    | 6.0.0   | 6.x         | pinned via `requirements-lock.txt` | Declared in base `dependencies`            |
| Obsidian desktop | 1.12 | current   | 1.12+                      | Out of process; required for MCPB surfaces that drive the app |

## Operating System Support

| OS        | Version    | Architecture   | Status                    | Notes                                      |
|-----------|------------|----------------|---------------------------|--------------------------------------------|
| macOS     | 14+        | arm64, x86_64  | supported                 | Primary dev target; DMG installer built     |
| macOS     | 13         | arm64, x86_64  | best-effort               | Covered by `macos-latest` GitHub runner; not hand-tested |
| Ubuntu    | 22.04+     | x86_64         | supported                 | pip-only install surface; no DMG/installer  |
| Debian    | 12         | x86_64         | best-effort               | Not in CI; follow Ubuntu install path       |
| Fedora    | 39+        | x86_64         | best-effort               | Not in CI                                   |
| Windows   | 10+        | x86_64         | supported                 | MSI installer built; `installer-smoke.yml` covers PowerShell subset |
| Windows   | 11         | arm64          | untested                  | Python / textual wheels on Windows arm64 not verified |

## Python Version Matrix

| Python | CI      | Base Install | `[tui]` | `[graphify]` | `[live]` | `[semantic]` |
|--------|---------|--------------|---------|--------------|----------|--------------|
| 3.11   | yes     | supported    | supported | supported  | supported | supported  |
| 3.12   | yes     | supported    | supported | supported  | supported | supported  |
| 3.13   | yes     | supported    | supported | supported  | supported | supported  |
| 3.14   | no      | untested     | untested | untested    | untested  | untested    |

## Optional Extras

| Extra        | Top-level package(s)                 | Version range            | Purpose                                   |
|--------------|--------------------------------------|--------------------------|-------------------------------------------|
| `scheduling` | `pyyaml`                             | `>=6.0,<7.0`             | Schedule config parsing (already in base) |
| `tui`        | `textual`                            | `>=1.0.0`                | Textual TUI dashboard                     |
| `live`       | `watchdog`                           | `>=4.0,<5.0`             | Filesystem watcher for live reindex       |
| `semantic`   | `sentence-transformers`              | `>=3.0,<4.0`             | Embedding-backed retrieval                |
| `graphify`   | `networkx`                           | `>=3.0,<4.0`             | Knowledge-graph module                    |
| `dev`        | `pytest`                             | `>=8.0,<9.0`             | Test runner                               |

## Install Surfaces

| Surface                    | Artifact                          | Min Claude / host requirement         | Verified?                       |
|----------------------------|-----------------------------------|---------------------------------------|----------------------------------|
| PyPI / pip                 | `obsidian_connector-0.9.0-*.whl` + sdist | Python 3.11+                     | yes (test suite)                |
| MCPB                       | `mcpb.json` + module archive     | MCPB-compatible client                | yes (build script)              |
| Claude Code plugin         | `builds/claude-code/*`            | Claude Code with plugin marketplace   | yes (plugin.json synced to 0.9.0 in 3fd3d9a) |
| macOS DMG                  | `obsidian-connector-0.9.0.dmg`    | macOS 14+                             | built by CI, click-through untested |
| Windows MSI                | `obsidian-connector-0.9.0.msi`    | Windows 10+                           | built by CI, click-through untested |

## Downstream Consumer Compatibility

| Consumer                        | Expected Pin                                | Required Surface                       |
|---------------------------------|---------------------------------------------|----------------------------------------|
| obsidian-capture-service Task 20 | `obsidian-connector==0.9.0` or `>=0.9.0,<0.10.0` | `obsidian_connector.smart_triage` (smart_triage, ClassificationResult, LLMClient, Kind, Source) + `obsidian_connector.classifiers.rule_based.RuleBasedClassifier` |
| obsidian-capture-service 15.A.2 bridge | same | `obsidian_connector.commitment_notes` (related fence) |
| obsidian-capture-service 15.C bridge | same | `obsidian_connector.entity_notes` (wiki fence) |

## Breaking Changes from 0.8.3

| Change                                                  | Migration Path                                      |
|---------------------------------------------------------|-----------------------------------------------------|
| `textual` moved from runtime to `[tui]` optional extra  | `pip install 'obsidian-connector[tui]'` if TUI used |

No other breaking changes. Public Python API, MCP tool contract, and CLI
command surface are compatible with 0.8.3.

## Deprecated Features

None deprecated in 0.9.0.

## Database Compatibility

| Component       | Min Version        | Tested With        | Notes                   |
|-----------------|--------------------|--------------------|-------------------------|
| SQLite          | stdlib `sqlite3`   | stdlib `sqlite3`   | Used by index store; stdlib-only, no external DB |

## Browser Compatibility

Not applicable. No browser-facing UI shipped in this release.
