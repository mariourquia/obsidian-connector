---
title: "Roadmap"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-30"
---

# Roadmap

Prioritized backlog for obsidian-connector. Items are tagged by type and
ordered by priority within each milestone. Community PRs welcome -- see
[CONTRIBUTING.md](../../CONTRIBUTING.md).

> **How to pick up an item**: Comment on the linked issue (or open one if
> none exists), describe your approach, and wait for approval before starting.
> This prevents duplicate work.

---

## Legend

| Tag | Meaning |
|-----|---------|
| `feature` | New user-facing capability |
| `improvement` | Enhancement to existing functionality |
| `limitation` | Known constraint to overcome |
| `risk` | Data integrity or operational risk to mitigate |
| `infra` | CI, tooling, packaging, developer experience |
| `docs` | Documentation improvement |

Priority: P0 (next release) > P1 (near-term) > P2 (planned) > P3 (future)

---

## v0.7.0 -- Cross-Project & Tooling

### P1

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 25 | `feature` | **Cross-project integration with obsidian-capture-service** | Wire voice capture API into the connector for seamless vault ingestion of transcribed captures. | Open |
| 26 | `feature` | **PDF export for reports** | Generate weekly/monthly reports as PDF. Combine drift analysis, graduation history, and vault health into a downloadable artifact. | Open |
| 27 | `feature` | **Advanced graph quality tools** | Orphan detection, duplicate concept identification, and graph health scoring. | Open |
| 28 | `feature` | **Event-triggered automation** | Fire workflows in response to vault events (file create, rename, tag change) beyond scheduled cron. | Open |

### P2

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 29 | `improvement` | **Policy engine beyond protected_folders** | Extensible rule engine for write guards, naming conventions, and structural constraints. | Open |
| 30 | `infra` | **pytest migration** | Move test suites from custom `scripts/` runners to pytest for standard tooling, fixtures, and coverage reporting. | Open |
| 31 | `infra` | **PyPI publication** | Publish to PyPI so users can `pip install obsidian-connector` instead of cloning. | Open |
| 32 | `infra` | **MCPB distribution target** | Add `--target mcpb` to `tools/build.ts` to produce `.mcpb` bundles from the existing `mcpb.json` manifest. The multi-target pipeline is in place; this wires the final format. | Open |

---

## Backlog (P3 -- Future)

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 11 | `improvement` | **Newline encoding fix** | Obsidian CLI does not distinguish literal `\n` from actual newlines in output. Investigate binary-safe IPC or direct file read as workaround. | Open |
| 12 | `feature` | **Obsidian URI protocol** | Partially addressed via capability detection. Full `obsidian://` URI scheme support for read operations would eliminate the CLI plugin requirement. | Open |
| 14 | `feature` | **Export and reporting** | Generate weekly/monthly reports as standalone Markdown or PDF. Combine drift analysis, graduation history, and vault health into a single artifact. | Open |
| 16 | `feature` | **Plugin marketplace** | Package individual tool groups (graph, thinking, workflows) as separate optional installs. | Open |
| 17 | `feature` | **Collaborative vaults** | Support for shared vaults with per-user delegation tracking and conflict resolution. | Open |
| 20 | `docs` | **Video walkthrough** | Screen recording of the morning-to-evening workflow showing all four rituals in action. | Open |
| 21 | `improvement` | **Graceful pyyaml fallback** | Scheduling config currently logs a warning and uses defaults when pyyaml is missing. Surface a one-time install hint to the user instead of silently degrading. | Open |
| 23 | `risk` | **Scheduled jobs without user presence** | launchd jobs fire regardless of whether the user is at their machine, appending to the daily note silently. Add an optional "active hours" window or skip if no recent user activity. | Open |
| 24 | `infra` | **Linux/Windows native installers** | AppImage/deb for Linux, MSI/exe for Windows -- equivalent to the macOS .dmg. Currently Linux and Windows use script-based installation. | Open |

---

## Completed

| # | Type | Title | Shipped In |
|---|------|-------|------------|
| 2 | `risk` | Write conflict protection during sync | v0.6.0 |
| 3 | `improvement` | Configurable daily note format | v0.6.0 |
| 4 | `improvement` | File-watching index updates | v0.6.0 |
| 5 | `feature` | Multi-vault workflows | v0.6.0 |
| 7 | `improvement` | Scheduled automation expansion | v0.6.0 |
| 8 | `risk` | Agent draft lifecycle management | v0.6.0 |
| 9 | `feature` | Semantic search | v0.6.0 |
| 10 | `feature` | Template system | v0.6.0 |
| 15 | `improvement` | Configurable sentinel headings | v0.6.0 |
| 22 | `improvement` | Index staleness indicator | v0.6.0 |
| -- | `infra` | GitHub Actions CI | v0.1.1 |
| -- | `infra` | Release automation with sha256 checksums | v0.1.1 |
| -- | `docs` | CONTRIBUTING.md | v0.1.1 |
| -- | `docs` | SECURITY.md | v0.1.1 |
| -- | `infra` | SBOM generation | v0.1.1 |
| -- | `infra` | pyyaml optional dependency | v0.1.1 |
| -- | `infra` | `__version__` in package | v0.1.1 |
| -- | `feature` | Safe two-mode uninstaller (`obsx uninstall`) | v0.2.0 |
| -- | `infra` | Cross-platform path resolution (`platform.py`) | v0.2.0 |
| -- | `risk` | Audit log directory permissions (0o700) | v0.2.0 |
| -- | `infra` | CI expanded to macOS + Ubuntu, 15 test files | v0.2.0 |
| -- | `infra` | Circular dependency resolved (`errors.py` canonical) | v0.2.0 |
| -- | `infra` | Broad `except Exception` replaced in 8 MCP tools | v0.2.0 |
| -- | `infra` | Installer cross-platform config path resolution | v0.2.0 |
| -- | `improvement` | `file_backend.py` wired in via `client_fallback.py` adapter | v0.2.0 |
| -- | `feature` | 4 skills (`/morning`, `/evening`, `/idea`, `/weekly`) and SessionStart hook | v0.2.0 |
| 1 | `limitation` | Linux support (systemd timers, XDG paths, CI validation) | v0.2.0 |
| 6 | `improvement` | Reduce IPC dependency (`file_backend.py` + `client_fallback.py` adapter) | v0.2.0 |
| 13 | `feature` | Windows support (Task Scheduler, `%APPDATA%` paths, PowerShell installer) | v0.2.0 |
| -- | `infra` | Sigstore cosign signing on release assets | v0.2.0 |
| -- | `infra` | Hash-pinned lockfile (`requirements-lock.txt` with pip-compile) | v0.2.0 |
| -- | `infra` | 14-expert panel security review + 17 blocker remediation | v0.2.0 |

---

## Contributing to the Roadmap

**Suggest new items**: Open a [GitHub issue](https://github.com/mariourquia/obsidian-connector/issues)
with the `roadmap` label. Include the type tag, a one-paragraph description,
and your proposed priority.

**Claim an item**: Comment on the issue with your approach. Wait for maintainer
approval before starting work. This prevents wasted effort on items that may
need design discussion first.

**Priority changes**: Priorities reflect current project direction. They may
shift between releases based on community feedback and contributor interest.
