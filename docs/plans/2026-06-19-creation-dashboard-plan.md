---
title: "Creation Dashboard (Phase 4, full read layer) Implementation Plan"
status: draft
owner: mariourquia
last_reviewed: "2026-06-19"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/creation_projects.py"
  - "obsidian_connector/creation_repo_status.py"
  - "obsidian_connector/creation_next.py"
  - "obsidian_connector/creation_dashboards.py"
  - "obsidian_connector/creation_migrate.py"
  - "obsidian_connector/project_sync.py"
  - "obsidian_connector/cli.py"
  - "obsidian_connector/mcp_server.py"
related_docs:
  - "../architecture/creation-dashboard.md"
  - "../architecture/creation-vault-schema.md"
  - "./2026-06-18-creation-vault-os.md"
  - "./2026-06-18-creation-backlog-engine-plan.md"
tags: ["creation-vault-os", "dashboard", "project", "next-action", "phase-4", "plan"]
---

# Creation Dashboard (Phase 4, full read layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Creation Dashboard operating console (read layer): a first-class **Project** entity over repos, a git+PR+test/build/deploy **repo classifier**, an explainable **next-action engine**, the **migration** of the flat `projects/{slug}/` hubs into `Projects/{Project}/Repos/{slug}.md`, and the generated Obsidian markdown dashboards + `obsx creation dashboard|projects|project show|repo show|next` (with MCP parity).

**Architecture:** Extends `project_sync.py` (which already gathers per-repo git `RepoState` and writes `Dashboard.md`/`projects/{dir}.md`/`groups/` MOCs). New `creation_*` modules add the Project entity, the enriched classifier, the scoring engine, and the fenced dashboard generators. The append-only event log + backlog remain the source of truth for items; the dashboards are materialized views read from git + the backlog + the freshness audit (a deliberately **loose, read-only seam** — `creation_dashboards` calls `creation_backlog.list_backlog` and `creation_status.freshness_audit`, never the reverse). The design was approved interactively (global = hybrid triage+table; project/repo drilldowns; explainable next-actions) — see `docs/architecture/creation-dashboard.md`.

**Tech Stack:** Python 3 stdlib + `subprocess` (git, `gh`), `write_manager.atomic_write`, argparse CLI, FastMCP tools. Tests via `pytest` mirroring `tests/test_creation_*.py` (temp vaults, `monkeypatch.setenv("HOME", ...)`, monkeypatched subprocess for git/gh/test probes — never hit the network or run real repos in tests).

## Global Constraints

