# Build System Refactor -- Execution Plan

**Branch**: `feature/build-system-refactor`
**Created**: 2026-04-02
**Completed**: 2026-04-02
**Status**: Complete

---

## Problem Statement

The repo serves five distribution surfaces (Claude Code plugin, Claude Desktop,
portable skills, PyPI package, DMG/EXE installers) but uses the same raw source
tree for all of them. The `portable/` directory is a manual attempt at
multi-target that duplicates 5 skills without a build pipeline. Installer scripts
reach into the source tree directly. There is no validation that a given
distribution surface gets the right subset of files in the right format.

---

## Current State (v0.7.1)

| Component | Count | Location | Format |
|-----------|-------|----------|--------|
| Python package | 39 modules | `obsidian_connector/` | Python 3.11+ |
| Skills (Claude Code) | 17 | `skills/<name>/SKILL.md` | YAML frontmatter: name, description |
| Skills (Portable) | 5 | `portable/skills/<name>/SKILL.md` | Manual copy of Claude Code skills |
| Hooks | 3 | `hooks/hooks.json` + `.sh`/`.md` | Bash scripts, markdown prompts |
| Plugin manifest | 1 | `.claude-plugin/plugin.json` | JSON |
| MCP config | 1 | `.mcp.json` | JSON, uses `${CLAUDE_PLUGIN_ROOT}` |
| MCP server | 1 | `obsidian_connector/mcp_server.py` | FastMCP, 62 tools |
| CLI | 65 cmds | `obsidian_connector/cli.py` | argparse |
| Installers | 3 | `scripts/install.sh`, `Install.ps1`, `create-dmg.sh` | Shell/PS1 |
| CI | 7 | `.github/workflows/` | GitHub Actions |
| Tests | 20+ | `scripts/*_test.py` + `tests/` | pytest |
| Docs | 40+ | `docs/` | Markdown |

### Distribution Surfaces

| Surface | What Ships | Current Mechanism |
|---------|-----------|-------------------|
| Claude Code plugin | Python pkg + skills + hooks + manifest + MCP config | `claude --plugin-dir .` (raw source) |
| Claude Desktop | Python pkg + MCP server | `install.sh` writes `claude_desktop_config.json` |
| Portable (Codex/OpenCode/Gemini) | 5 stripped skills | Manual copy in `portable/` |
| PyPI | Python package only | `pip install obsidian-connector` |
| DMG/EXE | Python pkg + installer wrapper | `create-dmg.sh` / Inno Setup |

### What Breaks Today

- `portable/` is a manual fork of 5 skills -- drifts from `skills/` source
- No validation that Claude Code skills have correct frontmatter
- No validation that portable skills stripped Claude-Code-specific content
- Installer scripts reference raw source paths, not built artifacts
- `pyproject.toml` packages the raw source (fine for PyPI, but DMG/EXE should use a built distribution)
- Skills that reference MCP tools (`obsidian_check_in`, etc.) ship to portable targets where those tools do not exist
- No way to know if a skill works on a given surface without manual testing

---

## Target Architecture

```
src/                              <-- only place humans edit
  obsidian_connector/             <-- Python package (39 modules, unchanged)
  skills/                         <-- 17 skill dirs (SKILL.md only)
  hooks/                          <-- hooks.json + script files
  plugin/                         <-- base plugin.json, .mcp.json
  bin/                            <-- obsx, obsx-mcp wrappers

config/
  targets/
    claude-code.yaml              <-- Claude Code plugin normalization
    claude-desktop.yaml           <-- Claude Desktop MCP setup
    portable.yaml                 <-- Portable skills (Codex/OpenCode/Gemini)
    pypi.yaml                     <-- PyPI Python package
  defaults/
    skill-portability.yaml        <-- per-skill portability flags

tools/
  build.ts                        <-- entry: build --target <target>
  validate.ts                     <-- entry: validate --target <target>
  diff.ts                         <-- entry: diff --target <target>
  doctor.ts                       <-- entry: doctor
  normalize/
    skills.ts                     <-- strip MCP-dependent steps for portable
    hooks.ts                      <-- omit for non-plugin targets
    manifest.ts                   <-- compile target-specific plugin.json
    mcp-config.ts                 <-- target-specific .mcp.json
  package/
    package-claude-code.ts        <-- full plugin zip
    package-claude-desktop.ts     <-- MCP server + install config
    package-portable.ts           <-- portable skills bundle
    package-pypi.ts               <-- sdist/wheel (delegates to python -m build)

builds/                           <-- generated only, gitignored
  claude-code/                    <-- ready-to-install Claude Code plugin
  claude-desktop/                 <-- MCP server config + package
  portable/                       <-- stripped skills for other agents
  pypi/                           <-- wheel/sdist

tests/
  (existing tests remain)
  golden/                         <-- known-good build outputs
  snapshots/                      <-- snapshot comparisons
  fixtures/                       <-- malformed input for negative tests
```

