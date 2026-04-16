"""MCP server exposing obsidian-connector tools for Claude Desktop."""

from __future__ import annotations

import json
import time
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from obsidian_connector.client_fallback import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    search_notes,
)
from obsidian_connector.doctor import run_doctor
from obsidian_connector.errors import (
    CommandTimeout,
    MalformedCLIOutput,
    ObsidianNotFound,
    ObsidianNotRunning,
    ProtectedFolderError,
    RollbackError,
    VaultNotFound,
    WriteLockError,
)
from obsidian_connector.graph import NoteIndex, resolve_note_path
from obsidian_connector.thinking import (
    deep_ideas,
    drift_analysis,
    ghost_voice_profile,
    trace_idea,
)
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.index_store import IndexStore, load_or_build_index
from obsidian_connector.retrieval import hybrid_search, SearchResult
from obsidian_connector.audit import log_action
from obsidian_connector.uninstall import (
    detect_installed_artifacts,
    dry_run_uninstall,
    execute_uninstall,
)
from obsidian_connector.workflows import (
    challenge_belief,
    check_in,
    close_day_reflection,
    connect_domains,
    context_load_full,
    create_research_note,
    detect_delegations,
    emerge_ideas,
    find_prior_work,
    graduate_candidates,
    graduate_execute,
    list_open_loops,
    log_decision,
    my_world_snapshot,
    today_brief,
)


# ---------------------------------------------------------------------------
# Error-mapping helper
# ---------------------------------------------------------------------------

_ERROR_TYPE_MAP: dict[type, str] = {
    ObsidianNotFound: "ObsidianNotFound",
    ObsidianNotRunning: "ObsidianNotRunning",
    VaultNotFound: "VaultNotFound",
    CommandTimeout: "CommandTimeout",
    MalformedCLIOutput: "MalformedCLIOutput",
    ProtectedFolderError: "ProtectedFolderError",
    WriteLockError: "WriteLockError",
    RollbackError: "RollbackError",
}


def _error_envelope(exc: ObsidianCLIError) -> str:
    """Return a canonical JSON error envelope for an ObsidianCLIError."""
    error_type = _ERROR_TYPE_MAP.get(type(exc), "ObsidianCLIError")
    return json.dumps(
        {"ok": False, "error": {"type": error_type, "message": str(exc)}}
    )


def _read_vault_file(rel_path: str, vault: str | None = None) -> str:
    """Read a vault file by its vault-relative path without the Obsidian CLI.

    Parameters
    ----------
    rel_path:
        Vault-relative path to the note (e.g. ``"Cards/Home.md"``).
    vault:
        Vault name (uses default if omitted).

    Returns
    -------
    str
        File contents, or empty string if the file cannot be read or the
        path would escape the vault root.
    """
    from obsidian_connector.errors import VaultNotFound
    from pathlib import Path as _Path

    note_path = _Path(rel_path)
    if note_path.is_absolute():
        return ""
    try:
        root = resolve_vault_path(vault).resolve()
        full = (root / note_path).resolve()
        full.relative_to(root)  # raises ValueError if outside vault
        if full.is_file():
            return full.read_text(encoding="utf-8", errors="replace")
    except (ValueError, OSError, VaultNotFound):
        pass
    return ""


mcp = FastMCP(
    "Obsidian Connector",
    json_response=True,
)


