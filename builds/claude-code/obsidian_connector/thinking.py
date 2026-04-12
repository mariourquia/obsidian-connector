"""Deep thinking tools for obsidian-connector.

Surfaces patterns across the vault: writing voice analysis, intention/behavior
drift, idea evolution tracing, and latent idea discovery from graph structure.

All functions are **read-only** -- they never write to vault files.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from obsidian_connector.client_fallback import ObsidianCLIError, read_note, search_notes
from obsidian_connector.graph import NoteIndex


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_or_build_index(vault: str | None = None) -> NoteIndex | None:
    """Delegate to the canonical shared implementation."""
    from obsidian_connector.index_store import load_or_build_index

    return load_or_build_index(vault)


def _read_note_content(path: str, vault: str | None = None) -> str:
    """Read a note's content, returning empty string on expected errors."""
    try:
        from obsidian_connector.config import resolve_vault_path
        from obsidian_connector.errors import VaultNotFound

        note_path = Path(path)
        # Reject absolute user-provided paths before joining.
        if note_path.is_absolute():
            return ""
        root = resolve_vault_path(vault).resolve()
        full = (root / note_path).resolve()
        # Guard against path traversal: ensure full is inside the vault root.
        try:
            full.relative_to(root)
        except ValueError:
            return ""
        if full.is_file():
            return full.read_text(encoding="utf-8", errors="replace")
    except (OSError, VaultNotFound):
        pass

    # Fall back to CLI read.
    try:
        return read_note(path, vault=vault)
    except ObsidianCLIError:
        return ""


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"^```", re.MULTILINE)
_QUESTION_RE = re.compile(r"\?")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_INTENTION_RE = re.compile(
    r"(?:^|\n)\s*[-*]?\s*(?:I will|Plan to|Goal:|TODO:|Want to|Need to|Aim to)\s+(.+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 1. Ghost Voice Profile
# ---------------------------------------------------------------------------

def ghost_voice_profile(
    vault: str | None = None,
    sample_notes: int = 20,
) -> dict:
    """Analyze writing style from recent vault notes to build a voice profile.

    Reads the N most recently modified notes (by mtime from NoteIndex).
    Extracts sentence length, vocabulary richness, common bigrams/trigrams,
    structural preferences, and tone markers.

    Parameters
    ----------
    vault:
        Target vault name.
    sample_notes:
        Number of recent notes to sample (default 20).

    Returns
    -------
    dict
        ``{profile: {...}, sample_size: int, confidence: str}``
        Confidence: ``"low"`` (<10 notes), ``"medium"`` (10--30),
        ``"high"`` (>30).
    """
    idx = _load_or_build_index(vault)
    if idx is None or len(idx.notes) == 0:
        return {
            "profile": {},
            "sample_size": 0,
            "confidence": "low",
            "message": "Could not build note index or vault is empty.",
        }

    # Sort notes by mtime descending, take top N.
    sorted_notes = sorted(
        idx.notes.values(), key=lambda e: e.mtime, reverse=True
    )[:sample_notes]

    actual_sample = len(sorted_notes)
    if actual_sample < 5:
        return {
            "profile": {},
            "sample_size": actual_sample,
            "confidence": "low",
            "message": "Need 5+ authored notes for a meaningful voice profile.",
        }

    # Collect text from each note.
    all_sentences: list[list[str]] = []
    all_words: list[str] = []
    total_headings = 0
    total_bullets = 0
    total_prose_lines = 0
    total_code_blocks = 0
    total_questions = 0
    paragraph_sentence_counts: list[int] = []

    for entry in sorted_notes:
        content = _read_note_content(entry.path, vault=vault)
        if not content.strip():
            continue

        # Strip frontmatter.
        body = _strip_frontmatter_body(content)

        # Count structural elements.
        total_headings += len(_HEADING_RE.findall(body))
        total_bullets += len(_BULLET_RE.findall(body))
        total_code_blocks += len(_CODE_BLOCK_RE.findall(body)) // 2  # pairs
        total_questions += len(_QUESTION_RE.findall(body))

        # Split into paragraphs, then sentences.
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        for para in paragraphs:
            # Skip headings and bullet-only paragraphs.
            lines = para.split("\n")
            prose_lines = [
                ln for ln in lines
                if ln.strip()
                and not ln.strip().startswith("#")
                and not re.match(r"^\s*[-*+]\s+", ln)
                and not ln.strip().startswith("```")
            ]
            total_prose_lines += len(prose_lines)
            prose_text = " ".join(prose_lines)
            if not prose_text.strip():
                continue

            sentences = [s.strip() for s in _SENTENCE_SPLIT.split(prose_text) if s.strip()]
            paragraph_sentence_counts.append(len(sentences))
            for s in sentences:
                words = s.split()
                all_sentences.append(words)
                all_words.extend(w.lower() for w in words)

    if not all_sentences:
        return {
            "profile": {},
            "sample_size": actual_sample,
            "confidence": "low",
            "message": "Not enough prose content in sampled notes.",
        }

    # Metrics.
    total_words = len(all_words)
    unique_words = len(set(all_words))
    avg_sentence_length = round(
        sum(len(s) for s in all_sentences) / len(all_sentences), 1
    )
    avg_paragraph_length = round(
        sum(paragraph_sentence_counts) / len(paragraph_sentence_counts), 1
    ) if paragraph_sentence_counts else 0.0
    vocabulary_richness = round(unique_words / total_words, 3) if total_words else 0.0

    # Bigrams -- top 10.
    bigrams: Counter[tuple[str, str]] = Counter()
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "to", "of", "in", "for", "on", "with", "at", "by", "and", "or",
        "it", "its", "this", "that", "as", "from", "but", "not", "so",
        "if", "i", "my", "we", "he", "she", "they", "you", "me",
    }
    for sentence_words in all_sentences:
        filtered = [w.lower() for w in sentence_words if w.lower() not in stopwords and len(w) > 2]
        for i in range(len(filtered) - 1):
            bigrams[(filtered[i], filtered[i + 1])] += 1

    common_phrases = [
        f"{a} {b}" for (a, b), _count in bigrams.most_common(10)
    ]

    # Structural preferences.
    headings_per_note = round(total_headings / actual_sample, 1)
    bullet_lines = total_bullets
    prose_count = total_prose_lines
    bullets_vs_prose_ratio = round(
        bullet_lines / max(prose_count, 1), 2
    )
    code_block_frequency = round(total_code_blocks / actual_sample, 2)

    # Tone markers.
    tone_markers: list[str] = []
    if avg_sentence_length < 15:
        tone_markers.append("direct")
    elif avg_sentence_length > 25:
        tone_markers.append("elaborate")
    if vocabulary_richness > 0.6:
        tone_markers.append("technical")
    elif vocabulary_richness < 0.3:
        tone_markers.append("conversational")
    questions_per_note = total_questions / actual_sample
    if questions_per_note > 2:
        tone_markers.append("questioning")
    if bullets_vs_prose_ratio > 1.0:
        tone_markers.append("list-oriented")
    elif bullets_vs_prose_ratio < 0.2:
        tone_markers.append("narrative")
    if code_block_frequency > 0.5:
        tone_markers.append("code-heavy")
    if not tone_markers:
        tone_markers.append("balanced")

    # Confidence.
    if actual_sample < 10:
        confidence = "low"
    elif actual_sample <= 30:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "profile": {
            "avg_sentence_length": avg_sentence_length,
            "avg_paragraph_length": avg_paragraph_length,
            "vocabulary_richness": vocabulary_richness,
            "common_phrases": common_phrases,
            "structural_preferences": {
                "headings_per_note": headings_per_note,
                "bullets_vs_prose_ratio": bullets_vs_prose_ratio,
                "code_block_frequency": code_block_frequency,
            },
            "tone_markers": tone_markers,
        },
        "sample_size": actual_sample,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# 2. Drift Analysis
