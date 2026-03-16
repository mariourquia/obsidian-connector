"""MCP server exposing obsidian-connector tools for Claude Desktop."""

from __future__ import annotations

import json
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from obsidian_connector.client import (
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
    VaultNotFound,
)
from obsidian_connector.graph import NoteIndex
from obsidian_connector.thinking import (
    deep_ideas,
    drift_analysis,
    ghost_voice_profile,
    trace_idea,
)
from obsidian_connector.config import resolve_vault_path
from obsidian_connector.index_store import IndexStore, load_or_build_index
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
def obsidian_search(query: str, vault: str | None = None) -> str:
    """Search across all notes in the Obsidian vault.

    Returns matching files with line numbers and text excerpts.
    Use this to find notes on a topic, locate prior work, or check
    if something already exists in the vault.
    """
    try:
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

        # Resolve the note path: try exact match, then by title, then with .md suffix.
        resolved = None
        if note_path in idx.notes:
            resolved = note_path
        else:
            for path, entry in idx.notes.items():
                if entry.title.lower() == note_path.lower():
                    resolved = path
                    break
            if resolved is None and not note_path.endswith(".md"):
                candidate = note_path + ".md"
                if candidate in idx.notes:
                    resolved = candidate

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

        # Resolve the note path.
        resolved = None
        if note_path in idx.notes:
            resolved = note_path
        else:
            for path, entry in idx.notes.items():
                if entry.title.lower() == note_path.lower():
                    resolved = path
                    break
            if resolved is None and not note_path.endswith(".md"):
                candidate = note_path + ".md"
                if candidate in idx.notes:
                    resolved = candidate

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


@mcp.tool(
    title="Uninstall obsidian-connector",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def uninstall(
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
