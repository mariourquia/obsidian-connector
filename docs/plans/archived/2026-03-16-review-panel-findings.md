---
title: "v0.2.0 Review Panel Findings & Remediation Plan"
status: draft
owner: mariourquia
last_reviewed: "2026-03-16"
---

# v0.2.0 Review Panel Findings & Remediation Plan

14-member expert review panel findings, compiled by severity. Each finding
includes the file, line(s), issue, and remediation.

## Severity: CRITICAL (must fix before release)

### C1. PowerShell injection in `send_notification()` [SECURITY]
- **File**: `obsidian_connector/platform.py:385-394`
- **Issue**: `title` and `message` are interpolated directly into a PowerShell
  f-string. An attacker-controlled vault name or note title could execute
  arbitrary PowerShell commands.
- **Fix**: Use `-EncodedCommand` with base64-encoded script, or pass values via
  environment variables / `-ArgumentList` instead of string interpolation.

### C2. osascript incomplete escaping [SECURITY]
- **File**: `obsidian_connector/platform.py:369-371`
- **Issue**: Only backslash and double-quote are escaped. Single quotes,
  newlines, and other AppleScript special characters bypass the escaping.
- **Fix**: Use `subprocess.run(["osascript", "-e", ...])` with proper
  parameterized input, or escape all AppleScript metacharacters.

### C3. `doctor.py` returns false negatives for systemd/schtasks
- **File**: `obsidian_connector/doctor.py:262-272`
- **Issue**: `_check_scheduler_available()` returns hardcoded `False` for
  `systemd` and `task_scheduler` despite working implementations in
  `platform.py`. Users on Linux/Windows will see "not implemented" when
  scheduling actually works.
- **Fix**: Return `True` for all three backends since `platform.py` has
  complete implementations.

## Severity: HIGH (should fix before release)

### H1. `file_backend.py` is dead code
- **File**: `obsidian_connector/file_backend.py` (entire module)
- **Issue**: No module imports `file_backend`. Not wired into any MCP tool or
  CLI command. 68 tests exist but the code is unreachable in production.
- **Fix**: Wire into MCP server and CLI as fallback when Obsidian CLI is
  unavailable (the original design intent). OR defer to v0.2.1 and remove
  from this release to reduce surface area.
- **Decision**: Defer. Remove from this release. Ship as v0.2.1 feature.

### H2. Bare `except Exception: pass` patterns (7 instances)
- **Files**: `workflows.py:461-462`, `workflows.py:929-930`,
  `workflows.py:1560-1561`, `thinking.py:489-490`, `doctor.py:147`,
  `doctor.py:178`, `doctor.py:240`
- **Issue**: Silent exception swallowing masks bugs and hides failures from
  users. The `doctor.py` instances do log the exception, but the
  `workflows.py` and `thinking.py` instances silently discard errors.
- **Fix**: Replace with specific exception types (OSError, ValueError,
  subprocess.CalledProcessError). Where pass is used, at minimum log to
  stderr or audit log.

### H3. `uninstall` MCP tool breaks naming convention
- **File**: `obsidian_connector/mcp_server.py:1111`
- **Issue**: All other MCP tools use `obsidian_` prefix (e.g.,
  `obsidian_search`, `obsidian_read`). The `uninstall` tool breaks this
  convention, which causes inconsistency in tool discovery.
- **Fix**: Rename to `obsidian_uninstall`.

### H4. Inverted uninstall interactive prompt defaults
- **File**: `obsidian_connector/uninstall.py` (interactive prompts)
- **Issue**: Interactive prompts default to "yes" (destructive), meaning a
  user pressing Enter without reading will remove artifacts. Safe defaults
  should be "no" (non-destructive).
- **Fix**: Change all interactive prompt defaults to "n" (keep).

### H5. Non-atomic config write in `uninstall.py`
- **File**: `obsidian_connector/uninstall.py` (Claude Desktop config update)
- **Issue**: Config is written directly without atomic write pattern. A crash
  during write could corrupt the Claude Desktop config file.
