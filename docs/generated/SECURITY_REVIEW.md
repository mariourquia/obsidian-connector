---
title: "Security Review: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Security Review: obsidian-connector v0.2.0

> Review date: 2026-03-16
> Reviewer: 14-expert panel review + 4-agent verification team
> Scope: Full repository -- all modules, scripts, CI, and dependencies

## Review Status

| Area                       | Reviewed | Tool / Method             | Findings |
|----------------------------|----------|---------------------------|----------|
| Hardcoded secrets          | Y        | Manual search + grep      | 0        |
| Dependency vulnerabilities | Y        | pip-audit (manual run)    | 0        |
| Auth/authz flows           | N/A      | --                        | Local-only tool, no auth |
| Input validation           | Y        | Manual review             | 0 (after fixes) |
| SQL injection              | Y        | Manual review             | 0 (parameterized queries) |
| XSS / output encoding      | N/A      | --                        | No web UI |
| File system access         | Y        | Manual review             | 0 (after path traversal fix) |
| Network/API calls          | Y        | Manual review             | 0 (no network calls) |
| Shell command execution    | Y        | Manual review             | 0 (after PowerShell/osascript fixes) |
| Cryptographic usage        | N/A      | --                        | No crypto operations |
| Error handling / info leak | Y        | Manual review             | 0 (after exception narrowing) |
| CORS / CSP / headers       | N/A      | --                        | No web server |

## Not Assessed

- **CI supply chain**: GitHub Actions workflows use `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`. These are GitHub-maintained actions but are not pinned to SHA.
- **Transitive dependency code review**: The `mcp` package and its 13 transitive dependencies were audited for known CVEs via pip-audit but their source code was not reviewed line-by-line.
- **Obsidian desktop app security**: The Obsidian CLI binary is invoked as a subprocess. Security of the Obsidian app itself is out of scope.
- **Vault content as attack vector**: Malicious markdown content designed to exploit the frontmatter parser or regex-based extraction was not systematically tested.

## Findings

### Critical (Fixed in v0.2.0)

| ID  | Finding                                   | File          | Fix                                          |
|-----|-------------------------------------------|---------------|----------------------------------------------|
| C1  | PowerShell injection in notifications     | platform.py   | Values passed via env vars, no interpolation  |
| C2  | Incomplete osascript escaping             | platform.py   | Full metacharacter escape chain (\\, ", ', \n, \r, \t) |

### High (Fixed in v0.2.0)

| ID  | Finding                                   | File            | Fix                                        |
|-----|-------------------------------------------|-----------------|--------------------------------------------|
| H1  | CWD config.json hijack                   | config.py       | Package dir checked before CWD             |
| H2  | Silent exception swallowing (7x)          | workflows.py, thinking.py | Narrowed to specific types (OSError, ValueError, KeyError) |
| H3  | Doctor false negatives for schedulers     | doctor.py       | Returns True for all 3 backends            |
| H4  | Inverted destructive defaults             | cli.py          | All prompts default to non-destructive     |
| H5  | Non-atomic config write in uninstaller    | uninstall.py    | tempfile.mkstemp + os.replace              |

### Medium

| ID  | Finding                                   | Status   | Notes                                      |
|-----|-------------------------------------------|----------|--------------------------------------------|
| M1  | MCP uninstall lacks audit logging         | Open     | MCP tool does not call log_action(). CLI path does. Logging gap, not data safety issue. |
| M2  | install-linux.sh double schedule call     | Fixed    | Removed duplicate install_schedule invocation |
| M3  | Null bytes in osascript strings           | Accepted | Unlikely in practice. Would cause osascript to fail (not inject). |

### Low / Informational

- Config file read-modify-write has a theoretical TOCTOU gap. Mitigated by re-reading fresh and creating timestamped backup. Negligible real-world risk.
- CWD config.json still checked as fallback after package dir. An attacker with write access to CWD could inject config, but this requires local access (same threat as modifying the code directly).
- No `null` byte filtering on osascript input. Would cause the command to fail, not inject.

## Dependency Summary

- Total direct dependencies: 1 (`mcp`)
- Total transitive dependencies: 13 (via `mcp`)
- Known vulnerabilities at time of review: 0 (pip-audit)
- Outdated dependencies: 0
- Dependencies with no maintenance (>1yr no commits): 0
- All licenses permissive: MIT, BSD, Apache-2.0, PSF-2.0

## Secrets Handling

- Secrets management approach: none needed (no secrets stored or transmitted)
- Unsafe defaults: none. MCP uninstall defaults to dry-run. CLI uninstall defaults to non-destructive.
- No API keys, tokens, passwords, or credentials in the codebase.

## Supply Chain

- Lock file present: no
- Dependency pinning strategy: range (`mcp>=1.0.0,<2.0.0`)
- SBOM available: yes (`SBOM.md` at repo root, manually maintained)
- Build reproducibility: source archives from `git archive` should be reproducible from the same commit. Not independently verified.
- Release artifacts built in GitHub Actions (CI) not on maintainer's local machine.
