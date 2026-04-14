# Risk Disclosure: obsidian-connector 0.9.0

> Date: 2026-04-13

## Security Risks

| Risk                                              | Severity | Status     | Mitigation                                                                 |
|---------------------------------------------------|----------|------------|----------------------------------------------------------------------------|
| Stale `SECURITY.md` supported-versions table      | L        | open       | Post-release doc PR within 7 days; W1 in RELEASE_READINESS_REVIEW.md       |
| Vault path containment                            | M        | mitigated  | Path containment tests in `test_config_validation.py`; shell-metachar rejection on `obsidian_bin` |
| MCP surface exposes vault read/write              | M        | mitigated  | Local-only tool; no outbound network; user controls vault root via config  |
| Secrets in diff (grep sweep)                      | L        | mitigated  | 20 matches reviewed, all benign (docs placeholders, param names, typedefs) |
| Optional `[graphify]` extra audit coverage        | L        | open       | `pip-audit` not run against fully-installed extras; follow-up in SECURITY_REVIEW addendum |

## Operational Risks

| Risk                                               | Likelihood | Impact | Mitigation                                                            |
|----------------------------------------------------|------------|--------|------------------------------------------------------------------------|
| `textual` move to `[tui]` extra breaks downstream  | M          | L      | Covered by `test_cli_tui_optional.py`; documented in RELEASE_NOTES.md and COMPATIBILITY_MATRIX.md |
| Untracked `builds/` subtrees bloat future diffs    | M          | L      | Post-release hygiene: `.gitignore` or relocate                        |
| `pyyaml` install edge case in dev venvs            | L          | L      | Rerun `pip install -r requirements-lock.txt`; documented in KNOWN_LIMITATIONS.md |
| DMG / MSI post-install click-through untested      | M          | M      | Manual dry-run only; `installer-smoke.yml` covers PowerShell subset   |
| `SBOM.md` header metadata stale                    | L          | L      | Refresh in next docs sweep                                            |
| No automated UI tests for Textual TUI dashboard    | M          | L      | Manual smoke check; flagged in TESTING_SUMMARY.md                     |

## Compatibility Risks

| Risk                                                       | Affected Users                                        | Mitigation                                   |
|------------------------------------------------------------|-------------------------------------------------------|----------------------------------------------|
| `textual` no longer installed by a base install            | Users who imported Textual dashboard from their code  | `pip install 'obsidian-connector[tui]'`      |
| obsidian-capture-service Task 20 consumer pin              | capture-service running < v0.9.0 compatible release   | capture-service repo tracks pin in its own CLAUDE.md / requirements |
| Python 3.14 not tested                                     | Users on Python 3.14                                  | Stick with 3.11 / 3.12 / 3.13 until 3.14 is covered in CI |

## Maintenance Risks

- Maintainer count: 1
- Bus factor: 1
- Last commit on `main`: 2026-04-13 (099af67)
- Open issues: not surveyed for this release
- Open security issues: none known
- Dependency freshness: current (latest `security.yml` run green)

## Tradeoffs Accepted

- **Textual is now an optional extra.** This adds one install step for users
  who want the TUI dashboard, in exchange for keeping the base install small
  and unblocking non-TUI CLI usage in environments where `textual` misbehaves.
- **Graphify ships as an extra.** `networkx` is not a small dependency; paying
  for it in the base install would affect every user, even those who never
  touch the graph features.
- **No SLSA attestation or reproducible-build verification for 0.9.0.** Builds
  run on GitHub Actions hosted runners; tag signatures (GPG ED25519) provide
  source integrity, and `SHA256SUMS` provides artifact integrity, but the
  release does not ship a SLSA provenance statement.
- **No end-to-end MCP integration tests.** Decision made to keep the test
  suite fast (5.09s for 137 tests) and leave MCP-level integration to the
  consumer (Claude Desktop, Claude Code, or the capture-service) to validate.
- **SECURITY.md support matrix deferred.** Rather than auto-editing docs
  during the release, the stale matrix is flagged and a post-release PR is
  planned. This preserves the release-branch diff as purely the source code
  under review.

## Blast Radius

If 0.9.0 fails in production, the expected impact is:

- **Data**: No risk of vault data loss from this release's new surfaces. All
  writes remain atomic (write-then-rename via `write_manager.py` carried
  forward from 0.6.0). The related-fence and wiki-fence regeneration on
  commitment and entity notes is idempotent by test; user-authored content
  outside the fences is preserved.
- **Availability**: A broken import (e.g. a missing runtime dependency) would
  prevent the MCP server and CLI from starting on affected environments.
  `test_cli_tui_optional.py` and `test_graphify_smoke.py` specifically guard
  against the most likely class of such failures (optional-extra imports
  leaking into runtime paths).
- **Security**: No new inbound attack surface. The tool remains local-only
  with no outbound network. A misconfigured `obsidian_bin` with shell
  metacharacters is rejected at config parse time rather than executed.
- **Downstream**: obsidian-capture-service Task 20 depends on the
  `smart_triage` surface. A regression in `ClassificationResult` field shape
  would break that consumer. The shape is locked by the preflight assertion
  in RELEASE_READINESS_REVIEW.md and by the 10 tests in
  `test_smart_triage.py`.
