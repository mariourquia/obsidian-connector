# obsidian-connector v0.9.0

> Release date: 2026-04-13
> Classification: stable (Python package + MCPB + Claude Code plugin + macOS DMG + Windows installer)
> Verdict: READY

```text
+===================================================================+
|                                                                   |
|   OBSIDIAN-CONNECTOR  v0.9.0                                      |
|   ::  TRIAGE  ::  SEMANTIC MEMORY  ::  GRAPHIFY  ::  UX           |
|                                                                   |
|   [ rules -> threshold -> LLM fallback ]                          |
|   [ entities -> edges -> related blocks ]                         |
|   [ extract -> cluster -> god-nodes -> report ]                   |
|                                                                   |
+===================================================================+
```

## Headline Features

### 1. `smart_triage` module and `RuleBasedClassifier` (Task 20 triage surface)

A new `obsidian_connector.smart_triage` module and
`obsidian_connector.classifiers.rule_based.RuleBasedClassifier` together form
the connector-side surface consumed by obsidian-capture-service Task 20.

`smart_triage()` runs the rule-based classifier first. If its confidence meets
or exceeds `SMART_TRIAGE_LLM_THRESHOLD` (default `0.7`), the rule-based result
is returned. Otherwise, if an `LLMClient` is injected, the call falls through
to the LLM; if the LLM errors or returns `None`, the rules-only result is
returned with `reason="llm_failed"`. If the rule-based classifier itself raises,
a frozen fallback `ClassificationResult` with `kind=RAW`, `confidence=0.0`,
`source=RULES` is returned and no LLM call is made.

Exported symbols:

- `smart_triage(text, *, llm_client=None, threshold=0.7) -> ClassificationResult`
- `ClassificationResult` (frozen dataclass with fields `kind`, `confidence`,
  `reason`, `source`, `slug`)
- `LLMClient` (`@runtime_checkable` Protocol)
- `Kind`, `Source` enums
- `RuleBasedClassifier` at `obsidian_connector.classifiers.rule_based`

Coverage: 10 tests in `tests/test_smart_triage.py` and 24 tests in
`tests/test_classifiers_rule_based.py`.

### 2. Semantic memory 15.A.2 and 15.C bridges

`commitment_notes.py` and `entity_notes.py` now regenerate related-edges and
shared-entity groups on every sync.

- Commitment notes gain a fenced `related` block rendering edges (`blocks`,
  `follows_from`, `precedes`, `duplicates`, `relates_to`) as wiki-linked bullets
  plus a per-entity "Related actions" section.
- Entity notes gain the same related-actions surface wired off the
  `ActionInput` payload, with a mandatory `wiki` fence that is always
  round-tripped (empty when the caller did not supply content; replaced when
  supplied; preserved on re-render when not supplied).

25 dedicated tests cover fence lifecycle, user-notes preservation, and
idempotent re-render (`tests/test_entity_notes.py`, `tests/test_related_block.py`).

### 3. `graphify` knowledge-graph module (optional extra)

New `obsidian_connector.graphify` module: extract, build, cluster, analyze,
report, and export to JSON / HTML / SVG / Obsidian Canvas / wiki over code,
docs, papers, and audio.

- Opts in via `pip install 'obsidian-connector[graphify]'` (pulls
  `networkx>=3.0,<4.0`).
- CLI entrypoint: `python -m obsidian_connector.graphify`.
- Lazy `__getattr__` dispatch uses fully static absolute imports per attribute,
  so static security linters can trace the import allowlist.
- `__main__.py` version lookup now resolves against the real distribution name
  `obsidian-connector` (previously typoed as `graphifyy`).
- 18-test smoke suite (`tests/test_graphify_smoke.py`) that skips cleanly when
  networkx is absent.

### 4. CLI decoupled from optional TUI

`textual` moved from runtime dependency to `[tui]` optional extra in
`pyproject.toml`. The CLI starts cleanly without textual installed, and
`tests/test_cli_tui_optional.py` (7 tests) enforces that the import graph does
not pull textual on the basic path.

Install the dashboard separately:

```bash
pip install 'obsidian-connector[tui]'
```

### 5. Other additions

- `commitment_dashboards.py`: 4 generated dashboard views (open by priority,
  blocked, due this week, recently completed) rendered from capture-service
  actions.
