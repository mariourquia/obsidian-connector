"""Higher-level workflows built on top of the core client functions."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from obsidian_connector.client import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    run_obsidian,
    search_notes,
)


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
        Number of days to look back for daily notes.

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

    return {
        "recent_daily_notes": recent_daily_notes,
        "open_tasks": open_tasks,
        "open_loops": open_loops,
        "vault_stats": {"total_files": total_files},
        "recent_searches_hint": hint,
    }


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

    return {
        "date": today_str,
        "daily_note": daily_note,
        "open_tasks": open_tasks,
        "open_loops": open_loops,
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
