# obsidian-connector 0.9.0 Package Notes

> Published: 2026-04-13
> Registry surfaces: GitHub Release assets; PyPI (optional); MCPB; Claude Code plugin marketplace; macOS DMG; Windows MSI
> Classification: stable

## Summary

`obsidian-connector` is an MCP server and CLI that gives Claude read/write
access to an Obsidian vault. v0.9.0 adds the `smart_triage` surface consumed by
obsidian-capture-service Task 20, extends semantic memory with related-edges
and entity-wiki fences on commitment and entity notes, ships the optional
`graphify` knowledge-graph module, and decouples the CLI from the optional
Textual TUI.

## Install

```bash
# pip base install
pip install obsidian-connector==0.9.0

# pip with optional extras
pip install 'obsidian-connector[tui]==0.9.0'
pip install 'obsidian-connector[graphify]==0.9.0'
pip install 'obsidian-connector[scheduling,live,semantic]==0.9.0'
```

MCPB archive, Claude Code plugin, macOS DMG, and Windows installer are
attached to the GitHub Release for `v0.9.0`.

## Quick Start

```python
from obsidian_connector.smart_triage import smart_triage, ClassificationResult

result: ClassificationResult = smart_triage("draft the Q2 board deck")
# ClassificationResult(kind=..., confidence=..., reason=..., source=..., slug=...)

print(result.kind, result.confidence, result.source)
```

## What's New in 0.9.0

- `smart_triage` module + `RuleBasedClassifier` (Task 20 surface).
- Semantic memory 15.A.2 / 15.C: related-edges fence on commitment notes,
  entity-wiki fence on entity notes.
- `graphify` optional extra (networkx-backed).
- CLI decoupled from optional TUI (textual moved to `[tui]` extra).
- Commitment dashboards (4 views), inspection/update CLI, commitment notes
  renderer, entity notes writer, first-run wizard, UX orchestrator.

See `CHANGELOG.md` for the full history.

## Requirements

- Runtime: Python `>=3.11` (3.11, 3.12, 3.13 covered in CI; 3.14 not tested).
- OS: macOS, Linux, Windows.
- Dependencies:
  - Runtime: 2 direct (`mcp>=1.0.0,<2.0.0`, `pyyaml>=6.0.0`).
  - Optional extras: `scheduling`, `tui`, `live`, `semantic`, `graphify`, `dev`.
  - Transitive runtime tree captured in `requirements-lock.txt`
    (root-level, 37275 bytes).

## Breaking Changes from 0.8.3

None. One dependency layout change callers should be aware of:

- `textual` is no longer installed by a base install. Previously-working CLI
  invocations that imported the Textual dashboard from user code will now
  raise `ModuleNotFoundError` unless the user installs the new `[tui]` extra.
  The test `tests/test_cli_tui_optional.py` guarantees that basic CLI import
  paths no longer pull textual.

## Security

- Dependencies scanned via `pip-audit` in `.github/workflows/security.yml`.
- No known vulnerabilities at time of publication.
- Security policy: `SECURITY.md` (support-matrix refresh pending, flagged in
  `KNOWN_LIMITATIONS.md`).
- Gitleaks config present at `.gitleaks.toml`.

## Provenance

- Source: GitHub `mariourquia/obsidian-connector`.
- Release tag: `v0.9.0` -> commit `099af67101645faea8ad8b48a00f8c39e387ba1c`.
- Build environment: GitHub Actions hosted runners
  (`macos-latest`, `ubuntu-latest`, `windows-latest`). See
  `.github/workflows/release.yml`.
- Tag signature: GPG ED25519, fingerprint
  `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`.

## License

MIT (SPDX: `MIT`). See `LICENSE`.
