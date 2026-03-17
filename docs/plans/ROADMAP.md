---
title: "Roadmap"
status: verified
owner: "mariourquia"
last_reviewed: "2026-03-16"
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

## v0.2.1 -- Resilience & Configuration

### P0 -- Must have

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 2 | `risk` | **Write conflict protection during sync** | Mutating commands (`log-daily`, `graduate execute`) can conflict with iCloud/Obsidian Sync. Add file-level locking or atomic write-then-rename to prevent partial writes. Current mitigation: atomic appends + audit log. | Open |
| 3 | `improvement` | **Configurable daily note format** | Hard-codes `YYYY-MM-DD.md` in `daily/` or root. Support arbitrary date formats and paths via `config.json` (e.g., `daily/%Y/%m/%Y-%m-%d.md`). | Open |

### P1 -- Should have

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 4 | `improvement` | **File-watching index updates** | Index lags behind live edits until `rebuild-index` runs. Add `fswatch`/`watchdog` listener to trigger incremental updates on file save. Current mitigation: mtime-based incremental on next query. | Open |
| 5 | `feature` | **Multi-vault workflows** | Cross-vault search, unified graph queries, vault-switching in CLI/MCP. Currently requires `--vault` flag or `OBSIDIAN_VAULT` env var per command. | Open |
| 7 | `improvement` | **Scheduled automation expansion** | Only morning briefing has a launchd job. Add configurable jobs for evening close and weekly review with per-workflow time/day settings. | Open |
| 8 | `risk` | **Agent draft lifecycle management** | Drafts accumulate in `Inbox/Agent Drafts/` without cleanup. Add `draft-review` command to list, approve, reject, or archive drafts. `check_in` already counts them. | Open |
| 15 | `improvement` | **Configurable sentinel headings** | Ritual detection uses hardcoded sentinels (`## Morning Briefing`, `## Day Close`). Make configurable via `config.json`. | Open |

---

## v0.3.0 -- Intelligence & Integrations

### P1

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 9 | `feature` | **Semantic search** | Full-text search is keyword-based. Add optional embedding-based semantic search using local models (e.g., sentence-transformers). No cloud dependency. | Open |
| 10 | `feature` | **Template system** | `create-research-note` uses a single hardcoded template. Support user-defined templates in a `templates/` vault folder with variable substitution. | Open |
| 11 | `improvement` | **Newline encoding fix** | Obsidian CLI does not distinguish literal `\n` from actual newlines in output. Investigate binary-safe IPC or direct file read as workaround. | Open |
| 12 | `feature` | **Obsidian URI protocol** | Use `obsidian://` URI scheme as alternative to CLI for read operations. Would eliminate the CLI plugin requirement for basic operations. | Open |

### P2

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 14 | `feature` | **Export and reporting** | Generate weekly/monthly reports as standalone Markdown or PDF. Combine drift analysis, graduation history, and vault health into a single artifact. | Open |

---

## Backlog (P3 -- Future)

| # | Type | Title | Description | Status |
|---|------|-------|-------------|--------|
| 16 | `feature` | **Plugin marketplace** | Package individual tool groups (graph, thinking, workflows) as separate optional installs. | Open |
| 17 | `feature` | **Collaborative vaults** | Support for shared vaults with per-user delegation tracking and conflict resolution. | Open |
| 18 | `infra` | **PyPI publication** | Publish to PyPI so users can `pip install obsidian-connector` instead of cloning. | Open |
| 19 | `infra` | **pytest migration** | Move test suites from custom `scripts/` runners to pytest for standard tooling, fixtures, and coverage reporting. | Open |
| 20 | `docs` | **Video walkthrough** | Screen recording of the morning-to-evening workflow showing all four rituals in action. | Open |
| 21 | `improvement` | **Graceful pyyaml fallback** | Scheduling config currently logs a warning and uses defaults when pyyaml is missing. Surface a one-time install hint to the user instead of silently degrading. | Open |
| 22 | `improvement` | **Index staleness indicator** | Show age of last index scan in graph tool output. Warn if index is older than a configurable threshold. Current mitigation: `rebuild-index` forces full rescan. | Open |
| 23 | `risk` | **Scheduled jobs without user presence** | launchd jobs fire regardless of whether the user is at their machine, appending to the daily note silently. Add an optional "active hours" window or skip if no recent user activity. | Open |
| 24 | `infra` | **Linux/Windows native installers** | AppImage/deb for Linux, MSI/exe for Windows -- equivalent to the macOS .dmg. Currently Linux and Windows use script-based installation. | Open |

---

## Completed

| # | Type | Title | Shipped In |
|---|------|-------|------------|
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
