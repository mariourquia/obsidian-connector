# Harness Engineering — Adopt into this repo

You are adopting the Harness Engineering framework into the current repository.
This gives the repo agent-friendly knowledge architecture, application legibility
tooling, and mechanical enforcement via CI and local runners.

## Arguments

$ARGUMENTS may contain:
- `--tier knowledge|legibility|full` (default: full)
- `--owner <team-name>` (default: platform)
- `--dry-run` (preview only)
- Any other context about the repo

## Procedure

### Step 1: Locate the harness-engineering source

Check if the harness-engineering repo exists at a known path:
```
~/Documents/GitHub/harness-engineering/tools/harness_adopt.py
```

If found, use it directly. If not, check if `tools/harness_adopt.py` exists in the
current repo (it may have been copied previously).

### Step 2: Run the adoption tool

If `harness_adopt.py` is available, run it:
```bash
python3 <path-to>/tools/harness_adopt.py --target . --yes $ARGUMENTS
```

If the adoption tool is NOT available, perform the adoption manually by following
the steps below.

### Step 3: Manual adoption (only if harness_adopt.py is unavailable)

If you cannot find `harness_adopt.py`, perform these steps manually:

1. **Create the directory scaffold:**
   ```
   docs/{architecture,design-docs,product-specs,exec-plans/active,exec-plans/completed,quality,reliability,security,references,generated}
   tools/ dev/{journeys,assertions,docker} skills/ artifacts/ templates/
   .github/workflows/ .claude/
   ```

2. **Generate AGENTS.md** — a routing map (≤120 lines) customized to this repo's
   actual directory structure. Include links to ARCHITECTURE.md, docs/index.md,
   and any existing doc indexes. Include operating rules, navigation tips,
   required artifacts by change type, and escalation policy.

3. **Generate ARCHITECTURE.md** — scan the repo for top-level directories,
   detect languages (package.json, pyproject.toml, Cargo.toml, go.mod),
   identify domains (src/*, apps/*, packages/*), and generate a domain map.

4. **Generate CLAUDE.md** — agent instructions pointing to AGENTS.md, listing
   available make targets, rules for doc maintenance, and the frontmatter contract.

5. **Generate docs/index.md** — top-level catalog linking to all sub-indexes.
   If docs already exist, list them with "TODO: add frontmatter" notes.

6. **Generate sub-indexes** — design-docs/index.md, product-specs/index.md.

7. **Generate stub docs** — QUALITY_SCORE.md, RELIABILITY.md, SECURITY.md,
   tech-debt-tracker.md (all with proper frontmatter).

8. **Copy or create tools/docs_lint.py** — the full docs linter from the
   harness-engineering framework. This is ~570 lines of Python that checks
   frontmatter, links, discoverability, staleness, and AGENTS.md integrity.

9. **Copy or create the Makefile targets** — append harness targets to the
   existing Makefile, or create a new one. Targets: docs-lint, docs-lint-strict,
   docs-staleness, docs-changed, sandbox-up, sandbox-down, harness-validate,
   ci-local, ci-full, install-harness-deps, harness-help.

10. **Copy or create CI workflows** (if tier=full):
    - `.github/workflows/docs-lint.yml` — PR check for docs
    - `.github/workflows/doc-gardener.yml` — weekly staleness sweep
    - `.github/workflows/harness-validate.yml` — full harness pipeline

11. **Copy or create skills/** (if tier=legibility or full):
    - `skills/sandbox.py` — sandbox lifecycle
    - `skills/ui_playwright.py` — UI automation + artifact capture
    - `skills/obs_prom_loki.py` — PromQL + LogQL queries
    - `skills/assertions.py` — declarative budget evaluation

12. **Update .gitignore** — add artifacts/, lint-*.json, .harness/

13. **Run the linter** to verify: `make docs-lint`

### Step 4: Post-adoption guidance

After adoption, tell the user:
1. Review and customize AGENTS.md and ARCHITECTURE.md (fill in TODOs)
2. Add frontmatter to any pre-existing docs
3. Run `make docs-lint` to see remaining issues
4. Commit the harness files
5. Run `make help` to see all available commands
