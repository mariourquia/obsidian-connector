"""CLI entry point for obsidian-connector.

This module is the canonical CLI implementation. The root ``main.py`` is a
thin wrapper that imports from here for backward compatibility with
``python main.py ...`` invocations.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

from obsidian_connector.client_fallback import (
    ObsidianCLIError,
    list_tasks,
    log_to_daily,
    read_note,
    search_notes,
)
from obsidian_connector.config import load_config
from obsidian_connector.envelope import (
    error_envelope,
    format_output,
    success_envelope,
)
from obsidian_connector.audit import log_action
from obsidian_connector.retrieval import hybrid_search, SearchResult, PROFILE_WEIGHTS
from obsidian_connector.search import enrich_search_results
from obsidian_connector.startup import is_first_run
from obsidian_connector.thinking import (
    deep_ideas,
    drift_analysis,
    ghost_voice_profile,
    trace_idea,
)
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

_TUI_PYPI_INSTALL = "pip install 'obsidian-connector[tui]'"
_TUI_SOURCE_INSTALL = "pip install -e '.[tui]'"


def _is_missing_textual_dependency(exc: ModuleNotFoundError) -> bool:
    name = exc.name or ""
    return name == "textual" or name.startswith("textual.")


def _missing_tui_dependency_message(feature: str) -> str:
    return (
        f"The {feature} requires the optional Textual dependency.\n"
        f"Install it with: {_TUI_PYPI_INSTALL}\n"
        f"From a local clone, use: {_TUI_SOURCE_INSTALL}"
    )


def _run_tui_entrypoint(entrypoint: str, feature: str) -> int:
    try:
        ui_dashboard = importlib.import_module("obsidian_connector.ui_dashboard")
    except ModuleNotFoundError as exc:
        if _is_missing_textual_dependency(exc):
            print(_missing_tui_dependency_message(feature), file=sys.stderr)
            return 2
        raise
    return getattr(ui_dashboard, entrypoint)()


# ---------------------------------------------------------------------------
# Human-readable formatters
# ---------------------------------------------------------------------------

def _fmt_search(results: list[dict]) -> str:
    if not results:
        return "No matches."
    lines: list[str] = []
    for r in results:
        n = len(r.get("matches", []))
        lines.append(f"  {r['file']}  ({n} match{'es' if n != 1 else ''})")
        for m in r.get("matches", [])[:3]:
            lines.append(f"    L{m['line']}: {m['text'][:120]}")
        if n > 3:
            lines.append(f"    ... and {n - 3} more")
    return "\n".join(lines)


def _fmt_hybrid_search(results: list[SearchResult], explain: bool = False) -> str:
    """Format hybrid_search results for human-readable CLI output."""
    if not results:
        return "No matches."
    lines: list[str] = []
    for r in results:
        lines.append(f"  {r.path}  (score: {r.score:.3f})")
        if r.title:
            lines.append(f"    title: {r.title}")
        if r.snippet:
            lines.append(f"    snippet: {r.snippet[:160]}{'...' if len(r.snippet) > 160 else ''}")
        if explain and r.match_reasons:
            for reason in r.match_reasons:
                lines.append(f"    - {reason}")
    return "\n".join(lines)


def _fmt_tasks(results: list[dict]) -> str:
    if not results:
        return "No tasks."
    lines: list[str] = []
    for t in results:
        marker = "x" if t.get("status", " ").strip() else " "
        lines.append(f"  [{marker}] {t['text'].lstrip('- [x] ').lstrip('- [ ] ')}  ({t['file']}:{t['line']})")
    return "\n".join(lines)


def _fmt_prior_work(results: list[dict]) -> str:
    if not results:
        return "No prior work found."
    lines: list[str] = []
    for r in results:
        lines.append(f"  {r['file']}")
        lines.append(f"    heading:  {r['heading']}")
        if r["excerpt"]:
            lines.append(f"    excerpt:  {r['excerpt'][:120]}{'...' if len(r['excerpt']) > 120 else ''}")
        lines.append(f"    matches:  {r['match_count']}")
    return "\n".join(lines)


def _fmt_doctor(checks: list[dict]) -> str:
    """Human-readable doctor output."""
    lines: list[str] = []
    for c in checks:
        icon = "PASS" if c.get("ok") else "FAIL"
        lines.append(f"  [{icon}] {c['check']}: {c.get('detail', '')}")
    return "\n".join(lines)


def _fmt_my_world(data: dict) -> str:
    """Human-readable my-world snapshot."""
    lines: list[str] = []
    stats = data.get("vault_stats", {})
    lines.append(f"Vault: {stats.get('total_files', '?')} files")

    daily = data.get("recent_daily_notes", [])
    if daily:
        lines.append(f"\nRecent daily notes ({len(daily)}):")
        for d in daily[:10]:
            lines.append(f"  {d}")

    tasks = data.get("open_tasks", [])
    if tasks:
        lines.append(f"\nOpen tasks ({len(tasks)}):")
        lines.append(_fmt_tasks(tasks))

    loops = data.get("open_loops", [])
    if loops:
        lines.append(f"\nOpen loops ({len(loops)}):")
        lines.append(_fmt_open_loops(loops))

    hint = data.get("recent_searches_hint", "")
    if hint:
        lines.append(f"\n{hint}")

    vault_summary = data.get("vault_summary")
    if vault_summary:
        lines.append(f"\nVault graph summary:")
        lines.append(f"  Notes: {vault_summary.get('total_notes', '?')}")
        lines.append(f"  Orphans: {vault_summary.get('orphan_count', '?')}")
        lines.append(f"  Dead ends: {vault_summary.get('dead_end_count', '?')}")
        top_tags = vault_summary.get("top_tags", [])
        if top_tags:
            lines.append(f"  Top tags: {', '.join(top_tags)}")

    return "\n".join(lines)


def _fmt_today(data: dict) -> str:
    """Human-readable today brief."""
    lines: list[str] = []
    lines.append(f"Date: {data.get('date', '?')}")

    note = data.get("daily_note")
    if note:
        preview = note[:300].replace("\n", "\n  ")
        lines.append(f"\nDaily note (preview):\n  {preview}")
        if len(note) > 300:
            lines.append("  ...")
    else:
        lines.append("\nNo daily note found for today.")

    tasks = data.get("open_tasks", [])
    if tasks:
        lines.append(f"\nOpen tasks ({len(tasks)}):")
        lines.append(_fmt_tasks(tasks))

    loops = data.get("open_loops", [])
    if loops:
        lines.append(f"\nOpen loops ({len(loops)}):")
        lines.append(_fmt_open_loops(loops))

    linked = data.get("linked_context", [])
    if linked:
        lines.append(f"\nLinked notes ({len(linked)}):")
        for ctx in linked:
            lines.append(f"  {ctx.get('file', '?')}")
            if ctx.get("heading"):
                lines.append(f"    heading: {ctx['heading']}")
            if ctx.get("excerpt"):
                excerpt = ctx["excerpt"][:120]
                lines.append(f"    excerpt: {excerpt}{'...' if len(ctx.get('excerpt', '')) > 120 else ''}")

    return "\n".join(lines)


def _fmt_close(data: dict) -> str:
    """Human-readable close-day reflection."""
    lines: list[str] = []
    lines.append(f"Date: {data.get('date', '?')}")

    summary = data.get("daily_note_summary")
    if summary:
        preview = summary[:200].replace("\n", "\n  ")
        lines.append(f"\nDaily note summary:\n  {preview}")
    else:
        lines.append("\nNo daily note found for today.")

    done = data.get("completed_tasks", [])
    if done:
        lines.append(f"\nCompleted tasks ({len(done)}):")
        lines.append(_fmt_tasks(done))

    remaining = data.get("remaining_tasks", [])
    if remaining:
        lines.append(f"\nRemaining tasks ({len(remaining)}):")
        lines.append(_fmt_tasks(remaining))

    prompts = data.get("reflection_prompts", [])
    if prompts:
        lines.append("\nReflection prompts:")
        for i, p in enumerate(prompts, 1):
            lines.append(f"  {i}. {p}")

    actions = data.get("suggested_actions", [])
    if actions:
        lines.append("\nSuggested actions for tomorrow:")
        for a in actions:
            lines.append(f"  - {a}")

    return "\n".join(lines)


def _fmt_open_loops(data: list[dict]) -> str:
    """Human-readable open loops list."""
    if not data:
        return "No open loops."
    lines: list[str] = []
    for item in data:
        src = item.get("source", "?")
        text = item.get("text", "").strip()
        f = item.get("file", "")
        ln = item.get("line", 0)
        lines.append(f"  [{src}] {text}  ({f}:{ln})")
    return "\n".join(lines)


def _fmt_challenge(data: dict) -> str:
    """Human-readable challenge belief output."""
    lines: list[str] = []
    lines.append(f"Belief: {data.get('belief', '?')}")

    counter = data.get("counter_evidence", [])
    if counter:
        lines.append(f"\nCounter-evidence ({len(counter)}):")
        for item in counter:
            lines.append(f"  {item['file']}")
            if item.get("heading"):
                lines.append(f"    heading: {item['heading']}")
            if item.get("excerpt"):
                excerpt = item["excerpt"][:120]
                lines.append(f"    excerpt: {excerpt}{'...' if len(item.get('excerpt', '')) > 120 else ''}")
    else:
        lines.append("\nNo counter-evidence found.")

    supporting = data.get("supporting_evidence", [])
    if supporting:
        lines.append(f"\nSupporting evidence ({len(supporting)}):")
        for item in supporting:
            lines.append(f"  {item['file']}")
            if item.get("heading"):
                lines.append(f"    heading: {item['heading']}")
            if item.get("excerpt"):
                excerpt = item["excerpt"][:120]
                lines.append(f"    excerpt: {excerpt}{'...' if len(item.get('excerpt', '')) > 120 else ''}")
    else:
        lines.append("\nNo supporting evidence found.")

    verdict = data.get("verdict", "")
    if verdict:
        lines.append(f"\nVerdict: {verdict}")

    return "\n".join(lines)


def _fmt_emerge(data: dict) -> str:
    """Human-readable emerge ideas output."""
    lines: list[str] = []
    lines.append(f"Topic: {data.get('topic', '?')}")
    lines.append(f"Total notes: {data.get('total_notes', 0)}")

    clusters = data.get("clusters", [])
    if clusters:
        lines.append(f"\nClusters ({len(clusters)}):")
        for cluster in clusters:
            lines.append(f"\n  [{cluster.get('folder', '?')}] ({cluster.get('count', 0)} notes)")
            for note in cluster.get("notes", []):
                lines.append(f"    {note['file']}")
                if note.get("heading"):
                    lines.append(f"      heading: {note['heading']}")
                if note.get("excerpt"):
                    excerpt = note["excerpt"][:120]
                    lines.append(f"      excerpt: {excerpt}{'...' if len(note.get('excerpt', '')) > 120 else ''}")
    else:
        lines.append("\nNo clusters found.")

    return "\n".join(lines)


def _fmt_connect(data: dict) -> str:
    """Human-readable connect domains output."""
    lines: list[str] = []
    lines.append(f"Domain A: {data.get('domain_a', '?')}")
    lines.append(f"Domain B: {data.get('domain_b', '?')}")

    connections = data.get("connections", [])
    if connections:
        lines.append(f"\nConnections ({len(connections)}):")
        for conn in connections:
            lines.append(f"  {conn['file']}")
            if conn.get("heading"):
                lines.append(f"    heading: {conn['heading']}")
            if conn.get("excerpt"):
                excerpt = conn["excerpt"][:120]
                lines.append(f"    excerpt: {excerpt}{'...' if len(conn.get('excerpt', '')) > 120 else ''}")
            lines.append(f"    matches: A={conn.get('match_a', 0)}, B={conn.get('match_b', 0)}")
    else:
        lines.append("\nNo connections found.")

    a_only = data.get("domain_a_only", [])
    if a_only:
        lines.append(f"\nDomain A only ({len(a_only)}):")
        for f in a_only[:10]:
            lines.append(f"  {f}")
        if len(a_only) > 10:
            lines.append(f"  ... and {len(a_only) - 10} more")

    b_only = data.get("domain_b_only", [])
    if b_only:
        lines.append(f"\nDomain B only ({len(b_only)}):")
        for f in b_only[:10]:
            lines.append(f"  {f}")
        if len(b_only) > 10:
            lines.append(f"  ... and {len(b_only) - 10} more")

    return "\n".join(lines)


def _fmt_neighborhood(data: dict) -> str:
    """Human-readable neighborhood output."""
    lines: list[str] = []
    lines.append(f"Note: {data.get('note', '?')}")

    backlinks = data.get("backlinks", [])
    if backlinks:
        lines.append(f"\nBacklinks ({len(backlinks)}):")
        for bl in backlinks:
            lines.append(f"  <- {bl}")
    else:
        lines.append("\nNo backlinks.")

    forward = data.get("forward_links", [])
    if forward:
        lines.append(f"\nForward links ({len(forward)}):")
        for fl in forward:
            lines.append(f"  -> {fl}")
    else:
        lines.append("\nNo forward links.")

    tags = data.get("tags", [])
    if tags:
        lines.append(f"\nTags: {', '.join(tags)}")

    neighbors = data.get("neighbors", [])
    if neighbors:
        lines.append(f"\nNeighbors ({len(neighbors)}):")
        for nb in neighbors:
            lines.append(f"  {nb}")

    return "\n".join(lines)


def _fmt_vault_structure(data: dict) -> str:
    """Human-readable vault structure output."""
    lines: list[str] = []
    lines.append(f"Total notes: {data.get('total_notes', 0)}")

    orphans = data.get("orphans", [])
    if orphans:
        lines.append(f"\nOrphans ({len(orphans)}):")
        for o in orphans:
            lines.append(f"  {o}")

    dead_ends = data.get("dead_ends", [])
    if dead_ends:
        lines.append(f"\nDead ends ({len(dead_ends)}):")
        for d in dead_ends:
            lines.append(f"  {d}")

    unresolved = data.get("unresolved_links", {})
    if unresolved:
        lines.append(f"\nUnresolved links ({len(unresolved)}):")
        for link, sources in unresolved.items():
            lines.append(f"  [[{link}]] referenced by: {', '.join(sources)}")

    tag_cloud = data.get("tag_cloud", {})
    if tag_cloud:
        lines.append(f"\nTag cloud ({len(tag_cloud)}):")
        for tag, count in tag_cloud.items():
            lines.append(f"  {tag} ({count})")

    top_connected = data.get("top_connected", [])
    if top_connected:
        lines.append(f"\nMost connected ({len(top_connected)}):")
        for item in top_connected:
            lines.append(f"  {item['note']} ({item['backlink_count']} backlinks)")

    return "\n".join(lines)


def _fmt_backlinks(data: list[dict]) -> str:
    """Human-readable backlinks output."""
    if not data:
        return "No backlinks found."
    lines: list[str] = []
    for item in data:
        ctx = item.get("context_line", "")
        tags = item.get("tags", [])
        line = f"  <- {item['file']}"
        if ctx:
            line += f"\n     {ctx}"
        if tags:
            line += f"\n     tags: {', '.join(tags)}"
        lines.append(line)
    return "\n".join(lines)


def _fmt_graduate_list(data: list[dict]) -> str:
    """Human-readable graduate candidates list."""
    if not data:
        return "No graduate candidates found."
    lines: list[str] = []
    for i, cand in enumerate(data, 1):
        lines.append(f"  {i}. {cand.get('title', '?')}")
        lines.append(f"     source: {cand.get('source_file', '?')}")
        if cand.get("existing_note"):
            lines.append(f"     existing: {cand['existing_note']}")
        tags = cand.get("tags", [])
        if tags:
            lines.append(f"     tags: {', '.join(tags)}")
        excerpt = cand.get("excerpt", "")
        if excerpt:
            preview = excerpt[:120].replace("\n", " ")
            lines.append(f"     excerpt: {preview}{'...' if len(excerpt) > 120 else ''}")
    return "\n".join(lines)


def _fmt_graduate_exec(data: dict) -> str:
    """Human-readable graduate execute output."""
    if data.get("dry_run"):
        lines = [
            "[dry-run] Would create agent draft:",
            f"  path: {data.get('would_create', '?')}",
        ]
        preview = data.get("content_preview", "")
        if preview:
            lines.append(f"  preview: {preview[:120]}{'...' if len(preview) > 120 else ''}")
        return "\n".join(lines)
    return f"Created agent draft: {data.get('created', '?')}"


def _fmt_ghost(data: dict) -> str:
    """Human-readable ghost voice profile output."""
    lines: list[str] = []
    confidence = data.get("confidence", "?")
    sample = data.get("sample_size", 0)
    lines.append(f"Voice profile (confidence: {confidence}, sample: {sample} notes)")

    msg = data.get("message")
    if msg:
        lines.append(f"\n  {msg}")
        return "\n".join(lines)

    profile = data.get("profile", {})
    if not profile:
        lines.append("\n  No profile data.")
        return "\n".join(lines)

    lines.append(f"\n  Avg sentence length: {profile.get('avg_sentence_length', '?')} words")
    lines.append(f"  Avg paragraph length: {profile.get('avg_paragraph_length', '?')} sentences")
    lines.append(f"  Vocabulary richness: {profile.get('vocabulary_richness', '?')}")

    phrases = profile.get("common_phrases", [])
    if phrases:
        lines.append(f"\n  Common phrases: {', '.join(phrases[:5])}")

    tone = profile.get("tone_markers", [])
    if tone:
        lines.append(f"  Tone: {', '.join(tone)}")

    prefs = profile.get("structural_preferences", {})
    if prefs:
        lines.append(f"\n  Headings/note: {prefs.get('headings_per_note', '?')}")
        lines.append(f"  Bullets-to-prose ratio: {prefs.get('bullets_vs_prose_ratio', '?')}")
        lines.append(f"  Code block frequency: {prefs.get('code_block_frequency', '?')}")

    question = data.get("question")
    if question:
        lines.append(f"\n  Question: {question}")

    return "\n".join(lines)


def _fmt_drift(data: dict) -> str:
    """Human-readable drift analysis output."""
    lines: list[str] = []
    lines.append(f"Drift analysis ({data.get('daily_notes_found', 0)} daily notes, {data.get('lookback_days', '?')} days)")

    msg = data.get("message")
    if msg:
        lines.append(f"\n  {msg}")
        return "\n".join(lines)

    intentions = data.get("stated_intentions", [])
    if intentions:
        lines.append(f"\nStated intentions ({len(intentions)}):")
        for item in intentions[:10]:
            lines.append(f"  - {item['text']}  ({item['source_file']}, {item['date']})")
    else:
        lines.append("\nNo stated intentions found.")

    gaps = data.get("gaps", [])
    if gaps:
        lines.append(f"\nUnaddressed intentions ({len(gaps)}):")
        for item in gaps[:10]:
            lines.append(f"  - {item['intention']}")

    surprises = data.get("surprises", [])
    if surprises:
        lines.append(f"\nSurprises -- attention without intent ({len(surprises)}):")
        for item in surprises[:5]:
            lines.append(f"  - {item['topic']}: {item['description']}")

    coverage = data.get("coverage_pct", 0)
    lines.append(f"\nCoverage: {coverage}% of intentions addressed")

    return "\n".join(lines)


def _fmt_trace(data: dict) -> str:
    """Human-readable trace idea output."""
    lines: list[str] = []
    lines.append(f"Trace: \"{data.get('topic', '?')}\" ({data.get('total_mentions', 0)} mentions)")

    timeline = data.get("timeline", [])
    if not timeline:
        lines.append("\nNo mentions found.")
        return "\n".join(lines)

    first = data.get("first_mention")
    if first:
        lines.append(f"\nFirst mention: {first.get('date', '?')} in {first.get('file', '?')}")
    latest = data.get("latest_mention")
    if latest:
        lines.append(f"Latest mention: {latest.get('date', '?')} in {latest.get('file', '?')}")

    phases = data.get("phases", [])
    if phases:
        lines.append(f"\nPhases ({len(phases)}):")
        for phase in phases:
            lines.append(
                f"  {phase.get('name', '?')}: {phase.get('start_date', '?')} -- "
                f"{phase.get('end_date', '?')} ({phase.get('note_count', 0)} notes)"
            )

    if timeline:
        lines.append(f"\nTimeline ({len(timeline)} entries):")
        for entry in timeline[:10]:
            excerpt = entry.get("excerpt", "")[:80]
            lines.append(f"  {entry.get('date', '?')} | {entry.get('file', '?')}")
            if excerpt:
                lines.append(f"    {excerpt}{'...' if len(entry.get('excerpt', '')) > 80 else ''}")
        if len(timeline) > 10:
            lines.append(f"  ... and {len(timeline) - 10} more")

    return "\n".join(lines)


def _fmt_ideas(data: dict) -> str:
    """Human-readable deep ideas output."""
    lines: list[str] = []

    health = data.get("vault_health", {})
    lines.append(
        f"Vault health: {health.get('orphan_pct', 0)}% orphans, "
        f"{health.get('dead_end_pct', 0)}% dead ends, "
        f"{health.get('unresolved_count', 0)} unresolved links"
    )

    msg = data.get("message")
    if msg:
        lines.append(f"\n  {msg}")
        return "\n".join(lines)

    ideas = data.get("ideas", [])
    if ideas:
        lines.append(f"\nIdeas ({len(ideas)}):")
        for idea in ideas:
            priority = idea.get("priority", "?")
            lines.append(f"\n  [{priority.upper()}] {idea.get('title', '?')}")
            lines.append(f"    type: {idea.get('type', '?')}")
            lines.append(f"    rationale: {idea.get('rationale', '')[:120]}")
            sources = idea.get("source_notes", [])
            if sources:
                lines.append(f"    sources: {', '.join(sources[:3])}")
    else:
        lines.append("\nNo ideas surfaced.")

    return "\n".join(lines)


def _fmt_rebuild_index(data: dict) -> str:
    """Human-readable rebuild-index output."""
    return (
        f"Index rebuilt: {data.get('notes_indexed', 0)} notes, "
        f"{data.get('orphans', 0)} orphans, "
        f"{data.get('tags', 0)} tags "
        f"({data.get('duration_ms', 0)}ms)"
    )


def _fmt_delegations(data: list[dict]) -> str:
    """Human-readable delegations output."""
    if not data:
        return "No delegations found."
    lines: list[str] = []
    for d in data:
        status_marker = "DONE" if d.get("status") == "done" else "PENDING"
        lines.append(
            f"  [{status_marker}] {d.get('instruction', '')}  "
            f"({d.get('file', '')}:{d.get('line_number', 0)})"
        )
    return "\n".join(lines)


def _fmt_context_load(data: dict) -> str:
    """Human-readable context-load output."""
    lines: list[str] = []
    lines.append(f"Read count: {data.get('read_count', 0)} / 20")

    cf = data.get("context_files", [])
    if cf:
        lines.append(f"\nContext files ({len(cf)}):")
        for f in cf:
            has_content = "loaded" if f.get("content") else "empty"
            lines.append(f"  {f.get('path', '?')} ({has_content})")

    daily = data.get("daily_note", {})
    if daily.get("content"):
        preview = daily["content"][:200].replace("\n", "\n  ")
        lines.append(f"\nToday's daily note ({daily.get('path', '?')}):")
        lines.append(f"  {preview}")
        linked = daily.get("linked_notes", [])
        if linked:
            lines.append(f"  Linked notes ({len(linked)}):")
            for ln in linked:
                lines.append(f"    {ln.get('path', '?')}: {ln.get('heading', '')}")
    else:
        lines.append("\nNo daily note found for today.")

    recent = data.get("recent_dailies", [])
    if recent:
        lines.append(f"\nRecent dailies ({len(recent)}):")
        for r in recent:
            summary_preview = (r.get("summary", "") or "")[:80]
            lines.append(f"  {r.get('date', '?')}: {summary_preview}")

    tasks = data.get("tasks", [])
    if tasks:
        lines.append(f"\nOpen tasks ({len(tasks)}):")
        lines.append(_fmt_tasks(tasks))

    loops = data.get("open_loops", [])
    if loops:
        lines.append(f"\nOpen loops ({len(loops)}):")
        lines.append(_fmt_open_loops(loops))

    return "\n".join(lines)


def _fmt_check_in(data: dict) -> str:
    """Human-readable check-in output."""
    lines: list[str] = []
    lines.append(f"Time: {data.get('time_of_day', '?')}")
    lines.append(f"Daily note: {'exists' if data.get('daily_note_exists') else 'not found'}")

    completed = data.get("completed_rituals", [])
    if completed:
        lines.append(f"Completed: {', '.join(completed)}")

    pending = data.get("pending_rituals", [])
    if pending:
        lines.append(f"Pending: {', '.join(pending)}")

    loops = data.get("open_loop_count", 0)
    if loops:
        lines.append(f"Open loops: {loops}")

    delegations = data.get("pending_delegations", 0)
    if delegations:
        lines.append(f"Pending delegations: {delegations}")

    drafts = data.get("unreviewed_drafts", 0)
    if drafts:
        lines.append(f"Unreviewed drafts: {drafts}")

    suggestion = data.get("suggestion", "")
    if suggestion:
        lines.append(f"\n{suggestion}")

    return "\n".join(lines)


def _format_uninstall_plan(data: dict) -> str:
    """Human-readable dry-run uninstall plan."""
    lines: list[str] = []
    lines.append("Uninstall Plan (dry-run):")
    lines.append("=" * 40)

    plan = data.get("plan", {})
    files = plan.get("files_to_remove", [])
    if files:
        lines.append(f"\nFiles to remove ({len(files)}):")
        for f in files:
            lines.append(f"  - {f}")

    config = plan.get("config_changes", {})
    if config:
        lines.append("\nConfig changes:")
        for config_file, change in config.items():
            if change.get("action") == "remove_key":
                path_str = " > ".join(change.get("path", []))
                lines.append(f"  - {config_file}: remove {path_str}")

    plist = plan.get("plist_action")
    if plist:
        lines.append(f"\nPlist action:")
        lines.append(f"  - {plist}")

    summary = plan.get("summary", "")
    if summary:
        lines.append(f"\nSummary: {summary}")

    return "\n".join(lines)


def _format_uninstall_result(data: dict) -> str:
    """Human-readable uninstall result."""
    if data.get("cancelled"):
        return "Uninstall cancelled."

    lines: list[str] = []
    status = data.get("status", "unknown")
    if status == "ok":
        lines.append("Uninstall complete!")
    else:
        lines.append("Uninstall complete with warnings.")

    removed = data.get("removed", [])
    if removed:
        lines.append("\nRemoved:")
        for item in removed:
            lines.append(f"  - {item}")

    errors = data.get("errors", [])
    if errors:
        lines.append("\nErrors:")
        for error in errors:
            lines.append(f"  - {error}")

    summary = data.get("summary", "")
    if summary:
        lines.append(f"\n{summary}")

    return "\n".join(lines)


def _fmt_sync_projects(data: dict) -> str:
    """Human-readable sync output."""
    lines = [
        f"Synced {data.get('synced', 0)} projects.",
        f"Active threads: {data.get('active_threads', 0)}",
        f"Dashboard: {data.get('dashboard', '?')}",
    ]
    if data.get("todo_updated"):
        lines.append("Running TODO updated.")
    lines.append(f"Timestamp: {data.get('timestamp', '?')}")
    return "\n".join(lines)


def _fmt_project_status(data: dict) -> str:
    """Human-readable single project status."""
    if not data.get("exists"):
        return f"{data.get('project', '?')}: directory not found"
    if not data.get("is_git"):
        return f"{data.get('project', '?')}: not a git repo"

    lines = [
        f"{data.get('display_name', data.get('project', '?'))}",
        f"  Branch: {data.get('branch', '?')}",
        f"  Last commit: {data.get('last_commit', '?')}",
        f"  Activity: {data.get('activity', '?')}",
        f"  Uncommitted: {data.get('uncommitted', 0)}",
        f"  Staged: {data.get('staged', 0)}",
    ]

    modified = data.get("modified_files", [])
    if modified:
        lines.append(f"  Modified files ({len(modified)}):")
        for f in modified[:10]:
            lines.append(f"    - {f}")

    recent = data.get("recent_commits", [])
    if recent:
        lines.append(f"  Recent commits ({len(recent)}):")
        for c in recent[:5]:
            lines.append(f"    - {c}")

    return "\n".join(lines)


def _fmt_active_threads(data: list) -> str:
    """Human-readable active threads."""
    if not data:
        return "All projects are on main with clean working trees."

    lines = [f"{len(data)} active thread(s):", ""]
    for t in data:
        lines.append(f"  {t.get('display_name', t.get('project', '?'))}")
        if t.get("branch") not in ("main", "master"):
            lines.append(f"    Branch: {t.get('branch')}")
        if t.get("uncommitted", 0) > 0:
            lines.append(f"    Uncommitted: {t['uncommitted']} files")
        lines.append(f"    Last: {t.get('last_commit', '?')}")
        lines.append("")

    return "\n".join(lines)


def _fmt_log_session(data: dict) -> str:
    """Human-readable session log confirmation."""
    projects = ", ".join(data.get("projects", []))
    return (
        f"Session logged for: {projects}\n"
        f"File: {data.get('session_file', '?')}"
    )


def _fmt_running_todo(data: dict) -> str:
    """Human-readable running TODO summary."""
    lines = [
        f"Open items: {data.get('total_open', 0)}",
        f"Completed: {data.get('total_completed', 0)}",
    ]

    by_source = data.get("by_source", {})
    if by_source:
        lines.append("")
        for source, items in sorted(by_source.items()):
            lines.append(f"  {source}:")
            for item in items[:5]:
                lines.append(f"    - [ ] {item}")
            if len(items) > 5:
                lines.append(f"    ... and {len(items) - 5} more")

    return "\n".join(lines)


def _fmt_init_vault(data: dict) -> str:
    """Human-readable vault init result."""
    if data.get("cancelled"):
        return "Vault initialization cancelled."
    return (
        f"Vault initialized at: {data.get('vault_path', '?')}\n"
        f"Tracking {data.get('repos_tracked', 0)} repos\n"
        f"Created {len(data.get('files_created', []))} files\n"
        f"\nNext: {data.get('next_step', 'run obsx sync-projects')}"
    )


def _fmt_rollback(data: dict) -> str:
    """Human-readable rollback output."""
    restored = data.get("restored", [])
    snap = data.get("snapshot", "?")
    lines = [f"Restored from snapshot: {snap}", f"Files restored: {len(restored)}"]
    for f in restored[:10]:
        lines.append(f"  {f}")
    if len(restored) > 10:
        lines.append(f"  ... and {len(restored) - 10} more")
    return "\n".join(lines)


def _fmt_drafts_list(data: list) -> str:
    """Human-readable draft listing."""
    if not data:
        return "No agent drafts found."
    lines: list[str] = []
    for d in data:
        status = d.get("status", "?")
        lines.append(f"  [{status}] {d.get('title', '?')} ({d.get('age_days', 0)}d old)")
        lines.append(f"    path: {d.get('path', '?')}")
        lines.append(f"    source: {d.get('source_tool', '?')}")
    return "\n".join(lines)


def _fmt_draft_action(data: dict) -> str:
    """Human-readable draft approve/reject output."""
    if data.get("error"):
        return f"Error: {data['error']}"
    if data.get("dry_run"):
        return f"[dry-run] Would move: {data.get('from', '?')} -> {data.get('to', '?')}"
    return f"{data.get('status', 'moved').capitalize()}: {data.get('from', '?')} -> {data.get('to', '?')}"


def _fmt_draft_clean(data: list) -> str:
    """Human-readable stale draft cleanup output."""
    if not data:
        return "No stale drafts to clean."
    lines = [f"Cleaned {len(data)} stale draft(s):"]
    for d in data:
        lines.append(f"  {d.get('from', '?')} -> {d.get('to', '?')}")
    return "\n".join(lines)


def _fmt_vaults_list(data: list) -> str:
    """Human-readable vault registry listing."""
    if not data:
        return "No vaults registered."
    lines: list[str] = []
    for v in data:
        default_marker = " (default)" if v.get("is_default") else ""
        lines.append(f"  {v.get('name', '?')}{default_marker}")
        lines.append(f"    path: {v.get('path', '?')}")
        lines.append(f"    profile: {v.get('profile', '?')}")
    return "\n".join(lines)


def _fmt_vault_action(data: dict) -> str:
    """Human-readable vault add/remove/default output."""
    if data.get("error"):
        return f"Error: {data['error']}"
    action = data.get("action", "done")
    name = data.get("name", "?")
    return f"Vault {name}: {action}"


def _fmt_templates_list(data: list) -> str:
    """Human-readable template listing."""
    if not data:
        return "No templates found."
    lines: list[str] = []
    for t in data:
        lines.append(f"  {t.get('name', '?')} (v{t.get('version', '?')})")
        desc = t.get("description", "")
        if desc:
            lines.append(f"    {desc}")
        variables = t.get("variables", [])
        if variables:
            lines.append(f"    variables: {', '.join(variables)}")
    return "\n".join(lines)


def _fmt_templates_init(data: dict) -> str:
    """Human-readable template init output."""
    written = data.get("written", [])
    if not written:
        return "No new templates written (all already exist)."
    return f"Initialized {len(written)} template(s): {', '.join(written)}"


def _fmt_templates_check(data: list) -> str:
    """Human-readable template check output."""
    if not data:
        return "All templates are up to date."
    lines = ["Outdated templates:"]
    for t in data:
        lines.append(f"  {t.get('name', '?')}: vault={t.get('vault_version', '?')} builtin={t.get('builtin_version', '?')}")
    return "\n".join(lines)


def _fmt_schedule_list(data: list) -> str:
    """Human-readable schedule listing."""
    if not data:
        return "No schedules configured."
    lines: list[str] = []
    for s in data:
        enabled = "enabled" if s.get("enabled", True) else "disabled"
        lines.append(f"  {s.get('name', '?')} [{enabled}] ({s.get('schedule_type', '?')})")
        chain = s.get("tool_chain", [])
        if chain:
            lines.append(f"    tools: {' -> '.join(chain)}")
    return "\n".join(lines)


def _fmt_schedule_preview(data: dict) -> str:
    """Human-readable schedule preview output."""
    name = data.get("name", "?")
    chain = data.get("tool_chain", [])
    if not chain:
        return f"Schedule {name}: no tools configured."
    lines = [f"Schedule {name} would run:"]
    for i, tool in enumerate(chain, 1):
        lines.append(f"  {i}. {tool}")
    return "\n".join(lines)


def _fmt_schedule_status(data: list) -> str:
    """Human-readable schedule status output."""
    if not data:
        return "No schedules configured."
    lines: list[str] = []
    for s in data:
        missed = " MISSED" if s.get("missed") else ""
        result = s.get("last_result") or "never"
        lines.append(f"  {s.get('name', '?')}: last={s.get('last_run', 'never')} result={result}{missed}")
        if s.get("next_run"):
            lines.append(f"    next: {s['next_run']}")
    return "\n".join(lines)


def _fmt_report(data: dict) -> str:
    """Human-readable report generation output."""
    return (
        f"Report generated: {data.get('report_type', '?')}\n"
        f"Path: {data.get('path', '?')}\n"
        f"Generated at: {data.get('generated_at', '?')}"
    )


def _fmt_stats(data: dict) -> str:
    """Human-readable telemetry stats output."""
    if not data:
        return "No telemetry data available."
    lines: list[str] = []
    lines.append(f"Notes read: {data.get('notes_read', 0)}")
    lines.append(f"Notes written: {data.get('notes_written', 0)}")
    lines.append(f"Errors: {data.get('errors', 0)}")
    lines.append(f"Retrieval misses: {data.get('retrieval_misses', 0)}")
    lines.append(f"Write risk events: {data.get('write_risk_events', 0)}")
    tools = data.get("tools_called", {})
    if tools:
        lines.append(f"Tools called ({len(tools)}):")
        for tool, count in sorted(tools.items(), key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"  {tool}: {count}")
    return "\n".join(lines)


def _fmt_project_health(data: list) -> str:
    """Human-readable project health output."""
    if not data:
        return "No project health data."
    lines: list[str] = []
    for p in data:
        status = p.get("status", "?")
        score = p.get("score", 0)
        lines.append(f"  {p.get('name', '?')}: {score:.0f}/100 [{status}]")
        factors = p.get("factors", {})
        if factors.get("days_since_last_commit"):
            lines.append(f"    last commit: {factors['days_since_last_commit']}d ago")
        if factors.get("open_todo_count"):
            lines.append(f"    open TODOs: {factors['open_todo_count']}")
    return "\n".join(lines)


def _fmt_project_changelog(data: str) -> str:
    """Human-readable project changelog (already Markdown)."""
    return data if data else "No changelog entries found."


def _fmt_project_packet(data: str) -> str:
    """Human-readable weekly project packet (already Markdown)."""
    return data if data else "No project activity in the requested period."


def _fmt_index_status(data: dict) -> str:
    """Human-readable index status output."""
    age = data.get("age_seconds", float("inf"))
    stale = data.get("is_stale", True)
    if age == float("inf"):
        return "Index: no data (never built or inaccessible)"
    lines = [
        f"Index age: {age:.0f}s ({age / 60:.1f}m)",
        f"Stale: {'yes' if stale else 'no'}",
    ]
    return "\n".join(lines)


def _fmt_commitments(items: list[dict]) -> str:
    """Human-readable commitment list."""
    if not items:
        return "No commitments found."
    lines: list[str] = []
    for c in items:
        overdue_marker = " OVERDUE" if c.get("overdue") else ""
        due = f"  due: {c['due_at']}" if c.get("due_at") else ""
        lines.append(f"  [{c['status']}] {c['title']}{overdue_marker}")
        lines.append(f"    id: {c['action_id']}  priority: {c['priority']}  project: {c['project'] or 'none'}")
        if due:
            lines.append(f"    {due.strip()}")
        lines.append(f"    path: {c['path']}")
    return "\n".join(lines)


def _fmt_commitment_detail(c: dict) -> str:
    """Human-readable single commitment detail."""
    lines = [
        f"{c['title']}",
        f"  action_id:      {c['action_id']}",
        f"  status:         {c['status']}",
        f"  priority:       {c['priority']}",
        f"  project:        {c['project'] or 'none'}",
        f"  due_at:         {c['due_at'] or 'none'}",
        f"  postponed_until:{c['postponed_until'] or 'none'}",
        f"  requires_ack:   {'yes' if c['requires_ack'] else 'no'}",
        f"  path:           {c['path']}",
    ]
    return "\n".join(lines)


def _fmt_mark_done(result: dict) -> str:
    """Human-readable mark-done output."""
    lines = [
        f"Marked done: {result['action_id']}",
        f"  previous status: {result['previous_status']}",
        f"  completed_at: {result['completed_at']}",
        f"  path: {result['path']}",
    ]
    if result.get("moved_from"):
        lines.append(f"  moved from: {result['moved_from']}")
    if result.get("service_sync"):
        sync = result["service_sync"]
        status = "synced" if sync.get("ok") else f"failed ({sync.get('error', '?')})"
        lines.append(f"  service sync: {status}")
    return "\n".join(lines)


def _fmt_postpone(result: dict) -> str:
    """Human-readable postpone output."""
    lines = [
        f"Postponed: {result['action_id']}",
        f"  until: {result['postponed_until']}",
        f"  path: {result['path']}",
    ]
    if result.get("service_sync"):
        sync = result["service_sync"]
        status = "synced" if sync.get("ok") else f"failed ({sync.get('error', '?')})"
        lines.append(f"  service sync: {status}")
    return "\n".join(lines)


def _fmt_add_reason(result: dict) -> str:
    """Human-readable add-reason output."""
    return (
        f"Reason added to: {result['action_id']}\n"
        f"  reason: {result['reason_added']}\n"
        f"  at: {result['timestamp']}\n"
        f"  path: {result['path']}"
    )


def _fmt_due_soon(items: list[dict], within_days: int = 3) -> str:
    """Human-readable due-soon list."""
    if not items:
        return f"No open commitments due within {within_days} day(s)."
    lines = [f"Due within {within_days} day(s): {len(items)} commitment(s)"]
    for c in items:
        overdue = " OVERDUE" if c.get("overdue") else ""
        lines.append(f"  {c['due_at']}{overdue}  {c['title']}")
        lines.append(f"    id: {c['action_id']}  priority: {c['priority']}")
    return "\n".join(lines)


def _fmt_sync_commitments(result: dict) -> str:
    """Human-readable sync-commitments output."""
    if not result.get("ok"):
        return f"Sync failed: {result.get('error', 'unknown error')}"
    lines = [
        f"Synced {result.get('synced', 0)} commitment(s) from service.",
        f"  source: {result.get('source_url', '?')}",
    ]
    errors = result.get("errors", [])
    if errors:
        lines.append(f"  errors ({len(errors)}):")
        for e in errors[:5]:
            lines.append(f"    {e}")
        if len(errors) > 5:
            lines.append(f"    ... and {len(errors) - 5} more")
    return "\n".join(lines)


def _fmt_review_dashboards(results) -> str:
    """Human-readable review-dashboards refresh output."""
    lines = [f"Refreshed {len(results)} review dashboard(s):"]
    for r in results:
        lines.append(f"  {r.path}  ({r.written} entries)")
    return "\n".join(lines)


def _fmt_find_commitments(result: dict) -> str:
    """Human-readable find-commitments output."""
    if not result.get("ok"):
        return f"Find failed: {result.get('error', 'unknown error')}"
    data = result.get("data", {}) or {}
    items = data.get("items", [])
    lines = [f"Found {len(items)} commitment(s):"]
    for it in items:
        due = it.get("due_at") or "(no due)"
        urgency = it.get("urgency", "normal")
        lines.append(
            f"  [{urgency}] {it.get('title', '(untitled)')}"
            f"  due: {due}  status: {it.get('status', '?')}"
        )
        lines.append(
            f"    id: {it.get('action_id', '?')}"
            f"  priority: {it.get('priority', '?')}"
            f"  stage: {it.get('lifecycle_stage', '?')}"
        )
    if data.get("next_cursor"):
        lines.append(f"  next_cursor: {data['next_cursor']}")
    return "\n".join(lines)


def _fmt_commitment_detail(result: dict) -> str:
    """Human-readable commitment-detail output."""
    if not result.get("ok"):
        return f"Detail fetch failed: {result.get('error', 'unknown error')}"
    data = result.get("data", {}) or {}
    action = data.get("action", {})
    if not action:
        return "(no action in response)"
    lines = [
        f"Action: {action.get('title', '(untitled)')}",
        f"  id:        {action.get('action_id', '?')}",
        f"  status:    {action.get('status', '?')}"
        f"  priority:  {action.get('priority', '?')}"
        f"  urgency:   {action.get('urgency', '?')}",
        f"  stage:     {action.get('lifecycle_stage', '?')}",
        f"  due_at:    {action.get('due_at') or '(none)'}",
        f"  next_fu:   {action.get('next_follow_up_at') or '(none)'}",
    ]
    proj = action.get("projects", [])
    ppl = action.get("people", [])
    areas = action.get("areas", [])
    if proj:
        lines.append(f"  projects:  {', '.join(proj)}")
    if ppl:
        lines.append(f"  people:    {', '.join(ppl)}")
    if areas:
        lines.append(f"  areas:     {', '.join(areas)}")
    deliveries = action.get("deliveries", [])
    if deliveries:
        lines.append(f"  deliveries ({len(deliveries)}):")
        for d in deliveries:
            lines.append(
                f"    {d.get('channel', '?')}: {d.get('status', '?')}"
                f" @ {d.get('scheduled_at') or '-'}"
            )
    return "\n".join(lines)


def _fmt_commitment_stats(result: dict) -> str:
    """Human-readable commitment-stats output."""
    if not result.get("ok"):
        return f"Stats fetch failed: {result.get('error', 'unknown error')}"
    data = result.get("data", {}) or {}
    lines = [f"Total actions: {data.get('total', 0)}"]

    def _render(title: str, mapping: dict) -> None:
        if not mapping:
            return
        lines.append(title)
        for k, v in sorted(mapping.items()):
            lines.append(f"    {k}: {v}")

    _render("by_status:", data.get("by_status", {}) or {})
    _render("by_lifecycle_stage:", data.get("by_lifecycle_stage", {}) or {})
    _render("by_priority:", data.get("by_priority", {}) or {})
    _render("by_source_app:", data.get("by_source_app", {}) or {})
    return "\n".join(lines)


# Map command names to their human-readable formatter.
_HUMAN_FORMATTERS: dict[str, callable] = {
    "search": _fmt_search,
    "tasks": _fmt_tasks,
    "find-prior-work": _fmt_prior_work,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-connector",
        description="Python CLI wrapper for the Obsidian desktop app.",
    )
    parser.add_argument(
        "--vault", default=None, help="Target vault name (overrides OBSIDIAN_VAULT).",
    )
    parser.add_argument(
        "--json", dest="as_json", action="store_true", default=False,
        help="Output canonical JSON envelope for any command.",
    )
    sub = parser.add_subparsers(dest="command")

    # -- log-daily ---------------------------------------------------------
    p = sub.add_parser("log-daily", help="Append text to today's daily note.")
    p.add_argument("content", help="Markdown text to append.")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- search ------------------------------------------------------------
    p = sub.add_parser("search", help="Full-text search across the vault.")
    p.add_argument("query", help="Search query string.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")
    p.add_argument("--max-results", type=int, default=None, help="Limit number of files returned.")
    p.add_argument("--context-lines", type=int, default=0, help="Lines of context around matches.")
    p.add_argument("--dedupe", action="store_true", help="Deduplicate matches per file.")
    p.add_argument("--profile", choices=["default", "journal", "project", "research", "review"], default=None, help="Retrieval profile for hybrid search.")
    p.add_argument("--explain", action="store_true", help="Include scoring breakdown in results.")

    # -- read --------------------------------------------------------------
    p = sub.add_parser("read", help="Read a note by name or path.")
    p.add_argument("note", help="Note name (wikilink) or vault-relative path.")

    # -- tasks -------------------------------------------------------------
    p = sub.add_parser("tasks", help="List tasks in the vault.")
    p.add_argument("--status", choices=["todo", "done"], default=None, help="Filter by completion status.")
    p.add_argument("--path-prefix", default=None, help="Filter by vault-relative path prefix.")
    p.add_argument("--due-before", default=None, metavar="DATE", help="Due before ISO date (stored, not yet enforced by CLI).")
    p.add_argument("--due-after", default=None, metavar="DATE", help="Due after ISO date (stored, not yet enforced by CLI).")
    p.add_argument("--limit", type=int, default=None, help="Max results.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- log-decision ------------------------------------------------------
    p = sub.add_parser("log-decision", help="Append a structured decision record to the daily note.")
    p.add_argument("--project", required=True, help="Project or workstream name.")
    p.add_argument("--summary", required=True, help="One-line decision summary.")
    p.add_argument("--details", required=True, help="Longer context or rationale (markdown OK).")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- create-research-note ----------------------------------------------
    p = sub.add_parser("create-research-note", help="Create a new note from a template.")
    p.add_argument("--title", required=True, help="Note title (becomes file name).")
    p.add_argument("--template", required=True, help='Template name (e.g. "Template, Note").')
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")

    # -- find-prior-work ---------------------------------------------------
    p = sub.add_parser("find-prior-work", help="Search for prior work on a topic and summarise hits.")
    p.add_argument("topic", help="Search topic.")
    p.add_argument("--top-n", type=int, default=5, help="Max notes to return (default 5).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- my-world ----------------------------------------------------------
    p = sub.add_parser("my-world", help="Snapshot of vault state: tasks, open loops, daily notes.")
    p.add_argument("--lookback-days", type=int, default=14, help="Days to look back for daily notes (default 14).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- today -------------------------------------------------------------
    p = sub.add_parser("today", help="Brief for today: daily note, tasks, open loops.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- close -------------------------------------------------------------
    p = sub.add_parser("close", help="End-of-day reflection prompts (read-only).")
    p.add_argument("--confirm", action="store_true", help="Reserved for future write support (currently ignored).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- open-loops --------------------------------------------------------
    p = sub.add_parser("open-loops", help="List open loops (OL: lines and #openloop tags).")
    p.add_argument("--lookback-days", type=int, default=30, help="Lookback window in days (default 30).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- challenge ---------------------------------------------------------
    p = sub.add_parser("challenge", help="Challenge a belief against vault evidence.")
    p.add_argument("belief", help="The belief to challenge.")
    p.add_argument("--max-evidence", type=int, default=10, help="Max evidence items (default 10).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- emerge ------------------------------------------------------------
    p = sub.add_parser("emerge", help="Cluster notes into idea groups around a topic.")
    p.add_argument("topic", help="Topic to explore.")
    p.add_argument("--max-clusters", type=int, default=5, help="Max clusters (default 5).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- connect -----------------------------------------------------------
    p = sub.add_parser("connect", help="Find connections between two domains.")
    p.add_argument("domain_a", help="First domain.")
    p.add_argument("domain_b", help="Second domain.")
    p.add_argument("--max-connections", type=int, default=10, help="Max connections (default 10).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- neighborhood ------------------------------------------------------
    p = sub.add_parser("neighborhood", help="Graph neighborhood of a note: backlinks, forward links, tags, neighbors.")
    p.add_argument("note", help="Note name or vault-relative path.")
    p.add_argument("--depth", type=int, default=1, help="Traversal depth for neighbors (default 1).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- vault-structure ---------------------------------------------------
    p = sub.add_parser("vault-structure", help="Vault topology: orphans, dead ends, unresolved links, tag cloud.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- backlinks ---------------------------------------------------------
    p = sub.add_parser("backlinks", help="All notes that link to a given note, with context.")
    p.add_argument("note", help="Note name or vault-relative path.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- ghost -------------------------------------------------------------
    p = sub.add_parser("ghost", help="Analyze writing voice from recent notes.")
    p.add_argument("question", nargs="?", default=None, help="Optional question to answer in the user's voice.")
    p.add_argument("--sample", type=int, default=20, help="Number of recent notes to sample (default 20).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- drift -------------------------------------------------------------
    p = sub.add_parser("drift", help="Analyze drift between intentions and behavior.")
    p.add_argument("--days", type=int, default=60, help="Lookback days (default 60).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- trace -------------------------------------------------------------
    p = sub.add_parser("trace", help="Trace an idea's evolution across vault notes.")
    p.add_argument("topic", help="Topic to trace.")
    p.add_argument("--max-notes", type=int, default=20, help="Max notes in timeline (default 20).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- ideas -------------------------------------------------------------
    p = sub.add_parser("ideas", help="Surface latent ideas from vault graph structure.")
    p.add_argument("--max", type=int, default=10, help="Max ideas to return (default 10).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- graduate ----------------------------------------------------------
    grad = sub.add_parser("graduate", help="Graduate ideas from daily notes to standalone drafts.")
    grad_sub = grad.add_subparsers(dest="graduate_action")

    p = grad_sub.add_parser("list", help="Scan recent daily notes for graduate candidates.")
    p.add_argument("--lookback", type=int, default=7, help="Days to look back (default 7).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = grad_sub.add_parser("execute", help="Create an agent draft note.")
    p.add_argument("--title", required=True, help="Note title.")
    p.add_argument("--content", default="", help="Note body (markdown).")
    p.add_argument("--source", default=None, help="Source daily note path.")
    p.add_argument("--confirm", action="store_true", help="Actually create the note.")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="Preview without writing.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- rebuild-index -----------------------------------------------------
    p = sub.add_parser("rebuild-index", help="Rebuild the vault graph index.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- delegations -------------------------------------------------------
    p = sub.add_parser("delegations", help="Scan for @agent:/@claude: delegation instructions.")
    p.add_argument("--days", type=int, default=1, help="Lookback days (default 1).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- context-load ------------------------------------------------------
    p = sub.add_parser("context-load", help="Load full context bundle for agent session.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- check-in ----------------------------------------------------------
    p = sub.add_parser("check-in", help="Time-aware check-in: what should you do now?")
    p.add_argument("--timezone", default=None, help="IANA timezone (e.g. America/New_York).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- doctor ------------------------------------------------------------
    sub.add_parser("doctor", help="Run health checks on Obsidian CLI and vault connectivity.")

    # -- uninstall ---------------------------------------------------------
    p = sub.add_parser("uninstall", help="Safely remove obsidian-connector (interactive or MCP mode).")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what will be removed without making changes."
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Non-interactive mode (for MCP) - requires explicit flags for each artifact type."
    )
    p.add_argument(
        "--remove-venv",
        action="store_true",
        help="Remove .venv directory (use with --force)."
    )
    p.add_argument(
        "--remove-skills",
        action="store_true",
        help="Remove Claude Code skills (use with --force)."
    )
    p.add_argument(
        "--remove-hook",
        action="store_true",
        help="Remove SessionStart hook (use with --force)."
    )
    p.add_argument(
        "--remove-plist",
        action="store_true",
        help="Remove launchd plist (use with --force)."
    )
    p.add_argument(
        "--remove-logs",
        action="store_true",
        help="Remove logs (use with --force)."
    )
    p.add_argument(
        "--remove-cache",
        action="store_true",
        help="Remove cache/index files (use with --force)."
    )
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- sync-projects -----------------------------------------------------
    p = sub.add_parser("sync-projects", help="Sync all tracked repos into the vault.")
    p.add_argument("--github-root", default=None, help="Path to directory containing git repos.")
    p.add_argument("--no-todo", action="store_true", help="Skip Running TODO update.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- project-status ----------------------------------------------------
    p = sub.add_parser("project-status", help="Get git status for a single project.")
    p.add_argument("project", help="Directory name of the project.")
    p.add_argument("--github-root", default=None, help="Path to directory containing git repos.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- active-threads ----------------------------------------------------
    p = sub.add_parser("active-threads", help="List projects with active work.")
    p.add_argument("--github-root", default=None, help="Path to directory containing git repos.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- log-session -------------------------------------------------------
    p = sub.add_parser("log-session", help="Write a session log entry to the vault.")
    p.add_argument("--projects", required=True, help="Pipe-separated project names.")
    p.add_argument("--work-types", default="", help="Pipe-separated work types.")
    p.add_argument("--completed", default="", help="Pipe-separated completed items.")
    p.add_argument("--next-steps", default="", help="Pipe-separated next step items.")
    p.add_argument("--decisions", default="", help="Pipe-separated decision notes.")
    p.add_argument("--context", default="", help="Free-text session context.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- running-todo ------------------------------------------------------
    p = sub.add_parser("running-todo", help="Show the running TODO state.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- init --------------------------------------------------------------
    p = sub.add_parser("init", help="Initialize a new vault for project tracking.")
    p.add_argument("--vault-path", default=None, help="Path for the new vault.")
    p.add_argument("--github-root", default=None, help="Path to directory containing git repos.")
    p.add_argument("--use-defaults", action="store_true", help="Use built-in default repo list.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- rollback ----------------------------------------------------------
    p = sub.add_parser("rollback", help="Restore vault files from a snapshot.")
    p.add_argument("--last", action="store_true", default=True, help="Restore from the most recent snapshot (default).")
    p.add_argument("--snapshot", default=None, help="Specific snapshot directory to restore.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be restored without mutating.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- drafts ------------------------------------------------------------
    drafts_p = sub.add_parser("drafts", help="Manage agent-generated draft notes.")
    drafts_sub = drafts_p.add_subparsers(dest="drafts_action")

    p = drafts_sub.add_parser("list", help="List all agent drafts.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = drafts_sub.add_parser("approve", help="Move a draft to a target folder.")
    p.add_argument("path", help="Vault-relative path to the draft.")
    p.add_argument("--target", required=True, help="Target folder for the approved draft.")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = drafts_sub.add_parser("reject", help="Archive a draft as rejected.")
    p.add_argument("path", help="Vault-relative path to the draft.")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without mutating.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = drafts_sub.add_parser("clean", help="Auto-archive stale drafts.")
    p.add_argument("--max-age", type=int, default=14, help="Max draft age in days (default 14).")
    p.add_argument("--dry-run", action="store_true", help="Show what would be archived without mutating.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- vaults ------------------------------------------------------------
    vaults_p = sub.add_parser("vaults", help="Manage the named vault registry.")
    vaults_sub = vaults_p.add_subparsers(dest="vaults_action")

    p = vaults_sub.add_parser("list", help="List all registered vaults.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = vaults_sub.add_parser("add", help="Register a new vault.")
    p.add_argument("name", help="Vault name.")
    p.add_argument("path", help="Filesystem path to the vault directory.")
    p.add_argument("--profile", choices=["personal", "work", "research", "creative"], default="personal", help="Vault profile (default personal).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = vaults_sub.add_parser("remove", help="Unregister a vault.")
    p.add_argument("name", help="Vault name to remove.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = vaults_sub.add_parser("default", help="Set a vault as the default.")
    p.add_argument("name", help="Vault name to set as default.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- templates ---------------------------------------------------------
    templates_p = sub.add_parser("templates", help="Manage vault templates.")
    templates_sub = templates_p.add_subparsers(dest="templates_action")

    p = templates_sub.add_parser("list", help="List all templates in the vault.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = templates_sub.add_parser("init", help="Seed _templates/ from built-in templates.")
    p.add_argument("--dry-run", action="store_true", help="Show what would be created without mutating.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = templates_sub.add_parser("check", help="Show outdated templates.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- schedule ----------------------------------------------------------
    schedule_p = sub.add_parser("schedule", help="Manage connector schedules.")
    schedule_sub = schedule_p.add_subparsers(dest="schedule_action")

    p = schedule_sub.add_parser("list", help="List all configured schedules.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = schedule_sub.add_parser("preview", help="Show what a schedule would run.")
    p.add_argument("name", help="Schedule name.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = schedule_sub.add_parser("status", help="Show health of all schedules.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = schedule_sub.add_parser("run", help="Execute a named schedule now.")
    p.add_argument("name", help="Schedule name to execute.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = schedule_sub.add_parser("fire", help="Fire an event trigger.")
    p.add_argument("event", help="Event name (after_sync, after_note_create, after_session_end).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = schedule_sub.add_parser("tools", help="List available automation tools.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- report ------------------------------------------------------------
    p = sub.add_parser("report", help="Generate a vault report.")
    p.add_argument("type", choices=["weekly", "monthly", "vault-health", "project-status"], help="Report type.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- stats -------------------------------------------------------------
    p = sub.add_parser("stats", help="Show session telemetry stats.")
    p.add_argument("--weekly", action="store_true", help="Show weekly aggregate instead of current session.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- project -----------------------------------------------------------
    project_p = sub.add_parser("project", help="Project intelligence commands.")
    project_sub = project_p.add_subparsers(dest="project_action")

    p = project_sub.add_parser("health", help="Show health scores for all projects.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = project_sub.add_parser("changelog", help="Generate a project changelog.")
    p.add_argument("name", help="Project name.")
    p.add_argument("--days", type=int, default=7, help="Lookback days (default 7).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    p = project_sub.add_parser("packet", help="Generate a weekly project packet.")
    p.add_argument("--days", type=int, default=7, help="Lookback days (default 7).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- index-status ------------------------------------------------------
    p = sub.add_parser("index-status", help="Show index age and staleness.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- ix (intercepted) --------------------------------------------------
    p = sub.add_parser("ix", help="Ix codebase mapping engine (intercepted early). Run 'obsx ix --help' for details.")

    # -- run (recipes) -----------------------------------------------------
    p = sub.add_parser("run", help="Run a determinisic YAML workflow recipe from ~/.obsx/recipes/.")

    # -- menu (interactive dashboard) --------------------------------------
    p = sub.add_parser(
        "menu",
        help="Open the interactive configuration dashboard (requires the optional 'tui' extra).",
    )

    # -- setup-wizard (first-run onboarding) -------------------------------
    p = sub.add_parser(
        "setup-wizard",
        help="Run the interactive setup wizard (requires the optional 'tui' extra).",
    )

    # -- commitments -------------------------------------------------------
    p = sub.add_parser("commitments", help="List commitment notes in the vault.")
    p.add_argument("--status", choices=["open", "done"], default=None, help="Filter by status.")
    p.add_argument("--project", default=None, help="Filter by project name (case-insensitive).")
    p.add_argument("--priority", choices=["low", "normal", "high"], default=None, help="Filter by priority.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- commitment-status -------------------------------------------------
    p = sub.add_parser("commitment-status", help="Show the current state of a commitment.")
    p.add_argument("action_id", help="action_id from the commitment frontmatter.")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- mark-done ---------------------------------------------------------
    p = sub.add_parser("mark-done", help="Mark a commitment as done.")
    p.add_argument("action_id", help="action_id of the commitment to close.")
    p.add_argument("--completed-at", default=None, metavar="ISO_TIMESTAMP", help="Completion timestamp (default: now).")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing.")

    # -- postpone ----------------------------------------------------------
    p = sub.add_parser("postpone", help="Set or update postponed_until on a commitment.")
    p.add_argument("action_id", help="action_id of the commitment to postpone.")
    p.add_argument("--until", required=True, metavar="ISO_TIMESTAMP", help="Resurface timestamp (ISO 8601).")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing.")

    # -- add-reason --------------------------------------------------------
    p = sub.add_parser("add-reason", help="Append a timestamped reason to a commitment's notes.")
    p.add_argument("action_id", help="action_id of the target commitment.")
    p.add_argument("reason", help="Reason text to append.")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing.")

    # -- due-soon ----------------------------------------------------------
    p = sub.add_parser("due-soon", help="List open commitments due within N days.")
    p.add_argument("--within-days", type=int, default=3, metavar="N", help="Look-ahead window in days (default 3).")
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- sync-commitments --------------------------------------------------
    p = sub.add_parser("sync-commitments", help="Sync commitments from obsidian-capture-service.")
    p.add_argument("--service-url", default=None, help="Base URL of the capture service (overrides env var).")
    p.add_argument("--dry-run", action="store_true", help="Show what would happen without writing.")

    # -- review-dashboards -------------------------------------------------
    p = sub.add_parser(
        "review-dashboards",
        help="Regenerate Daily/Weekly/Stale/Merge Candidates review dashboards.",
    )
    p.add_argument(
        "--stale-days", type=int, default=14, metavar="N",
        help="Threshold (days) for the Weekly + Stale surfaces (default 14).",
    )
    p.add_argument(
        "--merge-window-days", type=int, default=14, metavar="N",
        help="Max days between created_at of merge-candidate pairs (default 14).",
    )
    p.add_argument(
        "--merge-jaccard", type=float, default=0.6, metavar="X",
        help="Minimum title token-Jaccard for candidate pairs (default 0.6).",
    )
    p.add_argument(
        "--now", default=None, metavar="ISO_TIMESTAMP",
        help="Reference timestamp for deterministic output (default: now).",
    )
    p.add_argument("--json", dest="sub_json", action="store_true", help="(alias for global --json)")

    # -- find-commitments (Task 28) ---------------------------------------
    p = sub.add_parser(
        "find-commitments",
        help="Query the capture service's GET /api/v1/actions endpoint with filters.",
    )
    p.add_argument("--status", default=None, help="Filter by action status.")
    p.add_argument(
        "--lifecycle-stage", dest="lifecycle_stage", default=None,
        help="Filter by lifecycle stage.",
    )
    p.add_argument("--project", default=None, help="Filter by project (canonical or alias).")
    p.add_argument("--person", default=None, help="Filter by person (canonical or alias).")
    p.add_argument("--area", default=None, help="Filter by area (canonical or alias).")
    p.add_argument("--urgency", default=None, help="low | normal | elevated | critical")
    p.add_argument("--priority", default=None, help="low | normal | high | urgent")
    p.add_argument(
        "--source-app", dest="source_app", default=None,
        help="Filter by source app (e.g. wispr_flow).",
    )
    p.add_argument(
        "--due-before", dest="due_before", default=None, metavar="ISO",
        help="Only actions with due_at <= ISO.",
    )
    p.add_argument(
        "--due-after", dest="due_after", default=None, metavar="ISO",
        help="Only actions with due_at >= ISO.",
    )
    p.add_argument("--limit", type=int, default=50, help="Page size (default 50, max 200).")
    p.add_argument("--cursor", default=None, help="Opaque cursor from a prior response.")
    p.add_argument(
        "--service-url", dest="service_url", default=None,
        help="Overrides OBSIDIAN_CAPTURE_SERVICE_URL.",
    )
    p.add_argument(
        "--json", dest="sub_json", action="store_true",
        help="(alias for global --json)",
    )

    # -- commitment-detail (Task 28) --------------------------------------
    p = sub.add_parser(
        "commitment-detail",
        help="Fetch a single action from the capture service by ID.",
    )
    p.add_argument("--action-id", dest="action_id", required=True, help="Action ULID.")
    p.add_argument(
        "--service-url", dest="service_url", default=None,
        help="Overrides OBSIDIAN_CAPTURE_SERVICE_URL.",
    )
    p.add_argument(
        "--json", dest="sub_json", action="store_true",
        help="(alias for global --json)",
    )

    # -- commitment-stats (Task 28) ---------------------------------------
    p = sub.add_parser(
        "commitment-stats",
        help="Fetch grouped action counts from the capture service.",
    )
    p.add_argument(
        "--service-url", dest="service_url", default=None,
        help="Overrides OBSIDIAN_CAPTURE_SERVICE_URL.",
    )
    p.add_argument(
        "--json", dest="sub_json", action="store_true",
        help="(alias for global --json)",
    )

    return parser


def _resolve_json(args: argparse.Namespace) -> bool:
    """Return True if JSON output was requested via global or subcommand flag."""
    return args.as_json or getattr(args, "sub_json", False)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "run":
        from obsidian_connector.recipes import run_recipe
        try:
            return run_recipe(argv[1], argv[2:]) if len(argv) > 1 else run_recipe("", [])
        except SystemExit as e:
            return e.code or 0
            
    # Early intercept for ix commands
    if argv and argv[0] == "ix":
        from obsidian_connector.ix_engine.runner import run_ix
        # Re-write sys.argv so ix parser works properly
        sys.argv = [sys.argv[0] + " ix"] + argv[1:]
        try:
            return run_ix(argv[1:])
        except SystemExit as e:
            return e.code or 0
        except Exception as e:
            import traceback
            traceback.print_exc()
            return 1

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # If no command given and this is the very first run, launch wizard
        if is_first_run():
            return _run_tui_entrypoint("run_wizard", "interactive setup wizard")
        parser.print_help()
        return 0

    if args.command == "menu":
        return _run_tui_entrypoint("run_menu", "interactive dashboard")

    if args.command == "setup-wizard":
        return _run_tui_entrypoint("run_wizard", "interactive setup wizard")

    use_json = _resolve_json(args)
    cfg = load_config()
    vault = args.vault or cfg.default_vault
    t0 = time.monotonic()

    try:
        data: object = None
        human: str | None = None

        if args.command == "log-daily":
            dry = getattr(args, "dry_run", False)
            log_action(
                "log-daily", {"content": args.content}, vault,
                dry_run=dry, affected_path="daily", content=args.content,
            )
            if dry:
                data = {"dry_run": True, "action": "append_to_daily", "content": args.content}
                human = f"[dry-run] Would append to daily note:\n  {args.content}"
            else:
                log_to_daily(args.content, vault=args.vault)
                data = {"appended": True}
                human = "Appended to daily note."

        elif args.command == "search":
            use_hybrid = getattr(args, "profile", None) or getattr(args, "explain", False)
            if use_hybrid:
                from obsidian_connector.config import resolve_vault_path
                vault_path = resolve_vault_path(args.vault)
                profile = getattr(args, "profile", None) or "default"
                explain = getattr(args, "explain", False)
                top_k = getattr(args, "max_results", None) or 10
                hybrid_results = hybrid_search(
                    query=args.query,
                    vault_path=vault_path,
                    profile=profile,
                    top_k=top_k,
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
                human = _fmt_hybrid_search(hybrid_results, explain=explain)
            else:
                results = search_notes(args.query, vault=args.vault)
                results = enrich_search_results(
                    results,
                    vault=args.vault,
                    context_lines=getattr(args, "context_lines", 0),
                    dedupe=getattr(args, "dedupe", False),
                    max_results=getattr(args, "max_results", None),
                )
                data = results
                human = _fmt_search(results)

        elif args.command == "read":
            content = read_note(args.note, vault=args.vault)
            data = {"file": args.note, "content": content}
            human = content.rstrip("\n")

        elif args.command == "tasks":
            f: dict = {}
            if args.status == "todo":
                f["todo"] = True
            elif args.status == "done":
                f["done"] = True
            if args.path_prefix:
                f["path"] = args.path_prefix
            if args.limit is not None:
                f["limit"] = args.limit
            if args.due_before:
                f["due_before"] = args.due_before
            if args.due_after:
                f["due_after"] = args.due_after
            results = list_tasks(filter=f or None, vault=args.vault)
            data = results
            human = _fmt_tasks(results)

        elif args.command == "log-decision":
            dry = getattr(args, "dry_run", False)
            log_action(
                "log-decision",
                {"project": args.project, "summary": args.summary, "details": args.details},
                vault, dry_run=dry, affected_path="daily",
                content=args.details,
            )
            if dry:
                data = {
                    "dry_run": True, "action": "log_decision",
                    "project": args.project, "summary": args.summary, "details": args.details,
                }
                human = (
                    f"[dry-run] Would log decision:\n"
                    f"  project: {args.project}\n"
                    f"  summary: {args.summary}\n"
                    f"  details: {args.details}"
                )
            else:
                log_decision(
                    project=args.project,
                    summary=args.summary,
                    details=args.details,
                    vault=args.vault,
                )
                data = {"logged": True, "project": args.project}
                human = "Decision logged to daily note."

        elif args.command == "create-research-note":
            dry = getattr(args, "dry_run", False)
            log_action(
                "create-research-note",
                {"title": args.title, "template": args.template},
                vault, dry_run=dry, affected_path=f"{args.title}.md",
            )
            if dry:
                data = {
                    "dry_run": True, "action": "create_research_note",
                    "title": args.title, "template": args.template,
                }
                human = (
                    f"[dry-run] Would create note:\n"
                    f"  title:    {args.title}\n"
                    f"  template: {args.template}"
                )
            else:
                path = create_research_note(
                    title=args.title,
                    template=args.template,
                    vault=args.vault,
                )
                data = {"created": True, "path": path}
                human = f"Created: {path}"

        elif args.command == "find-prior-work":
            results = find_prior_work(
                topic=args.topic,
                vault=args.vault,
                top_n=args.top_n,
            )
            data = results
            human = _fmt_prior_work(results)

        elif args.command == "my-world":
            result = my_world_snapshot(
                vault=args.vault,
                lookback_days=args.lookback_days,
            )
            data = result
            human = _fmt_my_world(result)

        elif args.command == "today":
            result = today_brief(vault=args.vault)
            data = result
            human = _fmt_today(result)

        elif args.command == "close":
            result = close_day_reflection(vault=args.vault)
            data = result
            human = _fmt_close(result)

        elif args.command == "open-loops":
            result = list_open_loops(
                vault=args.vault,
                lookback_days=args.lookback_days,
            )
            data = result
            human = _fmt_open_loops(result)

        elif args.command == "challenge":
            result = challenge_belief(
                belief=args.belief,
                vault=args.vault,
                max_evidence=args.max_evidence,
            )
            data = result
            human = _fmt_challenge(result)

        elif args.command == "emerge":
            result = emerge_ideas(
                topic=args.topic,
                vault=args.vault,
                max_clusters=args.max_clusters,
            )
            data = result
            human = _fmt_emerge(result)

        elif args.command == "connect":
            result = connect_domains(
                domain_a=args.domain_a,
                domain_b=args.domain_b,
                vault=args.vault,
                max_connections=args.max_connections,
            )
            data = result
            human = _fmt_connect(result)

        elif args.command == "neighborhood":
            from obsidian_connector.index_store import load_or_build_index as _load_or_build_index
            idx = _load_or_build_index(args.vault)
            if idx is None:
                raise ObsidianCLIError(
                    command=["neighborhood"],
                    returncode=1,
                    stdout="",
                    stderr="Could not build note index",
                )
            # Resolve note path.
            note = args.note
            resolved = None
            if note in idx.notes:
                resolved = note
            else:
                for path, entry in idx.notes.items():
                    if entry.title.lower() == note.lower():
                        resolved = path
                        break
                if resolved is None and not note.endswith(".md"):
                    candidate = note + ".md"
                    if candidate in idx.notes:
                        resolved = candidate
            if resolved is None:
                raise ObsidianCLIError(
                    command=["neighborhood"],
                    returncode=1,
                    stdout="",
                    stderr=f"Note not found in index: {note}",
                )
            entry = idx.notes[resolved]
            result = {
                "note": resolved,
                "backlinks": sorted(idx.backlinks.get(resolved, set())),
                "forward_links": sorted(idx.forward_links.get(resolved, set())),
                "tags": entry.tags,
                "neighbors": sorted(idx.neighborhood(resolved, depth=args.depth)),
            }
            data = result
            human = _fmt_neighborhood(result)

        elif args.command == "vault-structure":
            from obsidian_connector.index_store import load_or_build_index as _load_or_build_index
            idx = _load_or_build_index(args.vault)
            if idx is None:
                raise ObsidianCLIError(
                    command=["vault-structure"],
                    returncode=1,
                    stdout="",
                    stderr="Could not build note index",
                )
            orphans = sorted(idx.orphans)[:20]
            dead_ends = sorted(idx.dead_ends)[:20]
            unresolved_sorted = sorted(
                idx.unresolved.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            )[:20]
            unresolved_links = {
                link: sorted(sources) for link, sources in unresolved_sorted
            }
            tag_counts = sorted(
                ((tag, len(paths)) for tag, paths in idx.tags.items()),
                key=lambda x: x[1],
                reverse=True,
            )[:30]
            tag_cloud = {tag: count for tag, count in tag_counts}
            backlink_counts = sorted(
                (
                    (path, len(bl))
                    for path, bl in idx.backlinks.items()
                    if bl
                ),
                key=lambda x: x[1],
                reverse=True,
            )[:10]
            top_connected = [
                {"note": path, "backlink_count": count}
                for path, count in backlink_counts
            ]
            result = {
                "total_notes": len(idx.notes),
                "orphans": orphans,
                "dead_ends": dead_ends,
                "unresolved_links": unresolved_links,
                "tag_cloud": tag_cloud,
                "top_connected": top_connected,
            }
            data = result
            human = _fmt_vault_structure(result)

        elif args.command == "backlinks":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.errors import VaultNotFound
            from obsidian_connector.index_store import load_or_build_index as _load_or_build_index
            from pathlib import Path as _Path
            idx = _load_or_build_index(args.vault)
            if idx is None:
                raise ObsidianCLIError(
                    command=["backlinks"],
                    returncode=1,
                    stdout="",
                    stderr="Could not build note index",
                )
            # Resolve note path.
            note = args.note
            resolved = None
            if note in idx.notes:
                resolved = note
            else:
                for path, entry in idx.notes.items():
                    if entry.title.lower() == note.lower():
                        resolved = path
                        break
                if resolved is None and not note.endswith(".md"):
                    candidate = note + ".md"
                    if candidate in idx.notes:
                        resolved = candidate
            if resolved is None:
                raise ObsidianCLIError(
                    command=["backlinks"],
                    returncode=1,
                    stdout="",
                    stderr=f"Note not found in index: {note}",
                )
            note_title = idx.notes[resolved].title
            backlink_paths = sorted(idx.backlinks.get(resolved, set()))
            # Resolve vault root once before iterating backlinks.
            try:
                _vault_root = resolve_vault_path(args.vault).resolve()
            except VaultNotFound:
                _vault_root = None
            results_list: list[dict] = []
            for bl_path in backlink_paths:
                bl_entry = idx.notes.get(bl_path)
                context_line = ""
                # Read the backlinking note directly from vault files (no Obsidian CLI needed).
                if _vault_root is not None:
                    try:
                        _note_p = _Path(bl_path)
                        if not _note_p.is_absolute():
                            _full = (_vault_root / _note_p).resolve()
                            _full.relative_to(_vault_root)  # raises ValueError if outside vault
                            if _full.is_file():
                                content = _full.read_text(encoding="utf-8", errors="replace")
                                for line in content.split("\n"):
                                    if f"[[{note_title}]]" in line or f"[[{note_title}|" in line:
                                        context_line = line.strip()
                                        break
                                    if f"[[{resolved}" in line:
                                        context_line = line.strip()
                                        break
                    except (ValueError, OSError):
                        pass
                results_list.append({
                    "file": bl_path,
                    "context_line": context_line,
                    "tags": bl_entry.tags if bl_entry else [],
                })
            data = results_list
            human = _fmt_backlinks(results_list)

        elif args.command == "ghost":
            result = ghost_voice_profile(
                vault=args.vault,
                sample_notes=args.sample,
            )
            if args.question:
                result["question"] = args.question
            data = result
            human = _fmt_ghost(result)

        elif args.command == "drift":
            result = drift_analysis(
                vault=args.vault,
                lookback_days=args.days,
            )
            data = result
            human = _fmt_drift(result)

        elif args.command == "trace":
            result = trace_idea(
                topic=args.topic,
                vault=args.vault,
                max_notes=args.max_notes,
            )
            data = result
            human = _fmt_trace(result)

        elif args.command == "ideas":
            result = deep_ideas(
                vault=args.vault,
                max_ideas=args.max,
            )
            data = result
            human = _fmt_ideas(result)

        elif args.command == "graduate":
            action = getattr(args, "graduate_action", None)
            if action == "list":
                result = graduate_candidates(
                    vault=args.vault, lookback_days=args.lookback,
                )
                data = result
                human = _fmt_graduate_list(result)
            elif action == "execute":
                if not args.confirm and not args.dry_run:
                    print("Error: graduate execute requires --confirm or --dry-run", file=sys.stderr)
                    return 1
                result = graduate_execute(
                    title=args.title,
                    content=args.content,
                    vault=args.vault,
                    source_file=args.source,
                    confirm=args.confirm,
                    dry_run=args.dry_run,
                )
                data = result
                human = _fmt_graduate_exec(result)
            else:
                parser.parse_args(["graduate", "--help"])
                return 0

        elif args.command == "rebuild-index":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.index_store import IndexStore

            vault_path = resolve_vault_path(args.vault)
            store = IndexStore()
            try:
                t0_rebuild = time.monotonic()
                index = store.build_full(vault_path=vault_path)
                rebuild_ms = int((time.monotonic() - t0_rebuild) * 1000)
            finally:
                store.close()

            data = {
                "notes_indexed": len(index.notes),
                "orphans": len(index.orphans),
                "tags": len(index.tags),
                "duration_ms": rebuild_ms,
            }
            human = _fmt_rebuild_index(data)

        elif args.command == "delegations":
            result = detect_delegations(
                vault=args.vault,
                lookback_days=args.days,
            )
            data = result
            human = _fmt_delegations(result)

        elif args.command == "context-load":
            result = context_load_full(vault=args.vault)
            data = result
            human = _fmt_context_load(result)

        elif args.command == "check-in":
            result = check_in(vault=vault, timezone_name=args.timezone)
            data = result
            human = _fmt_check_in(result)

        elif args.command == "uninstall":
            # Resolve paths
            repo_root = Path(__file__).parent.parent
            venv_path = repo_root / ".venv"
            from obsidian_connector.platform import get_platform_paths
            claude_config_path = get_platform_paths().claude_config_dir / "claude_desktop_config.json"

            # Detect what's installed
            plan = detect_installed_artifacts(
                repo_root=repo_root,
                venv_path=venv_path,
                claude_config_path=claude_config_path
            )

            # Handle --dry-run flag
            if args.dry_run:
                result = dry_run_uninstall(plan)
                data = result
                human = _format_uninstall_plan(result)
            # Handle --force flag (MCP mode)
            elif args.force:
                plan.remove_venv = args.remove_venv
                plan.remove_skills = args.remove_skills
                plan.remove_hook = args.remove_hook
                plan.remove_plist = args.remove_plist
                plan.remove_logs = args.remove_logs
                plan.remove_cache = args.remove_cache
                result = execute_uninstall(plan, config_path=claude_config_path)
                data = result
                human = _format_uninstall_result(result)
            # Interactive mode (default for CLI)
            else:
                print("\nObsidian Connector Uninstaller")
                print("=" * 40)
                print("\nWhat would you like to keep?")
                print()

                # Log the uninstall action with interactive mode intent
                log_action(
                    "uninstall",
                    {"mode": "interactive", "force": False},
                    vault,
                    dry_run=False,
                    affected_path="system-config",
                )

                # Ask about each artifact type (safe default: keep)
                plan.remove_venv = input("Remove .venv directory? [y/N] ").lower() in ["y", "yes"]
                plan.remove_skills = input("Remove Claude Code skills? [y/N] ").lower() in ["y", "yes"]
                plan.remove_hook = input("Remove SessionStart hook? [y/N] ").lower() in ["y", "yes"]

                # Add explicit prompt for Claude config entry
                keep_claude_config = input("Keep Claude config entry? [Y/n] ").lower() not in ["n", "no"]
                if not keep_claude_config and plan.config_changes:
                    # Mark to remove config entry
                    pass
                elif keep_claude_config and plan.config_changes:
                    # Don't remove config entry
                    plan.config_changes = {}

                plan.remove_plist = input("Remove launchd/systemd schedule? [y/N] ").lower() in ["y", "yes"]
                plan.remove_logs = input("Remove logs? [y/N] ").lower() in ["y", "yes"]
                plan.remove_cache = input("Remove cache/index files? [y/N] ").lower() in ["y", "yes"]

                # Show plan
                print("\n" + "=" * 40)
                print("Removal Plan:")
                print("=" * 40)
                if plan.remove_venv and venv_path.exists():
                    print(f"  - Remove: {venv_path}")
                if plan.remove_skills:
                    print("  - Remove: Claude Code skills from .claude/commands/")
                if plan.remove_hook:
                    print("  - Remove: SessionStart hook from .claude/settings.json")
                if plan.remove_plist and plan.plist_path:
                    print(f"  - Remove: {plan.plist_path}")
                if plan.remove_logs:
                    print("  - Remove: Audit logs")
                if plan.remove_cache:
                    print("  - Remove: Index cache")
                for config_file, change in plan.config_changes.items():
                    if change.get("action") == "remove_key":
                        path_str = " > ".join(change.get("path", []))
                        print(f"  - Remove from {config_file}: {path_str}")

                # Final confirmation
                print()
                confirm = input("Proceed with removal? [y/N] ").lower() in ["y", "yes"]

                if not confirm:
                    print("Cancelled.")
                    data = {"cancelled": True}
                    human = "Uninstall cancelled."
                else:
                    # Execute
                    result = execute_uninstall(plan, config_path=claude_config_path)
                    data = result
                    human = _format_uninstall_result(result)

        elif args.command == "doctor":
            from obsidian_connector.doctor import run_doctor
            checks = run_doctor(vault=args.vault)
            data = checks
            human = _fmt_doctor(checks)

        elif args.command == "sync-projects":
            from obsidian_connector.project_sync import sync_projects
            result = sync_projects(
                vault=vault,
                github_root=args.github_root,
                update_todo=not args.no_todo,
            )
            data = result
            human = _fmt_sync_projects(result)

        elif args.command == "project-status":
            from obsidian_connector.project_sync import get_project_status
            result = get_project_status(
                project=args.project,
                vault=vault,
                github_root=args.github_root,
            )
            data = result
            human = _fmt_project_status(result)

        elif args.command == "active-threads":
            from obsidian_connector.project_sync import get_active_threads
            result = get_active_threads(
                vault=vault,
                github_root=args.github_root,
            )
            data = result
            human = _fmt_active_threads(result)

        elif args.command == "log-session":
            from obsidian_connector.project_sync import SessionEntry, log_session
            project_list = [p.strip() for p in args.projects.split("|") if p.strip()]
            wt_list = [w.strip() for w in args.work_types.split("|") if w.strip()] if args.work_types else []
            completed_list = [c.strip() for c in args.completed.split("|") if c.strip()] if args.completed else []
            next_list = [n.strip() for n in args.next_steps.split("|") if n.strip()] if args.next_steps else []
            decision_list = [d.strip() for d in args.decisions.split("|") if d.strip()] if args.decisions else []
            entries = [
                SessionEntry(
                    project=proj,
                    work_types=wt_list,
                    completed=completed_list,
                    next_steps=next_list,
                    decisions=decision_list,
                )
                for proj in project_list
            ]
            result = log_session(
                entries=entries,
                session_context=args.context,
                vault=vault,
            )
            data = result
            human = _fmt_log_session(result)

        elif args.command == "running-todo":
            from obsidian_connector.project_sync import get_running_todo
            result = get_running_todo(vault=vault)
            data = result
            human = _fmt_running_todo(result)

        elif args.command == "init":
            from obsidian_connector.vault_init import init_vault, interactive_init
            if args.vault_path:
                # Programmatic mode with explicit vault path
                result = init_vault(
                    vault_path=args.vault_path,
                    github_root=args.github_root,
                    use_defaults=args.use_defaults,
                )
                data = result
                human = _fmt_init_vault(result)
            elif use_json:
                # Avoid surprising writes to the current directory when using --json
                raise ObsidianCLIError(
                    "When using --json with 'init', you must also specify --vault-path "
                    "to avoid initializing the current directory by accident."
                )
            else:
                # Interactive wizard
                result = interactive_init(
                    default_vault_path=args.vault_path,
                    default_github_root=args.github_root,
                )
                data = result
                human = _fmt_init_vault(result)

        elif args.command == "rollback":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.write_manager import list_snapshots, rollback as wm_rollback

            vault_path = resolve_vault_path(args.vault)
            dry = getattr(args, "dry_run", False)
            snapshot_dir = args.snapshot  # None means use latest

            if dry:
                snaps = list_snapshots(vault_path)
                target = snapshot_dir or (snaps[-1] if snaps else None)
                data = {"dry_run": True, "snapshot": target, "available": snaps}
                human = f"[dry-run] Would restore from snapshot: {target}\nAvailable snapshots: {len(snaps)}"
            else:
                result = wm_rollback(vault_path, snapshot_dir=snapshot_dir)
                data = result
                human = _fmt_rollback(result)

        elif args.command == "drafts":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.draft_manager import (
                approve_draft,
                clean_stale_drafts,
                list_drafts,
                reject_draft,
            )

            vault_path = resolve_vault_path(args.vault)
            action = getattr(args, "drafts_action", None)

            if action == "list":
                result = list_drafts(vault_path)
                data = [
                    {
                        "path": d.path, "title": d.title,
                        "created_at": d.created_at, "age_days": d.age_days,
                        "source_tool": d.source_tool, "status": d.status,
                    }
                    for d in result
                ]
                human = _fmt_drafts_list(data)
            elif action == "approve":
                dry = getattr(args, "dry_run", False)
                if dry:
                    data = {"dry_run": True, "from": args.path, "to": args.target}
                    human = _fmt_draft_action(data)
                else:
                    result = approve_draft(vault_path, args.path, args.target)
                    data = result
                    human = _fmt_draft_action(result)
            elif action == "reject":
                dry = getattr(args, "dry_run", False)
                if dry:
                    data = {"dry_run": True, "from": args.path, "to": "Archive/Rejected Drafts/"}
                    human = _fmt_draft_action(data)
                else:
                    result = reject_draft(vault_path, args.path)
                    data = result
                    human = _fmt_draft_action(result)
            elif action == "clean":
                dry = getattr(args, "dry_run", False)
                result = clean_stale_drafts(
                    vault_path,
                    max_age_days=args.max_age,
                    dry_run=dry,
                )
                data = result
                human = _fmt_draft_clean(result)
            else:
                parser.parse_args(["drafts", "--help"])
                return 0

        elif args.command == "vaults":
            from obsidian_connector.vault_registry import VaultRegistry

            registry = VaultRegistry()
            action = getattr(args, "vaults_action", None)

            if action == "list":
                entries = registry.list_vaults()
                data = [e.to_dict() for e in entries]
                human = _fmt_vaults_list(data)
            elif action == "add":
                entry = registry.register(
                    name=args.name,
                    path=args.path,
                    profile=getattr(args, "profile", "personal"),
                )
                data = {"action": "registered", "name": entry.name, "path": entry.path}
                human = _fmt_vault_action(data)
            elif action == "remove":
                registry.unregister(args.name)
                data = {"action": "removed", "name": args.name}
                human = _fmt_vault_action(data)
            elif action == "default":
                registry.set_default(args.name)
                data = {"action": "set as default", "name": args.name}
                human = _fmt_vault_action(data)
            else:
                parser.parse_args(["vaults", "--help"])
                return 0

        elif args.command == "templates":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.template_engine import TemplateEngine, init_templates

            vault_path = resolve_vault_path(args.vault)
            action = getattr(args, "templates_action", None)

            if action == "list":
                engine = TemplateEngine(vault_path)
                templates = engine.list_templates()
                data = [
                    {
                        "name": t.name, "version": t.version,
                        "description": t.description,
                        "variables": t.variables, "extends": t.extends,
                    }
                    for t in templates
                ]
                human = _fmt_templates_list(data)
            elif action == "init":
                dry = getattr(args, "dry_run", False)
                if dry:
                    from obsidian_connector.template_engine import BUILTIN_TEMPLATES
                    data = {"dry_run": True, "would_create": list(BUILTIN_TEMPLATES.keys())}
                    human = f"[dry-run] Would create templates: {', '.join(BUILTIN_TEMPLATES.keys())}"
                else:
                    written = init_templates(vault_path)
                    data = {"written": written}
                    human = _fmt_templates_init(data)
            elif action == "check":
                engine = TemplateEngine(vault_path)
                outdated = engine.check_updates()
                data = outdated
                human = _fmt_templates_check(outdated)
            else:
                parser.parse_args(["templates", "--help"])
                return 0

        elif args.command == "schedule":
            from obsidian_connector.scheduler import Scheduler

            cfg_dict = cfg.raw if hasattr(cfg, "raw") else {}
            sched = Scheduler(config=cfg_dict)
            action = getattr(args, "schedule_action", None)

            if action == "list":
                entries = sched.list_schedules()
                data = [
                    {
                        "name": e.name, "schedule_type": e.schedule_type,
                        "tool_chain": e.tool_chain, "enabled": e.enabled,
                    }
                    for e in entries
                ]
                human = _fmt_schedule_list(data)
            elif action == "preview":
                chain = sched.preview(args.name)
                data = {"name": args.name, "tool_chain": chain}
                human = _fmt_schedule_preview(data)
            elif action == "status":
                statuses = sched.all_statuses()
                data = [
                    {
                        "name": s.name, "last_run": s.last_run,
                        "next_run": s.next_run, "missed": s.missed,
                        "last_result": s.last_result,
                    }
                    for s in statuses
                ]
                human = _fmt_schedule_status(data)
            elif action == "run":
                from obsidian_connector.automation import run_schedule_now
                result = run_schedule_now(vault, args.name, config=cfg_dict)
                data = {
                    "chain_name": result.chain_name, "trigger": result.trigger,
                    "all_ok": result.all_ok, "total_duration_ms": result.total_duration_ms,
                    "steps": [{"tool": s.tool_name, "ok": s.ok, "ms": s.duration_ms, "error": s.error} for s in result.steps],
                }
                lines = [f"Schedule '{args.name}': {'OK' if result.all_ok else 'FAILED'} ({result.total_duration_ms}ms)"]
                for s in result.steps:
                    status = "OK" if s.ok else f"FAIL: {s.error}"
                    lines.append(f"  {s.tool_name}: {status} ({s.duration_ms}ms)")
                human = "\n".join(lines)
            elif action == "fire":
                from obsidian_connector.automation import run_event_now
                results = run_event_now(vault, args.event, config=cfg_dict)
                data = [
                    {
                        "chain_name": r.chain_name, "trigger": r.trigger,
                        "all_ok": r.all_ok, "total_duration_ms": r.total_duration_ms,
                    }
                    for r in results
                ]
                if not results:
                    human = f"No triggers matched event '{args.event}'."
                else:
                    lines = [f"Event '{args.event}': {len(results)} chain(s) fired"]
                    for r in results:
                        lines.append(f"  {r.chain_name}: {'OK' if r.all_ok else 'FAILED'} ({r.total_duration_ms}ms)")
                    human = "\n".join(lines)
            elif action == "tools":
                from obsidian_connector.automation import list_available_tools
                tools = list_available_tools()
                data = tools
                human = "Available automation tools:\n" + "\n".join(f"  {t}" for t in tools)
            else:
                parser.parse_args(["schedule", "--help"])
                return 0

        elif args.command == "report":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.reports import generate_report

            vault_path = resolve_vault_path(args.vault)
            report_type = args.type.replace("-", "_")
            result = generate_report(str(vault_path), report_type)
            data = {
                "report_type": result.report_type,
                "path": result.path,
                "generated_at": result.generated_at,
                "summary": result.summary,
            }
            human = _fmt_report(data)

        elif args.command == "stats":
            from obsidian_connector.telemetry import TelemetryCollector

            collector = TelemetryCollector()
            if args.weekly:
                result = collector.weekly_summary()
            else:
                result = collector.session_summary()
            data = result
            human = _fmt_stats(result)

        elif args.command == "project":
            from obsidian_connector.config import resolve_vault_path
            from obsidian_connector.project_intelligence import (
                project_changelog,
                project_health,
                project_packet,
            )

            vault_path = resolve_vault_path(args.vault)
            action = getattr(args, "project_action", None)

            if action == "health":
                results = project_health(vault_path)
                data = [
                    {
                        "name": h.name, "score": h.score,
                        "status": h.status, "factors": h.factors,
                    }
                    for h in results
                ]
                human = _fmt_project_health(data)
            elif action == "changelog":
                result = project_changelog(
                    vault_path,
                    project_name=args.name,
                    since_days=args.days,
                )
                data = {"changelog": result}
                human = _fmt_project_changelog(result)
            elif action == "packet":
                result = project_packet(vault_path, days=args.days)
                data = {"packet": result}
                human = _fmt_project_packet(result)
            else:
                parser.parse_args(["project", "--help"])
                return 0

        elif args.command == "commitments":
            from obsidian_connector.commitment_ops import list_commitments
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            items = list_commitments(
                vault_path,
                status=getattr(args, "status", None),
                project=getattr(args, "project", None),
                priority=getattr(args, "priority", None),
            )
            data = {"count": len(items), "commitments": items}
            human = _fmt_commitments(items)

        elif args.command == "commitment-status":
            from obsidian_connector.commitment_ops import get_commitment
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            item = get_commitment(vault_path, args.action_id)
            if item is None:
                raise ValueError(f"commitment not found: {args.action_id!r}")
            data = item
            human = _fmt_commitment_detail(item)

        elif args.command == "mark-done":
            from obsidian_connector.commitment_ops import get_commitment, mark_commitment_done
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            dry = getattr(args, "dry_run", False)
            log_action(
                "mark-done",
                {"action_id": args.action_id, "completed_at": getattr(args, "completed_at", None)},
                vault,
                dry_run=dry,
            )
            if dry:
                item = get_commitment(vault_path, args.action_id)
                if item is None:
                    raise ValueError(f"commitment not found: {args.action_id!r}")
                data = {"dry_run": True, "action_id": args.action_id, "would_set_status": "done"}
                human = (
                    f"[dry-run] Would mark done: {item['title']}\n"
                    f"  action_id: {args.action_id}\n"
                    f"  current status: {item['status']}"
                )
            else:
                result = mark_commitment_done(
                    vault_path,
                    args.action_id,
                    completed_at=getattr(args, "completed_at", None),
                )
                data = result
                human = _fmt_mark_done(result)

        elif args.command == "postpone":
            from obsidian_connector.commitment_ops import get_commitment, postpone_commitment
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            dry = getattr(args, "dry_run", False)
            log_action(
                "postpone",
                {"action_id": args.action_id, "until": args.until},
                vault,
                dry_run=dry,
            )
            if dry:
                item = get_commitment(vault_path, args.action_id)
                if item is None:
                    raise ValueError(f"commitment not found: {args.action_id!r}")
                data = {"dry_run": True, "action_id": args.action_id, "would_set_postponed_until": args.until}
                human = (
                    f"[dry-run] Would postpone: {item['title']}\n"
                    f"  action_id: {args.action_id}\n"
                    f"  until: {args.until}"
                )
            else:
                result = postpone_commitment(vault_path, args.action_id, postponed_until=args.until)
                data = result
                human = _fmt_postpone(result)

        elif args.command == "add-reason":
            from obsidian_connector.commitment_ops import add_commitment_reason, get_commitment
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            dry = getattr(args, "dry_run", False)
            log_action(
                "add-reason",
                {"action_id": args.action_id, "reason": args.reason},
                vault,
                dry_run=dry,
                content=args.reason,
            )
            if dry:
                item = get_commitment(vault_path, args.action_id)
                if item is None:
                    raise ValueError(f"commitment not found: {args.action_id!r}")
                data = {"dry_run": True, "action_id": args.action_id, "would_add_reason": args.reason}
                human = (
                    f"[dry-run] Would add reason to: {item['title']}\n"
                    f"  reason: {args.reason}"
                )
            else:
                result = add_commitment_reason(vault_path, args.action_id, args.reason)
                data = result
                human = _fmt_add_reason(result)

        elif args.command == "due-soon":
            from obsidian_connector.commitment_ops import list_due_soon
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            items = list_due_soon(vault_path, within_days=args.within_days)
            data = {"count": len(items), "commitments": items}
            human = _fmt_due_soon(items, within_days=args.within_days)

        elif args.command == "sync-commitments":
            from obsidian_connector.commitment_ops import sync_commitments_from_service
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            dry = getattr(args, "dry_run", False)
            if dry:
                data = {"dry_run": True, "action": "sync_commitments"}
                human = "[dry-run] Would fetch and write commitment notes from service."
            else:
                result = sync_commitments_from_service(
                    vault_path,
                    service_url=getattr(args, "service_url", None),
                )
                data = result
                human = _fmt_sync_commitments(result)

        elif args.command == "review-dashboards":
            from obsidian_connector.commitment_dashboards import (
                update_all_review_dashboards,
            )
            from obsidian_connector.config import resolve_vault_path

            vault_path = resolve_vault_path(args.vault)
            results = update_all_review_dashboards(
                vault_path,
                now_iso=getattr(args, "now", None),
                stale_days=getattr(args, "stale_days", 14),
                merge_window_days=getattr(args, "merge_window_days", 14),
                merge_jaccard=getattr(args, "merge_jaccard", 0.6),
            )
            payload = [
                {"path": str(r.path), "written": r.written} for r in results
            ]
            data = {"count": len(payload), "dashboards": payload}
            human = _fmt_review_dashboards(results)

        elif args.command == "find-commitments":
            from obsidian_connector.commitment_ops import list_service_actions

            result = list_service_actions(
                status=getattr(args, "status", None),
                lifecycle_stage=getattr(args, "lifecycle_stage", None),
                project=getattr(args, "project", None),
                person=getattr(args, "person", None),
                area=getattr(args, "area", None),
                urgency=getattr(args, "urgency", None),
                priority=getattr(args, "priority", None),
                source_app=getattr(args, "source_app", None),
                due_before=getattr(args, "due_before", None),
                due_after=getattr(args, "due_after", None),
                limit=getattr(args, "limit", 50),
                cursor=getattr(args, "cursor", None),
                service_url=getattr(args, "service_url", None),
            )
            data = result
            human = _fmt_find_commitments(result)

        elif args.command == "commitment-detail":
            from obsidian_connector.commitment_ops import get_service_action

            result = get_service_action(
                args.action_id,
                service_url=getattr(args, "service_url", None),
            )
            data = result
            human = _fmt_commitment_detail(result)

        elif args.command == "commitment-stats":
            from obsidian_connector.commitment_ops import get_service_action_stats

            result = get_service_action_stats(
                service_url=getattr(args, "service_url", None),
            )
            data = result
            human = _fmt_commitment_stats(result)

        elif args.command == "index-status":
            from obsidian_connector.index_store import IndexStore
            from obsidian_connector.watcher import get_index_age, is_stale

            store = IndexStore()
            try:
                age = get_index_age(store)
                stale = is_stale(store)
            finally:
                store.close()

            data = {"age_seconds": age, "is_stale": stale}
            human = _fmt_index_status(data)

        duration_ms = int((time.monotonic() - t0) * 1000)

        if use_json:
            env = success_envelope(args.command, data, vault, duration_ms)
            print(format_output(env, as_json=True))
        else:
            print(human if human is not None else str(data))

    except ObsidianCLIError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        if use_json:
            env = error_envelope(
                command=args.command,
                error_type=type(exc).__name__,
                message=str(exc),
                stderr=getattr(exc, "stderr", ""),
                exit_code=getattr(exc, "returncode", None),
                vault=vault,
            )
            print(format_output(env, as_json=True))
            return 1
        else:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except (OSError, json.JSONDecodeError, FileNotFoundError, FileExistsError) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        if use_json:
            env = error_envelope(
                command=args.command,
                error_type=type(exc).__name__,
                message=str(exc),
                stderr="",
                exit_code=1,
                vault=vault,
            )
            print(format_output(env, as_json=True))
            return 1
        else:
            print(f"Error ({type(exc).__name__}): {exc}", file=sys.stderr)
            return 1
    except (ValueError, KeyError, TypeError) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        if use_json:
            env = error_envelope(
                command=args.command,
                error_type=type(exc).__name__,
                message=str(exc),
                stderr="",
                exit_code=1,
                vault=vault,
            )
            print(format_output(env, as_json=True))
            return 1
        else:
            print(f"Error ({type(exc).__name__}): {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