### Release Artifacts

| Target | Artifact | Install Method |
|--------|----------|----------------|
| `claude-code` | `obsidian-connector-claude-code.zip` | `claude plugin install` or `--plugin-dir` |
| `claude-desktop` | `obsidian-connector-desktop.zip` | Extract + run install script |
| `portable` | `obsidian-connector-portable.zip` | Copy skills to agent config dir |
| `pypi` | `obsidian-connector-0.7.x.tar.gz` + `.whl` | `pip install obsidian-connector` |
| `dmg` | `obsidian-connector-v0.7.x.dmg` | Double-click installer |
| `exe` | `obsidian-connector-v0.7.x.exe` | Windows installer wizard |

---

## Implementation Phases

### Phase 0: Scaffolding (no behavior change)

**Goal**: Create directory structure without moving any files yet.

1. Create `config/targets/claude-code.yaml`, `claude-desktop.yaml`, `portable.yaml`, `pypi.yaml`
2. Create `config/defaults/skill-portability.yaml` -- flags each of 17 skills as `portable: true/false` based on whether they depend on MCP tools
3. Create `tools/` directory with stub files
4. Create `tools/normalize/` and `tools/package/` with stubs
5. Add `builds/` to `.gitignore`
6. Create `tests/golden/`, `tests/snapshots/`, `tests/fixtures/`

**Language choice**: TypeScript (consistency with cre-skills-plugin build system). Minimal deps: `tsx`, `zod`, `glob`, `yaml`. Add `tools/package.json`.

**Acceptance**: All stubs exist. No existing behavior changed.

---

### Phase 1: Source Migration

**Goal**: Move all human-authored plugin content into `src/`.

The Python package `obsidian_connector/` does NOT move -- it is already the right shape for PyPI and is referenced by `pyproject.toml`. Only the plugin-specific content moves:

1. Create `src/` directory
2. Move:
   - `skills/` -> `src/skills/`
   - `hooks/` -> `src/hooks/`
   - `.claude-plugin/plugin.json` -> `src/plugin/plugin.json`
   - `.mcp.json` -> `src/plugin/.mcp.json`
   - `bin/` -> `src/bin/`
3. Create symlinks from old locations to `src/` equivalents (keeps `claude --plugin-dir .` working)
4. Delete `portable/` -- the build system will generate it from source skills
5. Keep `obsidian_connector/` at top level (PyPI needs it there)
6. Update `hooks/hooks.json` paths

**Key difference from cre-skills-plugin**: The Python package stays at the top level because it has its own packaging story (`pyproject.toml`, `pip install`). Only the Claude-specific plugin artifacts move to `src/`.

**Acceptance**: `claude --plugin-dir .` still works via symlinks. `pip install -e .` still works. `portable/` deleted.

---

### Phase 2: Skill Portability Analysis + Target Profiles

**Goal**: Define what each target accepts and classify skill portability.

#### Skill Portability Classification

Each skill falls into one of these categories:

| Category | Criteria | Example | Portable? |
|----------|----------|---------|-----------|
| MCP-dependent workflow | Calls MCP tools (obsidian_*) | morning, evening, weekly, idea, ritual, capture, float, explore, sync, sync-vault, new-vault, init-vault | No |
| Knowledge reference | Static knowledge, no tool calls | obsidian-markdown, obsidian-bases, json-canvas, obsidian-cli, defuddle | Yes |

```yaml
# config/defaults/skill-portability.yaml
portable_skills:
  - obsidian-markdown
  - obsidian-bases
  - json-canvas
  - obsidian-cli
  - defuddle

non_portable_skills:
  - morning
  - evening
  - weekly
  - idea
  - ritual
  - capture
  - float
  - explore
  - sync
  - sync-vault
  - new-vault
  - init-vault
```

#### `config/targets/claude-code.yaml`

