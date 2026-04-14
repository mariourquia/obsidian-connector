# Testing Summary: obsidian-connector 0.9.0

> Date: 2026-04-13
> Environment: macOS darwin 25.3.0; Python 3.11 in project `.venv`; pytest 8.x

## Test Inventory

| Test Type        | Count | Pass | Fail | Skip | Runner |
|------------------|-------|------|------|------|--------|
| Unit             | 137   | 137  | 0    | 0    | pytest |
| Integration      | 0     | 0    | 0    | 0    | --     |
| End-to-end       | 0     | 0    | 0    | 0    | --     |
| Smoke            | 18    | 18   | 0    | 0    | pytest (counted above, under `test_graphify_smoke.py`) |

The 18 graphify smoke tests are part of the 137 unit total, not in addition to
it. They are enumerated separately to make it explicit that graphify has smoke
coverage even when the optional `networkx` dependency is not installed.

## Full Suite Output

```
$ .venv/bin/python -m pytest -q
........................................................................ [ 52%]
.................................................................        [100%]
137 passed in 5.09s
```

## Per-File Breakdown

| File                                    | Tests | Area                                              |
|-----------------------------------------|-------|---------------------------------------------------|
| `tests/test_classifiers_rule_based.py`  | 24    | RuleBasedClassifier decision tree (Task 20)       |
| `tests/test_build_system.py`            | 23    | packaging manifests, extras, mcpb.json sync       |
| `tests/test_config_validation.py`       | 19    | `obsidian_bin` shell-metachar sanitization, config parsing |
| `tests/test_graphify_smoke.py`          | 18    | graphify lazy imports + all-submodules importable (skips cleanly when networkx absent) |
| `tests/test_entity_notes.py`            | 15    | entity notes writer: frontmatter, fences, rewrite idempotency, wiki-fence round-trip |
| `tests/test_all_suites.py`              | 11    | legacy test-script wrapper aggregating other scripts |
| `tests/test_smart_triage.py`            | 10    | smart_triage decision tree: rules >= threshold, LLM fallback, rules-only on LLM error, fallback on rules crash, module exports |
| `tests/test_related_block.py`           | 10    | commitment-note related fence: edge labels, wikilinks, idempotent replace, empty-group skip |
| `tests/test_cli_tui_optional.py`        | 7     | CLI starts without textual installed              |
| **Total**                               | **137** |                                                 |

## Coverage

- Line coverage: not measured for this release.
- Branch coverage: not measured.
- Coverage tool: none configured in `pyproject.toml` for 0.9.0
  (coverage-gated CI was present in earlier releases; the threshold was
  lowered to 10 in 0.6.1 and the measurement step has since drifted).
- Coverage report: not available.

## What Was Tested

- **Smart triage decision tree** (10 tests): rule confidence >= threshold
  short-circuits, missing LLM client returns low-confidence rules, LLM fallback
  invoked below threshold, LLM exception returns rules-only with
  `reason="llm_failed"`, rules-crash returns a frozen fallback and suppresses
  the LLM, module exports match the documented symbol set,
  `ClassificationResult` is frozen, `LLMClient` Protocol is runtime-checkable.
- **RuleBasedClassifier** (24 tests): full decision tree covering the Task 20
  triage surface; this is a port from obsidian-capture-service.
- **Graphify smoke** (18 tests): `obsidian_connector.graphify` imports without
  pulling networkx; lazy `__getattr__` resolves each documented callable
  (`extract`, `collect_files`, `build_from_json`, `cluster`, `score_all`,
  `cohesion_score`, `god_nodes`, `surprising_connections`, `suggest_questions`,
  `generate`, `to_json`, `to_html`, `to_svg`, `to_canvas`, `to_wiki`);
  unknown attr raises `AttributeError`; every submodule is importable.
- **Entity notes writer** (15 tests): path resolution for project/person kinds,
  invalid-kind raises, unsafe-slug raises, file creation, idempotent rewrite,
  frontmatter fields, open / done / empty commitments sections, user notes
  preserved on rewrite, wiki fence always present, wiki content written /
  preserved / replaced per call shape.
- **Commitment-note related fence** (10 tests): no fence when no related data,
  edges render, incoming edge labels, wiki-link path rendering, shared-entities
  section, empty actions-group skip, fence replace on re-render, fence
  disappears when cleared, user notes preserved alongside fence.
- **CLI/TUI separation** (7 tests): CLI starts and basic import paths succeed
  with textual uninstalled.
- **Config validation** (19 tests): `obsidian_bin` rejects shell metacharacters
  like `;`, `|`, `&&`, command substitution `$()`, and backticks.
- **Packaging** (23 tests): `pyproject.toml`, `mcpb.json`, Claude Code plugin
  manifest, and extras stay in sync.

## What Was NOT Tested

This section carries unquantified risk. Consumers should treat these as
untested paths:

- **Live integration against obsidian-capture-service**: the Task 20 smart
  triage consumer side was tested in the capture-service repo; end-to-end
  cross-repo wiring was not exercised in this test suite.
- **Live MCP tool invocation from Claude Desktop or Claude Code**: no MCP
  harness is wired up in the 0.9.0 suite. MCP surface is exercised only via
  unit tests of its Python entrypoints.
- **macOS DMG install path**: the DMG is built by
  `.github/workflows/build-macos-dmg.yml`, but no automated post-install smoke
  test actually mounts the DMG and clicks through the installer. Manual dry-run
  only.
- **Windows installer**: same as above for the MSI via
  `build-windows-installer.yml`. `installer-smoke.yml` covers PowerShell bits
  but not a full click-through install.
- **Textual TUI user flows**: no automated dashboard interaction tests. The TUI
  extra is verified to install and import; rendering and user flows were only
  manually smoke-checked.
- **Graphify full path with networkx installed**: the 18 smoke tests cover
  import structure and lazy dispatch. Cluster / report / export behavior with
  networkx loaded was exercised in `.tmp-graphify/` during development but is
  not in the 137-test CI suite.
- **macOS / Linux / Windows parity**: local run was macOS only. CI runs
  `ci.yml` on ubuntu-latest + windows-latest; those reports were not
  individually inspected for this release.
- **Python 3.14**: classifier says 3.11 / 3.12 / 3.13 in the
  `Programming Language :: Python :: 3.N` list. 3.14 is not in CI.

## Test Environment

- OS: darwin 25.3.0 (macOS)
- Runtime: Python 3.11 (`.venv/bin/python`)
- CI system: GitHub Actions (`ci.yml`, `security.yml`, `installer-smoke.yml`,
  `verify-release.yml`)
- Database: SQLite stdlib (no external DB)
- External services: none (local-first)

## Flaky Tests

No known flaky tests. All 137 pass deterministically in 5.09s.

## Manual Testing Performed

- Smart triage import smoke: `from obsidian_connector.smart_triage import ...`
  returned `ok`.
- ClassificationResult field assertion: field set matches
  `{'kind', 'confidence', 'reason', 'source', 'slug'}`.

Beyond these two preflight probes, no additional manual testing was performed
for 0.9.0. Regressions outside automated coverage may be present in the
untested areas listed above.
