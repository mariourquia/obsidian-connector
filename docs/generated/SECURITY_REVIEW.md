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
- **Transitive dependency code review**: The `mcp` package and its 21 transitive dependencies were audited for known CVEs via pip-audit but their source code was not reviewed line-by-line.
- **Obsidian desktop app security**: The Obsidian CLI binary is invoked as a subprocess. Security of the Obsidian app itself is out of scope.
- **Vault content as attack vector**: Malicious markdown content designed to exploit the frontmatter parser or regex-based extraction was not systematically tested.

## Findings

### Critical (Fixed in v0.2.0)

| ID  | Finding                                   | File          | Fix                                          |
|-----|-------------------------------------------|---------------|----------------------------------------------|
| C1  | PowerShell injection in notifications     | platform.py   | Values passed via env vars, no interpolation  |
| C2  | Incomplete osascript escaping             | platform.py   | Full metacharacter escape chain (\\, ", ', \n, \r, \t) |

### High (Fixed in v0.2.0)

4 HIGH security findings fixed. 17 total blockers resolved across all severity levels.

| ID  | Finding                                   | File            | Fix                                        |
|-----|-------------------------------------------|-----------------|--------------------------------------------|
| H1  | CWD config.json hijack                   | config.py       | Package dir checked before CWD             |
| H2  | Silent exception swallowing (7x)          | workflows.py, thinking.py | Narrowed to specific types (OSError, ValueError, KeyError) |
| H3  | Installer script injection vectors        | install*.sh, Install.ps1 | Input sanitization, quoted variables, no eval |
| H4  | HTML injection in notification strings    | platform.py     | Escaped before passing to osascript/PowerShell |
| H5  | Doctor false negatives for schedulers     | doctor.py       | Returns True for all 3 backends            |
| H6  | Inverted destructive defaults             | cli.py          | All prompts default to non-destructive     |
| H7  | Non-atomic config write in uninstaller    | uninstall.py    | tempfile.mkstemp + os.replace              |
| H8  | Lockfile not enforced in CI               | ci.yml          | `pip-compile --generate-hashes` lockfile with CI check job |

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
- Total transitive dependencies: 21 (via `mcp`, pinned with hashes in `requirements-lock.txt`)
- Known vulnerabilities at time of review: 0 (pip-audit)
- Outdated dependencies: 0
- Dependencies with no maintenance (>1yr no commits): 0
- All licenses permissive: MIT, BSD, Apache-2.0, PSF-2.0

## Secrets Handling

- Secrets management approach: none needed (no secrets stored or transmitted)
- Unsafe defaults: none. MCP uninstall defaults to dry-run. CLI uninstall defaults to non-destructive.
- No API keys, tokens, passwords, or credentials in the codebase.

## Supply Chain

- Lock file present: yes (`requirements-lock.txt`, generated via `pip-compile --generate-hashes`)
- Lockfile CI check: `lockfile-check` job verifies lockfile is in sync with `pyproject.toml`
- Dependency pinning strategy: range in `pyproject.toml` (`mcp>=1.0.0,<2.0.0`), exact versions + SHA256 hashes in lockfile
- Total pinned packages: 1 direct + 21 transitive (mcp 1.26.0 locked)
- SBOM available: yes (`SBOM.md` at repo root, manually maintained)
- Release signing: Sigstore cosign keyless (OIDC via GitHub Actions). Each of 4 artifacts gets `.sig` + `.cert`.
- Build reproducibility: source archives from `git archive` should be reproducible from the same commit. Not independently verified.
- Release artifacts built in GitHub Actions (CI) not on maintainer's local machine.

## Remaining Known Gaps

- **Dependabot not configured**: No automated dependency update PRs. Manual `pip-audit` runs are the current process.
- **Audit log not tamper-resistant**: JSONL audit files have same-user ownership. A local attacker with the user's privileges can modify or delete entries. Append-only or signed logging not implemented.
- **GitHub Actions not pinned to SHA**: Uses tag-based references (`actions/checkout@v4`) rather than commit SHAs.
- **No CodeQL or SAST scanning**: Static analysis is manual. CodeQL planned for v0.3.0.