```yaml
name: claude-code
description: Full Claude Code plugin with all skills, hooks, and MCP server

skills:
  include: all
  normalize: false  # keep all frontmatter as-is

hooks:
  include: true
  variant: full  # all hooks (SessionStart, UserPromptSubmit, Stop)

manifest:
  include_mcp: true  # include .mcp.json
  include_plugin: true  # include .claude-plugin/plugin.json

python_package:
  include: true  # bundle obsidian_connector/ for MCP server
  venv: true  # create venv with deps

bin:
  include: true  # include obsx, obsx-mcp wrappers
```

#### `config/targets/claude-desktop.yaml`

```yaml
name: claude-desktop
description: Claude Desktop MCP server configuration

skills:
  include: none  # Desktop uses MCP tools directly, not skills

hooks:
  include: false  # Desktop does not use hooks

manifest:
  include_mcp: true  # generate claude_desktop_config.json snippet
  include_plugin: false

python_package:
  include: true
  venv: true

bin:
  include: true
```

#### `config/targets/portable.yaml`

```yaml
name: portable
description: Portable skills for Codex, OpenCode, Gemini, and other agent systems

skills:
  include: portable_only  # only skills in skill-portability.yaml portable list
  normalize: true
  transformations:
    - strip_mcp_references  # remove any stray MCP tool mentions
    - add_portable_header   # add note that this is a portable skill

hooks:
  include: false

manifest:
  include_mcp: false
  include_plugin: false

python_package:
  include: false

bin:
  include: false
```

#### `config/targets/pypi.yaml`

```yaml
name: pypi
description: Python package for pip install

skills:
  include: none  # PyPI users use the Python API, not skills

hooks:
  include: false

manifest:
  include_mcp: false
  include_plugin: false

python_package:
  include: true
  venv: false  # user manages their own venv

bin:
  include: true  # install obsx CLI entry point via pyproject.toml
```

**Acceptance**: All target profiles defined. Skill portability classification reviewed and correct.

---

### Phase 3: Build Pipeline

**Goal**: `build --target <target>` produces complete artifacts for each surface.

#### Build Flows

**claude-code**:
```
1. Clean builds/claude-code/
2. Copy src/skills/ -> builds/claude-code/skills/
3. Copy src/hooks/ -> builds/claude-code/hooks/
4. Copy src/plugin/plugin.json -> builds/claude-code/.claude-plugin/plugin.json
5. Copy src/plugin/.mcp.json -> builds/claude-code/.mcp.json
6. Copy obsidian_connector/ -> builds/claude-code/obsidian_connector/
7. Copy src/bin/ -> builds/claude-code/bin/
8. Copy pyproject.toml, requirements-lock.txt -> builds/claude-code/
9. Generate setup script (creates venv, installs deps)
10. Validate
```

**claude-desktop**:
```
1. Clean builds/claude-desktop/
2. Copy obsidian_connector/ -> builds/claude-desktop/obsidian_connector/
3. Copy src/bin/ -> builds/claude-desktop/bin/
4. Generate MCP config snippet for claude_desktop_config.json
5. Generate install script (venv setup + config injection)
6. Copy pyproject.toml, requirements-lock.txt
7. Validate
```

**portable**:
```
1. Clean builds/portable/
2. For each portable skill:
   a. Copy SKILL.md
   b. Run normalize/skills.ts to strip MCP references
   c. Add portable header
3. Generate README.md with install instructions per agent system
4. Validate
```

**pypi** (delegates to Python tooling):
```
1. Clean builds/pypi/
2. Run python -m build (produces sdist + wheel)
3. Copy artifacts to builds/pypi/
4. Validate with twine check
```

#### CLI Interface

```bash
npx tsx tools/build.ts --target claude-code
npx tsx tools/build.ts --target claude-desktop
npx tsx tools/build.ts --target portable
npx tsx tools/build.ts --target pypi
npx tsx tools/build.ts --target all

npx tsx tools/validate.ts --target claude-code
npx tsx tools/diff.ts --target portable
npx tsx tools/doctor.ts
```

**Acceptance**: All four build targets produce valid output. `builds/portable/` replaces the old `portable/` directory with identical (or improved) content.

---

### Phase 4: Validation Engine

**Goal**: `validate --target <target>` catches issues before packaging.

#### Validation Rules

