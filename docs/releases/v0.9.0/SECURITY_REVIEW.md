# Security Review: obsidian-connector 0.9.0

> Review date: 2026-04-13
> Reviewer: release-engineer (self-reviewed by maintainer; automated scans via CI)
> Scope: diff since v0.8.3 + current runtime dependency tree

## Review Status

| Area                        | Reviewed | Tool / Method                      | Findings |
|-----------------------------|----------|------------------------------------|----------|
| Hardcoded secrets           | Yes      | `.gitleaks.toml` + manual grep     | 0 real   |
| Dependency vulnerabilities  | Yes      | `pip-audit` (CI: security.yml)     | 0 known  |
| Auth/authz flows            | Partial  | Manual review (local-only tool)    | 0        |
| Input validation            | Yes      | Manual + `test_config_validation`  | 0        |
| SQL/NoSQL injection         | Yes      | Manual (SQLite stdlib, paramized)  | 0        |
| XSS / output encoding       | N/A      | No HTML render path in runtime     | --       |
| File system access          | Yes      | Manual; path containment tests     | 0        |
| Network/API calls           | Yes      | Manual (no outbound HTTP)          | 0        |
| Shell command execution     | Yes      | Manual + `test_config_validation`  | 0        |
| Cryptographic usage         | N/A      | No runtime crypto code             | --       |
| Error handling / info leak  | Partial  | Manual review                      | 0        |
| CORS / CSP / headers        | N/A      | No HTTP server                     | --       |

## Not Assessed

- **`graphify` optional extra with `networkx>=3.0,<4.0`**: full transitive
  dependency tree of networkx was not audited for 0.9.0. The smoke test suite
  confirms the extra is inert when not installed and that the lazy-import
  dispatch does not reach into networkx unnecessarily, but no pip-audit pass
  was run against a fully-installed `[graphify]` environment.
- **Textual TUI in `[tui]` extra**: new user-facing UI surface. Manual review
  confirmed no credential prompts, no disk writes outside the configured vault
  root, and no outbound network traffic, but the dashboard widget tree was not
  fuzzed.
- **macOS DMG and Windows installer bootstrap scripts**: script-level review
  only. No static analysis or signing chain verification for this release.
- **Third-party MCP client behavior**: the connector is an MCP server.
  Security of the client connecting to it (Claude Desktop, Claude Code, etc.)
  is out of scope.

## Findings

### Critical

No critical findings.

### High

No high findings.

### Medium

- **M1: `SECURITY.md` support-matrix is stale.** Still lists 0.7.x as the
  actively supported version series after 0.8.x and 0.9.x have shipped.
  Operational rather than code risk, but users following the policy may
  misidentify which versions receive security fixes.
  - Location: `SECURITY.md` lines 3-9.
  - Remediation status: OPEN. Slated for a post-release doc-only PR within 7
    days of the 0.9.0 tag. Not auto-edited in this release per release plan.

### Low / Informational

- **L1**: `SBOM.md` header line still reads `v0.2.0` / `2026-03-16`. Table
  contents remain accurate for the minimum runtime tree (mcp, pyyaml, plus the
  mcp transitives). Refresh in the next docs sweep.
- **L2**: `builds/` working tree contains six untracked subtrees
  (`claude-code/obsidian_connector/`, `claude-code/skills/`,
  `claude-code/requirements-lock.txt`, `claude-desktop/`, `cowork/`,
  `portable/`). These are local staging artifacts, not release payload, and
  should be either `.gitignore`d or moved under a clearly-excluded path.
- **L3**: Vendored TypeScript type-declaration files under `.venv/` and
  `.tmp-graphify/` include benign `password: BinaryLike` signatures from
  Node.js crypto type defs. These triggered the grep sweep; they are normal
  and not committed to the repo.

## Grep Sweep Output (v0.8.3..HEAD)

Command:

```bash
git diff v0.8.3..HEAD | grep -iE "(password|api[_-]?key|secret|token|bearer)\s*[=:]" | head -20
```

Output and classification:

```
+export OBSIDIAN_CAPTURE_SERVICE_TOKEN="your-api-token"   # optional, Bearer auth   # docs env placeholder
+    api_key: str | None = None,                                                     # function parameter
+    api_key:                                                                        # function parameter (wrapped)
+_CHARS_PER_TOKEN = 4  # standard approximation                                      # constant for LLM token sizing
+    password: str,                                                                  # function parameter
+result = push_to_neo4j(G, uri='NEO4J_URI', user='NEO4J_USER', password='NEO4J_PASSWORD', communities=communities)   # docs example x10 identical lines
+ * const secret = 'abcdefg';                                                        # vendored type-def JSDoc comment
+    function createCipher(algorithm: CipherCCMTypes, password: BinaryLike, options: CipherCCMOptions): CipherCCM;   # type declaration
+    function createCipher(algorithm: CipherGCMTypes, password: BinaryLike, options?: CipherGCMOptions): CipherGCM;  # type declaration
+    function createCipher(algorithm: CipherOCBTypes, password: BinaryLike, options: CipherOCBOptions): CipherOCB;   # type declaration
+        password: BinaryLike,                                                        # type declaration (wrapped)
+    function createCipher(algorithm: string, password: BinaryLike, options?: stream.TransformOptions): Cipher;      # type declaration
```

All 20 matches are either docs placeholders, function signature parameter
names, an LLM token-sizing constant (`_CHARS_PER_TOKEN`), or vendored Node.js
type declarations. No real credentials were committed.

## Dependency Summary

- Total direct runtime dependencies: 2 (`mcp>=1.0.0,<2.0.0`, `pyyaml>=6.0.0`)
- Total transitive runtime dependencies (via mcp, as pinned in
  `requirements-lock.txt`): 13 (see `SBOM.md`)
- Optional extras dependencies: 5 distinct top-level packages across 5 extras
  (`scheduling`, `tui`, `live`, `semantic`, `graphify`) + 1 dev extra
  (`pytest`)
- Known vulnerabilities at time of review: 0 (latest `security.yml` run green)
- Outdated dependencies: 0 in the pinned base tree
- Dependencies with no maintenance (>1yr no commits): 0

## Secrets Handling

- Secrets management approach: environment variables only (tool is
  local-first, no server-side secret store).
- Unsafe defaults: none. No default credentials. No default outbound network
  endpoint.
- Documentation for secret configuration: `README.md` + `docs/INSTALL.md`
  document the `OBSIDIAN_CAPTURE_SERVICE_TOKEN` Bearer token env variable
  used when integrating with the capture service.

## Supply Chain

- Lock file present: yes (`requirements-lock.txt`).
- Lock file committed: yes.
- Dependency pinning strategy: bounded range in `pyproject.toml`; exact pins
  in `requirements-lock.txt`.
- SBOM available: yes (`SBOM.md`), though the header metadata lines are stale
  and due for refresh.
- Build reproducibility: not formally verified. Build runs on GitHub Actions
  hosted runners; no SLSA attestation generated for this release.

## Recommendations

1. File the M1 SECURITY.md matrix refresh PR within 7 days of the 0.9.0 tag.
2. Refresh `SBOM.md` header metadata (version, generation date) in the next
   docs sweep.
3. Add `builds/claude-desktop/`, `builds/cowork/`, `builds/portable/`,
   `builds/claude-code/obsidian_connector/`, `builds/claude-code/skills/`,
   `builds/claude-code/requirements-lock.txt` to `.gitignore` or relocate
   them under an already-ignored path.
4. Run `pip-audit` against a fully-installed `[graphify,tui,live,semantic,
   scheduling]` environment and record the result in a follow-up
   SECURITY_REVIEW addendum.