@mcp.tool(
    title="Search Obsidian Vault",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_search(
    query: str,
    vault: str | None = None,
    profile: str | None = None,
    explain: bool = False,
) -> str:
    """Search across all notes in the Obsidian vault.

    Returns matching files with line numbers and text excerpts.
    Use this to find notes on a topic, locate prior work, or check
    if something already exists in the vault.

    When ``profile`` or ``explain`` is provided, uses the hybrid
    retrieval engine (lexical + semantic + graph + recency scoring).
    Profiles: default, journal, project, research, review.
    """
    try:
        if profile or explain:
            vault_path = resolve_vault_path(vault)
            hybrid_results = hybrid_search(
                query=query,
                vault_path=vault_path,
                profile=profile or "default",
                top_k=10,
                explain=explain,
            )
            data = [
                {
                    "path": r.path,
                    "title": r.title,
                    "score": r.score,
                    "snippet": r.snippet,
                    **({"match_reasons": r.match_reasons} if explain else {}),
                }
                for r in hybrid_results
            ]
            return json.dumps(data, indent=2)
        results = search_notes(query, vault=vault)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Read Obsidian Note",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_read(name_or_path: str, vault: str | None = None) -> str:
    """Read the full content of a note from the Obsidian vault.

    Accepts either a wikilink-style name (e.g. "Project Alpha") or a
    vault-relative path (e.g. "Cards/Project Alpha.md").
    """
    try:
        return read_note(name_or_path, vault=vault)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="List Obsidian Tasks",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_tasks(
    status: str | None = None,
    path_prefix: str | None = None,
    limit: int | None = None,
    vault: str | None = None,
) -> str:
    """List tasks from the Obsidian vault.

    Args:
        status: Filter by "todo" or "done". Omit for all tasks.
        path_prefix: Only include tasks from files under this path.
        limit: Maximum number of tasks to return.
        vault: Target vault name (uses default if omitted).
    """
    try:
        f: dict = {}
        if status == "todo":
            f["todo"] = True
        elif status == "done":
            f["done"] = True
        if path_prefix:
            f["path"] = path_prefix
        if limit is not None:
            f["limit"] = limit
        results = list_tasks(filter=f or None, vault=vault)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Log to Daily Note",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_log_daily(content: str, vault: str | None = None) -> str:
    """Append text to today's daily note in Obsidian.

    Use this to log meetings, decisions, ideas, or any timestamped entry.
    Supports full markdown (headings, bullets, links, etc.).
    """
    try:
        log_to_daily(content, vault=vault)
        return "Appended to daily note."
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Log Decision Record",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_log_decision(
    project: str,
    summary: str,
    details: str,
    vault: str | None = None,
) -> str:
    """Log a structured decision record to today's daily note.

    Creates a formatted block with project name, timestamp, summary,
    and detailed rationale. Use this for architectural decisions,
    strategy choices, or any decision worth recording.
    """
    try:
        log_decision(project, summary, details, vault=vault)
        return f"Decision logged for project: {project}"
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Find Prior Work",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_find_prior_work(
    topic: str,
    top_n: int = 5,
    vault: str | None = None,
) -> str:
    """Search for existing notes on a topic and return structured summaries.

    Returns the top N matching notes with their heading, first paragraph
    excerpt, and match count. Use this before creating new content to
    check what already exists.
    """
    try:
        results = find_prior_work(topic, vault=vault, top_n=top_n)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Create Note from Template",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_create_note(
    title: str,
    template: str,
    vault: str | None = None,
) -> str:
    """Create a new note from a template in Obsidian.

    The template name must match exactly as shown by `obsidian templates`
    (e.g. "Template, Note"). The note is created and opened in Obsidian.
    """
    try:
        path = create_research_note(title, template, vault=vault)
        return f"Created: {path}"
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="My World Snapshot",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_my_world(
    vault: str | None = None,
    lookback_days: int = 14,
) -> str:
    """Get a snapshot of the entire vault state.

    Returns recent daily notes, open tasks, open loops, vault file count,
    and a hint about what to focus on next. Use this as a starting point
    when beginning a work session.

    Args:
        vault: Target vault name (uses default if omitted).
        lookback_days: Days to look back for daily notes (default 14).
    """
    try:
        result = my_world_snapshot(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Today Brief",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_today(vault: str | None = None) -> str:
    """Get a brief for today: daily note content, open tasks, open loops.

    Use this to see what is on the plate for the current day.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = today_brief(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Close Day Reflection",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_close_day(vault: str | None = None) -> str:
    """Generate an end-of-day reflection prompt (read-only).

    Returns completed tasks, remaining tasks, reflection questions, and
    suggested actions for tomorrow. Does NOT write to the vault.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = close_day_reflection(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Open Loops",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_open_loops(
    vault: str | None = None,
    lookback_days: int = 30,
) -> str:
    """List open loops in the vault.

    Finds lines starting with "OL:" and notes tagged with #openloop.
    Use this to review unresolved items that need attention.

    Args:
        vault: Target vault name (uses default if omitted).
        lookback_days: Lookback window in days (default 30).
    """
    try:
        result = list_open_loops(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Challenge Belief",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_challenge_belief(
    belief: str,
    vault: str | None = None,
    max_evidence: int = 10,
) -> str:
    """Challenge a belief by searching the vault for counter-evidence.

    Searches for contradicting and supporting evidence in your notes.
    Use this to stress-test assumptions, validate hypotheses, or play
    devil's advocate against a stated belief.

    Args:
        belief: The belief or assumption to challenge.
        vault: Target vault name (uses default if omitted).
        max_evidence: Maximum evidence items to return (default 10).
    """
    try:
        result = challenge_belief(belief, vault=vault, max_evidence=max_evidence)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Emerge Ideas",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_emerge_ideas(
    topic: str,
    vault: str | None = None,
    max_clusters: int = 5,
) -> str:
    """Cluster related notes into idea groups around a topic.

    Searches the vault for the topic, groups results by folder, and
    returns summaries for each cluster. Use this to discover how a topic
    is spread across your vault and find emergent patterns.

    Args:
        topic: Topic to explore.
        vault: Target vault name (uses default if omitted).
        max_clusters: Maximum number of clusters to return (default 5).
    """
    try:
        result = emerge_ideas(topic, vault=vault, max_clusters=max_clusters)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Connect Domains",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_connect_domains(
    domain_a: str,
    domain_b: str,
    vault: str | None = None,
    max_connections: int = 10,
) -> str:
    """Find connections between two domains in the vault.

    Searches for each domain separately, then finds notes that appear
    in both result sets. Use this to discover interdisciplinary links,
    bridge concepts, or find notes that span multiple topics.

    Args:
        domain_a: First domain to search.
        domain_b: Second domain to search.
        vault: Target vault name (uses default if omitted).
        max_connections: Maximum connecting notes to return (default 10).
    """
    try:
        result = connect_domains(
            domain_a, domain_b, vault=vault, max_connections=max_connections
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Note Neighborhood",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_neighborhood(
    note_path: str,
    depth: int = 1,
    vault: str | None = None,
) -> str:
    """Get the graph neighborhood of a note: backlinks, forward links, shared tags, and N-hop neighbors.

    Args:
        note_path: Vault-relative path or note name (e.g. "Home" or "Cards/Home.md").
        depth: Traversal depth for neighbors (default 1).
        vault: Target vault name (uses default if omitted).
    """
    try:
        idx = load_or_build_index(vault)
        if idx is None:
            return json.dumps(
                {"ok": False, "error": {"type": "IndexError", "message": "Could not build note index"}}
            )

        resolved = resolve_note_path(idx, note_path)

        if resolved is None:
            return json.dumps(
                {"ok": False, "error": {"type": "NoteNotFound", "message": f"Note not found in index: {note_path}"}}
            )

        entry = idx.notes[resolved]
        backlinks = sorted(idx.backlinks.get(resolved, set()))
        forward_links = sorted(idx.forward_links.get(resolved, set()))
        tags = entry.tags
        neighbors = sorted(idx.neighborhood(resolved, depth=depth))

        return json.dumps({
            "note": resolved,
            "backlinks": backlinks,
            "forward_links": forward_links,
            "tags": tags,
            "neighbors": neighbors,
        }, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Vault Structure",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_vault_structure(vault: str | None = None) -> str:
    """Get vault topology: orphans, dead ends, unresolved links, tag cloud, and most-connected notes.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        idx = load_or_build_index(vault)
        if idx is None:
            return json.dumps(
                {"ok": False, "error": {"type": "IndexError", "message": "Could not build note index"}}
            )

        total_notes = len(idx.notes)

        orphans = sorted(idx.orphans)[:20]
        dead_ends = sorted(idx.dead_ends)[:20]

        # Unresolved links: {link_target: [source_files]}
        unresolved_sorted = sorted(
            idx.unresolved.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:20]
        unresolved_links = {
            link: sorted(sources) for link, sources in unresolved_sorted
        }

        # Tag cloud: {tag: count}
        tag_counts = sorted(
            ((tag, len(paths)) for tag, paths in idx.tags.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:30]
        tag_cloud = {tag: count for tag, count in tag_counts}

        # Top connected: notes with most backlinks.
        backlink_counts = sorted(
            (
                (path, len(bl))
                for path, bl in idx.backlinks.items()
                if bl  # skip notes with 0 backlinks
            ),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        top_connected = [
            {"note": path, "backlink_count": count}
            for path, count in backlink_counts
        ]

        return json.dumps({
            "total_notes": total_notes,
            "orphans": orphans,
            "dead_ends": dead_ends,
            "unresolved_links": unresolved_links,
            "tag_cloud": tag_cloud,
            "top_connected": top_connected,
        }, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Note Backlinks",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_backlinks(note_path: str, vault: str | None = None) -> str:
    """Get all notes that link to a given note, with context.

    Args:
        note_path: Vault-relative path or note name (e.g. "Home" or "Cards/Home.md").
        vault: Target vault name (uses default if omitted).
    """
    try:
        idx = load_or_build_index(vault)
        if idx is None:
            return json.dumps(
                {"ok": False, "error": {"type": "IndexError", "message": "Could not build note index"}}
            )

        resolved = resolve_note_path(idx, note_path)

        if resolved is None:
            return json.dumps(
                {"ok": False, "error": {"type": "NoteNotFound", "message": f"Note not found in index: {note_path}"}}
            )

        backlink_paths = sorted(idx.backlinks.get(resolved, set()))
        note_title = idx.notes[resolved].title

        results: list[dict] = []
        for bl_path in backlink_paths:
            bl_entry = idx.notes.get(bl_path)
            context_line = ""

            # Read the backlinking note directly from vault files (no Obsidian CLI needed).
            content = _read_vault_file(bl_path, vault=vault)
            if content:
                for line in content.split("\n"):
                    if f"[[{note_title}]]" in line or f"[[{note_title}|" in line:
                        context_line = line.strip()
                        break
                    # Also check for path-based links.
                    if f"[[{resolved}" in line:
                        context_line = line.strip()
                        break

            results.append({
                "file": bl_path,
                "context_line": context_line,
                "tags": bl_entry.tags if bl_entry else [],
            })

        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Doctor Health Check",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_doctor(vault: str | None = None) -> str:
    """Run health checks on the Obsidian CLI connection.

    Checks: binary presence, version, vault resolution, and reachability.
    Use this to diagnose connectivity issues.
    """
    try:
        checks = run_doctor(vault=vault)
        return json.dumps(checks, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Graduate Candidates",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_graduate_candidates(
    lookback_days: int = 7,
    vault: str | None = None,
) -> str:
    """Scan recent daily notes for ideas worth promoting to standalone notes.

    Detects headings with rich content, paragraphs with multiple wikilinks,
    #idea/#insight tags, and "TODO: expand" markers. Returns candidates
    ranked by richness with existing-note detection.

    Args:
        lookback_days: Days to look back for daily notes (default 7).
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = graduate_candidates(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Graduate Execute",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_graduate_execute(
    title: str,
    content: str,
    source_file: str | None = None,
    target_folder: str | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    vault: str | None = None,
) -> str:
    """Create a note in the agent drafts folder with provenance frontmatter.

    Enforces "agents read, humans write": notes land in a segregated
    drafts folder (default: Inbox/Agent Drafts) for human review.

    REQUIRES confirm=True to write, or dry_run=True to preview.

    Args:
        title: Note title (becomes the file name).
        content: Markdown body of the note.
        source_file: Vault-relative path of the originating daily note.
        target_folder: Target folder (default: Inbox/Agent Drafts).
        confirm: Must be True to actually create the note.
        dry_run: If True, return a preview without creating anything.
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = graduate_execute(
            title=title,
            content=content,
            vault=vault,
            target_folder=target_folder,
            source_file=source_file,
            confirm=confirm,
            dry_run=dry_run,
        )
        return json.dumps(result, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": {"type": "ValueError", "message": str(exc)}})
    except (OSError, FileExistsError) as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
    except ObsidianCLIError as exc:
        return _error_envelope(exc)


@mcp.tool(
    title="Ghost Voice Profile",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_ghost(
    question: str | None = None,
    sample_notes: int = 20,
    vault: str | None = None,
) -> str:
    """Analyze writing style from recent vault notes to build a voice profile.

    Reads the N most recently modified notes, extracts sentence length,
    vocabulary richness, common phrases, structural preferences, and tone
    markers. Use this to understand and reproduce the user's authentic
    writing voice.

    Args:
        question: Optional question to answer in the user's voice (included in response for context).
        sample_notes: Number of recent notes to sample (default 20).
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = ghost_voice_profile(vault=vault, sample_notes=sample_notes)
        if question:
            result["question"] = question
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Drift Analysis",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_drift(
    lookback_days: int = 60,
    vault: str | None = None,
) -> str:
    """Analyze drift between stated intentions and actual behavior.

    Reads daily notes over the lookback period, extracts stated intentions
    (I will, Plan to, Goal:, TODO:, etc.), and cross-references with topics
    actually discussed. Surfaces gaps (intentions not acted on) and surprises
    (topics getting attention without stated intent).

    Args:
        lookback_days: Days to look back (default 60).
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = drift_analysis(vault=vault, lookback_days=lookback_days)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Trace Idea",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_trace(
    topic: str,
    max_notes: int = 20,
    vault: str | None = None,
) -> str:
    """Trace how an idea or topic evolved over time across vault notes.

    Searches for the topic, sorts matching notes by date, extracts excerpts
    around mentions, and groups into temporal phases (first_mention, growth,
    plateau, revival). Use this to understand the evolution of your thinking.

    Args:
        topic: Topic string to trace.
        max_notes: Maximum notes in the timeline (default 20).
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = trace_idea(topic, vault=vault, max_notes=max_notes)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Deep Ideas",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_ideas(
    max_ideas: int = 10,
    vault: str | None = None,
) -> str:
    """Surface latent ideas from vault graph structure.

    Finds forgotten ideas (orphaned #idea/#insight notes), convergence points
    (high backlinks, no outgoing links), unresolved links (ideas referenced
    but never written), rare tag connections, and cross-domain opportunities.
    Use this to discover hidden patterns and actionable next steps.

    Args:
        max_ideas: Maximum ideas to return (default 10).
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = deep_ideas(vault=vault, max_ideas=max_ideas)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Rebuild Index",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_rebuild_index(vault: str | None = None) -> str:
    """Trigger a full rebuild of the vault graph index.

    Use at session start for fresh data. Returns index statistics
    including notes indexed, orphan count, tag count, and duration.
    """
    try:
        vault_path = resolve_vault_path(vault)
        store = IndexStore()
        try:
            t0 = time.monotonic()
            index = store.build_full(vault_path=vault_path)
            duration_ms = int((time.monotonic() - t0) * 1000)
        finally:
            store.close()

        return json.dumps({
            "notes_indexed": len(index.notes),
            "orphans": len(index.orphans),
            "tags": len(index.tags),
            "duration_ms": duration_ms,
        }, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Detect Delegations",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_delegations(
    lookback_days: int = 1,
    vault: str | None = None,
) -> str:
    """Scan recent notes for @agent: or @claude: delegation instructions.

    Finds delegation patterns in daily notes and vault-wide searches.
    Returns each delegation with file, line number, instruction text,
    and status (pending or done).

    Args:
        lookback_days: Days to look back for daily notes (default 1).
        vault: Target vault name (uses default if omitted).
    """
    try:
        results = detect_delegations(vault=vault, lookback_days=lookback_days)
        return json.dumps(results, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Load Full Context",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_context_load(vault: str | None = None) -> str:
    """Load full context bundle: context files, daily note with links, recent dailies, tasks, loops.

    Use this at the start of an agent session to load all relevant vault
    context in a single call. Reads are capped at 20 notes total.

    Args:
        vault: Target vault name (uses default if omitted).
    """
    try:
        result = context_load_full(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Check In",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_check_in(
    vault: str | None = None,
    timezone: str | None = None,
) -> str:
    """Time-aware check-in: what should you do now?

    Call this at the start of a conversation. Returns what time of day
    it is, which daily rituals have already run, how many open loops and
    delegations are pending, and a suggested next action.

    Use the suggestion to proactively offer the user their morning
    briefing, evening close, or other relevant workflow.
    """
    try:
        result = check_in(vault=vault, timezone_name=timezone)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Uninstall obsidian-connector",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_uninstall(
    dry_run: bool = True,
    remove_venv: bool = False,
    remove_skills: bool = False,
    remove_hook: bool = False,
    remove_plist: bool = False,
    remove_logs: bool = False,
    remove_cache: bool = False,
) -> str:
    """Safely remove obsidian-connector installation artifacts.

    Two-mode operation:
    1. dry_run=True (default): Preview what will be removed (JSON plan)
    2. dry_run=False: Execute removal with all specified --remove-* flags

    Args:
        dry_run: If True, show plan without removing anything. Default True.
        remove_venv: Remove .venv directory (use with dry_run=False).
        remove_skills: Remove Claude Code skills.
        remove_hook: Remove SessionStart hook.
        remove_plist: Remove launchd plist.
        remove_logs: Remove audit logs.
        remove_cache: Remove cache/index files.

    Returns:
        JSON with removal plan (dry_run=True) or removal results (dry_run=False).
        Includes backed-up config file locations for safe rollback.
    """
    from pathlib import Path

    try:
        # Resolve paths
        repo_root = Path(__file__).parent.parent
        venv_path = repo_root / ".venv"
        from obsidian_connector.platform import claude_desktop_config_path
        claude_config_path = claude_desktop_config_path()

        # Detect what's installed
        plan = detect_installed_artifacts(
            repo_root=repo_root,
            venv_path=venv_path,
            claude_config_path=claude_config_path,
        )

        if dry_run:
            # Preview mode: show what would be removed
            log_action(
                "uninstall",
                {
                    "mode": "mcp",
                    "dry_run": True,
                    "remove_venv": remove_venv,
                    "remove_skills": remove_skills,
                    "remove_hook": remove_hook,
                    "remove_plist": remove_plist,
                    "remove_logs": remove_logs,
                    "remove_cache": remove_cache,
                },
                vault=None,
                dry_run=True,
                affected_path="system-config",
            )
            result = dry_run_uninstall(plan)
        else:
            # Execution mode: remove artifacts
            plan.remove_venv = remove_venv
            plan.remove_skills = remove_skills
            plan.remove_hook = remove_hook
            plan.remove_plist = remove_plist
            plan.remove_logs = remove_logs
            plan.remove_cache = remove_cache

            log_action(
                "uninstall",
                {
                    "mode": "mcp",
                    "dry_run": False,
                    "remove_venv": remove_venv,
                    "remove_skills": remove_skills,
                    "remove_hook": remove_hook,
                    "remove_plist": remove_plist,
                    "remove_logs": remove_logs,
                    "remove_cache": remove_cache,
                },
                vault=None,
                dry_run=False,
                affected_path="system-config",
            )
            result = execute_uninstall(plan, config_path=claude_config_path)

        return json.dumps(result, indent=2)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Project Sync tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Sync Projects to Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_sync_projects(
    vault: str | None = None,
    github_root: str | None = None,
    update_todo: bool = True,
) -> str:
    """Sync all tracked git repositories into the Obsidian vault.

    Generates per-project Markdown files with git state, a Dashboard with
    project table, Active Threads for repos with uncommitted work, and
    optionally updates the Running TODO list.

    This replaces standalone sync scripts with a cross-platform,
    vault-integrated alternative.
    """
    from obsidian_connector.project_sync import sync_projects

    try:
        result = sync_projects(
            vault=vault,
            github_root=github_root,
            update_todo=update_todo,
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Get Project Status",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_project_status(
    project: str,
    vault: str | None = None,
    github_root: str | None = None,
) -> str:
    """Get current git status for a single tracked project.

    Returns branch, last commit, uncommitted file count, modified files,
    recent commits, and activity classification.
    """
    from obsidian_connector.project_sync import get_project_status

    try:
        result = get_project_status(
            project=project,
            vault=vault,
            github_root=github_root,
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Get Active Threads",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_active_threads(
    vault: str | None = None,
    github_root: str | None = None,
) -> str:
    """List projects with active work -- non-main branches or uncommitted changes.

    Returns a list of active project threads with branch, uncommitted count,
    and last commit info.
    """
    from obsidian_connector.project_sync import get_active_threads

    try:
        result = get_active_threads(vault=vault, github_root=github_root)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Log Session to Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_log_session(
    projects: str,
    work_types: str = "",
    completed: str = "",
    next_steps: str = "",
    decisions: str = "",
    session_context: str = "",
    vault: str | None = None,
) -> str:
    """Write a structured session log entry to the vault.

    Session logs have YAML frontmatter with project tags, work types,
    and file counts -- enabling time-series analysis via Obsidian Bases.

    Parameters use pipe-separated values for multiple items:
    - projects: "obsidian-connector|site"
    - work_types: "feature-dev|integration"
    - completed: "Built sync module|Added MCP tools"
    - next_steps: "Write tests|Update docs"
    """
    from obsidian_connector.project_sync import SessionEntry, log_session

    try:
        project_list = [p.strip() for p in projects.split("|") if p.strip()]
        wt_list = [w.strip() for w in work_types.split("|") if w.strip()] if work_types else []
        completed_list = [c.strip() for c in completed.split("|") if c.strip()] if completed else []
        next_list = [n.strip() for n in next_steps.split("|") if n.strip()] if next_steps else []
        decision_list = [d.strip() for d in decisions.split("|") if d.strip()] if decisions else []

        entries = []
        for proj in project_list:
            entries.append(SessionEntry(
                project=proj,
                work_types=wt_list,
                completed=completed_list,
                next_steps=next_list,
                decisions=decision_list,
            ))

        result = log_session(
            entries=entries,
            session_context=session_context,
            vault=vault,
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Get Running TODO",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_running_todo(vault: str | None = None) -> str:
    """Get the current running TODO state -- all open items across the vault.

    Returns open item count, items grouped by source note, and recent
    completions. Use obsidian_sync_projects to refresh the Running TODO
    note in the vault.
    """
    from obsidian_connector.project_sync import get_running_todo

    try:
        result = get_running_todo(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Initialize Vault for Project Sync",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_init_vault(
    vault_path: str,
    github_root: str = "",
    use_defaults: bool = False,
    existing_vault: bool = False,
) -> str:
    """Initialize a vault for project tracking.

    For NEW vaults (existing_vault=False): creates the full directory
    structure with project tracking in the vault root.

    For EXISTING vaults (existing_vault=True): puts all project-tracking
    files in a 'Project Tracking' subdirectory so your existing notes
    are untouched. Auto-detected: if the vault already has .md files or
    directories, it's treated as existing.

    Use use_defaults=True to pre-populate with the standard repo list,
    or leave False to auto-discover repos from github_root.
    """
    from obsidian_connector.vault_init import init_vault

    try:
        result = init_vault(
            vault_path=vault_path,
            github_root=github_root if github_root else None,
            use_defaults=use_defaults,
            existing_vault=existing_vault,
        )
        return json.dumps(result, indent=2)
    except (ObsidianCLIError, OSError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Idea routing tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Float an Idea to a Project",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_float_idea(
    idea: str,
    project: str = "",
    vault: str | None = None,
) -> str:
    """Route an idea to the appropriate project's idea file in the vault.

    If project is specified, routes directly to that project's idea file.
    If omitted, auto-routes by matching keywords in the idea text against
    known projects and their tags.

    Ideas accumulate in Inbox/Ideas/{project}.md with timestamps.
    """
    from obsidian_connector.idea_router import float_idea

    try:
        result = float_idea(idea=idea, project=project, vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, FileExistsError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Incubate a New Project Idea",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_incubate_project(
    name: str,
    description: str,
    why: str = "",
    tags: str = "",
    related_projects: str = "",
    vault: str | None = None,
) -> str:
    """Create an inception card for a project that doesn't exist yet.

    Captures tangential ideas worth revisiting -- things that might become
    repos or products someday but aren't being built now. Cards live in
    Inbox/Project Ideas/{slug}.md.

    Parameters:
    - name: project name (e.g., "Flight Tracker Dashboard")
    - description: what it would do
    - why: why it matters (optional)
    - tags: comma-separated tags (optional)
    - related_projects: comma-separated related project names (optional)
    """
    from obsidian_connector.idea_router import incubate_project

    try:
        result = incubate_project(
            name=name,
            description=description,
            why=why,
            tags=tags,
            related_projects=related_projects,
            vault=vault,
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, FileExistsError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="List Incubating Projects",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_incubating(vault: str | None = None) -> str:
    """List all project inception cards -- ideas for projects not yet started."""
    from obsidian_connector.idea_router import list_incubating

    try:
        result = list_incubating(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="List Idea Files",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_idea_files(vault: str | None = None) -> str:
    """List all idea routing files with per-project idea counts."""
    from obsidian_connector.idea_router import list_idea_files

    try:
        result = list_idea_files(vault=vault)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Vault guardian tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Mark Auto-Generated Files",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_mark_auto_generated(vault: str | None = None) -> str:
    """Add 'do not edit' callouts to auto-generated vault files.

    Marks Dashboard.md, Running TODO.md, projects/*.md, and
    context/active-threads.md with a visible Obsidian callout warning
    users not to edit them manually (they get overwritten on sync).
    """
    from obsidian_connector.vault_guardian import mark_auto_generated

    try:
        vault_path = resolve_vault_path(vault)
        result = mark_auto_generated(vault_path)
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Detect Unorganized Notes",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_detect_unorganized(vault: str | None = None) -> str:
    """Find notes in the vault root that should be in a subfolder.

    Returns suggestions with the file name, recommended folder, and
    reasoning. Use obsidian_organize_file to execute the move.
    """
    from obsidian_connector.vault_guardian import detect_unorganized

    try:
        vault_path = resolve_vault_path(vault)
        suggestions = detect_unorganized(vault_path)
        return json.dumps({"suggestions": suggestions, "count": len(suggestions)}, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Organize a Vault File",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_organize_file(
    file_name: str,
    target_folder: str,
    vault: str | None = None,
) -> str:
    """Move a file from the vault root to the suggested folder.

    Only moves files from the vault root -- never touches files already
    in subfolders. Will not overwrite existing files at the destination.
    """
    from obsidian_connector.vault_guardian import organize_file

    try:
        result = organize_file(
            file_name=file_name,
            target_folder=target_folder,
            vault=vault,
        )
        return json.dumps(result, indent=2)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except (OSError, FileExistsError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Vault factory tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Create New Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_create_vault(
    name: str,
    description: str = "",
    seed_topics: str = "",
    vault_root: str = "",
    preset: str = "",
) -> str:
    """Create a new Obsidian vault for a topic or idea.

    Auto-detects where existing vaults are stored and creates the new one
    alongside them. Can use a preset template for common vault types.

    Parameters:
    - name: vault name (e.g., "My Journal", "Aviation Research")
    - description: what this vault is for
    - seed_topics: pipe-separated topics to create research stubs for
    - preset: use a curated template (see obsidian_vault_presets for list).
      Options: journaling, mental-health, business-ideas, research,
      project-management, second-brain, vacation-planning, life-planning,
      budgeting, creative-writing, self-expression
    - vault_root: override parent directory (auto-detected if empty)

    The vault gets: Home.md, Research/, Cards/, Inbox/, daily/, templates/
    and research stubs for each seed topic with key questions to explore.
    """
    from obsidian_connector.vault_factory import create_vault

    try:
        topics = [t.strip() for t in seed_topics.split("|") if t.strip()] if seed_topics else None
        result = create_vault(
            name=name,
            description=description,
            seed_topics=topics,
            vault_root=vault_root,
            preset=preset,
        )
        return json.dumps(result, indent=2)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="List Vault Presets",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_vault_presets() -> str:
    """List available vault preset templates.

    Presets are curated vault structures for common use cases:
    journaling, mental health, business ideas, research, project
    management, second brain, vacation planning, life planning,
    budgeting, creative writing, and self-expression.

    Pass the preset slug to obsidian_create_vault to use one.
    """
    from obsidian_connector.vault_presets import list_presets

    presets = list_presets()
    return json.dumps({"presets": presets, "count": len(presets)}, indent=2)


@mcp.tool(
    title="Seed Vault with Research",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_seed_vault(
    vault_path: str,
    title: str,
    content: str,
    tags: str = "",
    folder: str = "Cards",
) -> str:
    """Add a research note to a vault.

    Use this after researching a topic (web search, reading docs, etc.)
    to save findings as a structured note in the vault.

    Parameters:
    - vault_path: path to the vault
    - title: note title
    - content: markdown content (research findings, key points, links)
    - tags: comma-separated tags
    - folder: which folder to put it in (default: Cards/)
    """
    from obsidian_connector.vault_factory import _slugify, _render_seed_note
    from pathlib import Path as _Path

    try:
        vpath = _Path(vault_path).expanduser()
        target_dir = vpath / folder
        target_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(title)
        note_file = target_dir / f"{slug}.md"

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else ["research"]
        note_content = _render_seed_note(title=title, content=content, tags=tag_list)

        if note_file.exists():
            # Append instead of overwrite
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(note_file, "a", encoding="utf-8") as f:
                f.write(f"\n---\n\n## Update ({now})\n\n{content}\n")
        else:
            note_file.write_text(note_content, encoding="utf-8")

        log_action(
            "seed-vault",
            {"title": title, "folder": folder},
            None,
            affected_path=str(note_file),
            content=content,
        )

        return json.dumps({
            "file": str(note_file),
            "title": title,
            "folder": folder,
            "created": not note_file.exists(),
        }, indent=2)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="List Existing Vaults",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_list_vaults() -> str:
    """List all Obsidian vaults registered on this machine."""
    from obsidian_connector.vault_factory import list_existing_vaults

    try:
        vaults = list_existing_vaults()
        return json.dumps({"vaults": vaults, "count": len(vaults)}, indent=2)
    except (OSError, json.JSONDecodeError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Discard a Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_discard_vault(
    vault_path: str,
    confirm: bool = False,
) -> str:
    """Discard a vault that's no longer useful.

    Without confirm=True, this is a dry run that shows what would be deleted.
    With confirm=True, permanently removes the vault directory.
    """
    from obsidian_connector.vault_factory import discard_vault

    try:
        result = discard_vault(vault_path=vault_path, confirm=confirm)
        return json.dumps(result, indent=2)
    except (OSError, ValueError) as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Write Safety
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Rollback Last Write",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_rollback(vault: str | None = None) -> str:
    """Restore vault files from the most recent pre-write snapshot.

    Use this to undo the last write operation performed by the connector.
    Each write creates a snapshot; this restores from the latest one.
    """
    try:
        from obsidian_connector.write_manager import rollback

        vault_path = resolve_vault_path(vault)
        result = rollback(vault_path)
        return json.dumps(result, indent=2, default=str)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Draft Management
# ---------------------------------------------------------------------------


@mcp.tool(
    title="List Agent Drafts",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_list_drafts(vault: str | None = None) -> str:
    """List agent-generated drafts pending human review.

    Scans the Inbox/Agent Drafts/ folder for files with generated_by
    frontmatter. Returns draft metadata including age, source tool, and
    staleness status. Use this to see what the agent has written that
    has not yet been approved or rejected.
    """
    try:
        from obsidian_connector.draft_manager import list_drafts

        vault_path = resolve_vault_path(vault)
        drafts = list_drafts(vault_path)
        return json.dumps(
            [vars(d) for d in drafts], indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Approve Draft",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_approve_draft(
    draft_path: str,
    target_folder: str,
    vault: str | None = None,
) -> str:
    """Promote an agent draft to a target folder.

    Moves the draft from Inbox/Agent Drafts/ to the specified target
    folder, stripping the generated_by frontmatter. The draft becomes
    a permanent vault note.
    """
    try:
        from obsidian_connector.draft_manager import approve_draft

        vault_path = resolve_vault_path(vault)
        result = approve_draft(vault_path, draft_path, target_folder)
        return json.dumps(result, indent=2, default=str)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Reject Draft",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_reject_draft(
    draft_path: str,
    vault: str | None = None,
) -> str:
    """Archive a rejected agent draft.

    Moves the draft to Archive/Rejected Drafts/ with a datestamp suffix.
    Use this when a generated draft is not useful and should be removed
    from the active drafts queue.
    """
    try:
        from obsidian_connector.draft_manager import reject_draft

        vault_path = resolve_vault_path(vault)
        result = reject_draft(vault_path, draft_path)
        return json.dumps(result, indent=2, default=str)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Clean Stale Drafts",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_clean_drafts(
    max_age_days: int = 14,
    dry_run: bool = True,
    vault: str | None = None,
) -> str:
    """Auto-archive agent drafts older than the specified age.

    By default runs in dry-run mode, showing what would be moved without
    actually moving anything. Set dry_run=False to execute the cleanup.

    Args:
        max_age_days: Age threshold in days (default 14).
        dry_run: If True, report only; if False, actually move files.
        vault: Target vault name (uses default if omitted).
    """
    try:
        from obsidian_connector.draft_manager import clean_stale_drafts

        vault_path = resolve_vault_path(vault)
        result = clean_stale_drafts(
            vault_path, max_age_days=max_age_days, dry_run=dry_run
        )
        return json.dumps(
            {"dry_run": dry_run, "moved": result}, indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Vault Registry
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Register Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_register_vault(
    name: str,
    path: str,
    profile: str = "personal",
) -> str:
    """Add a vault to the named vault registry.

    Registers the vault with a unique name, filesystem path, and profile
    (personal, work, research, or creative). The path must exist on disk.

    Args:
        name: Unique identifier for the vault.
        path: Filesystem path to the vault directory.
        profile: One of personal, work, research, creative.
    """
    try:
        from obsidian_connector.vault_registry import VaultRegistry

        registry = VaultRegistry()
        entry = registry.register(name, path, profile=profile)
        return json.dumps(entry.to_dict(), indent=2, default=str)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Set Default Vault",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_set_default_vault(name: str) -> str:
    """Set the default vault in the registry.

    The named vault must already be registered. After setting, tools that
    accept an optional vault parameter will use this vault when none is
    specified.
    """
    try:
        from obsidian_connector.vault_registry import VaultRegistry

        registry = VaultRegistry()
        registry.set_default(name)
        return json.dumps(
            {"ok": True, "default_vault": name}, indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Templates
# ---------------------------------------------------------------------------


@mcp.tool(
    title="List Templates",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_list_templates(vault: str | None = None) -> str:
    """List available note templates in the vault.

    Scans the vault's _templates/ folder and returns metadata for each
    template including name, description, version, variables, and
    inheritance chain. Use this to see what templates are available
    before creating a note from one.
    """
    try:
        from obsidian_connector.template_engine import TemplateEngine

        vault_path = resolve_vault_path(vault)
        engine = TemplateEngine(vault_path)
        templates = engine.list_templates()
        return json.dumps(
            [vars(t) for t in templates], indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Create Note from Template",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_create_from_template(
    template_name: str,
    title: str,
    vault: str | None = None,
    variables: str | None = None,
) -> str:
    """Create a new note by rendering a template with variable substitution.

    Built-in variables (date, time, vault_name, etc.) are auto-populated.
    Pass additional variables as a JSON string of key-value pairs.

    Args:
        template_name: Name of the template (stem of the .md file in _templates/).
        title: Title for the new note (used as filename and {{title}} variable).
        vault: Target vault name (uses default if omitted).
        variables: Optional JSON string of extra variables, e.g. '{"author": "Mario"}'.
    """
    try:
        from obsidian_connector.template_engine import TemplateEngine
        from obsidian_connector.write_manager import atomic_write, snapshot
        from pathlib import Path as _Path

        vault_path = resolve_vault_path(vault)
        engine = TemplateEngine(vault_path)

        extra_vars: dict[str, str] = {}
        if variables:
            extra_vars = json.loads(variables)
        extra_vars.setdefault("title", title)

        content = engine.render(template_name, variables=extra_vars)
        note_path = vault_path / f"{title}.md"

        if note_path.is_file():
            snapshot(note_path, vault_path)

        written = atomic_write(
            note_path,
            content,
            vault_path,
            tool_name="obsidian_create_from_template",
            inject_generated_by=True,
        )

        return json.dumps(
            {"created": True, "path": str(written.relative_to(vault_path))},
            indent=2,
            default=str,
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Project Intelligence
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Project Changelog",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_project_changelog(
    project_name: str,
    since_days: int = 7,
    vault: str | None = None,
) -> str:
    """Generate a changelog for a project from session logs.

    Scans daily and session log files for entries mentioning the project,
    extracts work types and completed items, and returns a formatted
    Markdown changelog table.

    Args:
        project_name: Name of the project to generate a changelog for.
        since_days: Number of days to look back (default 7).
        vault: Target vault name (uses default if omitted).
    """
    try:
        from obsidian_connector.project_intelligence import project_changelog

        vault_path = resolve_vault_path(vault)
        result = project_changelog(vault_path, project_name, since_days=since_days)
        return json.dumps(
            {"project": project_name, "since_days": since_days, "changelog": result},
            indent=2,
            default=str,
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Project Health Scores",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_project_health(vault: str | None = None) -> str:
    """Compute health scores for all projects in the vault.

    Returns a score (0-100), status (healthy/warning/stale/inactive),
    and contributing factors for each project. Use this to identify
    which projects need attention.
    """
    try:
        from obsidian_connector.project_intelligence import project_health

        vault_path = resolve_vault_path(vault)
        results = project_health(vault_path)
        return json.dumps(
            [vars(r) for r in results], indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Weekly Project Packet",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_project_packet(
    days: int = 7,
    vault: str | None = None,
) -> str:
    """Generate a weekly project summary packet.

    Produces a Markdown report covering all projects with health scores,
    commit activity, session counts, open TODOs, and graduation
    candidates from the idea incubator.

    Args:
        days: Number of days to cover (default 7).
        vault: Target vault name (uses default if omitted).
    """
    try:
        from obsidian_connector.project_intelligence import project_packet

        vault_path = resolve_vault_path(vault)
        result = project_packet(vault_path, days=days)
        return json.dumps(
            {"days": days, "packet": result}, indent=2, default=str
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Reports
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Generate Report",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_generate_report(
    report_type: str,
    vault: str | None = None,
) -> str:
    """Generate a report and write it to the vault's Reports/ folder.

    Supported report types: weekly, monthly, vault_health, project_status.
    The report file is written as Markdown and a summary is returned.

    Args:
        report_type: One of weekly, monthly, vault_health, project_status.
        vault: Target vault name (uses default if omitted).
    """
    try:
        from obsidian_connector.reports import generate_report

        vault_path = resolve_vault_path(vault)
        result = generate_report(str(vault_path), report_type)
        return json.dumps(vars(result), indent=2, default=str)
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Telemetry
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Session Telemetry",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_session_stats() -> str:
    """Return telemetry for the current connector session.

    Shows notes read, notes written, tools called, retrieval misses,
    write risk events, and error counts. All data is local-only and
    never leaves the machine.
    """
    try:
        from obsidian_connector.telemetry import TelemetryCollector

        collector = TelemetryCollector()
        summary = collector.session_summary()
        return json.dumps(summary, indent=2, default=str)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# v0.6.0 Index Status
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Index Status",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_index_status(vault: str | None = None) -> str:
    """Check the age and staleness of the vault note index.

    Returns the index age in seconds and whether it exceeds the
    staleness threshold (60 seconds). Use this to decide whether
    a re-index is needed before running graph or search operations.
    """
    try:
        from obsidian_connector.watcher import get_index_age, is_stale

        vault_path = resolve_vault_path(vault)
        store = IndexStore()
        age = get_index_age(store)
        stale = is_stale(store)
        return json.dumps(
            {
                "vault": str(vault_path),
                "index_age_seconds": age,
                "is_stale": stale,
                "threshold_seconds": 60.0,
            },
            indent=2,
            default=str,
        )
    except ObsidianCLIError as exc:
        return _error_envelope(exc)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Commitment commands (v0.9.0)
# ---------------------------------------------------------------------------


@mcp.tool(
    title="List Commitments",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_commitments(
    status: str | None = None,
    project: str | None = None,
    priority: str | None = None,
    vault: str | None = None,
) -> str:
    """List commitment notes in the vault.

    Returns a JSON array of commitment summaries, each containing
    ``action_id``, ``title``, ``status``, ``priority``, ``project``,
    ``due_at``, ``postponed_until``, ``requires_ack``, and ``path``.

    Args:
        status: Filter by ``"open"`` or ``"done"``.  Omit for all.
        project: Case-insensitive project name filter.
        priority: Filter by ``"low"``, ``"normal"``, or ``"high"``.
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import list_commitments

    try:
        vault_path = resolve_vault_path(vault)
        items = list_commitments(vault_path, status=status, project=project, priority=priority)
        return json.dumps({"ok": True, "count": len(items), "commitments": items}, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Get Commitment Status",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_commitment_status(action_id: str, vault: str | None = None) -> str:
    """Return the current state of a single commitment by action ID.

    Returns a JSON object with all frontmatter fields, or an error
    envelope when the commitment is not found.

    Args:
        action_id: The ``action_id`` field from the commitment's frontmatter.
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import get_commitment

    try:
        vault_path = resolve_vault_path(vault)
        item = get_commitment(vault_path, action_id)
        if item is None:
            return json.dumps(
                {"ok": False, "error": {"type": "NotFound", "message": f"commitment not found: {action_id!r}"}}
            )
        return json.dumps({"ok": True, "commitment": item}, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Mark Commitment Done",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_mark_done(
    action_id: str,
    completed_at: str | None = None,
    vault: str | None = None,
) -> str:
    """Mark a commitment as done and move it to the Done bucket.

    Updates the commitment note's status to ``done``, relocates the file
    from ``Commitments/Open/`` to ``Commitments/Done/``, and appends a
    status-change entry to the follow-up log.

    When ``OBSIDIAN_CAPTURE_SERVICE_URL`` is set, also PATCHes the remote
    action.  The PATCH is best-effort and never rolls back the local write.

    Args:
        action_id: The ``action_id`` of the commitment to close.
        completed_at: ISO 8601 completion timestamp.  Defaults to UTC now.
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import mark_commitment_done

    try:
        vault_path = resolve_vault_path(vault)
        result = mark_commitment_done(vault_path, action_id, completed_at=completed_at)
        return json.dumps({"ok": True, **result}, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": {"type": "NotFound", "message": str(exc)}})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Postpone Commitment",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_postpone(
    action_id: str,
    until: str,
    vault: str | None = None,
) -> str:
    """Set or update the ``postponed_until`` date on a commitment.

    The follow-up log records the postponement.  When service integration
    is configured, the update is also PATCHed to the remote action.

    Args:
        action_id: The ``action_id`` of the commitment to postpone.
        until: ISO 8601 timestamp indicating when it should resurface.
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import postpone_commitment

    try:
        vault_path = resolve_vault_path(vault)
        result = postpone_commitment(vault_path, action_id, postponed_until=until)
        return json.dumps({"ok": True, **result}, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": {"type": "NotFound", "message": str(exc)}})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Add Reason to Commitment",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_add_reason(
    action_id: str,
    reason: str,
    vault: str | None = None,
) -> str:
    """Append a timestamped reason or note to a commitment's user-notes block.

    The reason is stored in the user-editable region of the commitment note
    and is preserved across future service syncs.

    Args:
        action_id: The ``action_id`` of the target commitment.
        reason: Non-empty text to append (e.g. why it was postponed).
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import add_commitment_reason

    try:
        vault_path = resolve_vault_path(vault)
        result = add_commitment_reason(vault_path, action_id, reason)
        return json.dumps({"ok": True, **result}, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": {"type": "NotFound", "message": str(exc)}})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="List Due Soon",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_due_soon(
    within_days: int = 3,
    vault: str | None = None,
) -> str:
    """List open commitments due within the next N days.

    Results are sorted earliest-due first.  Each item includes an
    ``overdue`` boolean when the due date is already past.

    Args:
        within_days: Look-ahead window in days (default 3).
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import list_due_soon

    try:
        vault_path = resolve_vault_path(vault)
        items = list_due_soon(vault_path, within_days=within_days)
        return json.dumps({"ok": True, "count": len(items), "commitments": items}, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Sync Commitments from Service",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_sync_commitments(
    service_url: str | None = None,
    vault: str | None = None,
) -> str:
    """Fetch open actions from obsidian-capture-service and write them as notes.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_URL`` and
    ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from environment when parameters are
    omitted.  When the service is unreachable, returns an error envelope
    without touching the vault.

    Args:
        service_url: Base URL of the capture service (overrides env var).
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_ops import sync_commitments_from_service

    try:
        vault_path = resolve_vault_path(vault)
        result = sync_commitments_from_service(vault_path, service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Refresh Review Dashboards",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_review_dashboards(
    stale_days: int = 14,
    merge_window_days: int = 14,
    merge_jaccard: float = 0.6,
    now: str | None = None,
    vault: str | None = None,
) -> str:
    """Regenerate the four review dashboards under ``Dashboards/Review/``.

    Writes ``Daily.md``, ``Weekly.md``, ``Stale.md``, and
    ``Merge Candidates.md`` deterministically from the current vault
    state.  Use this for on-demand inbox review; scheduled refresh uses
    :func:`obsidian_connector.commitment_dashboards.update_all_dashboards`.

    Args:
        stale_days: Threshold for Weekly + Stale surfaces (default 14).
        merge_window_days: Max days between created_at of candidate pairs.
        merge_jaccard: Minimum title token-Jaccard for candidate pairs.
        now: ISO 8601 reference timestamp (defaults to UTC now).
        vault: Target vault name (uses default if omitted).
    """
    from obsidian_connector.commitment_dashboards import (
        update_all_review_dashboards,
    )

    try:
        vault_path = resolve_vault_path(vault)
        results = update_all_review_dashboards(
            vault_path,
            now_iso=now,
            stale_days=stale_days,
            merge_window_days=merge_window_days,
            merge_jaccard=merge_jaccard,
        )
        payload = [
            {"path": str(r.path), "written": r.written} for r in results
        ]
        return json.dumps(
            {"ok": True, "count": len(payload), "dashboards": payload},
            indent=2,
        )
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 28: service retrieval helpers
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Find Commitments (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_find_commitments(
    status: str | None = None,
    lifecycle_stage: str | None = None,
    project: str | None = None,
    person: str | None = None,
    area: str | None = None,
    urgency: str | None = None,
    priority: str | None = None,
    source_app: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    service_url: str | None = None,
) -> str:
    """Query ``GET /api/v1/actions`` on the capture service.

    Filters are AND-joined. ``project``/``person``/``area`` resolve
    server-side through the alias table (case-insensitive). ``urgency``
    is post-filtered on the server after computing
    ``(priority, due_at, postponed_until, status)``.

    Pagination uses an opaque ``cursor``; when the response includes
    ``next_cursor``, pass it back verbatim on the next call to fetch
    the subsequent page.

    Args:
        status: Filter by action status (e.g. ``open``, ``awaiting_ack``).
        lifecycle_stage: Filter by lifecycle stage (e.g. ``active``).
        project: Project name (canonical or alias).
        person: Person name (canonical or alias).
        area: Area name (canonical or alias).
        urgency: ``low`` | ``normal`` | ``elevated`` | ``critical``.
        priority: ``low`` | ``normal`` | ``high`` | ``urgent``.
        source_app: e.g. ``wispr_flow`` or ``shortcut_text``.
        due_before: ISO 8601 timestamp.
        due_after: ISO 8601 timestamp.
        limit: Page size (default 50, max 200).
        cursor: Opaque pagination cursor from a prior response.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from environment. Never
    raises; errors are surfaced inside the JSON envelope.
    """
    from obsidian_connector.commitment_ops import list_service_actions

    try:
        result = list_service_actions(
            status=status,
            lifecycle_stage=lifecycle_stage,
            project=project,
            person=person,
            area=area,
            urgency=urgency,
            priority=priority,
            source_app=source_app,
            due_before=due_before,
            due_after=due_after,
            limit=limit,
            cursor=cursor,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Commitment Detail (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_commitment_detail(
    action_id: str,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/actions/{action_id}`` from the capture service.

    Returns the full action payload including entity buckets
    (projects/people/areas), delivery summary, and
    ``next_follow_up_at``. On 404 the envelope's ``status_code`` is
    404 and ``ok`` is False.

    Args:
        action_id: The action ULID (e.g. ``act_01HS...``).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
    """
    from obsidian_connector.commitment_ops import get_service_action

    try:
        result = get_service_action(action_id, service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Commitment Stats (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_commitment_stats(
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/actions/stats`` from the capture service.

    Returns ``total`` plus four grouped maps (``by_status``,
    ``by_lifecycle_stage``, ``by_priority``, ``by_source_app``). Zero-
    count keys are omitted.

    Args:
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
    """
    from obsidian_connector.commitment_ops import get_service_action_stats

    try:
        result = get_service_action_stats(service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Duplicate Candidates (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_duplicate_candidates(
    action_id: str,
    limit: int = 10,
    within_days: int = 30,
    min_score: float | None = None,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/actions/{action_id}/duplicate-candidates``.

    Returns the top-N likely duplicates for an action ranked by the
    service's deterministic score. Each candidate includes ``score``,
    ``tier`` (``strong`` | ``candidate`` | ``below_threshold``), and a
    ``reasons`` dict with title-Jaccard, shared people/areas, days
    apart, and due-close flags. Useful for a reviewer UI that wants to
    show *why* a pair was surfaced.

    Args:
        action_id: The base action ULID.
        limit: Page size (default 10, server caps at 50).
        within_days: Rolling window for the peer pool (default 30).
        min_score: Override the env-configured candidate threshold
            (defaults to 0.55 on the service side).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_duplicate_candidates

    try:
        result = list_duplicate_candidates(
            action_id,
            limit=limit,
            within_days=within_days,
            min_score=min_score,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Merge Commitment (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_merge_commitment(
    loser_id: str,
    winner_id: str,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/{loser_id}/merge`` on the capture service.

    Merges the loser action into the winner. The loser transitions to
    ``status='cancelled'``, ``lifecycle_stage='archived'`` and records
    ``postpone_reason="merged into {winner_id}"``. A duplicates edge is
    recorded ``loser -> winner`` at confidence 1.0. Idempotent on
    re-merge of the same pair.

    Args:
        loser_id: The action that will be cancelled + archived.
        winner_id: The action that survives (must be open-ish).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import merge_commitments

    try:
        result = merge_commitments(
            loser_id, winner_id, service_url=service_url
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 31: pattern intelligence tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Repeated Postponements (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_repeated_postponements(
    since_days: int = 30,
    limit: int = 50,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/patterns/repeated-postponements``.

    Returns actions with two or more ``postpone`` acknowledgements inside
    the window, sorted by count desc. Each row surfaces ``count``,
    ``cumulative_days_slipped``, ``last_reason``, and ISO timestamps
    for first/last postponement inside the window.

    Args:
        since_days: Rolling window (default 30, max 365).
        limit: Max rows (default 50, server caps at 200).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_repeated_postponements

    try:
        result = list_repeated_postponements(
            since_days=since_days, limit=limit, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Blocker Clusters (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_blocker_clusters(
    since_days: int = 60,
    limit: int = 50,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/patterns/blocker-clusters``.

    Returns actions that block many open downstream actions (via
    ``action_edges.relation='blocks'``). Only clusters where both
    endpoints are non-terminal. Each row carries ``blocks_count`` and a
    sorted ``downstream_action_ids`` list.

    Args:
        since_days: Window for the edge (default 60, max 365).
        limit: Max rows (default 50, server caps at 200).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_blocker_clusters

    try:
        result = list_blocker_clusters(
            since_days=since_days, limit=limit, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Recurring Unfinished (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_recurring_unfinished(
    by: str = "project",
    since_days: int = 90,
    limit: int = 50,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/patterns/recurring-unfinished``.

    Buckets open/postponed actions by a semantic anchor
    (``project`` | ``person`` | ``area``) and surfaces ``open_count``
    and ``median_age_days`` per bucket. Useful for "where is my open
    work concentrated?" reviews.

    Args:
        by: one of {"project", "person", "area"}.
        since_days: Window (default 90, max 365).
        limit: Max rows (default 50, server caps at 200).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_recurring_unfinished

    try:
        result = list_recurring_unfinished(
            by=by, since_days=since_days, limit=limit,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 32: why-still-open reasoning tool
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Explain Commitment (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_explain_commitment(
    action_id: str,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/actions/{action_id}/why-still-open``.

    Returns a deterministic explanation of why a still-open action has
    not closed yet — a list of reason bullets with machine codes
    (``OVERDUE_NO_MOVEMENT``, ``BLOCKED_BY_OPEN``,
    ``REPEATEDLY_POSTPONED``, ``WAITING_ON_PERSON``, ``STALE_INBOX``,
    ``HAS_DUPLICATES``, ``NO_OWNER_OR_PROJECT``,
    ``LOW_PRIORITY_NO_DUE``, ``NOT_YET_DUE``), human labels, and the
    input snippet that justifies each.

    Args:
        action_id: The action ULID.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    Returns 404 when the action is missing, 409 when it is already
    terminal (done/cancelled/expired).
    """
    from obsidian_connector.commitment_ops import explain_commitment

    try:
        result = explain_commitment(action_id, service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 38: delegation / waiting-on workflows
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Delegate Commitment (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_delegate_commitment(
    action_id: str,
    to_person: str,
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/{action_id}/delegate`` (Task 38).

    Assigns the action to a named person, creating the person entity
    on miss when the alias does not resolve. Moves ``lifecycle_stage``
    to ``waiting`` unless already in ``waiting``/``done``/``archived``.
    Idempotent on the same person (refreshes ``delegated_at``);
    swapping to a different person updates the FK and is logged with
    ``swapped_from_entity_id``.

    Args:
        action_id: The action ULID.
        to_person: Canonical name or alias of the delegate.
        note: Optional free-form delegation context.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import delegate_commitment

    try:
        result = delegate_commitment(
            action_id,
            to_person=to_person,
            note=note,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Reclaim Commitment (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_reclaim_commitment(
    action_id: str,
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/{action_id}/reclaim`` (Task 38).

    Clears the action's delegation columns and flips
    ``lifecycle_stage`` from ``waiting`` back to ``active`` when
    applicable. Idempotent on a non-delegated row (still records the
    audit ack).

    Args:
        action_id: The action ULID.
        note: Optional reclaim context.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import reclaim_commitment

    try:
        result = reclaim_commitment(
            action_id, note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Delegated To Person (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_delegated_to(
    person: str,
    limit: int = 50,
    cursor: str | None = None,
    include_terminal: bool = False,
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/actions/delegated-to/{person}`` (Task 38).

    Returns actions delegated to the named person (canonical or
    alias). By default only non-terminal rows are included; pass
    ``include_terminal=True`` for audit views. Keyset-paginated.

    Args:
        person: Canonical name or alias of the delegate.
        limit: Page size (default 50).
        cursor: Opaque keyset cursor returned by a previous page.
        include_terminal: Include done/cancelled/expired rows.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_delegated_to

    try:
        result = list_delegated_to(
            person,
            limit=limit,
            cursor=cursor,
            include_terminal=include_terminal,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Stale Delegations (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_stale_delegations(
    threshold_days: int = 14,
    limit: int = 50,
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/patterns/stale-delegations`` (Task 38).

    Returns per-person buckets of open actions whose ``delegated_at``
    is older than the threshold, sorted
    ``(count DESC, oldest_delegated_at ASC, canonical_name ASC)``.
    Each bucket carries up to 10 sample items.

    Args:
        threshold_days: Age in days (default 14; server bounds [1, 365]).
        limit: Max buckets (default 50; server bounds [1, 200]).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import list_stale_delegations

    try:
        result = list_stale_delegations(
            threshold_days=threshold_days,
            limit=limit,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 40: review coaching and recommendation layer
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Action Recommendations (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_action_recommendations(
    action_id: str,
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/coaching/action/{action_id}`` (Task 40).

    Returns deterministic review recommendations for a single open
    action. Each recommendation carries a machine code
    (``CONSIDER_CANCEL`` / ``CONSIDER_DELEGATE`` / ``CONSIDER_MERGE``
    / ``CONSIDER_RECLAIM`` / ``CONSIDER_RESCHEDULE`` /
    ``CONSIDER_UNBLOCK``), human label, action verb, fixed
    confidence score (0.6 / 0.7 / 0.8 / 0.9), rationale dict, and
    suggested inputs the caller can pass straight to the matching
    mutation endpoint. Recommendations are sorted alphabetically by
    ``code``.

    Args:
        action_id: The action ULID.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    Returns 404 when the action is missing, 409 when it is already
    terminal (done / cancelled / expired).
    """
    from obsidian_connector.coaching_ops import get_action_recommendations

    try:
        result = get_action_recommendations(
            action_id, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Review Recommendations (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_review_recommendations(
    since_days: int = 7,
    limit: int = 50,
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/coaching/review`` (Task 40).

    Bulk review surface over open actions touched in the window.
    Returns the top-N recommendable actions sorted by
    ``(impact_score DESC, action_id ASC)`` where impact blends
    urgency and recommendation count. Actions with zero
    recommendations are omitted from the response.

    Args:
        since_days: Rolling window against ``updated_at`` (default 7,
            max 365).
        limit: Max items (default 50, server cap 200).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.coaching_ops import list_review_recommendations

    try:
        result = list_review_recommendations(
            since_days=since_days, limit=limit, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 41: Mobile bulk actions
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Bulk Ack Commitments (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_ack(
    action_ids: list[str],
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/bulk-ack`` (Task 41).

    Batches ``awaiting_ack -> in_progress`` transitions atomically.
    Per-row skips (``missing | wrong_status | duplicate_id``) are
    reported without aborting. Server caps the batch at
    ``MAX_BULK_ACTION_IDS`` (default 50).

    Args:
        action_ids: Non-empty list of action ids.
        note: Optional note recorded on every ack audit row.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.commitment_ops import bulk_ack_commitments

    try:
        result = bulk_ack_commitments(
            action_ids, note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Bulk Done Commitments (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_done(
    action_ids: list[str],
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/bulk-done`` (Task 41).

    Batches non-terminal actions to ``done`` atomically. Sets
    ``completed_at`` server-side. Per-row skip envelope matches
    :func:`obsidian_bulk_ack`.
    """
    from obsidian_connector.commitment_ops import bulk_done_commitments

    try:
        result = bulk_done_commitments(
            action_ids, note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Bulk Postpone Commitments (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_postpone(
    action_ids: list[str],
    preset: str | None = None,
    postponed_until: str | None = None,
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/bulk-postpone`` (Task 41).

    Exactly one of ``preset`` or ``postponed_until`` must be supplied.
    The client-side wrapper validates exclusivity before hitting the
    network. The server echoes the resolved UTC ISO in
    ``data.resolved_postponed_until`` so callers never run their own
    preset math.

    Args:
        action_ids: Non-empty list of action ids.
        preset: Named preset (e.g. ``"tomorrow_9am"``). See
            :func:`obsidian_postpone_presets` for the current catalog.
        postponed_until: Explicit ISO 8601 datetime; accepts trailing
            ``Z``.
        note: Optional note recorded on the ack row and in
            ``actions.postpone_reason``.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
    """
    from obsidian_connector.commitment_ops import bulk_postpone_commitments

    try:
        result = bulk_postpone_commitments(
            action_ids, preset=preset, postponed_until=postponed_until,
            note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Bulk Cancel Commitments (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_cancel(
    action_ids: list[str],
    reason: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/actions/bulk-cancel`` (Task 41).

    Batches non-terminal actions to ``cancelled`` atomically.
    Optional ``reason`` is recorded on every ack row.
    """
    from obsidian_connector.commitment_ops import bulk_cancel_commitments

    try:
        result = bulk_cancel_commitments(
            action_ids, reason=reason, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Postpone Presets (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_postpone_presets(
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/actions/postpone-presets`` (Task 41).

    Read-only catalog of the named postpone presets the server
    accepts. Each entry carries ``name``, ``label``, and
    ``description``. Use the ``name`` field as the ``preset`` argument
    on :func:`obsidian_bulk_postpone`.
    """
    from obsidian_connector.commitment_ops import list_postpone_presets

    try:
        result = list_postpone_presets(service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 44: operational admin surfaces
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Queue Health (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_queue_health(
    since_hours: int = 24,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/admin/queue-health`` from the capture service.

    Returns the Neon ``capture_queue`` health snapshot: status counts,
    oldest pending row age (seconds), and error rate across the window.
    When the queue poller is disabled on the service side, ``enabled``
    is false and the counts are empty.

    Args:
        since_hours: Window in hours (default 24, max 720).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import get_queue_health

    try:
        result = get_queue_health(
            since_hours=since_hours, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Delivery Failures (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_delivery_failures(
    since_hours: int = 24,
    limit: int = 100,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/admin/delivery-failures``.

    Returns recent deliveries in ``failed`` or ``dead_letter`` status,
    joined with the parent action's title. Sorted by most recent
    ``scheduled_at`` first.

    Args:
        since_hours: Window in hours (default 24, max 720).
        limit: Max rows (default 100, server cap 500).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import list_delivery_failures

    try:
        result = list_delivery_failures(
            since_hours=since_hours, limit=limit, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Pending Approvals (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_pending_approvals(
    limit: int = 100,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/admin/pending-approvals``.

    Returns deliveries whose ``status = 'pending_approval'`` joined
    with action title, priority, and lifecycle stage. Sorted oldest
    first.

    Args:
        limit: Max rows (default 100, server cap 500).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import list_pending_approvals

    try:
        result = list_pending_approvals(
            limit=limit, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Stale Sync Devices (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_stale_sync_devices(
    threshold_hours: int = 24,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/admin/stale-sync-devices``.

    Returns devices whose ``last_sync_at`` is older than the
    threshold, or whose row has existed longer than the threshold with
    ``last_sync_at IS NULL``. Each row includes a pending-ops count
    from ``sync_operations``.

    Args:
        threshold_hours: Staleness threshold (default 24, max 8760).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import list_stale_sync_devices

    try:
        result = list_stale_sync_devices(
            threshold_hours=threshold_hours, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="System Health (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_system_health(
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/admin/system-health`` (composite summary).

    One-call operator summary wrapping the doctor report + compact
    counts of queue health, delivery failures, pending approvals, and
    stale sync devices. Includes an ``overall_status`` field
    (``ok`` / ``warn`` / ``fail``).

    Args:
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import get_system_health

    try:
        result = get_system_health(service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 42: Cross-device sync management
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Mobile Devices (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_mobile_devices(
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/mobile/devices`` (Task 42).

    Returns every registered device with human-readable label,
    platform, app version, first-seen timestamp, last-sync timestamp,
    pending operation count, and stored cursor. Sorted
    ``last_sync_at DESC NULLS LAST``.

    Args:
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import list_mobile_devices

    try:
        result = list_mobile_devices(service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Forget Mobile Device (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_forget_mobile_device(
    device_id: str,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/mobile/devices/{device_id}/forget`` (Task 42).

    Atomically drops the device's row from ``device_sync_state`` and
    supersedes all of its pending sync operations. Idempotent on a
    missing device id (returns ``deleted: False``). Acked operations
    are preserved for the audit trail.

    Args:
        device_id: The device id as listed by ``obsidian_mobile_devices``.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.admin_ops import forget_mobile_device

    try:
        result = forget_mobile_device(device_id, service_url=service_url)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 36: Approval UX (detail + bulk + digest)
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Delivery Detail (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_delivery_detail(
    delivery_id: str,
    service_url: str | None = None,
) -> str:
    """Fetch ``GET /api/v1/deliveries/{delivery_id}``.

    Returns the full approval context: delivery row + parent action +
    approval history + computed ``risk_factors`` list (Task 36). The
    risk factors are deterministic heuristics (no LLM) — see the
    service-side ADR at ``docs/architecture/task_36_approval_ux.md``.

    Args:
        delivery_id: Server-side delivery id (``dlv_...``).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.approval_ops import get_delivery_detail

    try:
        result = get_delivery_detail(
            delivery_id, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Bulk Approve Deliveries (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_approve(
    delivery_ids: list[str],
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/deliveries/bulk-approve``.

    Approves a batch of pending deliveries atomically. Per-row skips
    (missing id, wrong status, duplicate id) are reported without
    aborting. Server caps the batch at ``MAX_BULK_APPROVAL_IDS``
    (default 50).

    Args:
        delivery_ids: Non-empty list of delivery ids.
        note: Optional reason attached to every audit row.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.approval_ops import bulk_approve_deliveries

    try:
        result = bulk_approve_deliveries(
            delivery_ids, note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Bulk Reject Deliveries (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
def obsidian_bulk_reject(
    delivery_ids: list[str],
    note: str | None = None,
    service_url: str | None = None,
) -> str:
    """Call ``POST /api/v1/deliveries/bulk-reject``. Mirror of bulk-approve."""
    from obsidian_connector.approval_ops import bulk_reject_deliveries

    try:
        result = bulk_reject_deliveries(
            delivery_ids, note=note, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Approval Digest (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_approval_digest(
    since_hours: int = 24,
    service_url: str | None = None,
) -> str:
    """Call ``GET /api/v1/deliveries/approval-digest``.

    Returns the nightly-review summary: counts by channel, counts by
    urgency, age of oldest pending, top-5 pending approvals with
    risk factors, and the number of decisions in the window.

    Args:
        since_hours: Recent-decisions window (default 24, max 720).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.approval_ops import get_approval_digest

    try:
        result = get_approval_digest(
            since_hours=since_hours, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 39: Analytics (weekly activity report)
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Weekly Activity Report (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_weekly_report(
    week_offset: int = 0,
    service_url: str | None = None,
) -> str:
    """Fetch the Task 39 weekly activity report as JSON.

    Calls ``GET /api/v1/analytics/weekly?week_offset=...``. Returns the
    full envelope with ``window``, ``captures``, ``actions_created``,
    ``actions_completed``, ``actions_postponed``, ``lifecycle_transitions``,
    ``delivery_stats``, ``patterns_snapshot``, ``health_snapshot``.

    Args:
        week_offset: Shift from the current ISO week (``0`` = current,
            ``-1`` = last week). Bounded on the server to ``[-104, 104]``.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.analytics_ops import get_weekly_report

    try:
        result = get_weekly_report(
            week_offset=week_offset, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Weekly Activity Report - Markdown (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_weekly_report_markdown(
    week_offset: int = 0,
    service_url: str | None = None,
) -> str:
    """Fetch the Task 39 weekly activity report rendered as Markdown.

    Calls ``GET /api/v1/analytics/weekly/markdown?week_offset=...``.
    On success the envelope's ``data.markdown`` key holds the body.

    Args:
        week_offset: Shift from the current ISO week.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.analytics_ops import get_weekly_report_markdown

    try:
        result = get_weekly_report_markdown(
            week_offset=week_offset, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Analytics Weeks Available (via service)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_weeks_available(
    weeks_back: int = 12,
    service_url: str | None = None,
) -> str:
    """List past ISO-week windows with labels.

    Calls ``GET /api/v1/analytics/weeks-available?weeks_back=...``.
    Each item is ``{start_iso, end_iso, week_label}``.

    Args:
        weeks_back: How many past weeks to return (default 12, max 104).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from obsidian_connector.analytics_ops import list_weeks_available

    try:
        result = list_weeks_available(
            weeks_back=weeks_back, service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Write Weekly Report Note (Analytics/Weekly/)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_write_weekly_report(
    week_offset: int = 0,
    vault_root: str | None = None,
    service_url: str | None = None,
) -> str:
    """Fetch the weekly Markdown and project it into the vault.

    Writes ``Analytics/Weekly/<year>/<week_label>.md`` with deterministic
    frontmatter and a preserved ``service:analytics-user-notes:*`` fence.
    The path is idempotent — re-running with the same week produces the
    same file and never clobbers the user-notes block.

    Args:
        week_offset: Shift from the current ISO week (``0`` = current).
        vault_root: Vault root override. Defaults to ``$OBSIDIAN_VAULT_PATH``.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from pathlib import Path as _Path

    from obsidian_connector.analytics_ops import (
        fetch_and_write_weekly_report_note,
    )
    from obsidian_connector.config import resolve_vault_path

    try:
        root = _Path(vault_root) if vault_root else resolve_vault_path()
        result = fetch_and_write_weekly_report_note(
            root,
            week_offset=week_offset,
            service_url=service_url,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Task 43: Vault import / migration tools
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Plan Vault Import (scan + classify, no HTTP)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_plan_import(
    root: str,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    min_size: int = 10,
    max_size: int = 100_000,
    max_files: int = 1000,
) -> str:
    """Scan + classify a vault and return a deterministic import plan.

    Walks ``root`` recursively, classifies each ``*.md`` file
    (already-managed / ready-capture / unknown), and groups results
    into actionable buckets. **No HTTP. No mutation.** Pure planning.

    Args:
        root: Vault directory to scan. Absolute path or relative to cwd.
        include_globs: Optional list of POSIX globs to whitelist
            (e.g. ``["Inbox/**/*.md"]``).
        exclude_globs: Optional list of POSIX globs to drop
            (e.g. ``["Archive/**", ".obsidian/**"]``).
        min_size: Files smaller than this many bytes are skipped.
        max_size: Files larger than this many bytes are skipped.
        max_files: Hard cap; refuses cleanly if more than this many
            ``*.md`` files exist under ``root``.

    Returns a JSON envelope ``{ok: true, data: <plan_dict>}`` on
    success or ``{ok: false, error: "..."}`` on failure. Never raises.
    """
    from pathlib import Path as _Path

    from obsidian_connector.import_tools import plan_import, plan_to_dict

    try:
        plan = plan_import(
            _Path(root),
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            min_size=int(min_size),
            max_size=int(max_size),
            max_files=int(max_files),
        )
        return json.dumps({"ok": True, "data": plan_to_dict(plan)}, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


@mcp.tool(
    title="Execute Vault Import (POST /api/v1/ingest/text)",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
def obsidian_execute_import(
    root: str,
    dry_run: bool = True,
    confirm: bool = False,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    min_size: int = 10,
    max_size: int = 100_000,
    max_files: int = 1000,
    throttle_seconds: float = 0.1,
    source_app: str = "vault_import",
    service_url: str | None = None,
    write_report: bool = False,
    vault_root: str | None = None,
) -> str:
    """Plan then execute a vault import against ``/api/v1/ingest/text``.

    **Defaults to dry-run.** Requires both ``dry_run=False`` AND
    ``confirm=True`` to actually POST -- either alone returns a no-op
    result so a misconfigured agent cannot accidentally mutate.

    Each entry posts with deterministic
    ``X-Idempotency-Key: vault-import-<sha256[:16]>`` so re-runs
    collapse on the service-side Task 43 dedup substrate. Per-file
    failures are non-fatal: the loop continues and surfaces them in
    the result.

    Args:
        root: Directory to scan + import.
        dry_run: When True (default), no HTTP issued. Returns the
            planned result with ``dry_run=true``.
        confirm: Must be True (in addition to ``dry_run=False``) to
            actually issue HTTP. Belt-and-suspenders.
        include_globs / exclude_globs: Forwarded to ``plan_import``.
        min_size / max_size / max_files: Forwarded to ``plan_import``.
        throttle_seconds: Wait between successful POSTs (default 0.1s).
        source_app: ``source_app`` field on the ingest request body.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
        write_report: When True, also writes a Markdown report to
            ``<vault_root>/Analytics/Import/<ts>.md``.
        vault_root: Vault root for the report write. Defaults to
            ``$OBSIDIAN_VAULT_PATH`` when ``write_report=True``.

    Reads ``OBSIDIAN_CAPTURE_SERVICE_TOKEN`` from env. Never raises.
    """
    from pathlib import Path as _Path

    from obsidian_connector.config import resolve_vault_path
    from obsidian_connector.import_tools import (
        default_report_path,
        execute_import,
        plan_import,
        result_to_dict,
        write_import_report,
    )

    try:
        plan = plan_import(
            _Path(root),
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            min_size=int(min_size),
            max_size=int(max_size),
            max_files=int(max_files),
        )
        result = execute_import(
            plan,
            service_url=service_url,
            source_app=source_app,
            throttle_seconds=float(throttle_seconds),
            dry_run=bool(dry_run),
            confirm=bool(confirm),
        )
        report_info: dict | None = None
        if write_report:
            try:
                vroot = (
                    _Path(vault_root) if vault_root else resolve_vault_path()
                )
            except Exception:  # noqa: BLE001
                vroot = _Path(root)
            target = default_report_path(vroot)
            try:
                write_import_report(result, target, vault_root=vroot)
                report_info = {"ok": True, "path": str(target)}
            except Exception as exc:  # noqa: BLE001
                report_info = {"ok": False, "error": str(exc)}
        payload = {"ok": True, "data": result_to_dict(result)}
        if report_info is not None:
            payload["report"] = report_info
        return json.dumps(payload, indent=2)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        )


# ---------------------------------------------------------------------------
# Ix Memory commands (v0.9.0)
# ---------------------------------------------------------------------------


@mcp.tool(
    title="Ix: Map Workspace",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def obsidian_ix_map(
    path: str = ".",
    vault: str | None = None,
) -> str:
    """Trigger Ix to map or re-index the workspace/folder.

    This recursively parses code, tracing definitions, dependencies, and
    system boundaries, saving the system map to the `.ix` directory.

    Args:
        path: Path to map (defaults to '.' current working directory)
        vault: Target vault to map (overrides path if provided)
    """
    from obsidian_connector.ix_engine.runner import run_ix
    from obsidian_connector.config import resolve_vault_path
    import subprocess
    import sys

    try:
        target_path = str(resolve_vault_path(vault)) if vault else path
        from obsidian_connector.ix_engine.runner import IX_CLI_DIR, _setup_ix_if_needed
        _setup_ix_if_needed()
        main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
        
        result = subprocess.run(
            ["node", str(main_js_path), "map", target_path],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return json.dumps({"ok": False, "error": result.stderr})
        return json.dumps({"ok": True, "output": result.stdout})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Ix: Explain Concept",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_ix_explain(
    entity: str,
    vault: str | None = None,
) -> str:
    """Get an explanation of a codebase entity using the Ix system map.

    Args:
        entity: The name of the function, class, or service to explain
        vault: Target vault context (optional)
    """
    from obsidian_connector.ix_engine.runner import IX_CLI_DIR, _setup_ix_if_needed
    from obsidian_connector.config import resolve_vault_path
    import subprocess

    cwd = str(resolve_vault_path(vault)) if vault else "."
    
    try:
        _setup_ix_if_needed()
        main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
        result = subprocess.run(
            ["node", str(main_js_path), "explain", entity],
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return json.dumps({"ok": False, "error": result.stderr})
        return json.dumps({"ok": True, "output": result.stdout})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Ix: Trace Flow",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_ix_trace(
    flow: str,
    vault: str | None = None,
) -> str:
    """Trace a control flow or data path through the system using Ix.

    Args:
        flow: The entrypoint or flow name to trace.
        vault: Target vault context (optional).
    """
    from obsidian_connector.ix_engine.runner import IX_CLI_DIR, _setup_ix_if_needed
    from obsidian_connector.config import resolve_vault_path
    import subprocess

    cwd = str(resolve_vault_path(vault)) if vault else "."
    
    try:
        _setup_ix_if_needed()
        main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
        result = subprocess.run(
            ["node", str(main_js_path), "trace", flow],
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return json.dumps({"ok": False, "error": result.stderr})
        return json.dumps({"ok": True, "output": result.stdout})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Ix: Analyze Impact",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_ix_impact(
    entity: str,
    vault: str | None = None,
) -> str:
    """Analyze the downstream impact of changing a specific codebase entity.

    Args:
        entity: The target function, class, or module.
        vault: Target vault context (optional).
    """
    from obsidian_connector.ix_engine.runner import IX_CLI_DIR, _setup_ix_if_needed
    from obsidian_connector.config import resolve_vault_path
    import subprocess

    cwd = str(resolve_vault_path(vault)) if vault else "."
    
    try:
        _setup_ix_if_needed()
        main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
        result = subprocess.run(
            ["node", str(main_js_path), "impact", entity],
            cwd=cwd,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return json.dumps({"ok": False, "error": result.stderr})
        return json.dumps({"ok": True, "output": result.stdout})
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


@mcp.tool(
    title="Investigate Topic (Progressive Context)",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def obsidian_investigate(
    topic: str,
    vault: str | None = None,
) -> str:
    """Investigate a concept, feature, or code module using progressive disclosure.

    This "Super Tool" combines local Obsidian search with Ix system mapping.
    Instead of reading full files, it:
    1. Semantically searches the vault for related notes & summarizes them.
    2. Runs 'ix explain' on the topic to extract system architecture context.
    3. Returns a compact, token-efficient bundle.

    Args:
        topic: The concept or code module to investigate.
        vault: Target vault name (uses default if omitted).
    """
    import subprocess
    from obsidian_connector.config import resolve_vault_path
    from obsidian_connector.ix_engine.runner import IX_CLI_DIR, _setup_ix_if_needed
    from obsidian_connector.research import find_prior_work
    
    try:
        vault_path = resolve_vault_path(vault)
        
        # 1. Get knowledge from Obsidian Vault
        try:
            vault_results = find_prior_work(query=topic, top_n=3, vault_path=vault_path)
            vault_summary = "\n".join([
                f"- **{res['id']}** (Score: {res['score']:.2f})\n  Excerpts: {res['content'][:250]}..."
                for res in vault_results
            ])
            if not vault_results:
                vault_summary = "No relevant Obsidian notes found."
        except Exception as e:
            vault_summary = f"Vault search unavailable: {e}"

        # 2. Get system context from Ix Engine
        cwd = str(vault_path)
        try:
            _setup_ix_if_needed()
            main_js_path = IX_CLI_DIR / "dist" / "cli" / "main.js"
            ix_result = subprocess.run(
                ["node", str(main_js_path), "explain", topic],
                cwd=cwd,
                capture_output=True,
                text=True
            )
            if ix_result.returncode == 0 and ix_result.stdout.strip():
                ix_summary = ix_result.stdout.strip()
            else:
                ix_summary = "No architectural map context found in Ix for this topic."
        except Exception as e:
            ix_summary = f"Ix mapping unavailable: {e}"

        # 3. Combine and return
        payload = (
            f"=== INVESTIGATION REPORT: {topic} ===\n\n"
            f"--- 1. KNOWLEDGE BASE (OBSIDIAN) ---\n{vault_summary}\n\n"
            f"--- 2. SYSTEM MAP (IX ENGINE) ---\n{ix_summary}\n"
        )
        return json.dumps({"ok": True, "report": payload}, indent=2)

    except Exception as exc:
        return json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})


def main() -> None:
    """Run the MCP server.

    Default transport is stdio (for claude_desktop_config.json).
    Pass ``--http`` to start a Streamable HTTP server on port 8000
    (for the Claude Desktop "Add custom connector" UI).
    """
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