**claude-code**:
- All 17 skill SKILL.md files present with valid frontmatter (`name`, `description`)
- hooks.json valid JSON, references existing script files
- plugin.json has `name`, `version`, `description`
- .mcp.json references valid Python module path
- obsidian_connector/ importable (no syntax errors)
- pyproject.toml version matches plugin.json version

**claude-desktop**:
- obsidian_connector/ importable
- MCP config snippet valid JSON
- Install script references correct paths
- pyproject.toml version matches

**portable**:
- Only portable skills present (no workflow skills)
- No MCP tool references in portable skill content (`obsidian_` pattern)
- Each skill has valid frontmatter
- README.md present with install instructions

**pypi**:
- sdist/wheel valid (twine check)
- Version consistent across pyproject.toml, plugin.json, product_registry.py
- No Claude-specific files in the Python package

#### Cross-Target Version Consistency

All targets must agree on version. Validate:
```
pyproject.toml: version
.claude-plugin/plugin.json: version
obsidian_connector/product_registry.py: __version__
marketplace.json: version
mcpb.json: version
CHANGELOG.md: latest entry
```

Existing `scripts/version_check.py` partially does this -- integrate it into the validation engine.

**Acceptance**: `validate --target all` catches version drift, missing files, and content violations.

---

### Phase 5: Diff + Doctor Commands

**Goal**: Contributor trust and debugging.

#### `diff --target portable`

```
DIFF portable (source -> build)
  skills/morning/SKILL.md       [EXCLUDED -- MCP-dependent]
  skills/evening/SKILL.md       [EXCLUDED -- MCP-dependent]
  ...
  skills/obsidian-markdown/SKILL.md  [INCLUDED -- portable]
    (no changes)
  skills/defuddle/SKILL.md      [INCLUDED -- portable]
    + [Portable skill header]   [INJECTED]
```

#### `doctor`

```
DOCTOR -- obsidian-connector health check

  Python 3.11+     3.14.2     OK
  Node.js          20.11.0    OK  (for tools/ build system)
  tsx              available   OK
  Obsidian CLI     detected   OK
  pip              available   OK
  src/skills/      17 skills  OK
  builds/          empty      OK  (not yet built)
  venv             exists     OK
  Version sync     0.7.1      OK  (all files match)

  RECOMMENDATION: Run `build --target all` to generate artifacts.
```

**Acceptance**: Both commands produce useful, actionable output.

---

### Phase 6: Packaging

**Goal**: Produce named release artifacts.

| Target | Script | Output |
|--------|--------|--------|
| claude-code | `package-claude-code.ts` | `dist/obsidian-connector-claude-code.zip` |
| claude-desktop | `package-claude-desktop.ts` | `dist/obsidian-connector-desktop.zip` |
| portable | `package-portable.ts` | `dist/obsidian-connector-portable.zip` |
| pypi | `package-pypi.ts` | `dist/obsidian_connector-0.7.x.tar.gz` + `.whl` |
| dmg | existing `create-dmg.sh` (updated to consume `builds/claude-code/`) | `dist/obsidian-connector-v0.7.x.dmg` |
| exe | existing Inno Setup (updated) | `dist/obsidian-connector-v0.7.x.exe` |

Update `.github/workflows/release.yml` to build all targets, validate, package, and upload.

**Acceptance**: Release produces 6 distinct artifacts with checksums.

---

### Phase 7: Tests

**Goal**: Automated regression coverage.

#### Golden Tests

- `test_portable_no_mcp_references.py` -- grep builds/portable/ for `obsidian_` tool names, expect zero matches
- `test_portable_correct_skills.py` -- verify exactly 5 portable skills present
- `test_claude_code_all_skills.py` -- verify all 17 skills present
- `test_claude_code_hooks_present.py` -- verify hooks.json + scripts in build
- `test_claude_desktop_no_skills.py` -- verify no skills/ in desktop build
- `test_claude_desktop_has_mcp_config.py` -- verify MCP config snippet present
- `test_pypi_no_plugin_files.py` -- verify no .claude-plugin/, hooks/, or skills/ in wheel
- `test_version_consistency.py` -- all targets built with same version

#### Snapshot Tests

- Compare `builds/portable/skills/obsidian-markdown/SKILL.md` against known-good snapshot
- Compare `builds/claude-code/.claude-plugin/plugin.json` against snapshot

#### Negative Tests

- Skill with broken YAML frontmatter -> build fails
- Portable skill that references MCP tool -> validation fails
- Version mismatch between pyproject.toml and plugin.json -> validation fails

