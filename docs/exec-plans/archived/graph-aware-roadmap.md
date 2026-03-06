---
title: "Exec Plan: Graph-Aware Obsidian Connector Roadmap"
status: draft
owner: "mariourquia"
created: "2026-03-05"
last_reviewed: "2026-03-05"
review_cycle_days: 30
sources_of_truth:
  - "obsidian_connector/"
  - "TOOLS_CONTRACT.md"
  - "ARCHITECTURE.md"
---

# Graph-Aware Obsidian Connector Roadmap

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Read the entire plan before starting.

---

## 1) Repo Reconnaissance

### Package layout (main branch)

```
obsidian-connector/
  obsidian_connector/        # Core Python package (~1,600 LOC)
    __init__.py              # 21 public exports
    __main__.py              # Module execution -> cli.main()
    client.py                # Low-level CLI wrapper: run_obsidian(), search_notes(), read_note(), list_tasks(), log_to_daily()
    cli.py                   # argparse entry point: 8 subcommands + global flags (--json, --vault, --dry-run)
    mcp_server.py            # FastMCP server: 8 tools via stdio/HTTP
    workflows.py             # Composed workflows: log_decision(), create_research_note(), find_prior_work()
    cache.py                 # In-memory TTL cache (CLICache, thread-safe, mutation-aware)
    config.py                # Layered config: args > env > config.json > defaults (ConnectorConfig dataclass)
    audit.py                 # Append-only JSONL audit log (~/.obsidian-connector/logs/)
    doctor.py                # 4 health checks: binary, version, vault resolution, reachability
    envelope.py              # Canonical JSON response: success_envelope(), error_envelope()
    errors.py                # Typed exceptions: ObsidianNotFound, NotRunning, VaultNotFound, CommandTimeout, MalformedCLIOutput
    search.py                # Search result post-processing: truncate, dedupe, context extraction
  bin/
    obsx                     # CLI wrapper (no venv activation needed)
    obsx-mcp                 # MCP server wrapper
  scripts/
    smoke_test.py            # 8 core function tests
    cache_test.py            # 16 cache tests
    audit_test.py            # 3 audit tests
    workflow_test.py         # 3 workflow tests
    escaping_test.py         # 6 edge case tests
    mcp_launch_smoke.sh      # MCP server protocol check
  docs/                      # Harness Engineering knowledge base
  tools/docs_lint.py         # Frontmatter validator
  templates/                 # Reusable doc templates
  pyproject.toml             # hatchling build, mcp>=1.0.0, Python >=3.11
  config.json                # Default vault, folders, timeouts
  Makefile                   # docs-lint, test-*, ci-local, check, doctor
```

### Unmerged vnext branch (`feature/vnext-upgrade-wave`)

Adds ~2,400 lines across 24 files. Key additions:

| Addition | Status | Files |
|----------|--------|-------|
| Workflow OS tools (my-world, today, close-day, open-loops) | Code complete, unmerged | `workflows.py`, `cli.py`, `mcp_server.py` |
| Thinking tools (challenge-belief, emerge-ideas, connect-domains) | Code complete, unmerged | `workflows.py`, `cli.py`, `mcp_server.py` |
| MCP error envelopes + tool annotations | Code complete, unmerged | `mcp_server.py` |
| Doctor actionable steps | Code complete, unmerged | `doctor.py` |
| MCPB packaging (mcpb.json) | Artifact ready, unmerged | `mcpb.json` |
| Claude Code plugin scaffold | Artifact ready, unmerged | `.claude-plugin/plugin.json`, `.mcp.json` |
| Marketplace strategy + submission checklists | Docs ready, unmerged | `docs/distribution/` |
| Claude Desktop debugging guide | Doc ready, unmerged | `docs/reliability/` |
| Privacy policy | Doc ready, unmerged | `PRIVACY.md` |
| Test suites for new tools | Scripts ready, unmerged | `scripts/thinking_tools_test.py`, `scripts/workflow_os_test.py` |

The vnext branch reports all 5 epics complete with 16 MCP tools total.

### Architectural constraints discovered

1. **All vault access goes through `run_obsidian()`** which calls the Obsidian CLI
   via subprocess. There is no direct file access, no SQLite index, no graph API.
2. **The Obsidian CLI exposes**: `search:context`, `read`, `tasks`, `daily:append`,
   `create`, `files total`, `version`, `templates`. It does NOT expose: backlinks,
   outgoing links, tags, properties/frontmatter, graph queries, orphans, or
   file metadata.
3. **Graph-aware features require either**: (a) parsing markdown content to extract
   `[[wikilinks]]`, `#tags`, and YAML frontmatter after reading notes, or
   (b) direct vault file access (reading `.md` files from the vault directory).
4. **The cache layer is in-memory, per-process, disabled by default.** No persistent
   index exists. Every session starts cold.
5. **Write safety is CLI-only.** MCP tools execute mutations directly with no
   confirmation flow. No agent draft segregation exists.

### Extension points

| Extension point | Location | How to extend |
|----------------|----------|---------------|
| New CLI commands | `cli.py` → `build_parser()` | Add argparse subcommand |
| New MCP tools | `mcp_server.py` | Add `@mcp.tool()` function |
| New shared logic | `workflows.py` or new module | Python function, import in cli.py + mcp_server.py |
| New error types | `errors.py` | Subclass `ObsidianCLIError` |
| Cache mutation prefixes | `cache.py` → `_MUTATION_PREFIXES` | Add CLI arg prefix |
| Audit commands | `audit.py` → `log_action()` | Called from CLI dispatcher |
| Doctor checks | `doctor.py` → `run_doctor()` | Append check dict |
| Tool contracts | `TOOLS_CONTRACT.md` | Add command section |
| Test scripts | `scripts/` | Add `*_test.py` file |

---

## 2) Gap Analysis Matrix

### Legend

- **Exists (main)**: Implemented and on main branch
- **Exists (vnext)**: Implemented on `feature/vnext-upgrade-wave`, not merged
- **Partial**: Some code exists but missing key capabilities
- **Missing**: No implementation anywhere
- **Blocked**: Requires external capability or design decision

| Feature | Current Status | Existing Code Touchpoints | Main Gap | Notes / Risks |
|---------|---------------|--------------------------|----------|---------------|
| **Core search/read/tasks** | Exists (main) | `client.py`, `mcp_server.py`, `cli.py` | None | Stable foundation |
| **Log daily / decision / create note** | Exists (main) | `client.py`, `workflows.py`, `audit.py` | No confirmation flow in MCP | MCP writes execute without human approval |
| **find-prior-work** | Exists (main) | `workflows.py` | No link-awareness; reads N notes sequentially | Latency scales linearly with top_n |
| **doctor** | Exists (main) | `doctor.py` | No actionable steps (vnext adds these) | -- |
| **Cache layer** | Exists (main) | `cache.py`, `config.py`, `client.py` | Per-process, no persistence | Cold start every session |
| **my-world snapshot** | Exists (vnext) | `workflows.py` | Searches for daily notes by date string (slow, N subprocess calls); no context files, no backlinks | Core ritual but O(N) for lookback |
| **today brief** | Exists (vnext) | `workflows.py` | Reads daily note but doesn't follow `[[links]]` in it | Misses context the note points to |
| **close-day reflection** | Exists (vnext) | `workflows.py` | Static prompts, doesn't surface vault connections or extract structured items | Should scan note content for patterns |
| **open-loops** | Exists (vnext) | `workflows.py` | Convention-based (`OL:` prefix, `#openloop` tag); 2 search calls | Relies on user convention |
| **challenge-belief** | Exists (vnext) | `workflows.py` | Uses regex negation patterns, not semantic analysis; no graph traversal | Classification is crude |
| **emerge-ideas** | Exists (vnext) | `workflows.py` | Clusters by folder path, not by link relationships or tags | Folder != conceptual cluster |
| **connect-domains** | Exists (vnext) | `workflows.py` | Text search intersection, not link graph analysis | Misses notes linked through intermediaries |
| **Error envelopes in MCP** | Exists (vnext) | `mcp_server.py` | -- | Typed error mapping |
| **Tool annotations** | Exists (vnext) | `mcp_server.py` | -- | readOnlyHint, destructiveHint |
| **MCPB packaging** | Exists (vnext) | `mcpb.json`, `.mcp.json` | Not validated against real MCPB CLI | ASSUMPTION: mcpb schema is correct |
| **Plugin scaffold** | Exists (vnext) | `.claude-plugin/plugin.json`, `marketplace.json` | Not validated against real plugin install flow | ASSUMPTION: plugin.json schema correct |
| **Marketplace strategy** | Exists (vnext) | `docs/distribution/MARKETPLACE_STRATEGY.md` | Research-only, no submission done | -- |
| **Graph module (backlinks, links, tags)** | Missing | -- | No vault graph awareness anywhere | CRITICAL GAP. Must parse markdown or read vault files |
| **ghost (voice profile)** | Missing | -- | Requires deriving writing style from vault corpus | Complex NLP / prompt engineering |
| **drift (intentions vs behavior)** | Missing | -- | Requires temporal analysis across 30-60 days of notes | Needs graph module + date-indexed scanning |
| **ideas (deep scan)** | Missing | -- | Requires orphans, dead ends, unresolved links, cross-domain tags | Needs graph module |
| **trace (idea evolution)** | Missing | -- | Requires finding first appearance + temporal phases | Needs date-indexed content scanning |
| **graduate (promote ideas)** | Missing | -- | Write flow with human curation; must not auto-write | Safety-critical; needs confirmation UX |
| **Inline delegation** | Missing | -- | Agent detects structured commands from notes | Privacy + safety boundaries needed |
| **Team/shared vault** | Missing | -- | Multi-user access, privacy guardrails | Design-only for now |
| **Persistent index** | Missing | -- | Every session starts cold; no precomputed graph | Performance-critical for graph features |
| **Staged retrieval** | Missing | -- | All workflows read N notes in serial subprocess calls | Latency proportional to N |
| **Note fingerprinting** | Missing | -- | No change detection; cache invalidates everything | Needed for incremental scans |
| **Agent draft segregation** | Missing | -- | No `Inbox/Agent Drafts/` or similar | Safety principle: agents read, humans write |