# ---------------------------------------------------------------------------

def drift_analysis(
    vault: str | None = None,
    lookback_days: int = 60,
) -> dict:
    """Analyze drift between stated intentions and actual behavior.

    Reads daily notes over the lookback period.  Extracts stated intentions
    via regex (``I will``, ``Plan to``, ``Goal:``, ``TODO:``, ``Want to``,
    ``Need to``, ``Aim to``).  Cross-references with topics actually
    discussed and tasks completed.

    Parameters
    ----------
    vault:
        Target vault name.
    lookback_days:
        Number of days to look back (default 60).

    Returns
    -------
    dict
        Keys: ``stated_intentions``, ``actual_focus``, ``gaps``,
        ``surprises``, ``coverage_pct``, ``lookback_days``,
        ``daily_notes_found``.
    """
    today = datetime.now(timezone.utc).date()
    daily_notes: list[tuple[str, str, str]] = []  # (date_str, file, content)

    # Discover daily notes by searching for date strings.
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
                content = _read_note_content(fname, vault=vault)
                if content:
                    daily_notes.append((day_str, fname, content))
                break  # one daily note per day

    daily_notes_found = len(daily_notes)

    if daily_notes_found == 0:
        return {
            "stated_intentions": [],
            "actual_focus": [],
            "gaps": [],
            "surprises": [],
            "coverage_pct": 0.0,
            "lookback_days": lookback_days,
            "daily_notes_found": 0,
            "message": "No daily notes found in the lookback period.",
        }

    # Extract intentions.
    stated_intentions: list[dict] = []
    for date_str, fname, content in daily_notes:
        for m in _INTENTION_RE.finditer(content):
            text = m.group(1).strip().rstrip(".")
            if text:
                stated_intentions.append({
                    "text": text,
                    "source_file": fname,
                    "date": date_str,
                })

    # Build topic frequency from headings and bold text across all daily notes.
    topic_counter: Counter[str] = Counter()
    topic_first_seen: dict[str, str] = {}
    topic_last_seen: dict[str, str] = {}

    for date_str, fname, content in daily_notes:
        body = _strip_frontmatter_body(content)
        # Extract headings.
        for m in _HEADING_RE.finditer(body):
            heading_text = body[m.end():].split("\n", 1)[0].strip()
            if heading_text and len(heading_text) > 3:
                topic_key = heading_text.lower()
                topic_counter[topic_key] += 1
                if topic_key not in topic_first_seen:
                    topic_first_seen[topic_key] = date_str
                topic_last_seen[topic_key] = date_str

        # Extract bold text.
        for m in _BOLD_RE.finditer(body):
            bold_text = m.group(1).strip()
            if bold_text and len(bold_text) > 3:
                topic_key = bold_text.lower()
                topic_counter[topic_key] += 1
                if topic_key not in topic_first_seen:
                    topic_first_seen[topic_key] = date_str
                topic_last_seen[topic_key] = date_str

    # Top actual focus topics.
    actual_focus = [
        {
            "topic": topic,
            "mention_count": count,
            "first_seen": topic_first_seen.get(topic, ""),
            "last_seen": topic_last_seen.get(topic, ""),
        }
        for topic, count in topic_counter.most_common(20)
        if count >= 2  # filter noise
    ]

    # Cross-reference: gaps (intentions not matched in focus topics).
    focus_text = " ".join(topic_counter.keys())
    gaps: list[dict] = []
    matched_intentions = 0

    for intention in stated_intentions:
        intention_words = [
            w.lower() for w in intention["text"].split()
            if len(w) > 3
        ]
        # Check if any key word from the intention appears in focus topics.
        found = any(w in focus_text for w in intention_words)
        if found:
            matched_intentions += 1
            gaps.append({
                "intention": intention["text"],
                "status": "partially_addressed",
            })
        else:
            gaps.append({
                "intention": intention["text"],
                "status": "unaddressed",
            })

    # Surprises: topics with attention but no matching intention.
    intention_text = " ".join(i["text"].lower() for i in stated_intentions)
    surprises: list[dict] = []
    for topic, count in topic_counter.most_common(20):
        if count < 2:
            continue
        topic_words = [w for w in topic.split() if len(w) > 3]
        has_intent = any(w in intention_text for w in topic_words)
        if not has_intent:
            surprises.append({
                "topic": topic,
                "description": f"Discussed {count} times but no stated intention found.",
            })

    coverage_pct = round(
        (matched_intentions / len(stated_intentions) * 100) if stated_intentions else 0.0, 1
    )

    return {
        "stated_intentions": stated_intentions,
        "actual_focus": actual_focus,
        "gaps": [g for g in gaps if g["status"] == "unaddressed"],
        "surprises": surprises[:10],
        "coverage_pct": coverage_pct,
        "lookback_days": lookback_days,
        "daily_notes_found": daily_notes_found,
    }