**Acceptance**: All tests pass in CI. Added as gate in `ci.yml`.

---

### Phase 8: Documentation

**Goal**: Users and contributors know what to install.

#### Files to Create/Update

| File | Action |
|------|--------|
| `README.md` | Rewrite install section to point at specific artifacts per surface |
| `docs/INSTALL.md` | Detailed per-surface install with verification steps |
| `docs/TROUBLESHOOTING.md` | Common failures per surface |
| `docs/COMPATIBILITY.md` | Surface compatibility matrix |
| `docs/RELEASES.md` | Release process for maintainers |
| `CONTRIBUTING.md` | Update: edit `src/` for plugin content, edit `obsidian_connector/` for Python |
| `portable/README.md` | Delete (replaced by `builds/portable/README.md`) |

#### Compatibility Matrix

```
| Surface         | Artifact                          | Runtime      | Python | Obsidian | Install Method                     |
|-----------------|-----------------------------------|--------------|--------|----------|------------------------------------|
| Claude Code     | obsidian-connector-claude-code.zip| Claude Code  | 3.11+  | Yes      | claude plugin install              |
| Claude Desktop  | obsidian-connector-desktop.zip    | Claude Desktop| 3.11+ | Yes      | Extract + run install script       |
| Portable        | obsidian-connector-portable.zip   | Any agent    | No     | No       | Copy skills to config dir          |
| PyPI            | obsidian-connector on PyPI        | Python       | 3.11+  | Yes      | pip install obsidian-connector     |
| macOS           | .dmg                              | macOS 10.13+ | Bundled| Yes      | Double-click installer             |
| Windows         | .exe                              | Windows 10+  | Bundled| Yes      | Installer wizard                   |
```

**Acceptance**: A new user finds their surface, downloads the right artifact, installs, and verifies.

---

### Phase 9: Symlink Removal + Final Cleanup

**Goal**: Remove migration symlinks, clean up old structure.

1. Remove symlinks for `skills/`, `hooks/`, `.claude-plugin/`, `.mcp.json`, `bin/`
2. Update `pyproject.toml` if any paths changed
3. Update all CI workflows for final paths
4. Full `build --target all && validate --target all`
5. Full test suite green
6. Remove `portable/` directory entirely (now generated)

**Acceptance**: Clean repo. No stale symlinks. All builds and tests pass.

---

## Execution Sequence

| Phase | Depends On | Estimated Scope | Risk |
|-------|-----------|-----------------|------|
| 0: Scaffolding | None | ~15 files created | None |
| 1: Source Migration | Phase 0 | Move ~25 files, add symlinks | Medium (path breakage) |
| 2: Target Profiles | Phase 0 | ~8 config files | Low |
| 3: Build Pipeline | Phases 1, 2 | ~10 files | Medium |
| 4: Validation Engine | Phase 2 | ~6 files | Low |
| 5: Diff + Doctor | Phases 2, 3 | ~4 files | Low |
| 6: Packaging | Phases 3, 4 | ~6 files, CI updates | Low |
| 7: Tests | Phases 3, 4 | ~10 test files | Low |
| 8: Documentation | All above | ~6 doc files | Low |
| 9: Cleanup | All above | Delete symlinks | Medium |

---

## Differences from cre-skills-plugin Refactor

| Aspect | cre-skills-plugin | obsidian-connector |
|--------|-------------------|---------------------|
| Primary content | 112 skills, 54 agents, orchestrators | 39 Python modules, 17 skills |
| Python package | No (markdown/YAML only) | Yes (core product) |
| Targets | 2 (Cowork, Claude Code) | 4+ (Claude Code, Desktop, Portable, PyPI, DMG, EXE) |
| Key normalization | Strip frontmatter, inject agent fields | Strip MCP refs from portable skills |
| Package format | .plugin / .zip | .zip / .whl / .dmg / .exe |
| Source migration | Everything moves to src/ | Only plugin artifacts move; Python stays top-level |
| Existing build | catalog-generate.py | python -m build for PyPI |

---

## Out of Scope

- Rewriting the Python package (`obsidian_connector/`)
- Adding new MCP tools or CLI commands
- Changing skill content or workflows
- MCPB distribution format (tracked separately in ROADMAP.md)
- Marketplace submission process (tracked separately)
- Semantic search / embedding pipeline changes
