# Known Limitations: obsidian-connector 0.9.0

> Last updated: 2026-04-13

## Platform Limitations

| Platform  | Status     | Notes                                                         |
|-----------|------------|---------------------------------------------------------------|
| macOS     | supported  | Tested on macOS darwin 25.3.0; DMG installer built but not click-through tested |
| Linux     | supported  | ubuntu-latest in CI; no DMG/installer, pip-only               |
| Windows   | supported  | windows-latest in CI; MSI installer built but not click-through tested |
| Python 3.11 | supported | Primary dev target; all 137 tests pass                      |
| Python 3.12 | supported | CI covered                                                  |
| Python 3.13 | supported | CI covered                                                  |
| Python 3.14 | untested  | Not listed in `Programming Language :: Python :: 3.N` classifiers; may work but unverified |

## Documentation Limitations

- **Stale SECURITY.md support matrix.** `SECURITY.md` still lists `0.7.x` as
  the actively supported version and `0.6.x` as security-fixes-only. After
  0.9.0 ships this is three releases out of date. Users following the policy
  may misidentify which lines receive security fixes. This is flagged as a
  post-release doc follow-up; SECURITY.md is not being auto-edited in this
  release.
- **Stale SBOM.md header.** The header block reads
  `Generated: 2026-03-16` / `Package: obsidian-connector v0.2.0`. Table
  contents for direct and transitive dependencies remain accurate, but the
  metadata lines will be refreshed in the next docs sweep.

## Packaging / Install Limitations

- **`graphify` extra requires `networkx>=3.0,<4.0`.** When the `[graphify]`
  extra is not installed, the `obsidian_connector.graphify` package imports
  cleanly but any attribute access beyond the lazy-dispatch surface will
  raise `AttributeError`. The 18-test smoke suite
  (`tests/test_graphify_smoke.py`) verifies this degrades cleanly. Full
  graphify features (cluster, report, export) require the extra.
- **`tui` extra is new in 0.9.0.** Prior releases shipped `textual` as a
  runtime dependency. 0.9.0 moves it to `[tui]`. Users who previously relied
  on importing the Textual dashboard from their own code without declaring
  the extra will see `ModuleNotFoundError`. Remediation:
  `pip install 'obsidian-connector[tui]'`.
- **`pyyaml` install edge case observed during development.** In one
  development environment `pyyaml` failed to install automatically even though
  it is a declared runtime dependency. Rerunning
  `pip install -r requirements-lock.txt` resolved it. If this reproduces in
  the field, check that the pip resolver is up to date and that the user's
  Python matches the `>=3.11` requirement.
- **Untracked `builds/` subtrees.** Commit 099af67 cleaned up five divergent
  duplicate files in `builds/`, but the working tree still has six untracked
  directories / files under `builds/` that should be reviewed post-release:
  - `builds/claude-code/obsidian_connector/`
  - `builds/claude-code/skills/`
  - `builds/claude-code/requirements-lock.txt`
  - `builds/claude-desktop/`
  - `builds/cowork/`
  - `builds/portable/`

  These are local staging artifacts, not release payload. They do not affect
  installed-package behavior but should either be `.gitignore`d or moved under
  an already-excluded path.

## Performance Limitations

- No benchmarks were captured for 0.9.0.
- `graphify` extract / cluster / report has been exercised in `.tmp-graphify/`
  during development but not profiled under this release.
- MCP tool latency under high concurrency is not characterized.

## Feature Limitations

- **`smart_triage` LLM fallback** uses whatever `LLMClient` implementation the
  caller injects. No built-in LLM client is provided. If `llm_client=None` the
  function returns the low-confidence rule-based result directly.
- **Commitment note related fence** renders edges on each sync, but only edges
  present in the passed `ActionInput`. Stale edges from a prior sync that are
  no longer in the payload are removed on re-render.
- **Entity notes** always emit a `wiki` fence (possibly empty). Callers that
  do not pass `wiki_content` on re-render preserve any user-authored content
  inside the fence.
- **Textual TUI dashboard** screen transitions and the first-run wizard were
  manually smoke-checked only. No automated UI tests.

## Edge Cases

- `obsidian_bin` configuration rejects shell metacharacters `;`, `|`, `&&`,
  command substitution `$()`, and backticks. Users whose Obsidian binary path
  contains these characters will see an explicit config error rather than a
  silent exploit surface. This is tested behavior, not a limitation per se,
  but worth calling out.
- Entity / commitment note slugs are sanitized on write; unsafe slugs raise.
- If `graphify` is accessed through its `__main__.py` on an environment where
  the package distribution name is missing (editable installs into exotic
  namespace packages), the version lookup will fall back rather than fail.

## Unsupported Configurations

- Read-only vault filesystems: untested.
- FIPS mode: untested.
- Custom Python builds without `sqlite3`: the index store depends on the
  stdlib `sqlite3` module; builds compiled without it will fail at import.
- Running the MCP server inside a chrooted environment without access to the
  vault root: out of scope.

## Developer Preview / Experimental Features

- **`graphify` module**: ships under the `[graphify]` extra and is considered
  stable enough to depend on for read-only graph generation, but the
  clustering heuristics and report templates may evolve in 0.10.x without
  breaking the lazy-import surface.
- **UX orchestrator + Ix Integration + progressive MCP middleware**: new in
  0.9.0. The internal API between these modules is subject to change in
  0.10.x. Depending on the public MCP tool surface is safe; depending on the
  internal middleware chain is not.