---

## 3) North Star

"Better output" in this system means Claude's responses are shaped by the
**structure of your thinking**, not just the content of individual notes.

Today, the system can search for keywords and read note bodies. The agent
sees your vault as a flat search index. It cannot tell you what a note
links to, what links back to it, which ideas are orphaned, which beliefs
have evolved, or which intentions have drifted from behavior.

The north star is: **Claude reads your vault the way you read your vault**
-- following links, noticing patterns across time, surfacing contradictions,
and respecting the boundary between agent-assisted thinking and
human-authored writing.

Concretely, "better output" means:
- Responses that use relationships between notes, not just content within them
- Reflection rituals grounded in actual vault state (tasks, links, temporal patterns)
- Thinking tools that surface what you haven't noticed: drift, orphans, contradictions, emergent connections
- Safe-by-default operation where agents suggest and humans decide what gets written
- Acceptable latency despite richer context, through caching, precomputation, and staged retrieval

---

## 4) Ranked Roadmap

### Epic 0: Merge vnext and stabilize

**Why it matters.**
There are ~2,400 lines of implemented work on `feature/vnext-upgrade-wave` that
add 8 new tools, error envelopes, tool annotations, distribution artifacts, and
documentation. This work is prerequisite to everything else. Building on top of
an unmerged branch creates integration risk.

**User story.**
As a developer, I need a stable main branch with all 16 tools so I can build
graph-aware features on top of a solid foundation.

**Implementation scope.**
- Review and merge `feature/vnext-upgrade-wave` into `main`
- Run full verification: `make check`, all test scripts, `obsx doctor`
- Resolve any merge conflicts
- Verify MCP server starts and lists 16 tools
- Update `TOOLS_CONTRACT.md` if vnext docs diverge from main

**Acceptance tests.**
```bash
git checkout main
make check
python3 scripts/smoke_test.py
python3 scripts/cache_test.py
python3 scripts/workflow_os_test.py
python3 scripts/thinking_tools_test.py
bash scripts/mcp_launch_smoke.sh
./bin/obsx doctor
./bin/obsx --json my-world
./bin/obsx --json challenge "test belief"
```

**Risks & mitigations.**
- Risk: vnext tests may not pass against live Obsidian.
  Mitigation: run smoke tests with Obsidian open; fix any IPC issues first.
- Risk: merge conflicts in `cli.py`, `workflows.py`, `mcp_server.py`.
  Mitigation: vnext was branched from main HEAD; conflicts should be minimal.

**Effort:** S

**Dependencies:** None.

---

### Epic 1: Graph Module -- vault structure extraction

**Why it matters.**
This is the single highest-leverage piece of infrastructure in the roadmap.
Every thinking tool, every ritual, every "use the vault as a graph" feature
depends on the ability to extract `[[wikilinks]]`, `#tags`, YAML frontmatter
properties, and compute derived structures (backlinks, orphans, dead ends,
neighborhoods). Without this, the system treats the vault as a search engine.
With it, every existing tool becomes graph-aware.

The transcript explicitly states: "The core value claim is not 'read lots of
notes.' The core value claim is 'read relationships between notes.'"

**User story.**
When I ask Claude to analyze a topic in my vault, it should tell me not just
which notes mention it, but which notes link to those notes, what tags they
share, which are orphaned, and how they connect through the graph -- even if
no single note contains all the terms I searched for.

**Implementation scope.**

Create new module: `obsidian_connector/graph.py`

Core functions:
```python
def extract_links(content: str) -> list[str]
    # Parse [[wikilinks]] and [[wikilink|alias]] from markdown

def extract_tags(content: str) -> list[str]
    # Parse #tags and nested #tags/subtag

def extract_frontmatter(content: str) -> dict
    # Parse YAML frontmatter between --- fences

def build_note_index(vault: str | None = None) -> NoteIndex
    # Read all notes via search/read, extract links/tags/frontmatter
    # Return NoteIndex with forward links, backlinks, tags, properties

class NoteIndex:
    notes: dict[str, NoteEntry]        # path -> metadata
    backlinks: dict[str, set[str]]     # path -> set of paths linking TO it
    forward_links: dict[str, set[str]] # path -> set of paths it links TO
    tags: dict[str, set[str]]          # tag -> set of paths
    orphans: set[str]                  # notes with no inbound or outbound links
    dead_ends: set[str]               # notes with inbound but no outbound links
    unresolved: dict[str, set[str]]   # broken [[links]] -> set of source paths

    def neighborhood(self, path: str, depth: int = 1) -> set[str]
    def shortest_path(self, source: str, target: str) -> list[str] | None
    def notes_by_tag(self, tag: str) -> set[str]
    def notes_by_property(self, key: str, value: str | None = None) -> set[str]
```

**Strategy for vault traversal (two approaches, recommend Approach B):**

- **Approach A: CLI-only.** Use `run_obsidian(["files", "total"])` to get count,
  then search for common patterns to discover file paths, then `read_note()` each.
  Limitation: no `list files` command in the CLI; discovery is heuristic.

- **Approach B: Direct vault file access.** Read `.md` files directly from the
  vault directory on disk. The vault path can be resolved from Obsidian's
  config at `~/Library/Application Support/obsidian/obsidian.json` (macOS).
  This is faster (no subprocess per file), more complete (reads all files),
  and enables fingerprinting (stat mtime for change detection).

  **Recommendation:** Use Approach B for index building (bulk read), keep
  Approach A (CLI) for individual operations (search, read, write). The CLI
  remains the safe interface for mutations; direct file access is read-only
  for indexing. Add a `vault_path` resolution function to `config.py`.

Files to create/modify:
- Create: `obsidian_connector/graph.py` (~300 LOC)
- Modify: `obsidian_connector/config.py` -- add `vault_path` resolution
- Modify: `obsidian_connector/__init__.py` -- export graph functions
- Create: `scripts/graph_test.py` -- unit + integration tests
- Modify: `TOOLS_CONTRACT.md` -- document graph module

**Acceptance tests.**
```bash
# Unit tests for link/tag/frontmatter extraction
python3 scripts/graph_test.py

# Integration: build index from live vault
python3 -c "
from obsidian_connector.graph import build_note_index
idx = build_note_index()
print(f'Notes: {len(idx.notes)}')
print(f'Orphans: {len(idx.orphans)}')
print(f'Tags: {len(idx.tags)}')
print(f'Unresolved links: {len(idx.unresolved)}')
"
```

**Risks & mitigations.**
- Risk: Direct file access bypasses CLI safety layer.
  Mitigation: Graph module is strictly read-only. No file writes. Audit log
  not needed for reads.
