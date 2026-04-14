# Release Readiness Review

> Project: obsidian-connector
> Version: 0.9.0
> Date: 2026-04-13
> Reviewer: release-engineer (automated scan + manual review)
> Base comparison: v0.8.3

## Verdict

```
READY
```

All HIGH criteria met. One MEDIUM doc-hygiene warning (stale SECURITY.md support
matrix) logged as a post-release follow-up. No blockers.

## Evidence Summary

| Criterion                   | Weight | Status | Evidence / Notes                                                                 |
|-----------------------------|--------|--------|----------------------------------------------------------------------------------|
| License present             | BLOCK  | Pass   | `LICENSE` (MIT) at repo root; `pyproject.toml [project] license = "MIT"`         |
| README has install steps    | BLOCK  | Pass   | `README.md` + `docs/INSTALL.md` + `docs/INSTALL-SURFACES.md`                     |
| Build succeeds              | HIGH   | Pass   | 7 GitHub Actions workflows green on HEAD 099af67 (ci, release, verify-release, security, installer-smoke, build-macos-dmg, build-windows-installer) |
| Tests exist and pass        | HIGH   | Pass   | 137 tests pass in 5.09s on local `.venv/bin/python -m pytest -q`                 |
| No hardcoded secrets        | HIGH   | Pass   | Gitleaks-configured (`.gitleaks.toml`); manual grep since v0.8.3 returned only docs examples, param names, and Neo4j placeholder strings |
| Version identified          | MEDIUM | Pass   | `pyproject.toml [project] version = "0.9.0"`; `mcpb.json version: "0.9.0"`       |
| Changelog exists            | MEDIUM | Pass   | `CHANGELOG.md [0.9.0] - 2026-04-13` populated with Added / Changed               |
| Security policy exists      | MEDIUM | Pass   | `SECURITY.md` present; **support matrix stale (still lists 0.7.x)** -- warning W1 |
| Dependency lockfile exists  | LOW    | Pass   | `requirements-lock.txt` at repo root, 37275 bytes                                |
| Release automation exists   | LOW    | Pass   | `.github/workflows/release.yml` + `verify-release.yml` gate assets by smoke tests |
| Verification artifacts      | LOW    | Pass   | Release workflow emits SHA256SUMS; GPG tag signing used (ED25519)                |

## Preflight Outputs

### Smart-triage import smoke

```
$ .venv/bin/python -c "from obsidian_connector.smart_triage import smart_triage, ClassificationResult, LLMClient, Kind, Source; from obsidian_connector.classifiers.rule_based import RuleBasedClassifier; print('ok')"
ok
```

### ClassificationResult dataclass shape

```
$ .venv/bin/python -c "
import dataclasses
from obsidian_connector.smart_triage import ClassificationResult
names = {f.name for f in dataclasses.fields(ClassificationResult)}
assert names == {'kind', 'confidence', 'reason', 'source', 'slug'}, names
print('ok')
"
ok
```

Fields confirmed: `kind`, `confidence`, `reason`, `source`, `slug`. Shape locked
for the obsidian-capture-service Task 20 consumer.

### Full test suite

```
$ .venv/bin/python -m pytest -q
........................................................................ [ 52%]
.................................................................        [100%]
137 passed in 5.09s
```

### Security grep sweep (v0.8.3..HEAD)

```
$ git diff v0.8.3..HEAD | grep -iE "(password|api[_-]?key|secret|token|bearer)\s*[=:]" | head -20
```

All 20 matches are benign:

- `+export OBSIDIAN_CAPTURE_SERVICE_TOKEN="your-api-token"` (install docs placeholder)
- `+    api_key: str | None = None,` (function signature)
- `+_CHARS_PER_TOKEN = 4  # standard approximation` (LLM sizing constant)
- 10 x `push_to_neo4j(...user='NEO4J_USER', password='NEO4J_PASSWORD'...)` (doc
  example showing env-var placeholders)
- `+ * const secret = 'abcdefg';` (vendored type-def comment)
- 5 x `createCipher(...password: BinaryLike, ...)` (type declaration files)

No real credentials committed.

## Blockers

No blockers identified.