# ---------------------------------------------------------------------------
# 3. Trace Idea
# ---------------------------------------------------------------------------

def trace_idea(
    topic: str,
    vault: str | None = None,
    max_notes: int = 20,
) -> dict:
    """Trace how an idea/topic evolved over time across vault notes.

    Searches for the topic, sorts matching notes by date (mtime), extracts
    excerpts around mentions, and groups into temporal phases.

    Parameters
    ----------
    topic:
        Topic string to trace.
    vault:
        Target vault name.
    max_notes:
        Maximum notes to include in the timeline (default 20).

    Returns
    -------
    dict
        Keys: ``topic``, ``first_mention``, ``latest_mention``,
        ``timeline``, ``phases``, ``total_mentions``.
    """
    try:
        hits = search_notes(topic, vault=vault)
    except ObsidianCLIError:
        hits = []

    if not hits:
        return {
            "topic": topic,
            "first_mention": None,
            "latest_mention": None,
            "timeline": [],
            "phases": [],
            "total_mentions": 0,
        }

    # Load index for mtime data.
    idx = _load_or_build_index(vault)

    # Build timeline entries with dates.
    timeline_raw: list[dict] = []
    for hit in hits:
        file_path: str = hit.get("file", "")
        mtime = 0.0
        if idx and file_path in idx.notes:
            mtime = idx.notes[file_path].mtime
        else:
            # Try to get mtime from filesystem.
            try:
                from obsidian_connector.config import resolve_vault_path

                root = resolve_vault_path(vault)
                full = root / file_path
                if full.is_file():
                    mtime = full.stat().st_mtime
            except OSError:
                pass

        date_str = (
            datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            if mtime > 0
            else "unknown"
        )

        # Extract excerpt around the topic mention.
        excerpt = ""
        context = ""
        matches = hit.get("matches", [])
        if matches:
            match_text = matches[0].get("text", "")
            excerpt = match_text.strip()[:200]
            if len(matches) > 1:
                context = f"{len(matches)} mentions in this note"
            else:
                context = "1 mention in this note"

        timeline_raw.append({
            "date": date_str,
            "file": file_path,
            "excerpt": excerpt,
            "context": context,
            "mtime": mtime,
        })

    # Sort by mtime.
    timeline_raw.sort(key=lambda x: x["mtime"])

    # Limit to max_notes.
    total_mentions = len(timeline_raw)
    timeline = [
        {k: v for k, v in entry.items() if k != "mtime"}
        for entry in timeline_raw[:max_notes]
    ]

    first_mention = timeline[0] if timeline else None
    latest_mention = timeline[-1] if timeline else None

    # Phase detection: group by time gaps (>30 days gap = new phase).
    phases: list[dict] = []
    if timeline_raw:
        current_phase_start = timeline_raw[0]
        current_phase_entries: list[dict] = [timeline_raw[0]]

        for i in range(1, len(timeline_raw)):
            prev_mtime = timeline_raw[i - 1]["mtime"]
            curr_mtime = timeline_raw[i]["mtime"]
            gap_days = (curr_mtime - prev_mtime) / 86400 if prev_mtime > 0 and curr_mtime > 0 else 0

            if gap_days > 30:
                # Close current phase, start new one.
                phases.append(_classify_phase(
                    current_phase_start, current_phase_entries, len(phases)
                ))
                current_phase_start = timeline_raw[i]
                current_phase_entries = [timeline_raw[i]]
            else:
                current_phase_entries.append(timeline_raw[i])

        # Close final phase.
        phases.append(_classify_phase(
            current_phase_start, current_phase_entries, len(phases)
        ))

    return {
        "topic": topic,
        "first_mention": first_mention,
        "latest_mention": latest_mention,
        "timeline": timeline,
        "phases": phases,
        "total_mentions": total_mentions,
    }