- **Fix**: Use `tempfile.mkstemp()` + `os.replace()` (same pattern as
  `file_backend.py:_atomic_write()`).

### H6. Double-execution bug in `install-linux.sh`
- **File**: `scripts/install-linux.sh:314-342`
- **Issue**: `install_schedule()` is called twice with the same arguments,
  installing duplicate systemd timers.
- **Fix**: Remove the duplicate call block (lines 331-342).

### H7. CWD `config.json` hijack vector
- **File**: `obsidian_connector/config.py:26-34`
- **Issue**: `_find_config_file()` checks CWD before package directory. An
  attacker placing a `config.json` in the working directory could redirect
  vault resolution to a malicious path.
- **Fix**: Check package directory first, CWD second. Or remove CWD lookup
  entirely since the package config is the canonical source.

### H8. Legacy `typing` imports in `uninstall.py`
- **File**: `obsidian_connector/uninstall.py:7`
- **Issue**: Uses `from typing import Dict, List, Any` instead of built-in
  `dict`, `list` generics (Python 3.9+). Project targets 3.11+.
- **Fix**: Replace with built-in types. Remove unused `subprocess` import
  on line 3.

### H9. Stale documentation
- **Files**: `docs/generated/SECURITY_REVIEW.md` (references v0.1.1),
  `ARCHITECTURE.md` (missing `platform.py`, `file_backend.py`, `uninstall.py`)
- **Issue**: Docs reference outdated versions and miss 3 new modules.
- **Fix**: Update ARCHITECTURE.md to include new modules. Update version
  references.

### H10. MCP tools use private `_error_envelope()` instead of canonical `envelope.py`
- **File**: `obsidian_connector/mcp_server.py`
- **Issue**: A private `_error_envelope()` duplicates logic from `envelope.py`.
  MCP tools don't use the canonical envelope module.
- **Fix**: Defer to post-release. This is a refactoring task, not a
  correctness issue. The private function produces identical output.

## Severity: MEDIUM (nice to fix, can defer)

### M1. CLI is 1,599-line monolith (`cli.py`)
- **Fix**: Defer. Refactor to subcommand modules in v0.3.0.

### M2. Workflows is 1,594-line monolith (`workflows.py`)
- **Fix**: Defer. Split by domain (daily, search, graph) in v0.3.0.

### M3. CLI flag naming inconsistency
- `--lookback-days` vs `--days` vs `--lookback` across commands.
- **Fix**: Defer. Breaking change requires deprecation period.

### M4. Daily-note discovery O(n) subprocess pattern (5 duplications)
- **Fix**: Defer. Performance optimization for v0.3.0.

### M5. Module-level side effects in `config.py`
- `_OBSIDIAN_APP_JSON` and `_DEFAULT_INDEX_DB` evaluated at import time.
- **Fix**: Defer. Convert to lazy properties in v0.3.0.

---

## Remediation Execution Plan

### Wave 1: Security fixes (parallel, independent)

| Task | File(s) | Agent | Est. |
|------|---------|-------|------|
| Fix PowerShell injection (C1) | platform.py | Agent A | 10m |
| Fix osascript escaping (C2) | platform.py | Agent A | 10m |
| Fix CWD config hijack (H7) | config.py | Agent B | 5m |

### Wave 2: Correctness fixes (parallel, independent)

| Task | File(s) | Agent | Est. |
|------|---------|-------|------|
| Fix doctor.py false negatives (C3) | doctor.py | Agent C | 5m |
| Fix double-execution in install-linux.sh (H6) | install-linux.sh | Agent D | 5m |
| Fix non-atomic config write (H5) | uninstall.py | Agent E | 10m |
| Fix inverted prompt defaults (H4) | uninstall.py | Agent E | 5m |

### Wave 3: Convention fixes (parallel, independent)

| Task | File(s) | Agent | Est. |
|------|---------|-------|------|
| Rename uninstall MCP tool (H3) | mcp_server.py, TOOLS_CONTRACT.md | Agent F | 10m |
| Narrow bare exceptions (H2) | workflows.py, thinking.py | Agent G | 15m |
| Clean up legacy typing (H8) | uninstall.py | Agent E | 5m |
| Update ARCHITECTURE.md (H9) | ARCHITECTURE.md | Agent H | 10m |

