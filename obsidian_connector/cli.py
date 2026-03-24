"""CLI entry point for obsidian-connector.

This module is the canonical CLI implementation. The root ``main.py`` is a
thin wrapper that imports from here for backward compatibility with
``python main.py ...`` invocations.
"""

from __future__ import annotations

import argparse
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
from obsidian_connector.search import enrich_search_results
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

    return parser


def _resolve_json(args: argparse.Namespace) -> bool:
    """Return True if JSON output was requested via global or subcommand flag."""
    return args.as_json or getattr(args, "sub_json", False)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