def _classify_phase(
    start_entry: dict,
    entries: list[dict],
    phase_index: int,
) -> dict:
    """Classify a temporal phase based on position and density."""
    start_date = start_entry["date"]
    end_date = entries[-1]["date"]
    note_count = len(entries)

    if phase_index == 0 and note_count == 1:
        name = "first_mention"
    elif phase_index > 0:
        name = "revival"
    elif note_count >= 5:
        name = "growth"
    else:
        name = "plateau"

    return {
        "name": name,
        "start_date": start_date,
        "end_date": end_date,
        "note_count": note_count,
    }


# ---------------------------------------------------------------------------
# 4. Deep Ideas
# ---------------------------------------------------------------------------

def deep_ideas(
    vault: str | None = None,
    max_ideas: int = 10,
) -> dict:
    """Surface latent ideas from vault graph structure.

    Finds orphaned notes tagged ``#idea`` or ``#insight``, high-backlink
    notes with no outgoing links, notes sharing rare tags but not linked,
    unresolved links, and rare tag co-occurrences.

    Parameters
    ----------
    vault:
        Target vault name.
    max_ideas:
        Maximum ideas to return (default 10).

    Returns
    -------
    dict
        Keys: ``ideas``, ``vault_health``.
    """
    idx = _load_or_build_index(vault)
    if idx is None or len(idx.notes) == 0:
        return {
            "ideas": [],
            "vault_health": {
                "orphan_pct": 0.0,
                "dead_end_pct": 0.0,
                "unresolved_count": 0,
            },
            "message": "Could not build note index or vault is empty.",
        }

    ideas: list[dict] = []
    total_notes = len(idx.notes)

    # 1. Orphaned notes with #idea or #insight tags (forgotten ideas).
    idea_tags = {"#idea", "#insight"}
    for orphan_path in idx.orphans:
        entry = idx.notes.get(orphan_path)
        if entry is None:
            continue
        matching_tags = [t for t in entry.tags if t in idea_tags]
        if matching_tags:
            ideas.append({
                "title": entry.title,
                "type": "forgotten_idea",
                "source_notes": [orphan_path],
                "rationale": (
                    f"Orphaned note tagged {', '.join(matching_tags)} "
                    f"with no inbound or outbound links -- may be a forgotten idea."
                ),
                "priority": "high",
            })

    # 2. High-backlink notes with no outgoing links (convergence points).
    for path in idx.dead_ends:
        backlink_count = len(idx.backlinks.get(path, set()))
        if backlink_count >= 3:
            entry = idx.notes.get(path)
            title = entry.title if entry else Path(path).stem
            ideas.append({
                "title": title,
                "type": "convergence_point",
                "source_notes": [path],
                "rationale": (
                    f"Has {backlink_count} backlinks but no outgoing links -- "
                    f"a convergence point that could be expanded with new connections."
                ),
                "priority": "high",
            })

    # 3. Unresolved links (ideas referenced but never written).
    unresolved_sorted = sorted(
        idx.unresolved.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )
    for link_target, sources in unresolved_sorted[:10]:
        ideas.append({
            "title": link_target,
            "type": "unresolved_link",
            "source_notes": sorted(sources),
            "rationale": (
                f"Referenced via [[{link_target}]] in {len(sources)} note(s) "
                f"but the note does not exist -- an idea worth creating."
            ),
            "priority": "medium" if len(sources) >= 2 else "low",
        })

    # 4. Notes sharing rare tags but not linked (potential connections).
    rare_tag_threshold = 3
    for tag, tag_paths in idx.tags.items():
        if 2 <= len(tag_paths) <= rare_tag_threshold:
            paths_list = sorted(tag_paths)
            # Check if any pair is not linked.
            for i in range(len(paths_list)):
                for j in range(i + 1, len(paths_list)):
                    p_a, p_b = paths_list[i], paths_list[j]
                    forward_a = idx.forward_links.get(p_a, set())
                    forward_b = idx.forward_links.get(p_b, set())
                    if p_b not in forward_a and p_a not in forward_b:
                        entry_a = idx.notes.get(p_a)
                        entry_b = idx.notes.get(p_b)
                        title_a = entry_a.title if entry_a else Path(p_a).stem
                        title_b = entry_b.title if entry_b else Path(p_b).stem
                        ideas.append({
                            "title": f"Connect: {title_a} <-> {title_b}",
                            "type": "rare_tag_connection",
                            "source_notes": [p_a, p_b],
                            "rationale": (
                                f"Both share rare tag {tag} (only {len(tag_paths)} notes) "
                                f"but are not linked -- potential cross-domain connection."
                            ),
                            "priority": "medium",
                        })

    # 5. Tag pairs that co-occur rarely (cross-domain opportunities).
    tag_co_occurrence: Counter[tuple[str, str]] = Counter()
    for path, entry in idx.notes.items():
        tags = sorted(entry.tags)
        for i in range(len(tags)):
            for j in range(i + 1, len(tags)):
                tag_co_occurrence[(tags[i], tags[j])] += 1

    rare_pairs = [
        (pair, count) for pair, count in tag_co_occurrence.items()
        if count <= 2
    ]
    rare_pairs.sort(key=lambda x: x[1])
    for (tag_a, tag_b), count in rare_pairs[:5]:
        ideas.append({
            "title": f"Cross-domain: {tag_a} + {tag_b}",
            "type": "rare_tag_pair",
            "source_notes": sorted(
                idx.tags.get(tag_a, set()) & idx.tags.get(tag_b, set())
            ),
            "rationale": (
                f"Tags {tag_a} and {tag_b} co-occur in only {count} note(s) -- "
                f"a rare cross-domain intersection worth exploring."
            ),
            "priority": "low",
        })

    # Sort by priority, then limit.
    priority_order = {"high": 0, "medium": 1, "low": 2}
    ideas.sort(key=lambda x: priority_order.get(x["priority"], 3))
    ideas = ideas[:max_ideas]

    # Vault health.
    orphan_pct = round(len(idx.orphans) / max(total_notes, 1) * 100, 1)
    dead_end_pct = round(len(idx.dead_ends) / max(total_notes, 1) * 100, 1)
    unresolved_count = sum(len(v) for v in idx.unresolved.values())

    return {
        "ideas": ideas,
        "vault_health": {
            "orphan_pct": orphan_pct,
            "dead_end_pct": dead_end_pct,
            "unresolved_count": unresolved_count,
        },
    }


# ---------------------------------------------------------------------------
# Internal helper: strip frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_FENCE = re.compile(r"^---\s*$")


def _strip_frontmatter_body(content: str) -> str:
    """Remove YAML frontmatter block from the start of content."""
    lines = content.split("\n")
    if not lines or not _FRONTMATTER_FENCE.match(lines[0]):
        return content
    for i, line in enumerate(lines[1:], start=1):
        if _FRONTMATTER_FENCE.match(line):
            return "\n".join(lines[i + 1:])
    return content