### Wave 4: Cleanup

| Task | File(s) | Agent | Est. |
|------|---------|-------|------|
| Remove file_backend.py from release (H1) | file_backend.py, tests | Agent I | 5m |
| Run full test suite | all | Main | 5m |

### Deferred to v0.3.0

- M1: CLI monolith split
- M2: Workflows monolith split
- M3: CLI flag naming standardization
- M4: Daily-note O(n) dedup
- M5: config.py lazy evaluation
- H10: Canonical envelope migration
- H1: file_backend.py integration (v0.2.1)

---

## Expert Panel Additional Findings (v0.3.0+ Roadmap)

The following findings from the Obsidian CLI, Markdown, Second Brain, Systems
Thinking, and Claude Code Agent Planner experts are design-level or
feature-level issues. They do not block the v0.2.0 release but should inform
the roadmap.

### Obsidian CLI Expert

- **Error classification ordering bug**: `ObsidianNotRunning` missed when
  error message lacks "not found" (client.py:73-86). Fix: reorder checks.
- **TOOLS_CONTRACT.md incorrectly classifies CLI-dependent tools as offline**.
  Workflow tools (`today`, `my_world`, `close_day`, `open_loops`) require
  Obsidian running but docs say "works offline."
- **Case-sensitive vault name matching on macOS** (config.py:146). macOS HFS+
  is case-insensitive.
- **`obsidian version` may need `--version` flag** (doctor.py:104).
- **Embed links (`![[...]]`) not extracted by graph** (graph.py).
- **Binary path check missing newline/null** in rejected chars (config.py:74).

### Markdown Expert

- **Frontmatter parser rejects hyphenated keys** like `last-reviewed`
  (graph.py `_YAML_KV` regex).
- **Inline YAML lists `tags: [a, b]` parsed as string**, not list (graph.py).
- **`%%comment%%` content not masked** -- tags/links inside comments extracted.
- **Heading anchors `[[note#heading]]` break link resolution** (graph.py).
- **Tasks inside code blocks are matched** by file_backend.py (no code-block
  masking).
- **Code fence closing logic rejects valid 4+ tick closings** (graph.py).

### Second Brain Expert

- **Skills (`/morning`, `/evening`, `/idea`, `/weekly`) do not exist yet** --
  the orchestration layer is entirely aspirational.
- **Open loop `OL:` prefix is non-standard** -- no Obsidian plugin recognizes
  it. Suggests switching to task-style `- [ ] OL:`.
- **Drift analysis needs LLM-assisted semantic matching** -- current
  regex + word-overlap produces unreliable results.
- **No weekly review composite function** exists.
- **Missing PKM workflows**: spaced repetition, progressive summarization,
  MOC generation, inbox triage, PARA awareness.
- **Vault structure assumptions**: hardcoded daily note format, ritual
  sentinels, delegation markers.

### Systems Thinking Expert

- **No feedback loop on suggestions** -- system does not learn from user
  response to recommendations.
- **29 tools at cognitive tipping point** -- overlapping session-start tools
  (`today`, `check_in`, `context_load`, `my_world`) should be consolidated.
- **Decision-outcome loop is open** -- `log_decision` has no review date,
  no alternatives field, no outcome tracking.
- **`close_day` generates generic prompts** -- does not compute plan-vs-actual
  delta or reference morning briefing.
- **Over-automation risk**: daily notes can become machine-to-machine channel
  if human stops reading. Add `human_engagement` detection.

### Claude Code Agent Planner

- **5-agent team model** (Surgeon, Surface, Logic, Shield, Scribe) with
  non-overlapping file ownership for future large-scale remediation.
- **4-phase execution**: Foundation -> Surface+Logic+Tests (parallel) ->
  Docs -> Integration.
- **Module splits should use re-export facades** (keep `cli.py` and
  `workflows.py` as import facades after splitting).
- **Parameter renames need deprecation aliases**, not breaking changes.