- Risk: Large vaults (10k+ notes) may be slow to index.
  Mitigation: Use `os.scandir()` + mmap for large files. Add progress
  callback. Cache the index with mtime fingerprinting (see Epic 2).
- Risk: Vault path resolution differs across OS.
  Mitigation: Start with macOS (`~/Library/Application Support/obsidian/`).
  Document Linux/Windows paths. Make configurable via `OBSIDIAN_VAULT_PATH` env var.
- Risk: Wikilink resolution is complex (aliases, case insensitivity, nested paths).
  Mitigation: Start with exact-match resolution. Add fuzzy matching later.

**Effort:** M

**Dependencies:** Epic 0 (merge vnext).

---

### Epic 2: Persistent Index with change detection

**Why it matters.**
The graph module (Epic 1) builds an in-memory index by reading every note.
For a 1,000-note vault, this takes seconds. For a 10,000-note vault, minutes.
Users should not pay this cost on every tool invocation. A persistent index
with mtime-based change detection enables sub-second graph queries after the
first build.

The transcript explicitly requires: "staged retrieval, bounded scans, caching,
graph/index precomputation, memoized neighborhood expansion, note
fingerprinting/change detection."

**User story.**
Graph-aware tools respond in under 2 seconds even on large vaults because
the index is precomputed and only updated incrementally when notes change.

**Implementation scope.**

Create new module: `obsidian_connector/index_store.py`

```python
class IndexStore:
    """SQLite-backed persistent note index with change detection."""

    def __init__(self, db_path: Path)
    def build_full(self, vault_path: Path) -> NoteIndex
    def update_incremental(self, vault_path: Path) -> NoteIndex
    def get_index(self) -> NoteIndex
    def fingerprint(self, path: Path) -> str  # mtime + size hash

    # Internal schema:
    # notes(path TEXT PK, mtime REAL, size INT, content_hash TEXT,
    #       links TEXT, tags TEXT, frontmatter TEXT)
    # links(source TEXT, target TEXT, resolved INT)
    # tags(path TEXT, tag TEXT)
```

Files to create/modify:
- Create: `obsidian_connector/index_store.py` (~200 LOC)
- Modify: `obsidian_connector/graph.py` -- integrate IndexStore
- Modify: `obsidian_connector/config.py` -- add `index_db_path` config
  (default: `~/.obsidian-connector/index.sqlite`)
- Create: `scripts/index_test.py`
- Add Makefile target: `make rebuild-index`

**Acceptance tests.**
```bash
# Full build
python3 -c "
from obsidian_connector.index_store import IndexStore
from obsidian_connector.config import load_config
import time
store = IndexStore()
t0 = time.time(); idx = store.build_full(); t1 = time.time()
print(f'Full build: {t1-t0:.2f}s, {len(idx.notes)} notes')
t0 = time.time(); idx = store.update_incremental(); t1 = time.time()
print(f'Incremental (no changes): {t1-t0:.3f}s')
"

# Should be <0.1s for incremental with no changes
python3 scripts/index_test.py
```

**Risks & mitigations.**
- Risk: SQLite concurrent access if multiple MCP sessions run.
  Mitigation: Use WAL mode. Index is read-heavy; writes only during rebuild.
- Risk: Index gets stale if user edits notes outside Obsidian.
  Mitigation: mtime-based fingerprinting catches all file system changes.
  Add `obsidian_rebuild_index` MCP tool for manual refresh.

**Effort:** M

**Dependencies:** Epic 1 (graph module).

---

### Epic 3: Graph-aware upgrades to existing tools

**Why it matters.**
Once the graph module and persistent index exist, existing tools should use
them. This is where the product thesis proves itself: the same `search` and
`find-prior-work` queries return richer results because they include link
context, backlinks, and neighborhood information.

**User story.**
When I search for "CMBS spreads", results include not just notes containing
those words, but also notes that link to those notes, notes that share the
same tags, and orphaned notes in the same neighborhood -- all without
additional queries.

**Implementation scope.**

Modify existing functions in `workflows.py` and add new MCP tools:

1. **Enriched search results** -- Modify `enrich_search_results()` in `search.py`
   to optionally include backlinks and tags for each result.

2. **Note neighborhood tool** -- New MCP tool `obsidian_neighborhood`:
   Given a note path, return its backlinks, forward links, shared tags,
   and 1-hop neighbors. Backed by `graph.py:NoteIndex.neighborhood()`.

3. **Vault structure tool** -- New MCP tool `obsidian_vault_structure`:
   Return orphans, dead ends, unresolved links, tag cloud, and top
   connected notes. Useful for the agent to understand vault topology
   before deep queries.

4. **Backlinks tool** -- New MCP tool `obsidian_backlinks`:
   Given a note, return all notes that link to it with context.

5. **Upgrade find-prior-work** -- Modify `find_prior_work()` to include
   backlink count and shared tags in each result.

6. **Upgrade today/my-world** -- Follow `[[links]]` in today's daily note
   to read linked context. Instead of just returning the daily note body,
   also return summaries of linked notes.

Files to modify:
- `obsidian_connector/search.py` -- add graph-enrichment path
- `obsidian_connector/workflows.py` -- upgrade `find_prior_work()`, `today_brief()`, `my_world_snapshot()`
- `obsidian_connector/mcp_server.py` -- add 3 new tools
- `obsidian_connector/cli.py` -- add 3 new CLI commands
- `TOOLS_CONTRACT.md` -- document new tools

**Acceptance tests.**
```bash
./bin/obsx neighborhood "Project Alpha" --json
# Returns: {backlinks: [...], forward_links: [...], tags: [...], neighbors: [...]}

./bin/obsx vault-structure --json
# Returns: {orphans: [...], dead_ends: [...], unresolved: [...], tag_cloud: {...}, top_connected: [...]}

./bin/obsx backlinks "Project Alpha" --json
# Returns: [{file, context, line}]

./bin/obsx find-prior-work "CMBS" --json
# Each result now includes backlink_count and shared_tags

./bin/obsx today --json
# Now includes linked_context: [{file, heading, excerpt}] for notes linked from daily note
```

**Risks & mitigations.**
- Risk: Latency increase from graph lookups.
  Mitigation: Graph lookups are O(1) dict lookups on the NoteIndex. The index
  build is the expensive part (handled by Epic 2 persistence).
- Risk: Backward compatibility -- existing tool output changes.
  Mitigation: New fields are additive. Existing fields unchanged. JSON
  envelope structure preserved.

**Effort:** M

**Dependencies:** Epic 1, Epic 2.

---

### Epic 4: Deep thinking tools (ghost, drift, trace, ideas)

**Why it matters.**
These are the tools that differentiate this system from "yet another note
reader." They surface patterns the user hasn't noticed: how their thinking
has evolved, what they're avoiding, what ideas are latent in the graph,
and what their authentic voice sounds like.

The transcript calls these out explicitly and they require the graph module
(Epic 1) and persistent index (Epic 2) to work properly.

**User story.**
I ask Claude to show me how my thinking about "portfolio construction" has
evolved over the past 6 months, and it returns a timeline of first mentions,
phase transitions, and current state -- grounded in actual vault notes with
citations.

**Implementation scope.**

Add functions to `workflows.py` (or create `obsidian_connector/thinking.py`
if workflows.py exceeds ~500 LOC after vnext merge):

1. **`ghost_voice_profile(vault, sample_notes=20) -> dict`**
   - Read N recent notes authored by the user
   - Extract: sentence length distribution, vocabulary patterns, common
     phrases, tone markers, structural preferences (bullets vs prose,
     heading depth)
   - Return a voice profile dict that can be included in system prompts
   - CLI: `obsx ghost "question to answer in my voice"`
   - MCP: `obsidian_ghost`

2. **`drift_analysis(vault, lookback_days=60) -> dict`**
   - Read daily notes over the lookback period
   - Extract stated intentions ("I will...", "Plan to...", "Goal:...")
   - Cross-reference with tasks completed and topics actually written about
   - Surface: intentions not acted on, topics getting attention without
     stated intent, shifts in focus
   - CLI: `obsx drift --days 60`
   - MCP: `obsidian_drift`

3. **`trace_idea(topic, vault) -> dict`**
   - Search for the topic across all notes
   - Sort results by note creation date (from frontmatter `created` or file mtime)
   - Group into temporal phases (first mention, growth, plateau, revival)
   - Return timeline with citations
   - CLI: `obsx trace "portfolio construction"`
   - MCP: `obsidian_trace`