- `commitment_notes.py`: capture-service actions rendered as vault notes with
  lifecycle metadata and a follow-up log fence.
- Commitment inspection and update CLI commands.
- `entity_notes.py`: per-entity vault notes from extracted entities.
- Textual TUI dashboard with sidebar navigation and a multi-screen wizard
  (`obsx` menu).
- First-run setup wizard.
- UX orchestrator + Ix Integration + progressive MCP middleware coordinating
  user-facing flows across MCP, CLI, and TUI surfaces.

## Changes Since v0.8.3

### Added

- `smart_triage` module and `RuleBasedClassifier` (Task 20 triage surface).
- Semantic memory 15.A.2 commitment-note related fence and 15.C entity-note
  wiki fence.
- `entity_notes.py` writer.
- `commitment_notes.py` renderer and `commitment_dashboards.py` (4 views).
- Commitment inspection and update CLI commands.
- Textual TUI dashboard + first-run setup wizard.
- UX orchestrator, Ix Integration, progressive MCP middleware.
- `graphify` optional extra (networkx-backed).

### Changed

- `obsidian_connector/graphify/__init__.py` rewritten to use fully static
  absolute imports per attribute in its lazy `__getattr__` dispatch.
- `obsidian_connector/graphify/__main__.py` distribution-name lookup fixed
  (`graphifyy` -> `obsidian-connector`).
- `textual` dependency moved from runtime to optional `[tui]` extra.

### Fixed

- CLI startup no longer requires textual to be importable (5d3871f).

### Removed

No public APIs removed.

### Security

- No new CVEs introduced. `SECURITY.md` "Supported Versions" table is
  currently stale (still reads 0.7.x); flagged as a post-release doc follow-up.

## Installation

```bash
# Base install
pip install obsidian-connector==0.9.0

# With TUI
pip install 'obsidian-connector[tui]==0.9.0'

# With graphify
pip install 'obsidian-connector[graphify]==0.9.0'

# Everything
pip install 'obsidian-connector[tui,graphify,live,semantic,scheduling]==0.9.0'
```

For DMG / MSI / MCPB / Claude Code plugin install surfaces, see
`docs/INSTALL.md` and `docs/INSTALL-SURFACES.md`.

## Verification

Verify the download integrity:

```bash
sha256sum -c obsidian-connector-0.9.0-SHA256SUMS.txt
```

Verify the tag signature:

```bash
git verify-tag v0.9.0
# Expected signing key fingerprint:
# ED25519 SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4
```

## Compatibility

- Supported OS: macOS, Linux, Windows (see `COMPATIBILITY_MATRIX.md`)
- Python: `>=3.11` (CI covers 3.11, 3.12, 3.13; 3.14 untested)
- Breaking changes: none. `textual` is no longer pulled by a base install;
  opt in via `[tui]` extra.

## Known Limitations

- `SECURITY.md` supported-versions table is stale (0.7.x still listed).
- `graphify` extra skips its non-smoke tests when `networkx` is absent; the
  18-test smoke suite runs in both modes.
- `pyyaml` was observed failing to install in one dev venv despite being a
  declared runtime dependency; rerunning `pip install -r requirements-lock.txt`
  resolved it.
- 5 divergent duplicate files in `builds/` were resolved in commit 099af67, but
  6 untracked subtree directories under `builds/` remain and should be
  triaged post-release.

See `KNOWN_LIMITATIONS.md` for the full list.

## Testing Summary

137 tests pass in 5.09s on `.venv/bin/python -m pytest -q`. See
`TESTING_SUMMARY.md` for the per-file breakdown and the explicit list of areas
not under automated coverage.

## Security

Gitleaks-configured repo. Manual grep sweep of the v0.8.3..HEAD diff found no
real secrets (matches were docs examples, function-parameter names, and Neo4j
placeholder strings). See `SECURITY_REVIEW.md`.

## Rollback

```bash
pip install obsidian-connector==0.8.3
```

See `ROLLBACK_OR_UNINSTALL.md` for per-surface rollback instructions.

## Full Documentation

- `CHANGELOG.md`
- `docs/releases/v0.9.0/SECURITY_REVIEW.md`
- `docs/releases/v0.9.0/KNOWN_LIMITATIONS.md`
- `docs/releases/v0.9.0/COMPATIBILITY_MATRIX.md`
- `docs/releases/v0.9.0/TRUST_AND_PROVENANCE.md`