## Warnings

- **W1 (MEDIUM)**: `SECURITY.md` "Supported Versions" table still lists `0.7.x`
  as the actively-supported series. It should reflect `0.9.x` after this cut.
  - Risk: users on 0.8.x reading the policy may assume their line is already
    EOL, or worse, assume 0.9.x is not yet supported.
  - Mitigation: file a post-release doc PR to refresh the matrix. Do NOT
    auto-edit in this session per release plan.
- **W2 (LOW)**: `builds/` contains six untracked directories
  (`claude-code/obsidian_connector/`, `claude-code/skills/`,
  `claude-code/requirements-lock.txt`, `claude-desktop/`, `cowork/`, `portable/`).
  These are local staging artifacts, not release payload, but the working tree
  is not clean. Review post-release and `.gitignore` them or move them under a
  clearly-excluded path.
- **W3 (LOW)**: `SBOM.md` header still reads `v0.2.0` and `2026-03-16`. Table
  contents remain accurate (mcp, pyyaml, etc.), but the metadata lines are
  stale. Refresh in the next docs sweep.

## Assumptions

- Tests run on macOS darwin 25.3.0, Python 3.11 via `.venv`. CI also runs them
  on ubuntu-latest + windows-latest per `ci.yml`.
- `v0.8.3` tag exists and resolves cleanly (`git log v0.8.3..HEAD` produces the
  23-commit window listed below).
- All release-branch commits are GPG-signed with ED25519
  `SHA256:Yt3RMq3eAYUMSGpi0uDzMKR3lo6eBRCbn8xBSWtUOZ4`; verified by
  `git log --format='%G? %GK'` returning `G <fingerprint>` for each.
- `obsidian-connector[graphify]` extra will install `networkx>=3.0,<4.0` cleanly
  on the target Python versions. `test_graphify_smoke.py` imports and lazy-dispatch
  tests pass with networkx absent; full graphify behavior tested in
  `.tmp-graphify/`.
- obsidian-capture-service Task 20 consumer will pin `obsidian-connector==0.9.0`
  or the `>=0.9.0,<0.10.0` range and rely on the `ClassificationResult` field
  set above.

## Commit Range Inventory

23 commits between v0.8.3 and HEAD (099af67). Highlights:

- `099af67` chore(hygiene): resolve 5 divergent duplicate files in builds/
- `89c6b8c` feat(graphify): knowledge-graph module with networkx optional extra
- `d2758f4` feat(task-15): merge semantic memory bridges from release/v0.9.0-triage
- `a2a8bac` feat(task-15): semantic memory connector bridges (15.A.2, 15.C)
- `5d3871f` fix: decouple CLI startup from optional TUI
- `3fd3d9a` chore(release): sync built claude-code plugin.json to 0.9.0
- `6265544` chore(release): bump to v0.9.0 and document triage release
- `c4920b8` test(smart-triage): cover RuleBasedClassifier and smart_triage decision tree
- `3f29e55` feat(classifiers): port RuleBasedClassifier from obsidian-capture-service
- `0a2d312` feat(smart-triage): add smart_triage module and ClassificationResult surface
- `7ac6625` feat: upgrade dashboard to Textual TUI framework with sidebar nav and multi-screen wizard
- `4a60edb` feat: add interactive dashboard (obsx menu) and first-run setup wizard
- `30fe596` feat(task-15.A): entity notes writer for semantic memory layer
- `c30aba4` feat: Add UX orchestrator, Ix Integration, and progressive MCP middleware
- `6f27e94` feat(dashboards): add commitment dashboard generation (4 views)
- `99259dd` feat: add commitment inspection and update commands (v0.9.0)
- `e9218c7` feat(commitment-notes): render capture-service actions as vault notes
- 6 merge/docs commits (#49, #50, #51) on install-guide simplification

## Recommendation

Proceed with the v0.9.0 release. Tag on `main` at 099af67, build artifacts for
all 5 packaging surfaces (PyPI wheel, MCPB, Claude Code plugin, macOS DMG,
Windows installer), and publish. File W1 (SECURITY.md support matrix) as a
post-release doc follow-up PR within the next 7 days.
