---
title: "User Verification Checklist: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# User Verification Checklist: obsidian-connector v0.2.0

Use this checklist to verify the release before depending on it.

## Source Verification

- [ ] Confirm the release tag matches the commit you expect:
  ```bash
  git clone https://github.com/mariourquia/obsidian-connector.git
  cd obsidian-connector
  git log --oneline v0.2.0 -1
  ```
- [ ] Review the CHANGELOG entry for v0.2.0:
  ```bash
  head -35 CHANGELOG.md
  ```
- [ ] Check the LICENSE file exists and is MIT:
  ```bash
  head -3 LICENSE
  ```

## Artifact Verification

- [ ] Download the checksums file:
  ```bash
  curl -LO https://github.com/mariourquia/obsidian-connector/releases/download/v0.2.0/obsidian-connector-v0.2.0.sha256
  ```
- [ ] Verify artifact checksums:
  ```bash
  sha256sum -c obsidian-connector-v0.2.0.sha256
  ```

## Dependency Review

- [ ] Review direct dependencies (only 1: `mcp`):
  ```bash
  cat pyproject.toml | grep -A2 "dependencies"
  ```
- [ ] Audit for known vulnerabilities:
  ```bash
  pip install pip-audit
  pip-audit
  ```
- [ ] Review the SBOM:
  ```bash
  cat SBOM.md
  ```

## Functional Verification

- [ ] Install in a virtual environment:
  ```bash
  python3 -m venv /tmp/test-obsx
  source /tmp/test-obsx/bin/activate
  pip install -e .
  ```
- [ ] Run the test suite:
  ```bash
  python3 scripts/audit_test.py
  python3 scripts/graph_test.py
  python3 scripts/index_test.py
  python3 scripts/platform_test.py
  python3 scripts/uninstall_test.py
  python3 scripts/import_cycle_test.py
  python3 scripts/mcp_tool_contract_test.py
  python3 scripts/cli_parse_test.py
  ```
- [ ] Run the health check (requires Obsidian running):
  ```bash
  ./bin/obsx doctor
  ```
- [ ] Test the primary use case:
  ```bash
  ./bin/obsx search "test query"
  ```
- [ ] Test an error case (invalid vault):
  ```bash
  ./bin/obsx --vault "nonexistent" search "test"
  ```

## Security Spot-Check

- [ ] Search for hardcoded secrets:
  ```bash
  grep -rn "password\|secret\|api.key\|token" --include="*.py" obsidian_connector/
  ```
- [ ] Verify no shell=True in subprocess calls:
  ```bash
  grep -rn "shell=True" --include="*.py" obsidian_connector/
  ```
- [ ] Verify no network calls:
  ```bash
  grep -rn "requests\.\|urllib\.\|http\.\|socket\." --include="*.py" obsidian_connector/
  ```
- [ ] Review the security documentation:
  ```bash
  cat SECURITY.md
  cat docs/generated/SECURITY_REVIEW.md
  ```

## Uninstall Verification

- [ ] Confirm uninstall dry-run works:
  ```bash
  ./bin/obsx uninstall --dry-run
  ```
- [ ] Clean up test environment:
  ```bash
  deactivate
  rm -rf /tmp/test-obsx
  ```

## Decision

After completing this checklist:
- [ ] **ACCEPT**: All checks pass. Safe to use.
- [ ] **ACCEPT WITH RESERVATIONS**: Minor gaps noted: ________________
- [ ] **REJECT**: Unacceptable findings: ________________