- **Stdlib + subprocess only.** No new third-party deps. `gh`, git, and test/build probes run via `subprocess` with timeouts and **never raise** to the caller — failures degrade to an `unknown`/`unavailable` sub-status inside the result (the classifier and dashboards must render even when `gh` is unauthenticated, offline, or a test command is missing).
- **Reuse, don't duplicate** (per the machinery map): import `project_sync._extract_repo_state` (or its public wrapper) for the git baseline `RepoState`; reuse `project_sync.RepoEntry`/`SyncConfig`/`load_sync_config`, `write_manager.atomic_write`, `audit.log_action`, `draft_manager._parse_frontmatter`, `config.resolve_vault_path`. Do NOT reimplement git-state extraction.
- **Loose read-only seam to the spine.** `creation_dashboards`/`creation_next` may READ `creation_backlog.list_backlog(...)`, `creation_backlog.show_backlog_item(...)`, `creation_status.freshness_audit(...)`. They must NOT append events or mutate backlog. `project_sync.py` stays unaware of the spine.
- **All vault writes via `write_manager.atomic_write`** with `vault_root` + `tool_name`. Generated regions inside otherwise user-owned notes (the project one-pager, repo views) go inside `<!-- service:<name>:begin -->` / `<!-- service:<name>:end -->` fences and preserve hand-written content across regeneration (reuse the per-module fence-extractor pattern from `creation_backlog._extract_user_notes` / `entity_notes`). Fully-generated dashboards (`Dashboard.md`, `Projects.md`, `Next Actions.md`, etc.) may be wholly regenerated but must carry a `last_sync` + a "generated — edits are overwritten" banner.
- **Reads are side-effect-free; writes are dry-run-by-default.** `dashboard`/`projects`/`project show`/`repo show`/`next` are pure reads (no `--allow-write`). The generators (`refresh`, dashboard materialization) and the migration take `dry_run: bool` and are dry-run-by-default at the CLI/MCP edge (`--allow-write`); `log_action` fires only on real writes.
- **Clock boundary at the CLI/MCP edge** (`now_iso = datetime.now(timezone.utc).isoformat()`), passed down; core functions never read a clock (mirrors the spine).
- **Migration is reversible + gated.** `creation migrate-projects` defaults to dry-run, writes a `Projects/_migration-map.md` mapping note (old path → new path) enabling reversal, preserves all fences/user content, and leaves the flat `projects/{slug}.md` in place until `--allow-write` is given. It must never delete user content; the reverse is `--undo` using the map.
- **Project entity = promoted `group`.** A Project groups repos by their `group` field. The canonical registry is `sync_config.json` (`SyncConfig.repos[].group`); Phase 4 seeds/normalizes it from the current `~/.local/bin/sync-creation-vault` group assignments (mcmc, amos, keiki, cre-skills, obsidian, wine, site, agentops, harness, standalone, ...) so `obsx creation projects` lists the real programs. This also folds the "two sync engines" divergence onto the Python registry.
- **Classification enum** (exact strings): `clean-and-ready`, `mid-implementation`, `waiting-on-pr-review`, `blocked-by-tests`, `blocked-by-decision`, `stale`, `ahead`, `behind`, `needs-sync`, `ready-for-next-agent`, `dormant`, `unknown`.
- **Explainable ranking only.** Every recommendation names its top contributing factors and exposes the per-factor score; no opaque ranking. Weights live in vault config (`creation/dashboard-weights.json`), defaulted + user-editable.
- **CLI ↔ MCP parity.** Each read verb gets one MCP tool; `mcpb.json tools_count` bumps by the number of new tools; `scripts/integrity_check.py` (incl. ARCHITECTURE.md module inventory) and `scripts/manifest_check.py` must pass.
- **Add `.superpowers/` to `.gitignore`** (the brainstorm companion artifacts).
- **No model/provider co-author/attribution trailer** on any commit. Branch: `feat/creation-dashboard`.

## Out of scope (later phases)

Interactive TUI mutations — reprioritize, mark-decision, assign-workflow, accept/reject voice, start/resume from the console (Phase 6, visual-companion pass already informs it). `context-pack` generation + `/start creation work` (Phase 7). Voice-to-backlog (Phase 3). The optional `session.start` event bridge from `log_session`. Live deploy probes beyond a best-effort, config-declared check (no cloud SDKs). These are explicitly NOT built here; the read layer must function without them.

## Approved layouts (the rendering spec)

The generated markdown must match the interactively-approved IA:

- **`Dashboard.md` (hybrid):** (1) a `## ▶ Do next` block — the top 3-5 ranked recommendations (from the next-engine) with one-line reasons; then (2) a `## Projects` dense table — `Project | Pri | State | Repos | Flags | Next action`; then (3) `## Needs decision`, `## Stale`, `## Clean & ready` short rollups; then a links/footer. Leads with action, follows with the full scan.
- **`Projects/{Project}/Project Dashboard.md`:** header (name + one-liner goal/intent from the one-pager fence) → `**→ Next:**` lead → state badges (decisions/stale/blocked/clean counts) → `## Repos (N)` table (`Repo | Branch | State | Next`) → `## Top backlog (ranked)` → `## Load for an agent` (one-pager + pack + key docs) → links.
- **`Projects/{Project}/Repos/{repo}.md`:** classification line → `## Git` (path, branch@HEAD, tree, vs-origin, recent commits) → `## PRs` (open + merged-since-sync) → `## Tests / build / deploy` (last result, build, deploy) → `## Work context` (phase, linked backlog, blockers, suggested agent, related sessions/docs). Generated state inside a `service:repo-status` fence; user notes preserved.
- **`Next Actions.md`:** ranked list; each item: rank, action, project·repo, confidence, reason chips (top factors), `needs-decision`/`blocked` flags, suggested workflow, context-pack link; footer states the transparent scoring formula + that weights are user-editable.
- **`Stale Context.md` / `Pending Decisions.md` / `Active Sessions.md`:** focused rollups derived from the freshness audit, `needs_decision` backlog items, and the active-session marker + recent session notes respectively.