4. **`deep_ideas(vault, max_ideas=10) -> dict`**
   - Use NoteIndex to find: orphans, dead ends, notes with high backlink
     count but low outgoing links (convergence points), unresolved links,
     tags that appear in only 1-2 notes
   - Cross-reference with tag co-occurrence patterns
   - Return: actionable idea candidates with source citations
   - CLI: `obsx ideas`
   - MCP: `obsidian_ideas`

Files to create/modify:
- Create (if needed): `obsidian_connector/thinking.py` (~400 LOC)
- Modify: `obsidian_connector/mcp_server.py` -- 4 new tools
- Modify: `obsidian_connector/cli.py` -- 4 new subcommands
- Modify: `obsidian_connector/__init__.py` -- export new functions
- Create: `scripts/thinking_deep_test.py`
- Modify: `TOOLS_CONTRACT.md`

**Acceptance tests.**
```bash
./bin/obsx ghost "What should I prioritize this quarter?" --json
# Returns: {voice_profile: {...}, response_guidance: "..."}

./bin/obsx drift --days 60 --json
# Returns: {stated_intentions: [...], actual_focus: [...], gaps: [...], surprises: [...]}

./bin/obsx trace "CMBS" --json
# Returns: {topic, first_mention: {date, file}, phases: [...], timeline: [...]}

./bin/obsx ideas --json
# Returns: {ideas: [{title, source_notes, rationale, type}]}

python3 scripts/thinking_deep_test.py
```

**Risks & mitigations.**
- Risk: ghost voice profile may produce poor results on small vaults.
  Mitigation: Require minimum sample size; return confidence score.
  Document that this works best with 50+ authored notes.
- Risk: drift analysis depends on consistent daily note authoring.
  Mitigation: Graceful degradation -- report coverage gaps, don't fail.
- Risk: Latency for trace across large vaults.
  Mitigation: Use persistent index for date-sorted lookups. Bound scan
  to notes matching the topic (search first, then sort).
- Risk: Privacy -- voice profile reveals writing patterns.
  Mitigation: Voice profile is ephemeral (computed per request, not stored).
  Document in PRIVACY.md.

**Effort:** L

**Dependencies:** Epic 1, Epic 2, Epic 3 (for graph-aware search).

---

### Epic 5: Graduate + agent draft segregation

**Why it matters.**
This is the safety boundary that enforces "agents read, humans write."
The `/graduate` flow lets agents identify daily-note ideas worth promoting
to standalone notes, but the human decides what gets written. Agent-generated
content goes to a segregated location (`Inbox/Agent Drafts/`) so it never
contaminates the human-authored knowledge base.

The transcript is explicit: "agents read by default, humans own durable
writing by default." And: "suggestion-only flows are preferred unless a
human explicitly approves writes."

**User story.**
At the end of a work session, I ask Claude to review my daily notes and
suggest which ideas should become standalone notes. Claude returns a ranked
list with draft titles and outlines. I choose which to graduate, and only
then does the system create the note -- in `Inbox/Agent Drafts/` with clear
provenance markers.

**Implementation scope.**

1. **`graduate_candidates(vault, lookback_days=7) -> list[dict]`**
   - Scan recent daily notes for idea-like patterns:
     - Headings with substantive content beneath them
     - Paragraphs with 3+ `[[wikilinks]]`
     - Lines tagged `#idea` or `#insight`
     - Sections with "TODO: flesh out" or similar markers
   - For each candidate: check if a standalone note already exists
     (via NoteIndex link resolution)
   - Return ranked candidates with: title, source note, excerpt, existing
     note (if any), tags, suggested template

2. **`graduate_execute(title, content, vault, target_folder="Inbox/Agent Drafts") -> str`**
   - Create note in segregated folder (configurable via `config.json`
     `default_folders.agent_drafts`)
   - Add provenance frontmatter: `source: agent`, `created_from: <daily note>`,
     `status: draft`, `created: <timestamp>`
   - Require explicit `--confirm` flag (CLI) or confirmation parameter (MCP)
   - Log to audit trail with full content hash

3. **Config extension:**
   - Add `default_folders.agent_drafts` to `config.json` (default: `Inbox/Agent Drafts`)

Files to create/modify:
- Modify: `obsidian_connector/workflows.py` -- add graduate functions
- Modify: `obsidian_connector/cli.py` -- add `graduate` subcommand (list + execute)
- Modify: `obsidian_connector/mcp_server.py` -- add `obsidian_graduate_candidates`
  and `obsidian_graduate_execute` tools
- Modify: `obsidian_connector/config.py` -- add agent_drafts folder config
- Modify: `TOOLS_CONTRACT.md`
- Create: `scripts/graduate_test.py`

**Acceptance tests.**
```bash
# List candidates (read-only, safe)
./bin/obsx graduate list --json
# Returns: [{title, source, excerpt, existing_note, tags, template}]

# Execute with confirmation (mutating)
./bin/obsx graduate execute --title "CMBS Analysis Framework" --confirm
# Creates: Inbox/Agent Drafts/CMBS Analysis Framework.md
# Frontmatter includes source: agent, status: draft

# Dry-run
./bin/obsx graduate execute --title "Test" --dry-run
# Returns dry-run envelope, no file created

# MCP: candidates tool is read-only
# MCP: execute tool requires confirm=true parameter
```

**Risks & mitigations.**
- Risk: Agent creates notes without human approval.
  Mitigation: `graduate_execute` requires explicit `confirm=True`.
  Default is suggestion-only. MCP tool docstring states this clearly.
- Risk: Agent drafts accumulate without review.
  Mitigation: Doctor check can report unreviewed drafts. Not blocking.
- Risk: Agent draft folder doesn't exist in vault.
  Mitigation: Create it on first use (mkdir -p equivalent). Document in
  README.

**Effort:** M

**Dependencies:** Epic 1 (for link analysis in candidate detection).

---

### Epic 6: Performance hardening

**Why it matters.**
Epics 1-5 add graph traversal, index building, and multi-note reading.
Without explicit performance work, latency will degrade as the vault grows
and tools chain more subprocess calls.

The transcript states: "richer context increases latency because the system
reads more." The roadmap must include concrete mitigation.

**User story.**
Graph-aware tools respond within 2 seconds on a 5,000-note vault. Ritual
tools (today, close-day) respond within 3 seconds. Deep thinking tools
(drift, trace) respond within 5 seconds.

**Implementation scope.**

1. **Batch read** -- Add `batch_read_notes(paths, vault) -> dict[str, str]` to
   `client.py` that reads multiple notes in parallel using `concurrent.futures`
   or sequential subprocess calls with shared cache warm-up. Used by workflows
   that read N notes.

2. **Bounded scans** -- All workflows that iterate over search results must
   accept and enforce `max_notes` parameter. Default bounds:
   - `find_prior_work`: 5 (already exists)
   - `challenge_belief`: 10 (already exists)
   - `my_world_snapshot`: 7 daily notes (currently 14, reduce default)
   - `drift_analysis`: 30 notes (new, needs bound)

3. **Index precomputation** -- Add MCP tool `obsidian_rebuild_index` that
   triggers a full index rebuild. Can be called at session start.
   Add Makefile target `make rebuild-index`.

4. **Rolling summaries** -- For `my_world_snapshot` and `today_brief`, cache
   a rolling summary of the past N daily notes rather than re-reading them
   each time. Store in the SQLite index as a precomputed field.

5. **Lazy graph loading** -- `NoteIndex` should be loaded from SQLite on
   first access, not rebuilt. If stale (any note mtime > last build time),
   trigger incremental update only for changed files.

Files to modify:
- `obsidian_connector/client.py` -- add `batch_read_notes()`
- `obsidian_connector/graph.py` -- lazy loading
- `obsidian_connector/index_store.py` -- rolling summaries
- `obsidian_connector/workflows.py` -- enforce bounds
- `obsidian_connector/mcp_server.py` -- add `obsidian_rebuild_index`
- Create: `scripts/perf_test.py` -- latency benchmarks

**Acceptance tests.**
```bash
# Benchmark: index rebuild
python3 -c "
import time
from obsidian_connector.index_store import IndexStore
s = IndexStore()
t0=time.time(); s.build_full(); t1=time.time()
print(f'Full: {t1-t0:.2f}s')
t0=time.time(); s.update_incremental(); t1=time.time()
print(f'Incr: {t1-t0:.3f}s')
"

# Benchmark: today_brief latency
time ./bin/obsx today --json > /dev/null
# Target: <3s on 1000-note vault

python3 scripts/perf_test.py
```

