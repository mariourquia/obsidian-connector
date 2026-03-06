"""Higher-level workflows built on top of the core client functions."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from obsidian_connector.audit import log_action
from obsidian_connector.client import (
    ObsidianCLIError,
    batch_read_notes,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)
from obsidian_connector.config import load_config, resolve_vault_path
from obsidian_connector.graph import extract_links


# ---------------------------------------------------------------------------
# Graph index helper
# ---------------------------------------------------------------------------

def _load_or_build_index(vault: str | None = None):
    """Delegate to the canonical shared implementation."""
    from obsidian_connector.index_store import load_or_build_index

    return load_or_build_index(vault)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INLINE_FIELD_RE = re.compile(r"^[A-Za-z_][\w\s]*::.*$")


def _extract_note_summary(text: str) -> tuple[str, str]:
    """Extract the first heading and first paragraph from markdown.

    Skips Obsidian inline-field lines (``key:: value``) and YAML
    frontmatter (``---`` fences).

    Returns
    -------
    tuple[str, str]
        (heading_or_first_line, first_paragraph_text)
    """
    lines = text.split("\n")
    heading = ""
    paragraph_lines: list[str] = []
    in_frontmatter = False
    found_heading = False

    for i, raw in enumerate(lines):
        stripped = raw.strip()

        # Skip YAML frontmatter block.
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Skip inline-field lines (e.g. "tags:: #on/Health").
        if _INLINE_FIELD_RE.match(stripped):
            continue

        # Skip blank lines (but they terminate the first paragraph).
        if not stripped:
            if found_heading and paragraph_lines:
                break
            continue

        if not found_heading:
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
            else:
                heading = stripped
            found_heading = True
            continue

        # Stop at the next heading.
        if stripped.startswith("#"):
            break

        paragraph_lines.append(stripped)

    return heading, " ".join(paragraph_lines)


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def log_decision(
    project: str,
    summary: str,
    details: str,
    vault: str | None = None,
) -> None:
    """Append a structured decision record to today's daily note.

    The resulting markdown block looks like::

        ## Decision -- <project>
        **Time:** 2026-03-05T14:32:00+00:00
        - **Summary:** <summary>

        <details>

    Parameters
    ----------
    project:
        Project or workstream name (used in the heading).
    summary:
        One-line description of the decision.
    details:
        Longer context, rationale, or follow-up items (markdown OK).
    vault:
        Target vault name.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    block = (
        f"## Decision -- {project}\n"
        f"**Time:** {ts}\n"
        f"- **Summary:** {summary}\n"
        f"\n"
        f"{details}"
    )
    log_to_daily(block, vault=vault)


def create_research_note(
    title: str,
    template: str,
    vault: str | None = None,
) -> str:
    """Create a new note from a template and return its vault-relative path.

    Parameters
    ----------
    title:
        Note title (becomes the file name).
    template:
        Template name as shown by ``obsidian templates`` (e.g.
        ``"Template, Note"``).
    vault:
        Target vault name.

    Returns
    -------
    str
        Vault-relative path of the created note (e.g. ``"My Note.md"``).

    Raises
    ------
    ObsidianCLIError
        If the CLI reports an error (template not found, etc.).
    """
    stdout = run_obsidian(
        ["create", f"name={title}", f"template={template}", "open"],
        vault=vault,
    )
    stripped = stdout.strip()

    # The CLI returns exit 0 even on errors; detect via stdout content.
    if stripped.startswith("Error:"):
        raise ObsidianCLIError(
            command=["create"],
            returncode=0,
            stdout=stdout,
            stderr=stripped,
        )

    # Expected: "Created: <path>"
    if stripped.startswith("Created:"):
        return stripped.removeprefix("Created:").strip()

    # Fallback: search for the note by title.
    results = search_notes(title, vault=vault)
    for r in results:
        fname: str = r.get("file", "")
        if title.lower() in fname.lower():
            return fname

    return f"{title}.md"


