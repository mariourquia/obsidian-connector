# User Verification Checklist: obsidian-connector 0.9.0

Use this checklist to verify the release before deploying to production or
depending on it from another project.

## Source Verification

- [ ] Confirm the release tag points to the commit you expect:
  ```bash
  git verify-tag v0.9.0
  git log --oneline v0.9.0 -1
  # Expected commit: 099af67101645faea8ad8b48a00f8c39e387ba1c
  # Expected signing key fingerprint: SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4
  ```
- [ ] Compare the release source tarball to the repository:
  ```bash
  gh release download v0.9.0 --archive tar.gz
  tar tzf obsidian-connector-0.9.0.tar.gz | head
  ```
- [ ] Review the CHANGELOG entry for 0.9.0 in `CHANGELOG.md`.
- [ ] Check the release date against the commit date (release: 2026-04-13;
  tagged commit: 2026-04-13; gap: 0 days).

## Artifact Verification

- [ ] Download the checksums file:
  ```bash
  gh release download v0.9.0 -p SHA256SUMS.txt
  ```
- [ ] Verify artifact checksums:
  ```bash
  sha256sum -c SHA256SUMS.txt
  ```
- [ ] Verify the GPG signature on the checksum file (if attached):
  ```bash
  gpg --verify SHA256SUMS.txt.asc SHA256SUMS.txt
  ```
- [ ] If installing from PyPI when published, verify provenance metadata via
  `pip show obsidian-connector` and `pip-audit`.

## Dependency Review

- [ ] Review direct dependencies for known vulnerabilities:
  ```bash
  pip-audit
  ```
- [ ] Check that dependency versions in `requirements-lock.txt` match your
  installed environment:
  ```bash
  pip freeze | diff - requirements-lock.txt
  ```
- [ ] Spot-check 2-3 transitive dependencies (e.g. `pydantic`, `httpx`,
  `anyio`) for maintenance status.

## Functional Verification

- [ ] Install in an isolated environment:
  ```bash
  python3.11 -m venv /tmp/obs-verify
  source /tmp/obs-verify/bin/activate
  pip install obsidian-connector==0.9.0
  ```
- [ ] Run the project's test suite at the tag:
  ```bash
  git clone https://github.com/mariourquia/obsidian-connector
  cd obsidian-connector
  git checkout v0.9.0
  python3.11 -m venv .venv && source .venv/bin/activate
  pip install -e '.[dev]'
  .venv/bin/python -m pytest -q
  # Expected: 137 passed
  ```
- [ ] Verify the `smart_triage` contract:
  ```bash
  .venv/bin/python -c "from obsidian_connector.smart_triage import smart_triage, ClassificationResult, LLMClient, Kind, Source; from obsidian_connector.classifiers.rule_based import RuleBasedClassifier; print('ok')"
  # Expected output: ok

  .venv/bin/python -c "
  import dataclasses
  from obsidian_connector.smart_triage import ClassificationResult
  names = {f.name for f in dataclasses.fields(ClassificationResult)}
  assert names == {'kind', 'confidence', 'reason', 'source', 'slug'}, names
  print('ok')
  "
  # Expected output: ok
  ```
- [ ] Exercise the primary MCP / CLI use case:
  ```bash
  obsx --version
  # Expected: 0.9.0
  ```
- [ ] Test at least one error case (e.g. invalid `obsidian_bin` with a shell
  metacharacter) and confirm the config parser rejects it.

## Security Spot-Check

- [ ] Search for hardcoded secrets in the installed source:
  ```bash
  grep -rn "password\|secret\|api.key\|token\|bearer" \
    --include="*.py" \
    $(python -c "import obsidian_connector, os; print(os.path.dirname(obsidian_connector.__file__))")
  ```
  Expected: only parameter names, docstrings, and config-variable references.
  No literal credentials.
- [ ] Confirm no outbound network calls on CLI or MCP startup (the project is
  local-only):
  ```bash
  # macOS
  sudo tcpdump -i any -n "host not 127.0.0.1" &
  obsx --version
  # kill tcpdump
  ```
- [ ] Review the `SECURITY.md` supported-versions table. Note that the 0.9.0
  release ships with a stale table (still listing 0.7.x); a doc follow-up is
  planned.

## Optional Extras

- [ ] If using the Textual TUI:
  ```bash
  pip install 'obsidian-connector[tui]==0.9.0'
  obsx menu
  ```
- [ ] If using graphify:
  ```bash
  pip install 'obsidian-connector[graphify]==0.9.0'
  python -m obsidian_connector.graphify --help
  ```

## Decision

After completing this checklist, choose one:

- [ ] **ACCEPT**: All checks pass. Safe to use in production and to depend on
  from downstream projects.
- [ ] **ACCEPT WITH RESERVATIONS**: Minor gaps noted. Examples:
  - `SECURITY.md` support matrix is stale.
  - `SBOM.md` header metadata is stale.
  - `[graphify]` transitive deps not audited end-to-end.
- [ ] **REJECT**: Unacceptable findings. Open an issue at
  `https://github.com/mariourquia/obsidian-connector/issues` with details.