**Risks & mitigations.**
- Risk: Parallel subprocess calls may overwhelm Obsidian IPC.
  Mitigation: Use semaphore (max 4 concurrent reads). Fall back to
  serial if errors detected.
- Risk: Rolling summaries become stale.
  Mitigation: Invalidate on note mtime change (same as index).

**Effort:** M

**Dependencies:** Epic 1, Epic 2.

---

### Epic 7: Inline delegation + context load

**Why it matters.**
This enables two-way interaction patterns: the user writes structured
commands in their notes (`@agent: summarize this section`), and the
agent can detect and respond to them. Combined with `context load full`,
this creates a seamless workflow where the vault is both the agent's
knowledge base and its instruction source.

**User story.**
I write `@claude: summarize the linked notes` in my daily note. When I
next invoke Claude with the vault connected, it detects this instruction
and offers to execute it -- with my approval.

**Implementation scope.**

1. **`detect_delegations(vault, lookback_days=1) -> list[dict]`**
   - Scan recent notes for delegation patterns:
     - `@agent:` or `@claude:` prefixed lines
     - Structured blocks: `> [!agent] instruction text`
   - Return: list of `{file, line, instruction, status}`
   - Status: `pending`, `done` (if followed by `[done]` marker)

2. **`context_load_full(vault, context_files=None) -> dict`**
   - Read configured context files (life context, work context, current state)
   - Read today's daily note + follow its `[[links]]` one level deep
   - Read recent daily notes (past 7 days) for continuity
   - Aggregate open tasks and open loops
   - Return structured context bundle
   - Context file paths configurable in `config.json`:
     ```json
     { "context_files": ["Life/Context.md", "Work/Current State.md"] }
     ```

3. **Safety boundaries for delegation:**
   - Delegation instructions are READ-ONLY by default
   - Agent can acknowledge seeing them but must not auto-execute
   - Any execution requires the same confirm/dry-run flow as graduate

Files to create/modify:
- Modify: `obsidian_connector/workflows.py` -- add functions
- Modify: `obsidian_connector/config.py` -- add `context_files` config
- Modify: `obsidian_connector/mcp_server.py` -- 2 new tools
- Modify: `obsidian_connector/cli.py` -- 2 new subcommands
- Modify: `TOOLS_CONTRACT.md`
- Create: `scripts/delegation_test.py`

**Acceptance tests.**
```bash
./bin/obsx delegations --json
# Returns: [{file, line, instruction, status}]

./bin/obsx context-load --json
# Returns: {context_files: [...], daily_note: ..., linked_notes: [...], tasks: [...], loops: [...]}
```

**Risks & mitigations.**
- Risk: Agent auto-executes delegation instructions.
  Mitigation: Detection is read-only. Execution requires separate
  confirmed action. Document this boundary in TOOLS_CONTRACT.md.
- Risk: Context load reads too many notes (unbounded).
  Mitigation: Bound link-following to depth 1. Bound daily note lookback
  to 7 days. Total note reads capped at 20.
- Risk: Privacy -- context files may contain sensitive personal data.
  Mitigation: Context files are user-configured. Document that these
  are sent to the LLM. Update PRIVACY.md.

**Effort:** M

**Dependencies:** Epic 1 (for link following), Epic 3 (for enriched reads).

---

### Epic 8: Distribution and marketplace readiness

**Why it matters.**
The product needs to reach users. The vnext branch already has distribution
artifacts (plugin.json, marketplace.json, mcpb.json) but they have not been
validated against real installation flows. This epic validates and polishes
the distribution path.

**User story.**
A new user discovers obsidian-connector in the Claude Code plugin directory,
installs it with one command, and has 20+ MCP tools available in Claude
Desktop within 5 minutes.

**Implementation scope.**

1. **Validate MCPB packaging** -- Install `mcpb` CLI, run `mcpb build`,
   verify the output is installable in Claude Desktop. Fix any issues.

2. **Validate plugin install** -- Create a test marketplace repo, run
   `/plugin marketplace add`, install the plugin, verify tools load.

3. **Add install hook** -- Create a `postinstall` script that:
   - Creates `.venv` and installs dependencies
   - Runs `obsx doctor` to verify connectivity
   - Prints setup instructions

4. **Submit to Anthropic directory** -- Follow the checklist in
   `docs/distribution/SUBMISSION_CHECKLIST.md`.

5. **README polish** -- Add badges, demo GIF, quick-start for each
   install method (pip, MCPB, plugin marketplace).

Files to modify:
- Modify: `mcpb.json` -- fix any validation issues
- Modify: `.claude-plugin/plugin.json` -- fix any validation issues
- Create: `scripts/postinstall.sh`
- Modify: `README.md` -- install methods, badges
- Modify: `docs/distribution/SUBMISSION_CHECKLIST.md` -- update status

**Acceptance tests.**
```bash
# MCPB build
mcpb build  # should produce valid package

# Plugin install (local test)
# In a separate directory:
# /plugin marketplace add file:///path/to/obsidian-connector
# /plugin install obsidian-connector

# Doctor after install
obsx doctor
# All 4 checks pass
```

**Risks & mitigations.**
- Risk: MCPB CLI may have undocumented requirements.
  Mitigation: MCPB research already done (vnext). Test with real CLI.
- Risk: Plugin install flow may have dependency issues (Python venv).
  Mitigation: postinstall script handles venv creation. Document
  Python 3.11+ requirement.
- ASSUMPTION: MCPB and plugin marketplace schemas are based on vnext
  research. Verify against current documentation before submitting.

**Effort:** M

**Dependencies:** Epic 0 (merge vnext), all feature epics for tool count.

---

### Epic 9: Team/shared vault pattern (design only)

**Why it matters.**
The transcript mentions team/org/shared vault patterns with privacy and
access guardrails. This is a design-only epic for now -- implementing
multi-user vault access requires significant architectural decisions
that should be documented before building.

**User story.**
A small team uses a shared Obsidian vault (via Obsidian Sync or git).
Each team member's Claude instance can read shared notes but personal
notes remain private. Agent writes go to a team-visible drafts folder.

**Implementation scope.**

Design document only. No code.

Create: `docs/design-docs/team-vault-pattern.md`

Topics to cover:
- Vault structure conventions (shared/ vs personal/ folders)
- Access control model (folder-based, tag-based, or frontmatter-based)
- Privacy boundaries for agent reads
- Agent draft location in shared context
- Conflict resolution for concurrent writes
- Integration with Obsidian Sync / git-based sync
- Impact on existing tools (vault parameter, config)

**Acceptance tests.**
```bash
make docs-lint
# docs/design-docs/team-vault-pattern.md passes frontmatter validation
```

**Effort:** S

**Dependencies:** None (design-only).

---

## 5) Milestone Plan

### M1: 1 week (must ship)

**What ships:**
- Epic 0: vnext merged to main (16 tools, error envelopes, distribution artifacts)
- Epic 1: Graph module -- `graph.py` with link/tag/frontmatter extraction + NoteIndex
- Epic 9: Team vault design doc (low effort, high signal)

**What is deferred:**
- Persistent index (Epic 2) -- graph module works in-memory first
- Graph-aware tool upgrades (Epic 3) -- tools work without graph initially
- Deep thinking tools (Epic 4) -- need graph module stable first

**Acceptable technical debt:**
- Graph module does in-memory full rebuild on each invocation (no persistence)
- NoteIndex uses direct vault file access without formal vault path resolution
  (hardcoded via `OBSIDIAN_VAULT_PATH` env var until config.py is updated)
- Wikilink resolution is exact-match only (no case-insensitive or alias matching)

**Verification:**
```bash
make check
python3 scripts/graph_test.py
./bin/obsx doctor
```

---

### M2: 3 weeks (polish + thinking tools)

**What ships:**
- Epic 2: Persistent index with SQLite + change detection
- Epic 3: Graph-aware upgrades (neighborhood, backlinks, vault-structure tools)
- Epic 4: Deep thinking tools (ghost, drift, trace, ideas)
- Epic 5: Graduate + agent draft segregation
- Epic 6: Performance hardening (batch read, bounds, lazy loading)

**What is deferred:**
- Context load full (Epic 7) -- works but not optimized
- Distribution validation (Epic 8) -- artifacts exist but not validated

**Acceptable technical debt:**
- Ghost voice profile uses basic heuristics (word frequency, sentence length),
  not fine-tuned NLP