def find_prior_work(
    topic: str,
    vault: str | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Search for existing notes on *topic* and return structured summaries.

    Parameters
    ----------
    topic:
        Search query.
    vault:
        Target vault name.
    top_n:
        Maximum number of notes to return (default 5).

    Returns
    -------
    list[dict]
        Each dict contains:

        - ``file`` -- vault-relative path
        - ``heading`` -- first markdown heading (or first non-empty line)
        - ``excerpt`` -- first paragraph after the heading
        - ``match_count`` -- number of search matches in that note
        - ``backlink_count`` -- number of notes linking to it (graph-enriched, optional)
        - ``shared_tags`` -- tags on the note (graph-enriched, optional)
    """
    hits = search_notes(topic, vault=vault)[:top_n]
    results: list[dict] = []

    for hit in hits:
        file_path: str = hit.get("file", "")
        match_count = len(hit.get("matches", []))

        try:
            content = read_note(file_path, vault=vault)
        except ObsidianCLIError:
            content = ""

        heading, excerpt = _extract_note_summary(content)
        results.append(
            {
                "file": file_path,
                "heading": heading,
                "excerpt": excerpt[:300],
                "match_count": match_count,
            }
        )

    # Graph enrichment: add backlink_count and shared_tags if index available.
    idx = _load_or_build_index(vault)
    if idx is not None:
        for r in results:
            file_path = r["file"]
            bl = idx.backlinks.get(file_path, set())
            r["backlink_count"] = len(bl)
            entry = idx.notes.get(file_path)
            r["shared_tags"] = list(entry.tags) if entry else []

    return results


# ---------------------------------------------------------------------------
# Workflow OS tools
# ---------------------------------------------------------------------------

def list_open_loops(
    vault: str | None = None,
    lookback_days: int = 30,
) -> list[dict]:
    """Find open loops in the vault.

    Convention: lines starting with ``OL:`` or notes tagged with
    ``#openloop``.

    Parameters
    ----------
    vault:
        Target vault name.
    lookback_days:
        Not currently used for filtering (reserved for future date-based
        pruning).

    Returns
    -------
    list[dict]
        Each dict contains:

        - ``text`` -- the open loop text
        - ``file`` -- source file
        - ``line`` -- line number
        - ``source`` -- ``"OL:"`` or ``"#openloop"``
    """
    seen: set[tuple[str, int]] = set()
    results: list[dict] = []

    for source_tag, query in [("OL:", "OL:"), ("#openloop", "#openloop")]:
        try:
            hits = search_notes(query, vault=vault)
        except ObsidianCLIError:
            hits = []
        for hit in hits:
            file_path: str = hit.get("file", "")
            for match in hit.get("matches", []):
                line_num: int = match.get("line", 0)
                key = (file_path, line_num)
                if key in seen:
                    continue
                seen.add(key)
                text = match.get("text", "").strip()
                results.append(
                    {
                        "text": text,
                        "file": file_path,
                        "line": line_num,
                        "source": source_tag,
                    }
                )

    return results


def my_world_snapshot(
    vault: str | None = None,
    lookback_days: int = 14,
) -> dict:
    """Return a snapshot of the vault state.

    Parameters
    ----------
    vault:
        Target vault name.
    lookback_days:
        Number of days to look back for daily notes (clamped to 1-90).

    Returns
    -------
    dict
        Keys:

        - ``recent_daily_notes`` -- list of daily note names found
        - ``open_tasks`` -- list of incomplete tasks (up to 20)
        - ``open_loops`` -- list of open loop items
        - ``vault_stats`` -- ``{total_files: int}``
        - ``recent_searches_hint`` -- a hint about what to search next
    """
    lookback_days = min(max(1, lookback_days), 90)

    # Open tasks
    try:
        open_tasks = list_tasks(filter={"todo": True, "limit": 20}, vault=vault)
    except ObsidianCLIError:
        open_tasks = []

    # Open loops
    open_loops = list_open_loops(vault=vault, lookback_days=lookback_days)

    # Vault stats
    total_files = 0
    try:
        stdout = run_obsidian(["files", "total"], vault=vault)
        stripped = stdout.strip()
        # Extract the integer from output like "Total: 123" or just "123"
        digits = re.search(r"\d+", stripped)
        if digits:
            total_files = int(digits.group())
    except ObsidianCLIError:
        pass

    # Recent daily notes
    today = datetime.now(timezone.utc).date()
    recent_daily_notes: list[str] = []
    for i in range(lookback_days):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        try:
            hits = search_notes(day_str, vault=vault)
            for hit in hits:
                fname: str = hit.get("file", "")
                if day_str in fname and fname not in recent_daily_notes:
                    recent_daily_notes.append(fname)
        except ObsidianCLIError:
            continue

    # Build hint based on what we found
    hint_parts: list[str] = []
    if open_tasks:
        hint_parts.append(f"review {len(open_tasks)} open tasks")
    if open_loops:
        hint_parts.append(f"check {len(open_loops)} open loops")
    if not recent_daily_notes:
        hint_parts.append("create today's daily note")
    hint = "Try: " + ", ".join(hint_parts) if hint_parts else "Vault looks tidy."

    result = {
        "recent_daily_notes": recent_daily_notes,
        "open_tasks": open_tasks,
        "open_loops": open_loops,
        "vault_stats": {"total_files": total_files},
        "recent_searches_hint": hint,
    }

    # Graph enrichment: add vault_summary from index if available.
    idx = _load_or_build_index(vault)
    if idx is not None:
        top_tags = sorted(
            ((tag, len(paths)) for tag, paths in idx.tags.items()),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        result["vault_summary"] = {
            "total_notes": len(idx.notes),
            "orphan_count": len(idx.orphans),
            "dead_end_count": len(idx.dead_ends),
            "top_tags": [tag for tag, _count in top_tags],
        }

    return result


def today_brief(vault: str | None = None) -> dict:
    """Return a brief for today.

    Parameters
    ----------
    vault:
        Target vault name.

    Returns
    -------
    dict
        Keys:

        - ``date`` -- today's date string
        - ``daily_note`` -- content of today's daily note, or ``None``
        - ``open_tasks`` -- list of incomplete tasks (up to 10)
        - ``open_loops`` -- list of open loop items from recent notes
        - ``linked_context`` -- excerpts from notes linked in the daily note (graph-enriched)
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Try to read today's daily note
    daily_note: str | None = None
    try:
        daily_note = read_note(today_str, vault=vault)
    except ObsidianCLIError:
        pass

    # Open tasks
    try:
        open_tasks = list_tasks(filter={"todo": True, "limit": 10}, vault=vault)
    except ObsidianCLIError:
        open_tasks = []

    # Open loops (recent)
    open_loops = list_open_loops(vault=vault, lookback_days=7)

    # Graph enrichment: extract wikilinks from daily note and read linked notes.
    linked_context: list[dict] = []
    if daily_note:
        try:
            from obsidian_connector.graph import extract_links
            links = extract_links(daily_note)
            for link_target in links[:5]:
                try:
                    linked_content = read_note(link_target, vault=vault)
                    heading, excerpt = _extract_note_summary(linked_content)
                    linked_context.append({
                        "file": link_target,
                        "heading": heading,
                        "excerpt": excerpt[:300],
                    })
                except (ObsidianCLIError, Exception):
                    continue
        except Exception:
            pass

    return {
        "date": today_str,
        "daily_note": daily_note,
        "open_tasks": open_tasks,
        "open_loops": open_loops,
        "linked_context": linked_context,
    }


def close_day_reflection(vault: str | None = None) -> dict:
    """Generate an end-of-day reflection prompt (READ-ONLY).

    This function does NOT write to the vault. It gathers the day's data
    and returns structured reflection prompts.

    Parameters
    ----------
    vault:
        Target vault name.

    Returns
    -------
    dict
        Keys:

        - ``date`` -- today's date string
        - ``daily_note_summary`` -- first 500 chars of today's note, or ``None``
        - ``completed_tasks`` -- list of done tasks
        - ``remaining_tasks`` -- list of todo tasks
        - ``reflection_prompts`` -- 3-5 reflection questions
        - ``suggested_actions`` -- action candidates extracted from tasks/notes
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Read today's daily note
    daily_note_summary: str | None = None
    try:
        content = read_note(today_str, vault=vault)
        daily_note_summary = content[:500] if content else None
    except ObsidianCLIError:
        pass

    # Completed tasks
    try:
        completed_tasks = list_tasks(filter={"done": True, "limit": 20}, vault=vault)
    except ObsidianCLIError:
        completed_tasks = []

    # Remaining tasks
    try:
        remaining_tasks = list_tasks(filter={"todo": True, "limit": 20}, vault=vault)
    except ObsidianCLIError:
        remaining_tasks = []

    # Build reflection prompts based on the day's data
    prompts: list[str] = [
        "What was the most important thing you accomplished today?",
        "What blocked you or slowed you down?",
        "What will you prioritize tomorrow?",
    ]
    if completed_tasks:
        prompts.append(
            f"You completed {len(completed_tasks)} task(s). "
            "Which had the highest impact?"
        )
    if remaining_tasks:
        prompts.append(
            f"You have {len(remaining_tasks)} task(s) still open. "
            "Which should be dropped or delegated?"
        )

    # Suggested actions from remaining tasks
    suggested_actions: list[str] = []
    for task in remaining_tasks[:5]:
        text = task.get("text", "").strip()
        if text:
            # Strip markdown checkbox prefix
            cleaned = re.sub(r"^-\s*\[.\]\s*", "", text)
            if cleaned:
                suggested_actions.append(cleaned)

    return {
        "date": today_str,
        "daily_note_summary": daily_note_summary,
        "completed_tasks": completed_tasks,
        "remaining_tasks": remaining_tasks,
        "reflection_prompts": prompts,
        "suggested_actions": suggested_actions,
    }


# ---------------------------------------------------------------------------
# Thinking tools
# ---------------------------------------------------------------------------

_NEGATION_PATTERNS = re.compile(
    r"\b(not|risk|problem|failed|wrong|however|but|despite|although|"
    r"unlikely|concern|drawback|limitation|caveat|downside|flaw|issue|"
    r"challenge|obstacle|threat|weakness|contradiction)\b",
    re.IGNORECASE,
)


def challenge_belief(
    belief: str,
    vault: str | None = None,
    max_evidence: int = 10,
) -> dict:
    """Search vault for counter-evidence to a stated belief.

    Extracts key terms from *belief*, searches for them alongside
    negation patterns, reads matching notes, and classifies each match
    as counter or supporting evidence.

    Parameters
    ----------
    belief:
        The belief or assumption to challenge.
    vault:
        Target vault name.
    max_evidence:
        Maximum evidence items to return (default 10).

    Returns
    -------
    dict
        Keys: ``belief``, ``counter_evidence``, ``supporting_evidence``,
        ``verdict``.
    """
    # Extract key terms from the belief (words >= 4 chars, skip stopwords).
    stopwords = {
        "that", "this", "with", "from", "have", "been", "will", "would",
        "should", "could", "about", "their", "there", "which", "these",
        "those", "than", "then", "into", "only", "also", "more", "most",
        "some", "such", "what", "when", "where", "does", "very",
    }
    words = re.findall(r"[A-Za-z]{4,}", belief)
    key_terms = [w for w in words if w.lower() not in stopwords]

    if not key_terms:
        key_terms = belief.split()[:3]

    counter_evidence: list[dict] = []
    supporting_evidence: list[dict] = []
    seen_files: set[str] = set()

    # Search for each key term.
    for term in key_terms:
        if len(counter_evidence) + len(supporting_evidence) >= max_evidence:
            break
        try:
            hits = search_notes(term, vault=vault)
        except ObsidianCLIError:
            continue

        for hit in hits:
            if len(counter_evidence) + len(supporting_evidence) >= max_evidence:
                break

            file_path: str = hit.get("file", "")
            if file_path in seen_files:
                continue
            seen_files.add(file_path)

            try:
                content = read_note(file_path, vault=vault)
            except ObsidianCLIError:
                content = ""

            heading, excerpt = _extract_note_summary(content)

            # Classify based on negation patterns in match context.
            match_texts = " ".join(
                m.get("text", "") for m in hit.get("matches", [])
            )
            has_negation = bool(_NEGATION_PATTERNS.search(match_texts))

            entry = {
                "file": file_path,
                "heading": heading,
                "excerpt": excerpt[:300],
                "relevance": "counter" if has_negation else "supporting",
            }

            if has_negation:
                counter_evidence.append(entry)
            else:
                supporting_evidence.append(entry)

    # Build verdict.
    notes_checked = len(seen_files)
    verdict = (
        f"Found {len(counter_evidence)} piece(s) of counter-evidence and "
        f"{len(supporting_evidence)} supporting across {notes_checked} notes"
    )

    return {
        "belief": belief,
        "counter_evidence": counter_evidence,
        "supporting_evidence": supporting_evidence,
        "verdict": verdict,
    }


def emerge_ideas(
    topic: str,
    vault: str | None = None,
    max_clusters: int = 5,
) -> dict:
    """Cluster related notes into idea groups around *topic*.

    Groups search results by folder path prefix, reads the top note in
    each cluster, and returns summaries.

    Parameters
    ----------
    topic:
        Topic to explore.
    vault:
        Target vault name.
    max_clusters:
        Maximum number of clusters to return (default 5).

    Returns
    -------
    dict
        Keys: ``topic``, ``total_notes``, ``clusters``.
    """
    try:
        hits = search_notes(topic, vault=vault)
    except ObsidianCLIError:
        hits = []

    # Group by folder (path prefix up to last /).
    folder_map: dict[str, list[dict]] = {}
    for hit in hits:
        file_path: str = hit.get("file", "")
        folder = os.path.dirname(file_path) or "(root)"
        folder_map.setdefault(folder, []).append(hit)

    # Sort clusters by count descending and limit.
    sorted_folders = sorted(folder_map.items(), key=lambda x: len(x[1]), reverse=True)
    sorted_folders = sorted_folders[:max_clusters]

    clusters: list[dict] = []
    for folder, folder_hits in sorted_folders:
        notes: list[dict] = []
        for hit in folder_hits:
            file_path = hit.get("file", "")
            try:
                content = read_note(file_path, vault=vault)
            except ObsidianCLIError:
                content = ""
            heading, excerpt = _extract_note_summary(content)
            notes.append({
                "file": file_path,
                "heading": heading,
                "excerpt": excerpt[:300],
            })
            # Only read the first note per cluster for summary.
            if len(notes) >= 1:
                # Add remaining notes without reading content.
                for remaining in folder_hits[len(notes):]:
                    r_file = remaining.get("file", "")
                    notes.append({
                        "file": r_file,
                        "heading": "",
                        "excerpt": "",
                    })
                break

        clusters.append({
            "folder": folder,
            "notes": notes,
            "count": len(folder_hits),
        })

    return {
        "topic": topic,
        "total_notes": len(hits),
        "clusters": clusters,
    }


def connect_domains(
    domain_a: str,
    domain_b: str,
    vault: str | None = None,
    max_connections: int = 10,
) -> dict:
    """Find connections between two domains in the vault.

    Searches for each domain separately, then finds notes that appear
    in both result sets (the intersection).

    Parameters
    ----------
    domain_a:
        First domain to search.
    domain_b:
        Second domain to search.
    vault:
        Target vault name.
    max_connections:
        Maximum connecting notes to return (default 10).

    Returns
    -------
    dict
        Keys: ``domain_a``, ``domain_b``, ``connections``,
        ``domain_a_only``, ``domain_b_only``.
    """
    try:
        hits_a = search_notes(domain_a, vault=vault)
    except ObsidianCLIError:
        hits_a = []

    try:
        hits_b = search_notes(domain_b, vault=vault)
    except ObsidianCLIError:
        hits_b = []

    # Build file -> match_count maps.
    map_a: dict[str, int] = {}
    for hit in hits_a:
        f = hit.get("file", "")
        map_a[f] = len(hit.get("matches", []))

    map_b: dict[str, int] = {}
    for hit in hits_b:
        f = hit.get("file", "")
        map_b[f] = len(hit.get("matches", []))

    # Intersection = connections.
    shared_files = set(map_a.keys()) & set(map_b.keys())
    a_only = sorted(set(map_a.keys()) - shared_files)
    b_only = sorted(set(map_b.keys()) - shared_files)

    connections: list[dict] = []
    for file_path in sorted(shared_files):
        if len(connections) >= max_connections:
            break

        try:
            content = read_note(file_path, vault=vault)
        except ObsidianCLIError:
            content = ""

        heading, excerpt = _extract_note_summary(content)
        connections.append({
            "file": file_path,
            "heading": heading,
            "excerpt": excerpt[:300],
            "match_a": map_a.get(file_path, 0),
            "match_b": map_b.get(file_path, 0),
        })

    return {
        "domain_a": domain_a,
        "domain_b": domain_b,
        "connections": connections,
        "domain_a_only": a_only,
        "domain_b_only": b_only,
    }
# ---------------------------------------------------------------------------

# Patterns that indicate an idea worth promoting to a standalone note.
_IDEA_TAG_RE = re.compile(r"#(?:idea|insight)\b", re.IGNORECASE)
_EXPAND_RE = re.compile(
    r"(?:TODO:\s*expand|flesh\s+out|write\s+up|develop\s+further)",
    re.IGNORECASE,
)
_WIKILINK_RE_GRAD = re.compile(r"\[\[[^\]]+\]\]")


def _score_candidate(
    tags: list[str], link_count: int, has_expand: bool
) -> int:
    """Compute a richness score for ranking graduate candidates."""
    score = link_count * 2
    score += len(tags) * 3
    if has_expand:
        score += 5
    return score


def graduate_candidates(
    vault: str | None = None,
    lookback_days: int = 7,
) -> list[dict]:
    """Scan recent daily notes for ideas worth promoting to standalone notes.

    Patterns detected:

    - Headings (## or ###) with 3+ lines of content beneath
    - Paragraphs containing 3+ ``[[wikilinks]]``
    - Lines tagged ``#idea`` or ``#insight``
    - Lines containing "TODO: expand", "flesh out", "write up", "develop further"

    For each candidate the :class:`~obsidian_connector.graph.NoteIndex` is
    checked for an existing standalone note.

    Parameters
    ----------
    vault:
        Target vault name.
    lookback_days:
        Number of days to look back for daily notes (default 7).

    Returns
    -------
    list[dict]
        Each dict contains:

        - ``title`` -- candidate title
        - ``source_file`` -- daily note path
        - ``excerpt`` -- first ~200 chars of the candidate section
        - ``existing_note`` -- path of an existing standalone note, or ``None``
        - ``tags`` -- list of tags found in the section
        - ``suggested_template`` -- template name hint
    """
    # Use the same daily-note lookback pattern as my_world_snapshot().
    today = datetime.now(timezone.utc).date()
    daily_notes: list[tuple[str, str]] = []  # (file_path, content)

    for i in range(lookback_days):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        try:
            hits = search_notes(day_str, vault=vault)
        except ObsidianCLIError:
            continue
        for hit in hits:
            fname: str = hit.get("file", "")
            if day_str in fname:
                try:
                    content = read_note(fname, vault=vault)
                except ObsidianCLIError:
                    continue
                daily_notes.append((fname, content))

    # Deduplicate by file path (same note may appear across multiple day searches).
    seen_files: set[str] = set()
    unique_notes: list[tuple[str, str]] = []
    for fpath, content in daily_notes:
        if fpath not in seen_files:
            seen_files.add(fpath)
            unique_notes.append((fpath, content))

    candidates: list[dict] = []

    for source_file, content in unique_notes:
        lines = content.split("\n")
        _scan_for_candidates(source_file, lines, candidates)

    # Try to check NoteIndex for existing standalone notes.
    try:
        index = _load_or_build_index(vault)
        if index is not None:
            title_set = {
                entry.title.lower(): entry.path
                for entry in index.notes.values()
            }
        else:
            title_set = {}
    except Exception:
        title_set = {}

    for cand in candidates:
        title_lower = cand["title"].lower()
        cand["existing_note"] = title_set.get(title_lower)

    # Sort by richness score descending.
    candidates.sort(
        key=lambda c: _score_candidate(
            c["tags"],
            c.get("_link_count", 0),
            c.get("_has_expand", False),
        ),
        reverse=True,
    )

    # Strip internal scoring fields.
    for cand in candidates:
        cand.pop("_link_count", None)
        cand.pop("_has_expand", None)

    return candidates


def _scan_for_candidates(
    source_file: str,
    lines: list[str],
    candidates: list[dict],
) -> None:
    """Scan lines of a daily note for promotable sections.

    Mutates *candidates* in place.
    """
    i = 0
    seen_titles: set[str] = set()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Pattern 1: headings with 3+ lines of content.
        if stripped.startswith("## ") or stripped.startswith("### "):
            heading_title = stripped.lstrip("#").strip()
            block_lines: list[str] = []
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith("## ") or next_stripped.startswith("### "):
                    break
                block_lines.append(next_stripped)
                j += 1

            content_lines = [l for l in block_lines if l]
            if len(content_lines) >= 3 and heading_title not in seen_titles:
                seen_titles.add(heading_title)
                block_text = "\n".join(block_lines)
                tags = _IDEA_TAG_RE.findall(block_text)
                all_tags_in_block = re.findall(
                    r"#[\w][\w/]*", block_text
                )
                link_count = len(_WIKILINK_RE_GRAD.findall(block_text))
                has_expand = bool(_EXPAND_RE.search(block_text))
                candidates.append({
                    "title": heading_title,
                    "source_file": source_file,
                    "excerpt": block_text[:200],
                    "existing_note": None,
                    "tags": all_tags_in_block,
                    "suggested_template": "Template, Note",
                    "_link_count": link_count,
                    "_has_expand": has_expand,
                })
            i = j
            continue

        # Pattern 2: paragraphs with 3+ wikilinks.
        links_in_line = _WIKILINK_RE_GRAD.findall(stripped)
        if len(links_in_line) >= 3:
            # Use the first wikilink target as the title.
            first_link = re.search(r"\[\[([^\]|]+)", stripped)
            title = first_link.group(1).strip() if first_link else stripped[:60]
            if title not in seen_titles:
                seen_titles.add(title)
                tags = re.findall(r"#[\w][\w/]*", stripped)
                candidates.append({
                    "title": title,
                    "source_file": source_file,
                    "excerpt": stripped[:200],
                    "existing_note": None,
                    "tags": tags,
                    "suggested_template": "Template, Note",
                    "_link_count": len(links_in_line),
                    "_has_expand": bool(_EXPAND_RE.search(stripped)),
                })

        # Pattern 3: #idea or #insight tags.
        if _IDEA_TAG_RE.search(stripped):
            # Use text after the tag as the title, or the whole line.
            tag_match = _IDEA_TAG_RE.search(stripped)
            after_tag = stripped[tag_match.end():].strip() if tag_match else stripped
            title = after_tag[:80] if after_tag else stripped[:80]
            title = title.strip(" :-")
            if title and title not in seen_titles:
                seen_titles.add(title)
                tags = re.findall(r"#[\w][\w/]*", stripped)
                candidates.append({
                    "title": title,
                    "source_file": source_file,
                    "excerpt": stripped[:200],
                    "existing_note": None,
                    "tags": tags,
                    "suggested_template": "Template, Note",
                    "_link_count": len(_WIKILINK_RE_GRAD.findall(stripped)),
                    "_has_expand": bool(_EXPAND_RE.search(stripped)),
                })

        # Pattern 4: "TODO: expand" / "flesh out" / "write up" / "develop further".
        if _EXPAND_RE.search(stripped):
            title = re.sub(
                r"(?:TODO:\s*expand|flesh\s+out|write\s+up|develop\s+further)",
                "",
                stripped,
                flags=re.IGNORECASE,
            ).strip(" :-")
            if not title:
                title = stripped[:80]
            if title and title not in seen_titles:
                seen_titles.add(title)
                tags = re.findall(r"#[\w][\w/]*", stripped)
                candidates.append({
                    "title": title,
                    "source_file": source_file,
                    "excerpt": stripped[:200],
                    "existing_note": None,
                    "tags": tags,
                    "suggested_template": "Template, Note",
                    "_link_count": len(_WIKILINK_RE_GRAD.findall(stripped)),
                    "_has_expand": True,
                })

        i += 1


def graduate_execute(
    title: str,
    content: str,
    vault: str | None = None,
    target_folder: str | None = None,
    source_file: str | None = None,
    confirm: bool = False,
    dry_run: bool = False,
) -> dict:
    """Create a note in the agent drafts folder with provenance frontmatter.

    Enforces the "agents read, humans write" principle: the note is created
    in a segregated drafts folder for human review before promotion.

    REQUIRES ``confirm=True`` or ``dry_run=True``, otherwise raises
    :class:`ValueError`.

    Parameters
    ----------
    title:
        Note title (becomes the file name).
    content:
        Markdown body of the note (provenance frontmatter is prepended).
    vault:
        Target vault name.
    target_folder:
        Vault-relative folder for the new note.  Falls back to
        ``config.json`` ``default_folders.agent_drafts``
        (default: ``"Inbox/Agent Drafts"``).
    source_file:
        Vault-relative path of the daily note that originated this idea.
    confirm:
        Must be ``True`` to actually create the note.
    dry_run:
        If ``True``, return a preview without creating anything.

    Returns
    -------
    dict
        ``{"created": path, "source": source_file, "provenance": {...}}``
        on success, or ``{"dry_run": True, ...}`` for dry-run mode.

    Raises
    ------
    ValueError
        If neither ``confirm`` nor ``dry_run`` is ``True``.
    """
    if not confirm and not dry_run:
        raise ValueError(
            "graduate_execute requires confirm=True or dry_run=True"
        )

    # Resolve target folder from config.
    if target_folder is None:
        cfg = load_config()
        target_folder = cfg.default_folders.get(
            "agent_drafts", "Inbox/Agent Drafts"
        )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
    provenance = {
        "source": "agent",
        "created_from": source_file or "unknown",
        "status": "draft",
        "created": ts,
    }

    full_content = (
        "---\n"
        f"source: agent\n"
        f"created_from: \"{source_file or 'unknown'}\"\n"
        f"status: draft\n"
        f"created: \"{ts}\"\n"
        "---\n"
        "\n"
        f"{content}"
    )
    # Sanitize title: remove path separators and reject path traversal.
    safe_title = title.replace("/", "-").replace("\\", "-").strip()
    if not safe_title or ".." in safe_title.split("-"):
        raise ValueError(f"graduate_execute: invalid title: {title!r}")

    # Sanitize target_folder: normalize separators, reject path traversal.
    if target_folder:
        safe_folder = target_folder.replace("\\", "/").strip("/")
        segments = safe_folder.split("/")
        if any(seg in ("..", "") for seg in segments):
            raise ValueError(
                f"graduate_execute: target_folder contains invalid path components: {target_folder!r}"
            )
    else:
        safe_folder = None

    note_path = f"{safe_folder}/{safe_title}.md" if safe_folder else f"{safe_title}.md"

    if dry_run:
        return {
            "dry_run": True,
            "would_create": note_path,
            "content_preview": full_content[:200],
        }

    # Write the note directly to the vault filesystem.
    # The Obsidian CLI `create` command creates empty notes; we need to
    # write frontmatter + content, so we use direct file write.
    from obsidian_connector.config import resolve_vault_path

    vault_dir = resolve_vault_path(vault)
    target_dir = vault_dir / (safe_folder or "")
    # Ensure target_dir is still under vault_dir.
    try:
        target_dir.resolve().relative_to(vault_dir.resolve())
    except ValueError:
        raise ValueError(
            f"graduate_execute: target_folder {target_folder!r} resolves outside vault"
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{safe_title}.md"
    if target_file.exists():
        raise FileExistsError(
            f"graduate_execute: destination already exists: {target_file}"
        )
    target_file.write_text(full_content, encoding="utf-8")

    # Log the mutation to the audit trail.
    effective_vault = vault or load_config().default_vault
    log_action(
        command="graduate-execute",
        args={"title": title, "source_file": source_file, "target_folder": target_folder},
        vault=effective_vault,
        dry_run=False,
        affected_path=note_path,
        content=full_content,
    )

    return {
        "created": note_path,
        "source": source_file,
        "provenance": provenance,
    }


_DELEGATION_PREFIX_RE = re.compile(
    r"^@(agent|claude):\s*(.+)$",
    re.IGNORECASE,
)
_DELEGATION_CALLOUT_RE = re.compile(
    r"^>\s*\[!agent\]\s*(.+)$",
    re.IGNORECASE,
)
_DONE_MARKER_RE = re.compile(
    r"\[(?:done|completed)\]",
    re.IGNORECASE,
)


def detect_delegations(
    vault: str | None = None,
    lookback_days: int = 1,
) -> list[dict]:
    """Scan recent notes for agent delegation patterns (read-only).

    Patterns detected:

    - Lines starting with ``@agent:`` or ``@claude:`` (case insensitive)
    - Obsidian callout blocks: ``> [!agent] instruction text``

    Status detection:

    - ``"pending"`` by default
    - ``"done"`` if the *next* line contains ``[done]`` or ``[completed]``

    Parameters
    ----------
    vault:
        Target vault name.
    lookback_days:
        Number of days to search backward for daily notes (default 1,
        max 30).

    Returns
    -------
    list[dict]
        Each dict has ``file``, ``line_number``, ``instruction``, and
        ``status`` keys.
    """
    lookback_days = min(lookback_days, 30)
    _MAX_NOTES = 15

    today = datetime.now(timezone.utc).date()
    daily_note_names: list[str] = []

    for i in range(lookback_days):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        try:
            hits = search_notes(day_str, vault=vault)
            for hit in hits:
                fname: str = hit.get("file", "")
                if day_str in fname and fname not in daily_note_names:
                    daily_note_names.append(fname)
                    if len(daily_note_names) >= _MAX_NOTES:
                        break
        except ObsidianCLIError:
            continue
        if len(daily_note_names) >= _MAX_NOTES:
            break

    # Also search for delegation markers across the vault.
    for query in ["@agent:", "@claude:", "[!agent]"]:
        try:
            hits = search_notes(query, vault=vault)
            for hit in hits:
                fname = hit.get("file", "")
                if fname not in daily_note_names:
                    daily_note_names.append(fname)
                    if len(daily_note_names) >= _MAX_NOTES:
                        break
        except ObsidianCLIError:
            continue
        if len(daily_note_names) >= _MAX_NOTES:
            break

    delegations: list[dict] = []
    contents = batch_read_notes(daily_note_names, vault=vault)

    for fname, content in contents.items():
        if not content:
            continue
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            instruction: str | None = None

            prefix_match = _DELEGATION_PREFIX_RE.match(stripped)
            if prefix_match:
                instruction = prefix_match.group(2).strip()
            else:
                callout_match = _DELEGATION_CALLOUT_RE.match(stripped)
                if callout_match:
                    instruction = callout_match.group(1).strip()

            if instruction is None:
                continue

            # Check next line for done marker.
            status = "pending"
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if _DONE_MARKER_RE.search(next_line):
                    status = "done"

            delegations.append({
                "file": fname,
                "line_number": i + 1,
                "instruction": instruction,
                "status": status,
            })

    return delegations


# ---------------------------------------------------------------------------
# Context load (Epic 7 -- read-only)
# ---------------------------------------------------------------------------

def context_load_full(vault: str | None = None) -> dict:
    """Load full context bundle for agent session start.

    Reads:

    1. Configured ``context_files`` from config.json.
    2. Today's daily note plus follows ``[[links]]`` depth 1
       (max 5 linked notes).
    3. Past 7 daily notes (first 500 chars each for summaries).
    4. Open tasks (from :func:`list_tasks`).
    5. Open loops (from :func:`list_open_loops`).

    Total note reads are capped at 20 to bound IPC overhead.

    Parameters
    ----------
    vault:
        Target vault name.

    Returns
    -------
    dict
        Keys: ``context_files``, ``daily_note``, ``recent_dailies``,
        ``tasks``, ``open_loops``, ``read_count``.
    """
    from obsidian_connector.config import load_config as _load_config

    _MAX_READS = 20
    read_count = 0

    cfg = _load_config()

    # 1. Context files from config (skip paths with traversal components).
    context_file_entries: list[dict] = []
    for cf_path in cfg.context_files:
        if read_count >= _MAX_READS:
            break
        if ".." in Path(cf_path).parts:
            continue
        try:
            content = read_note(cf_path, vault=vault)
            read_count += 1
            context_file_entries.append({"path": cf_path, "content": content})
        except ObsidianCLIError:
            context_file_entries.append({"path": cf_path, "content": ""})
            read_count += 1

    # 2. Today's daily note + depth-1 links.
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_note_entry: dict = {"path": today_str, "content": None, "linked_notes": []}

    if read_count < _MAX_READS:
        try:
            daily_content = read_note(today_str, vault=vault)
            read_count += 1
            daily_note_entry["content"] = daily_content

            # Follow [[links]] depth 1.
            links = extract_links(daily_content)
            linked_notes: list[dict] = []
            for link in links[:5]:
                if read_count >= _MAX_READS:
                    break
                try:
                    linked_content = read_note(link, vault=vault)
                    read_count += 1
                    heading, excerpt = _extract_note_summary(linked_content)
                    linked_notes.append({
                        "path": link,
                        "heading": heading,
                        "excerpt": excerpt[:300],
                    })
                except ObsidianCLIError:
                    read_count += 1

            daily_note_entry["linked_notes"] = linked_notes
        except ObsidianCLIError:
            read_count += 1

    # 3. Past 7 daily notes (first 500 chars each).
    recent_dailies: list[dict] = []
    for i in range(1, 8):
        if read_count >= _MAX_READS:
            break
        day = datetime.now(timezone.utc).date() - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        try:
            content = read_note(day_str, vault=vault)
            read_count += 1
            recent_dailies.append({
                "path": day_str,
                "date": day_str,
                "summary": content[:500],
            })
        except ObsidianCLIError:
            read_count += 1

    # 4. Open tasks.
    try:
        tasks = list_tasks(filter={"todo": True, "limit": 20}, vault=vault)
    except ObsidianCLIError:
        tasks = []

    # 5. Open loops.
    open_loops = list_open_loops(vault=vault, lookback_days=7)

    return {
        "context_files": context_file_entries,
        "daily_note": daily_note_entry,
        "recent_dailies": recent_dailies,
        "tasks": tasks,
        "open_loops": open_loops,
        "read_count": read_count,
    }


# ---------------------------------------------------------------------------
# Check-in (proactive assistant brain)
# ---------------------------------------------------------------------------

_RITUAL_SENTINELS = {
    "morning_briefing": "## Morning Briefing",
    "evening_close": "## Day Close",
}


def check_in(
    vault: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    """Time-aware check-in: what should the user do now?

    Reads the daily note, checks which rituals have run, counts open
    loops and pending delegations, and returns a structured suggestion.

    Parameters
    ----------
    vault:
        Target vault name.
    timezone_name:
        IANA timezone (e.g. "America/New_York"). Falls back to local time.

    Returns
    -------
    dict
        Keys: time_of_day, daily_note_exists, completed_rituals,
        pending_rituals, pending_delegations, unreviewed_drafts,
        open_loop_count, suggestion.
    """
    from zoneinfo import ZoneInfo

    # -- Determine time of day ------------------------------------------------
    if timezone_name:
        try:
            tz = ZoneInfo(timezone_name)
        except (KeyError, Exception):
            tz = None
    else:
        tz = None

    now = datetime.now(tz or timezone.utc)
    if tz is None:
        now = datetime.now()  # naive local time
    hour = now.hour

    if hour < 11:
        time_of_day = "morning"
    elif hour < 16:
        time_of_day = "midday"
    elif hour < 20:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    # -- Read today's daily note ----------------------------------------------
    daily_content = ""
    daily_note_exists = False
    try:
        brief = today_brief(vault=vault)
        raw = brief.get("daily_note")
        daily_note_exists = raw is not None  # exists even if empty
        daily_content = raw or ""
    except ObsidianCLIError:
        pass

    # -- Check completed rituals via sentinel headings ------------------------
    completed_rituals: list[str] = []
    pending_rituals: list[str] = []
    for ritual, sentinel in _RITUAL_SENTINELS.items():
        if sentinel in daily_content:
            completed_rituals.append(ritual)
        else:
            pending_rituals.append(ritual)

    # -- Count open loops -----------------------------------------------------
    open_loop_count = 0
    try:
        loops = list_open_loops(vault=vault)
        open_loop_count = len(loops)
    except ObsidianCLIError:
        pass

    # -- Count pending delegations --------------------------------------------
    pending_delegations = 0
    try:
        delegations = detect_delegations(vault=vault)
        pending_delegations = len([d for d in delegations if d.get("status") != "done"])
    except ObsidianCLIError:
        pass

    # -- Count unreviewed agent drafts ----------------------------------------
    unreviewed_drafts = 0
    try:
        vault_path = resolve_vault_path(vault)
        if vault_path:
            drafts_dir = os.path.join(vault_path, "Inbox", "Agent Drafts")
            if os.path.isdir(drafts_dir):
                unreviewed_drafts = len([
                    f for f in os.listdir(drafts_dir)
                    if f.endswith(".md")
                ])
    except Exception:
        pass

    # -- Build suggestion -----------------------------------------------------
    parts: list[str] = []

    if time_of_day == "morning" and "morning_briefing" in pending_rituals:
        parts.append("Morning briefing hasn't run yet.")
    if time_of_day == "evening" and "evening_close" in pending_rituals:
        parts.append("Evening close hasn't run yet.")
    if pending_delegations > 0:
        parts.append(f"{pending_delegations} pending delegation{'s' if pending_delegations != 1 else ''}.")
    if unreviewed_drafts > 0:
        parts.append(f"{unreviewed_drafts} unreviewed agent draft{'s' if unreviewed_drafts != 1 else ''}.")
    if open_loop_count > 5:
        parts.append(f"{open_loop_count} open loops -- consider triaging.")
    elif open_loop_count > 0:
        parts.append(f"{open_loop_count} open loop{'s' if open_loop_count != 1 else ''}.")

    if not parts:
        parts.append("All caught up.")

    suggestion = " ".join(parts)

    return {
        "time_of_day": time_of_day,
        "daily_note_exists": daily_note_exists,
        "completed_rituals": completed_rituals,
        "pending_rituals": pending_rituals,
        "pending_delegations": pending_delegations,
        "unreviewed_drafts": unreviewed_drafts,
        "open_loop_count": open_loop_count,
        "suggestion": suggestion,
    }