---

## Task 1: `creation_projects.py` — Project entity + registry + state rollup

**Files:**
- Create: `obsidian_connector/creation_projects.py`
- Create: `tests/test_creation_projects.py`
- Modify: `obsidian_connector/__init__.py` (export `list_projects`, `get_project`, `Project`)
- Modify: `.gitignore` (add `.superpowers/`)

**Interfaces:**
- Consumes: `project_sync.load_sync_config(vault)` → `SyncConfig` with `repos: list[RepoEntry]` (each has `dir_name`, `display_name`, `group`, `status`, `tags`); `draft_manager._parse_frontmatter`.
- Produces:
  - `@dataclass(frozen=True) Project` fields: `slug: str` (group slug), `name: str` (display, via `project_sync.group_display`), `group: str`, `repos: tuple[str, ...]` (repo dir_names), `status: str` (rollup: active if any active repo, else paused/dormant), `tags: tuple[str, ...]`.
  - `list_projects(vault) -> list[Project]` — group the registry's repos by `group`, one Project per distinct group (skip `archived` repos from the active rollup but keep them listed), sorted by name. Standalone repos (`group == "standalone"`) each... see Step 1 decision below.
  - `get_project(vault, name_or_slug) -> Project | None` — case-insensitive match on slug or display name.
  - `project_repo_entries(vault, project) -> list[RepoEntry]` — the `RepoEntry`s for a project's repos (for the classifier/dashboards).
  - `read_one_pager_prose(vault, project) -> dict` — parse the `Projects/{name}/Project One-Pager.md` fenced prose fields (`goal`, `intent`, `target_users`, `architecture`, `why`) if present, else `{}` (the one-pager is user-authored; missing is fine).

- [ ] **Step 1: Decide the standalone handling, then write the module.** Standalone repos (`group=="standalone"`) each become their own single-repo Project named after the repo `display_name` (so `obsidian-connector` etc. still appear as projects). Grouped repos collapse into one Project per group. Implement `creation_projects.py` accordingly: `list_projects` returns one `Project` per non-standalone group + one per standalone repo. Pure functions, no I/O beyond `load_sync_config` + reading the one-pager note (read-only). No clock.

- [ ] **Step 2: Write failing tests** (`tests/test_creation_projects.py`): with a temp `sync_config.json` containing repos across groups `mcmc` (3 repos), `cre-skills` (2), and 2 `standalone` repos → `list_projects` returns 4 Projects (MCMC, CRE Skills, + 2 standalone), MCMC has the 3 repos, standalone projects have 1 repo each; `get_project("mcmc")` and `get_project("MCMC")` both resolve; `read_one_pager_prose` returns `{}` when the one-pager is absent and the fenced `goal:`/`intent:` when present. Use `monkeypatch.setenv("HOME", ...)` + a temp vault with a written `sync_config.json`.

- [ ] **Step 3: Run tests** (`python3 -m pytest tests/test_creation_projects.py -v`), expect PASS.

- [ ] **Step 4: Export + gitignore.** Add the three exports to `__init__.py`; add `.superpowers/` to `.gitignore` under a `# Brainstorm companion` comment.

- [ ] **Step 5: Commit** (`feat(creation): Project entity + registry derivation over repo groups`).

---

## Task 2: `creation_repo_status.py` — enriched git + PR + test/build classifier

**Files:**
- Create: `obsidian_connector/creation_repo_status.py`
- Create: `tests/test_creation_repo_status.py`
- Modify: `obsidian_connector/__init__.py`