- Drift analysis uses simple regex for intention extraction
- Rolling summaries not yet implemented (daily notes re-read each time)
- Parallel reads use sequential fallback if Obsidian IPC is stressed

**Verification:**
```bash
make check
python3 scripts/graph_test.py
python3 scripts/index_test.py
python3 scripts/thinking_deep_test.py
python3 scripts/graduate_test.py
python3 scripts/perf_test.py
./bin/obsx today --json
./bin/obsx drift --days 30 --json
./bin/obsx trace "test topic" --json
./bin/obsx ideas --json
./bin/obsx ghost "test question" --json
./bin/obsx graduate list --json
./bin/obsx neighborhood "test note" --json
./bin/obsx vault-structure --json
```

---

### M3: 6-8 weeks (distribution + advanced autonomy)

**What ships:**
- Epic 7: Inline delegation + context load full
- Epic 8: Distribution validation (MCPB, plugin marketplace, directory submission)
- Performance polish: rolling summaries, parallel reads, optimized bounds
- Full test suite: 10+ test scripts, >100 test cases
- Documentation: all tools in TOOLS_CONTRACT.md, all features in README

**What is deferred:**
- Team vault implementation (Epic 9 was design-only)
- Advanced ghost (fine-tuned style matching)
- Cross-vault operations
- Real-time file watching / push-based index updates

**Acceptable technical debt:**
- Delegation detection uses simple regex patterns (not a full parser)
- Context load depth fixed at 1 (no multi-hop following)
- Plugin marketplace submission may be pending Anthropic review

**Verification:**
```bash
make check
python3 scripts/delegation_test.py
mcpb build  # if mcpb CLI available
# Full end-to-end demo (see section 6)
```

---

## 6) Recommended First Demo

**Demo: "Vault X-Ray"**

Run `obsx vault-structure --json` on a real vault with 100+ notes.
Show the output: orphans, dead ends, unresolved links, tag cloud, top
connected notes.

Then run `obsx neighborhood "your most-linked note" --json` to show the
local graph around a single note.

**Why this demo:**
1. It proves the graph module works (Epic 1) -- the hardest new infrastructure.
2. It surfaces value immediately -- users see their vault structure for the
   first time from Claude's perspective.
3. It requires no writes, no configuration, no risk.
4. It is visually compelling: a list of orphans and dead ends is inherently
   interesting to any knowledge worker.
5. It validates the core thesis: "use Obsidian as a graph, not a flat file store."

**Demo script:**
```bash
# Prerequisites: Obsidian running, vault configured
./bin/obsx doctor
./bin/obsx vault-structure --json | python3 -m json.tool
./bin/obsx neighborhood "your-important-note" --json | python3 -m json.tool
./bin/obsx backlinks "your-important-note" --json | python3 -m json.tool
```

---

## 7) Spawn-Agents Plan

### Agent 1: Graph Infrastructure

**Mission:** Build the foundational graph module and persistent index that
all other features depend on.

**Roadmap epics owned:** Epic 1, Epic 2

**Exact files/modules to touch:**
- Create: `obsidian_connector/graph.py`
- Create: `obsidian_connector/index_store.py`
- Modify: `obsidian_connector/config.py`
- Modify: `obsidian_connector/__init__.py`
- Create: `scripts/graph_test.py`
- Create: `scripts/index_test.py`

**Acceptance tests:**
- `python3 scripts/graph_test.py` passes (link extraction, tag extraction,
  frontmatter parsing, NoteIndex construction, orphan/dead-end detection)
- `python3 scripts/index_test.py` passes (SQLite persistence, incremental
  update, fingerprint-based change detection)
- Index builds on a real vault without errors

**Constraints:**
- Do not modify `client.py` or `mcp_server.py` (those are Agent 2's domain)
- Graph module is strictly read-only -- no file writes
- Use stdlib only (no new dependencies beyond what's in pyproject.toml)
- Follow existing code patterns (type hints, docstrings matching existing style)
- Export new symbols from `__init__.py`

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md first, then ARCHITECTURE.md, then CLAUDE.md.

Your mission: Build the graph infrastructure (Epics 1 and 2) from the
roadmap at docs/exec-plans/active/graph-aware-roadmap.md.

TASK 1: Create obsidian_connector/graph.py
- Functions: extract_links(), extract_tags(), extract_frontmatter(), build_note_index()
- Class: NoteIndex with notes, backlinks, forward_links, tags, orphans, dead_ends, unresolved
- Methods: neighborhood(path, depth), shortest_path(source, target), notes_by_tag(), notes_by_property()
- For vault file access: resolve vault path from OBSIDIAN_VAULT_PATH env var or
  ~/Library/Application Support/obsidian/obsidian.json. Read .md files directly.
- Parse [[wikilinks]], [[wikilink|alias]], #tags, #nested/tags, YAML frontmatter.

TASK 2: Create obsidian_connector/index_store.py
- Class: IndexStore with SQLite backend at ~/.obsidian-connector/index.sqlite
- Methods: build_full(), update_incremental(), get_index(), fingerprint()
- Schema: notes(path, mtime, size, content_hash, links_json, tags_json, frontmatter_json)
- Use WAL mode for concurrent safety. mtime-based change detection.

TASK 3: Update config.py
- Add vault_path resolution (OBSIDIAN_VAULT_PATH env var, then parse obsidian.json)
- Add index_db_path config (default ~/.obsidian-connector/index.sqlite)

TASK 4: Update __init__.py with new exports.

TASK 5: Write scripts/graph_test.py and scripts/index_test.py.

CONSTRAINTS:
- Do NOT modify client.py, cli.py, mcp_server.py, or workflows.py.
- Read-only operations only. Never write to vault files.
- Use Python stdlib only. No new pip dependencies.
- Follow the coding style in existing modules (type hints, docstrings, error handling).
- Run python3 -m compileall obsidian_connector/ after each file change.
```

---

### Agent 2: Graph-Aware Tool Integration

**Mission:** Wire the graph module into existing and new MCP tools and
CLI commands so users can query vault structure.

**Roadmap epics owned:** Epic 3

**Exact files/modules to touch:**
- Modify: `obsidian_connector/mcp_server.py` -- add 3 new tools
- Modify: `obsidian_connector/cli.py` -- add 3 new subcommands
- Modify: `obsidian_connector/search.py` -- add graph-enrichment
- Modify: `obsidian_connector/workflows.py` -- upgrade find_prior_work, today_brief, my_world_snapshot
- Modify: `TOOLS_CONTRACT.md`

**Acceptance tests:**
- `./bin/obsx neighborhood "test-note" --json` returns backlinks, forward links, neighbors
- `./bin/obsx vault-structure --json` returns orphans, dead ends, tag cloud
- `./bin/obsx backlinks "test-note" --json` returns backlink list
- `./bin/obsx find-prior-work "topic" --json` includes backlink_count and shared_tags
- `./bin/obsx today --json` includes linked_context from daily note links

**Constraints:**
- Import from graph.py and index_store.py (Agent 1 builds these)
- Do not modify graph.py or index_store.py
- Preserve backward compatibility: existing JSON fields unchanged, new fields additive
- All new MCP tools must have ToolAnnotations (readOnlyHint, etc.)
- Follow the _error_envelope() pattern for error handling in mcp_server.py

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md, ARCHITECTURE.md, CLAUDE.md, and the roadmap at
docs/exec-plans/active/graph-aware-roadmap.md (Epic 3).

Your mission: Add graph-aware MCP tools and upgrade existing tools to
use the NoteIndex from graph.py.

PREREQUISITE: Agent 1 must have completed graph.py and index_store.py.
Read those modules to understand the API before starting.

TASK 1: Add obsidian_neighborhood MCP tool + CLI command
- Parameters: note_path (str), depth (int, default 1), vault (str, optional)
- Returns: {backlinks, forward_links, tags, neighbors}
- Use NoteIndex.neighborhood()

TASK 2: Add obsidian_vault_structure MCP tool + CLI command
- Parameters: vault (str, optional)
- Returns: {orphans, dead_ends, unresolved_links, tag_cloud, top_connected}

TASK 3: Add obsidian_backlinks MCP tool + CLI command
- Parameters: note_path (str), vault (str, optional)
- Returns: [{file, context, line}]

TASK 4: Upgrade find_prior_work in workflows.py
- Add backlink_count and shared_tags to each result dict

TASK 5: Upgrade today_brief in workflows.py
- Extract [[wikilinks]] from today's daily note
- Read each linked note (bounded to 5 max)
- Add linked_context to return dict

TASK 6: Upgrade my_world_snapshot in workflows.py
- Add vault_structure summary (orphan count, dead end count, top 3 tags)

TASK 7: Update TOOLS_CONTRACT.md with new tool documentation.

CONSTRAINTS:
- Do NOT modify graph.py or index_store.py.
- All new MCP tools must have ToolAnnotations.
- Use _error_envelope() for error handling.
- Existing return fields must not change (additive only).
- Run: python3 -m compileall obsidian_connector/ after each change.
```

---

### Agent 3: Deep Thinking Tools

**Mission:** Implement ghost, drift, trace, and ideas -- the thinking
tools that surface patterns across the vault.

**Roadmap epics owned:** Epic 4

**Exact files/modules to touch:**
- Create: `obsidian_connector/thinking.py` (if workflows.py > 500 LOC)
  OR modify `obsidian_connector/workflows.py`
- Modify: `obsidian_connector/mcp_server.py` -- 4 new tools
- Modify: `obsidian_connector/cli.py` -- 4 new subcommands
- Modify: `obsidian_connector/__init__.py`
- Create: `scripts/thinking_deep_test.py`
- Modify: `TOOLS_CONTRACT.md`

**Acceptance tests:**
- `./bin/obsx ghost "test question" --json` returns voice profile + guidance
- `./bin/obsx drift --days 30 --json` returns intentions, actual focus, gaps
- `./bin/obsx trace "topic" --json` returns timeline with phases
- `./bin/obsx ideas --json` returns idea candidates with citations
- `python3 scripts/thinking_deep_test.py` passes

**Constraints:**
- Import NoteIndex from graph.py (Agent 1). Import IndexStore from index_store.py.
- Do not modify graph.py, index_store.py, or search.py.
- All tools are read-only. No vault writes.
- Graceful degradation: if vault has too few notes, return helpful message, not error.
- Include confidence scores where subjective analysis is involved.

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md, ARCHITECTURE.md, CLAUDE.md, and the roadmap at
docs/exec-plans/active/graph-aware-roadmap.md (Epic 4).

Your mission: Implement 4 deep thinking tools.

PREREQUISITE: graph.py and index_store.py must exist (Agent 1).

TASK 1: ghost_voice_profile(vault, sample_notes=20) -> dict
- Read N recent notes (by mtime from NoteIndex)
- Extract: avg sentence length, vocabulary richness, common phrases,
  tone markers, structural preferences
- Return: {profile: {...}, sample_size, confidence}
- CLI: obsx ghost "question" --json
- MCP: obsidian_ghost(question, vault?)

TASK 2: drift_analysis(vault, lookback_days=60) -> dict
- Read daily notes over lookback period (from NoteIndex, sorted by date)
- Extract intentions: regex for "I will", "Plan to", "Goal:", "TODO:", etc.
- Cross-reference with: topics actually discussed (from note content),
  tasks completed (from list_tasks)
- Return: {stated_intentions, actual_focus, gaps, surprises, coverage_pct}
- CLI: obsx drift --days 60 --json
- MCP: obsidian_drift(lookback_days?, vault?)

TASK 3: trace_idea(topic, vault) -> dict
- Search for topic via search_notes()
- For each hit, get note date (from NoteIndex frontmatter or mtime)
- Sort chronologically, group into phases (first mention, growth, plateau)
- Return: {topic, first_mention: {date, file}, phases: [...], timeline: [...]}
- CLI: obsx trace "topic" --json
- MCP: obsidian_trace(topic, vault?)

TASK 4: deep_ideas(vault, max_ideas=10) -> dict
- Use NoteIndex: orphans, dead_ends, high-backlink notes, rare tags,
  tag co-occurrence patterns
- Generate idea candidates: "Note X is orphaned but tagged #important",
  "Notes A and B share rare tag #thesis but are not linked", etc.
- Return: {ideas: [{title, type, source_notes, rationale}]}
- CLI: obsx ideas --json
- MCP: obsidian_ideas(max_ideas?, vault?)

CONSTRAINTS:
- All tools are READ-ONLY. No vault writes.
- Graceful degradation on small vaults (< 10 notes): return helpful message.
- Include confidence scores for subjective outputs (ghost, drift).
- Use NoteIndex for all graph queries. Do not re-read files unnecessarily.
- All MCP tools must have ToolAnnotations (readOnlyHint=True).
```

---

### Agent 4: Graduate + Safety

**Mission:** Implement the graduate flow and agent draft segregation
that enforces the "agents read, humans write" boundary.

**Roadmap epics owned:** Epic 5

**Exact files/modules to touch:**
- Modify: `obsidian_connector/workflows.py` -- add graduate functions
- Modify: `obsidian_connector/cli.py` -- add graduate subcommands
- Modify: `obsidian_connector/mcp_server.py` -- add 2 tools
- Modify: `obsidian_connector/config.py` -- add agent_drafts folder
- Modify: `obsidian_connector/audit.py` -- ensure graduate writes are logged
- Create: `scripts/graduate_test.py`
- Modify: `TOOLS_CONTRACT.md`

**Acceptance tests:**
- `./bin/obsx graduate list --json` returns candidates
- `./bin/obsx graduate execute --title "Test" --dry-run` shows dry-run envelope
- `./bin/obsx graduate execute --title "Test" --confirm` creates note in agent drafts
- Created note has provenance frontmatter (source: agent, status: draft)
- Audit log records the write with content hash
- `python3 scripts/graduate_test.py` passes

**Constraints:**
- graduate list is READ-ONLY (safe, no confirmation needed)
- graduate execute REQUIRES --confirm (CLI) or confirm=True (MCP)
- Default target folder: Inbox/Agent Drafts/ (configurable)
- Provenance frontmatter mandatory on all agent-created notes
- Do not modify graph.py or index_store.py

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md, ARCHITECTURE.md, CLAUDE.md, and the roadmap at
docs/exec-plans/active/graph-aware-roadmap.md (Epic 5).

Your mission: Implement the graduate flow and agent draft segregation.

TASK 1: graduate_candidates(vault, lookback_days=7) -> list[dict]
- Scan recent daily notes for idea-like patterns:
  - Headings with 3+ lines of content beneath
  - Paragraphs with 3+ [[wikilinks]]
  - Lines tagged #idea or #insight
  - Lines with "TODO: expand", "flesh out", "write up"
- For each candidate, check NoteIndex for existing standalone note
- Return: [{title, source_file, excerpt, existing_note, tags, template}]

TASK 2: graduate_execute(title, content, vault, target_folder, confirm) -> str
- REQUIRE confirm=True or raise ValueError
- Create note at {target_folder}/{title}.md
- Add provenance frontmatter:
  ---
  source: agent
  created_from: "{source_daily_note}"
  status: draft
  created: "{iso_timestamp}"
  ---
- Call log_action() with full content hash
- If --dry-run, return dry-run envelope without writing

TASK 3: Add config.py default_folders.agent_drafts (default "Inbox/Agent Drafts")

TASK 4: CLI subcommands: obsx graduate list, obsx graduate execute --title T --confirm

TASK 5: MCP tools: obsidian_graduate_candidates (readOnly), obsidian_graduate_execute (NOT readOnly, requires confirm param)

TASK 6: Write scripts/graduate_test.py

CONSTRAINTS:
- graduate_execute MUST require explicit confirmation. Never auto-write.
- Use run_obsidian(["create", ...]) for note creation (not direct file writes).
- If target folder doesn't exist in vault, document that user must create it.
- All writes logged to audit trail. Dry-run writes logged with dry_run=true.
- MCP tool for execute must have destructiveHint=False but readOnlyHint=False.
```

---

### Agent 5: Performance + Delegation

**Mission:** Implement batch read, bounded scans, lazy loading, inline
delegation detection, and context load full.

**Roadmap epics owned:** Epic 6, Epic 7

**Exact files/modules to touch:**
- Modify: `obsidian_connector/client.py` -- add batch_read_notes()
- Modify: `obsidian_connector/workflows.py` -- enforce bounds, add delegation/context functions
- Modify: `obsidian_connector/graph.py` -- lazy loading
- Modify: `obsidian_connector/mcp_server.py` -- add 3 tools (rebuild_index, delegations, context_load)
- Modify: `obsidian_connector/cli.py` -- add 3 subcommands
- Modify: `obsidian_connector/config.py` -- add context_files config
- Create: `scripts/perf_test.py`
- Create: `scripts/delegation_test.py`
- Modify: `TOOLS_CONTRACT.md`

**Acceptance tests:**
- `python3 scripts/perf_test.py` passes latency benchmarks
- `./bin/obsx delegations --json` detects @agent: lines in recent notes
- `./bin/obsx context-load --json` returns aggregated context bundle
- `./bin/obsx rebuild-index --json` triggers full index rebuild
- today_brief completes in <3s on 1000-note vault

**Constraints:**
- batch_read_notes() must use semaphore (max 4 concurrent reads)
- All workflows must enforce max_notes bounds
- Delegation detection is read-only. Never auto-execute.
- Context load follows links to depth 1 only, max 20 notes total
- Do not modify graph.py internals (only add lazy loading wrapper)

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md, ARCHITECTURE.md, CLAUDE.md, and the roadmap at
docs/exec-plans/active/graph-aware-roadmap.md (Epics 6 and 7).

Your mission: Performance hardening and delegation/context features.

TASK 1: batch_read_notes(paths, vault) -> dict[str, str] in client.py
- Read multiple notes with bounded concurrency (max 4 parallel reads)
- Use concurrent.futures.ThreadPoolExecutor
- Return {path: content} dict
- Fall back to sequential reads if IPC errors detected

TASK 2: Enforce bounds in all workflows in workflows.py
- my_world_snapshot: reduce lookback_days default to 7
- challenge_belief: already bounded (max_evidence=10)
- find_prior_work: already bounded (top_n=5)
- New tools: drift, trace, ideas must have explicit max_notes params

TASK 3: Lazy NoteIndex loading in graph.py
- On first access, load from SQLite (IndexStore)
- If any note mtime > last build time, trigger incremental update
- Cache NoteIndex in module-level variable

TASK 4: detect_delegations(vault, lookback_days=1) -> list[dict]
- Scan recent notes for @agent:, @claude:, > [!agent] patterns
- Return: [{file, line, instruction, status}]
- CLI: obsx delegations --json
- MCP: obsidian_delegations(vault?, lookback_days?)

TASK 5: context_load_full(vault) -> dict
- Read configured context_files from config.py
- Read today's daily note + follow [[links]] depth 1
- Read past 7 daily notes (summaries only, first 500 chars)
- Aggregate open tasks + open loops
- Total note reads capped at 20
- Return structured bundle
- CLI: obsx context-load --json
- MCP: obsidian_context_load(vault?)

TASK 6: obsidian_rebuild_index MCP tool + CLI command
- Trigger full index rebuild via IndexStore.build_full()
- Return: {notes_indexed, duration_ms}

TASK 7: Write scripts/perf_test.py (latency benchmarks)
TASK 8: Write scripts/delegation_test.py

CONSTRAINTS:
- Do NOT add new dependencies. Use stdlib concurrent.futures.
- Delegation detection is READ-ONLY. Never execute instructions.
- Context load bounded to 20 note reads total.
- All MCP tools need ToolAnnotations.
```

---

### Agent 6: Distribution + Docs

**Mission:** Validate and polish distribution artifacts, update all
documentation, prepare for marketplace submission.

**Roadmap epics owned:** Epic 8, Epic 9

**Exact files/modules to touch:**
- Modify: `README.md` -- badges, install methods, demo GIF placeholder
- Modify: `mcpb.json` -- validate and fix
- Modify: `.claude-plugin/plugin.json` -- validate and fix
- Modify: `.claude-plugin/marketplace.json` -- validate and fix
- Create: `scripts/postinstall.sh`
- Modify: `TOOLS_CONTRACT.md` -- ensure all tools documented
- Create: `docs/design-docs/team-vault-pattern.md`
- Modify: `docs/distribution/SUBMISSION_CHECKLIST.md` -- update status
- Modify: `docs/index.md` -- add new doc links
- Modify: `PRIVACY.md` -- update for new features
- Run: `make docs-lint`

**Acceptance tests:**
- `make docs-lint` passes with no errors
- All TOOLS_CONTRACT.md entries match actual MCP tools
- README includes install instructions for: pip, MCPB, plugin marketplace
- `docs/design-docs/team-vault-pattern.md` exists with valid frontmatter
- PRIVACY.md covers voice profile, delegation, context load

**Constraints:**
- Do not modify any Python code (this agent is docs/config only)
- Follow Harness Engineering frontmatter contract
- All docs must have title, status, owner, last_reviewed
- Do not submit to marketplaces without user approval

**Copy/paste prompt:**
```
You are working in /Users/mu/Documents/GitHub/obsidian-connector.

Read AGENTS.md, ARCHITECTURE.md, CLAUDE.md, and the roadmap at
docs/exec-plans/active/graph-aware-roadmap.md (Epics 8 and 9).

Your mission: Documentation, distribution artifacts, and design docs.

TASK 1: Update TOOLS_CONTRACT.md
- Document ALL MCP tools (should be 24+ after all agents complete)
- Each tool: name, parameters, return type, example, annotations
- Verify tool list matches mcp_server.py

TASK 2: Update README.md
- Add install methods: pip, MCPB, Claude Code plugin
- Add tool count badge placeholder
- Add quick-start for each method
- Add link to PRIVACY.md

TASK 3: Validate distribution artifacts
- Read mcpb.json, .claude-plugin/plugin.json, marketplace.json
- Check version numbers are consistent
- Check tool counts match actual tools
- Fix any schema issues found

TASK 4: Create scripts/postinstall.sh
- Create .venv, install deps, run obsx doctor
- Print setup instructions

TASK 5: Create docs/design-docs/team-vault-pattern.md
- Frontmatter: title, status: draft, owner: mariourquia
- Cover: shared vault structure, access control model, privacy boundaries,
  agent draft location, conflict resolution, sync integration

TASK 6: Update PRIVACY.md for new features
- Voice profile (ghost): what data is analyzed, not stored
- Delegation: what patterns are scanned
- Context load: what files are sent to LLM

TASK 7: Run make docs-lint and fix any issues.

CONSTRAINTS:
- Do NOT modify Python code. Docs and config only.
- Follow Harness Engineering frontmatter contract.
- Do not submit to any marketplace (user must approve).
```

---

## Decisions / Tradeoffs

| Decision | Date | Rationale |
|----------|------|-----------|
| Use direct vault file access for graph indexing (not CLI-only) | 2026-03-05 | CLI has no `list files` or `backlinks` command. Direct read is 100x faster for bulk indexing. Keeps CLI for mutations. |
| SQLite for persistent index (not JSON file) | 2026-03-05 | Supports incremental updates, concurrent reads (WAL mode), and structured queries. stdlib `sqlite3` -- no new deps. |
| Separate graph.py module (not inline in workflows.py) | 2026-03-05 | Graph infrastructure is foundational. Multiple consumers. Clean separation of concerns. |
| Ghost voice profile computed per-request, not stored | 2026-03-05 | Privacy: voice patterns should not be persisted. Latency acceptable for 20-note sample. |
| Graduate requires explicit confirm (never auto-write) | 2026-03-05 | Core safety principle: agents read, humans write. |
| macOS-first vault path resolution | 2026-03-05 | User is on macOS. Linux/Windows documented as future. |
| Merge vnext before any new work | 2026-03-05 | 2,400 lines of implemented, tested work. No reason to redo it. |

## Risks & mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Obsidian CLI lacks needed commands | High | Medium | Graph module uses direct file access. CLI only for search/read/write. |
| Large vault performance | Medium | Medium | Persistent index + incremental updates + bounded scans. |
| Vault path resolution across OS | Low | Low | Start macOS-only. Configurable via env var. |
| Agent writes contaminate vault | High | Low | Strict confirm requirement. Segregated drafts folder. Audit trail. |
| vnext branch has untested code | Medium | Medium | Run full test suite before merge. Fix issues first. |

## Validation

```bash
# After each milestone:
make check
python3 -m compileall obsidian_connector/ scripts/
./bin/obsx doctor
./bin/obsx --json vault-structure  # after M1
./bin/obsx --json drift --days 30  # after M2
./bin/obsx --json context-load     # after M3
make docs-lint
```

## Progress log

- 2026-03-05: Roadmap created. Full repo reconnaissance completed.
  Identified vnext branch with 2,400 lines of unmerged work.
  Graph module identified as critical gap. 9 epics defined across
  3 milestones with 6 parallel agent prompts.