**Interfaces:**
- Consumes: the git baseline from `project_sync` (`RepoState` + the internal `_extract_repo_state`; if `_extract_repo_state` is private, add a thin public `extract_repo_state(repo_entry, github_root) -> RepoState` wrapper in `project_sync.py` and use it — do not duplicate the git logic).
- Produces:
  - `@dataclass(frozen=True) RepoStatus`: `dir_name`, `display_name`, `project`, `repo_path`, `branch`, `head: str`, `dirty: bool`, `untracked: int`, `ahead: int`, `behind: int`, `recent_commits: tuple[str,...]`, `open_prs: tuple[dict,...]` (`{number,title,is_draft,review,updated}`), `merged_prs_recent: tuple[dict,...]`, `tests: dict` (`{status: passed|failed|errored|unknown|not-configured, summary, ran_at}`), `build: dict` (`{status, detail}`), `deploy: dict` (`{status, detail}`), `classification: str` (the enum), `next_action: str`, `blockers: tuple[str,...]`, `authority_level: str` (always `repo_grounded` for the git-derived parts).
  - `repo_status(repo_entry, *, github_root, now_iso, with_prs=True, with_tests=False, with_build=False, runner=subprocess_run) -> RepoStatus`. `runner` is an injectable command-runner (default wraps `subprocess.run` with a timeout) so tests monkeypatch it. PRs via `gh pr list --repo <owner/name> --json ... ` (parse JSON; on any failure → `open_prs=()` and a `pr_status='unavailable'` note, never raise). ahead/behind via `git rev-list --left-right --count origin/<branch>...HEAD`. Tests via the repo's declared test command (from `sync_config` repo `test_cmd` if present, else skip → `not-configured`); only run when `with_tests=True`. Build/deploy: best-effort from a declared `build_cmd`/`deploy_check` in config, else `unknown`.
  - `classify(rs_fields) -> (classification, next_action, blockers)`: pure function with these rules in priority order — unmerged conflicts → `needs-sync`; tests failed/errored → `blocked-by-tests`; an open non-draft PR awaiting review → `waiting-on-pr-review`; dirty tree or non-main branch with commits → `mid-implementation`; `behind>0` → `behind`; `ahead>0` and clean → `ahead`; a linked backlog item with `needs_decision` → `blocked-by-decision`; `days_since_commit > 30` → `dormant`; stale freshness on a linked note → `stale`; clean + on main + up-to-date + no open work → `clean-and-ready`; else `ready-for-next-agent`. `next_action`/`blockers` derived per branch.

- [ ] **Step 1:** Add the public `extract_repo_state` wrapper to `project_sync.py` if needed (one line delegating to `_extract_repo_state`), with a one-line test that it returns a `RepoState`.
- [ ] **Step 2: Write `classify` first (pure) + its unit tests** covering every enum branch with synthetic field dicts (tests-failed → blocked-by-tests; open PR → waiting-on-pr-review; dirty → mid-implementation; behind → behind; clean+main+uptodate → clean-and-ready; 40-days → dormant). This is the logic core — full code + exhaustive tests.
- [ ] **Step 3: Write `repo_status`** with the injectable `runner`. Tests monkeypatch `runner` to return canned git/gh/test outputs (a fake `gh pr list` JSON, a fake `rev-list` count, a fake test result) and assert the assembled `RepoStatus` + classification. Assert the no-raise contract: a `runner` that raises for `gh` yields `open_prs=()` + `pr_status` unavailable, not an exception.
- [ ] **Step 4: Run tests**, expect PASS. **Step 5: Export + commit** (`feat(creation): git+PR+test/build repo status classifier`).

---

## Task 3: `creation_next.py` — explainable next-action engine

**Files:**
- Create: `obsidian_connector/creation_next.py`
- Create: `tests/test_creation_next.py`
- Modify: `obsidian_connector/__init__.py`

**Interfaces:**
- Consumes (read-only): `creation_backlog.list_backlog(vault, ...)`, `creation_status.freshness_audit(vault)`, `creation_repo_status.repo_status(...)`, `creation_projects.list_projects(...)`.
- Produces:
  - `DEFAULT_WEIGHTS: dict` (`urgency, impact, dependency_unlock, stale_age, user_emphasis, deadline, unfinished_session, repo_readiness`) + `load_weights(vault) -> dict` (reads `creation/dashboard-weights.json`, falls back to defaults, tolerates malformed).
  - `score_item(item: dict, *, repo_status, signals, weights) -> tuple[float, list[tuple[str,float]]]` — pure: returns `(total, factors)` where `factors` is the named per-factor contributions sorted desc. Full formula = sum of `weight[k] * normalized_signal[k]`. **Full code + tests.**
  - `next_actions(vault, *, scope="global", project=None, repo=None, github_root, now_iso, limit=10, runner=...) -> list[dict]` — builds candidate actions from ready/blocked backlog items + repo classifications (e.g. a `waiting-on-pr-review` repo yields a "review PR #N" action; `blocked-by-tests` yields a "green up tests" action flagged blocked), scores each, returns the ranked `Recommendation` dicts (shape from `creation-dashboard.md` §5: `scope, project, repo, backlog_id, action, reason[list], confidence, requires_mario_decision, suggested_workflow, context_pack`). `confidence` = normalized top-score. Deterministic ordering (score desc, then id) — no clock/random in ordering.

- [ ] **Step 1: `score_item` + `load_weights` first, with unit tests** — assert factor naming + that a high-urgency+dependency-unlock item outranks a low one; assert weights override changes ranking; assert malformed weights file falls back. Full code.
- [ ] **Step 2: `next_actions`** — tests build a temp vault with 3 backlog items (one ready P0 with repo clean, one `needs_decision`, one whose repo is `blocked-by-tests`) + monkeypatched `repo_status`/`freshness_audit`, assert the ranking, the `requires_mario_decision` flag on the decision item, the `blocked` flag + lowered rank on the tests item, and that every recommendation lists ≥1 reason. Scope filters (`project=`, `repo=`) narrow the candidate set.
- [ ] **Step 3: Run tests**, expect PASS. **Step 4: Export + commit** (`feat(creation): explainable next-action engine`).

---

## Task 4: `creation_migrate.py` — flat → Projects/{Project}/Repos/ migration (reversible, dry-run default)

**Files:**
- Create: `obsidian_connector/creation_migrate.py`
- Create: `tests/test_creation_migrate.py`
- Modify: `obsidian_connector/__init__.py`

**Interfaces:**
- Produces:
  - `plan_migration(vault) -> list[dict]` — for each existing `projects/{slug}.md` (or `projects/{slug}/index.md`), compute the move to `Projects/{ProjectName}/Repos/{slug}.md` (ProjectName via the repo's `group` → `group_display`), plus the to-be-created `Projects/{ProjectName}/{Project One-Pager.md, Project Dashboard.md, Backlog.md}` (scaffolds with `service:` fences for prose). Pure; returns the plan (old_path, new_path, action).
  - `migrate(vault, *, now_iso, dry_run=True) -> dict` — when not dry-run: `atomic_write` each new repo-view note (carrying over the old note's body inside the repo-status fence; prose preserved), scaffold the per-project notes if absent, and write `Projects/_migration-map.md` (the reversible mapping). It does NOT delete the flat notes (leaves them; a later opt-in `--prune` can remove once verified). Returns `{planned, written, map_path, dry_run}`.
  - `undo_migration(vault, *, dry_run=True) -> dict` — reads `_migration-map.md` and reverses (removes the created `Projects/{...}` tree it created; never touches notes it didn't create). 
- All vault writes via `atomic_write`; fence-preserving; never clobber user prose.

- [ ] **Step 1: `plan_migration` (pure) + tests** — a temp vault with `projects/mcmc-erp.md` (group `mcmc`) + `projects/site.md` (standalone) yields a plan moving them under `Projects/MCMC/Repos/mcmc-erp.md` and `Projects/site/Repos/site.md` + scaffolds. Full code.
- [ ] **Step 2: `migrate` (dry-run + write) + `undo` + tests** — dry-run writes nothing; `--allow-write` creates the tree + map, preserves a hand-written `## Notes` section from the old note, is idempotent (second run = no-op/no dupes), and `undo` reverses cleanly. Assert the flat notes are untouched. 
- [ ] **Step 3: Run tests**, expect PASS. **Step 4: Export + commit** (`feat(creation): reversible flat→Projects/{Project}/Repos migration`).

---

## Task 5: `creation_dashboards.py` — fenced markdown generators (the approved layouts)

**Files:**
- Create: `obsidian_connector/creation_dashboards.py`
- Create: `tests/test_creation_dashboards.py`
- Modify: `obsidian_connector/__init__.py`

**Interfaces:** Consumes Tasks 1-3 + `creation_backlog`/`creation_status` (read). Produces one generator per file, each `generate_*(vault, *, now_iso, github_root, dry_run=False, ...) -> dict` returning `{path, dry_run}` and writing via `atomic_write` (fenced where noted in "Approved layouts"):
- `generate_global_dashboard` → `Dashboard.md` (hybrid: Do-next block + projects table + rollups). **Reuses `next_actions` for the Do-next block and `repo_status`/`list_projects` for the table.**
- `generate_projects_index` → `Projects.md`.
- `generate_next_actions` → `Next Actions.md`.
- `generate_stale_context` → `Stale Context.md` (from `freshness_audit`).
- `generate_pending_decisions` → `Pending Decisions.md` (backlog items with `needs_decision`).
- `generate_active_sessions` → `Active Sessions.md` (active marker + recent `sessions/*.md`).
- `generate_project_dashboard(vault, project, ...)` → `Projects/{Project}/Project Dashboard.md`.
- `generate_project_one_pager(vault, project, ...)` → scaffold `Project One-Pager.md` (prose fences; only if absent — never overwrite prose).
- `generate_repo_view(vault, project, repo, ...)` → `Projects/{Project}/Repos/{repo}.md` (repo-status fence; user notes preserved).
- `refresh_all(vault, *, now_iso, github_root, scope=None, dry_run=False, ...)` → orchestrator that regenerates the global set (+ per-project/-repo when scoped).

- [ ] **Step 1: A shared render helper module section** — small pure helpers: `_fm(meta: dict) -> str` (frontmatter block with `last_sync`), `_table(headers, rows) -> str`, `_fence(name, body, existing) -> str` (preserve prior fence content), `_badge`/`_state_label`. Full code + tests for `_table` and `_fence` (fence preservation idempotency).
- [ ] **Step 2: `generate_global_dashboard`** to the exact hybrid layout (Do-next from `next_actions(limit=5)` → projects table → rollups). Test against a temp vault (monkeypatched repo_status/next_actions/backlog) asserting the three sections in order, the table columns, and that re-running is byte-stable.
- [ ] **Step 3: `generate_project_dashboard` + `generate_repo_view` + `generate_project_one_pager`** to the approved drilldown layouts; test section order + repo-status fence preservation + that the one-pager scaffold never overwrites existing prose.
- [ ] **Step 4: `generate_projects_index`, `generate_next_actions`, `generate_stale_context`, `generate_pending_decisions`, `generate_active_sessions`** — each a focused generator + a render test.
- [ ] **Step 5: `refresh_all`** orchestrator + a test that dry-run writes nothing and `--allow-write` writes the expected file set. **Step 6: Export + commit** (`feat(creation): dashboard markdown generators (hybrid + drilldowns + next + rollups)`).

---

## Task 6: CLI verbs

**Files:**
- Modify: `obsidian_connector/cli.py` (extend the `creation` dispatch from the spine/backlog)
- Create: `tests/test_creation_dashboard_cli.py`

**Verbs** (reads take no write flag; generators/migrate are dry-run-by-default unless `--allow-write`; all support `--json`; clock at the edge; `log_action` only on real writes):
- `obsx creation dashboard [--project P | --repo R]` → human console + `--json`; with no flag prints the global console (reads; optionally `--refresh --allow-write` to also regenerate `Dashboard.md`).
- `obsx creation projects` → list Projects.
- `obsx creation project show <P>` → project drilldown (read).
- `obsx creation repo show <R> [--with-tests] [--with-build]` → repo status (read; tests/build only when flagged — they are slow).
- `obsx creation next [--project P] [--repo R] [--limit N]` → ranked recommendations (read).
- `obsx creation refresh [--project P | --repo R] [--allow-write]` → regenerate dashboards (dry-run default).
- `obsx creation migrate-projects [--allow-write] [--undo]` → run/reverse the migration (dry-run default).

- [ ] **Step 1: subparsers** for the seven verbs under the existing `creation` subparser. **Step 2: dispatch** mirroring the spine/backlog pattern (verify the real envelope shape via `creation status --json`; set `data`/`human`; `dry = args.dry_run or not args.allow_write` for writes). **Step 3: tests** (`tests/test_creation_dashboard_cli.py`): `creation projects --json` lists projects; `creation next --json` returns ranked items; `creation repo show <r> --json` returns a status; `creation refresh` is dry-run by default (writes nothing, no `log_action`) and `--allow-write` writes + logs; reuse the `--vault <path>` test helper from `test_creation_backlog_cli.py`. Monkeypatch the classifier/next runners so CLI tests stay offline. **Step 4: run, commit** (`feat(creation): obsx creation dashboard|projects|project|repo|next|refresh|migrate CLI`).

---

## Task 7: MCP parity + contract + integrity

**Files:**
- Modify: `obsidian_connector/mcp_server.py` (mirror the read verbs + refresh/migrate)
- Modify: `mcpb.json` (bump `tools_count` by the number of new tools)
- Modify: `TOOLS_CONTRACT.md`, `ARCHITECTURE.md`

- [ ] **Step 1: MCP tools** mirroring the existing `obsidian_creation_*` pattern (ToolAnnotations: reads `readOnlyHint=True, idempotentHint=True`; refresh/migrate `readOnlyHint=False`, `dry_run: bool = True`; lazy imports; `resolve_vault_path`; `now` for writes; json + error envelope): `obsidian_creation_dashboard`, `obsidian_creation_projects`, `obsidian_creation_project_show`, `obsidian_creation_repo_show`, `obsidian_creation_next`, `obsidian_creation_refresh`, `obsidian_creation_migrate_projects` (7 tools).
- [ ] **Step 2:** bump `mcpb.json` `tools_count` to the new actual count (current 123 + 7 = 130; set to whatever `integrity_check` reports as the actual `@mcp.tool` count). **Step 3:** add the new `creation_*` modules to `ARCHITECTURE.md`'s module table (integrity requires it). **Step 4:** document all CLI verbs + MCP mirrors in `TOOLS_CONTRACT.md` (format matching the spine/backlog sections).
- [ ] **Step 5: gates** — `python3 scripts/integrity_check.py` → 8/8; `python3 scripts/manifest_check.py` → PASS; reconcile any count/inventory the checks name (do not weaken them). **Step 6: commit** (`feat(creation): MCP parity for dashboard read verbs; tools_count; contract + ARCHITECTURE`).

---

## Task 8: docs reconcile + full-suite gate

**Files:** `docs/architecture/creation-dashboard.md` (add the new `creation_*` modules to `sources_of_truth`, mark Phase 4 read-layer shipped, note TUI/Phase 6 still pending), `docs/plans/2026-06-18-creation-vault-os.md` (Phase 4 status), `docs/plans/index.md` (register this plan).

- [ ] **Step 1:** reconcile the docs above (frontmatter `sources_of_truth` + a short "shipped in Phase 4 read layer vs deferred to Phase 6 TUI" note). **Step 2: full gate** — `python3 -m pytest tests/test_creation_*.py tests/test_hardening.py tests/test_build_system.py -q` all green; integrity 8/8; manifest PASS; `npx tsx tools/build.ts --target claude-code` builds clean (env: `npm install --prefix tools` first). **Step 3: commit** (`docs(creation): reconcile dashboard docs with shipped Phase 4 read layer`).

---

## Self-Review (controller, before dispatch)

- **Spec coverage:** Project entity (T1) · git+PR+test/build classifier (T2) · explainable next-engine (T3) · reversible migration (T4) · hybrid + drilldown + rollup generators to the approved layouts (T5) · read CLI + refresh/migrate (T6) · MCP parity + gates (T7) · docs (T8). All of Mario's maximal picks (migrate-first, git+PRs+live-tests/build, full read layer, built to the companion-approved IA) are covered.
- **Reuse seam:** the classifier builds on `project_sync` git extraction (no duplication); the dashboards read the backlog/freshness spine read-only; `project_sync` stays spine-unaware.
- **Safety:** reads are side-effect-free; generators + migration dry-run-by-default; migration reversible + non-destructive (leaves flat notes, writes a map); `gh`/test/build probes never raise; freshness completion gate still bars unevidenced `done`.
- **Type consistency:** `Project`, `RepoStatus`, and the `Recommendation` dict shape are defined once (T1/T2/T3) and consumed by the generators (T5) + CLI/MCP (T6/T7). The injectable `runner` keeps T2/T3 tests offline.
- **Placeholders:** logic cores (classify, score_item, plan_migration, fence/table helpers) carry full code + exhaustive tests; the rendering generators are specified by the exact approved layouts + per-generator render tests (mechanical assembly the implementer writes to the format). No "TBD".
