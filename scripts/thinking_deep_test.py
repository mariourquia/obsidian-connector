#!/usr/bin/env python3
"""Deep thinking tools tests -- validates ghost, drift, trace, ideas using mock vaults."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure the package is importable from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obsidian_connector.graph import NoteIndex, build_note_index
from obsidian_connector.thinking import (
    deep_ideas,
    drift_analysis,
    ghost_voice_profile,
    trace_idea,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}")
        PASS += 1
    else:
        print(f"  FAIL  {label}")
        FAIL += 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault(tmp: str, files: dict[str, str]) -> Path:
    """Create a temporary vault directory with the given files."""
    root = Path(tmp) / "vault"
    root.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        full = root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return root


def _set_mtime(vault: Path, rel: str, days_ago: int) -> None:
    """Set a file's mtime to N days ago."""
    full = vault / rel
    t = time.time() - (days_ago * 86400)
    os.utime(full, (t, t))


# ---------------------------------------------------------------------------
# Test: ghost_voice_profile
# ---------------------------------------------------------------------------

def test_ghost_voice_profile() -> None:
    print("\n--- ghost_voice_profile ---")

    with tempfile.TemporaryDirectory() as tmp:
        # Build vault with notes of known style.
        notes: dict[str, str] = {}
        for i in range(15):
            # Short direct sentences, some bullets, some headings.
            notes[f"Note{i:02d}.md"] = (
                f"---\ntitle: Note {i}\n---\n"
                f"# Topic {i}\n\n"
                f"This is short. Very direct. Minimal words.\n\n"
                f"- Bullet one\n"
                f"- Bullet two\n\n"
                f"Another paragraph here. Also short. Clear prose.\n"
            )

        vault = _make_vault(tmp, notes)
        # Set mtimes so newer notes are prioritized.
        for i in range(15):
            _set_mtime(vault, f"Note{i:02d}.md", 15 - i)

        # Patch resolve_vault_path to return our temp vault.
        import obsidian_connector.thinking as thinking_mod
        orig_load = thinking_mod._load_or_build_index
        vault_dir = vault  # closure-safe reference

        def mock_load(vault=None):
            return build_note_index(str(vault_dir))

        thinking_mod._load_or_build_index = mock_load

        # Also patch _read_note_content to read from temp vault.
        orig_read = thinking_mod._read_note_content

        def mock_read_note(path, vault=None):
            fp = vault_dir / path
            if fp.is_file():
                return fp.read_text(encoding="utf-8", errors="replace")
            return ""

        thinking_mod._read_note_content = mock_read_note

        try:
            result = ghost_voice_profile(sample_notes=15)

            check("returns dict", isinstance(result, dict))
            check("has profile key", "profile" in result)
            check("has sample_size", result.get("sample_size") == 15)
            check("confidence is medium", result.get("confidence") == "medium")

            profile = result.get("profile", {})
            check("has avg_sentence_length", "avg_sentence_length" in profile)
            check("has vocabulary_richness", "vocabulary_richness" in profile)
            check("has common_phrases", isinstance(profile.get("common_phrases"), list))
            check("has structural_preferences", "structural_preferences" in profile)
            check("has tone_markers", isinstance(profile.get("tone_markers"), list))

            # Short sentences should yield "direct" tone marker.
            check(
                "tone includes 'direct' for short sentences",
                "direct" in profile.get("tone_markers", []),
            )
        finally:
            thinking_mod._load_or_build_index = orig_load
            thinking_mod._read_note_content = orig_read


def test_ghost_low_confidence() -> None:
    print("\n--- ghost_voice_profile (low confidence, <5 notes) ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault_dir = _make_vault(tmp, {
            "One.md": "Short note.",
            "Two.md": "Another note.",
        })

        import obsidian_connector.thinking as thinking_mod
        orig_load = thinking_mod._load_or_build_index

        def mock_load(vault=None):
            return build_note_index(str(vault_dir))

        thinking_mod._load_or_build_index = mock_load

        try:
            result = ghost_voice_profile(sample_notes=20)

            check("returns dict", isinstance(result, dict))
            check("confidence is low", result.get("confidence") == "low")
            check("profile is empty", result.get("profile") == {})
            check("has message", "message" in result)
        finally:
            thinking_mod._load_or_build_index = orig_load


# ---------------------------------------------------------------------------
# Test: drift_analysis
# ---------------------------------------------------------------------------

def test_drift_analysis() -> None:
    print("\n--- drift_analysis ---")

    with tempfile.TemporaryDirectory() as tmp:
        # Build mock daily notes with intentions.
        from datetime import datetime, timedelta, timezone

        today = datetime.now(timezone.utc).date()
        notes: dict[str, str] = {}
        for i in range(5):
            day = today - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            content = (
                f"# {day_str}\n\n"
                f"## Plans\n"
                f"- I will finish the report\n"
                f"- Plan to review the budget\n\n"
                f"## Notes\n"
                f"**Important meeting** about quarterly review.\n"
                f"Discussed **team expansion** strategy.\n"
            )
            notes[f"{day_str}.md"] = content

        vault_dir = _make_vault(tmp, notes)

        # We need to mock search_notes to return hits from our vault.
        import obsidian_connector.thinking as thinking_mod
        orig_search = thinking_mod.search_notes
        orig_read = thinking_mod._read_note_content

        def mock_search(query, vault=None):
            results = []
            for fname, content in notes.items():
                if query in fname or query.lower() in content.lower():
                    results.append({
                        "file": fname,
                        "matches": [{"line": 1, "text": query}],
                    })
            return results

        def mock_read(path, vault=None):
            fp = vault_dir / path
            if fp.is_file():
                return fp.read_text(encoding="utf-8", errors="replace")
            return ""

        thinking_mod.search_notes = mock_search
        thinking_mod._read_note_content = mock_read

        try:
            result = drift_analysis(lookback_days=10)

            check("returns dict", isinstance(result, dict))
            check("has stated_intentions", "stated_intentions" in result)
            check("has actual_focus", "actual_focus" in result)
            check("has gaps", "gaps" in result)
            check("has surprises", "surprises" in result)
            check("has coverage_pct", "coverage_pct" in result)
            check("has daily_notes_found", "daily_notes_found" in result)
            check("daily notes found > 0", result.get("daily_notes_found", 0) > 0)

            # Should have extracted intentions.
            intentions = result.get("stated_intentions", [])
            check("extracted intentions", len(intentions) > 0)
            if intentions:
                check(
                    "intention has text",
                    "text" in intentions[0],
                )
        finally:
            thinking_mod.search_notes = orig_search
            thinking_mod._read_note_content = orig_read


def test_drift_no_daily_notes() -> None:
    print("\n--- drift_analysis (no daily notes) ---")

    import obsidian_connector.thinking as thinking_mod
    orig_search = thinking_mod.search_notes

    def mock_search(query, vault=None):
        return []

    thinking_mod.search_notes = mock_search

    try:
        result = drift_analysis(lookback_days=10)

        check("returns dict", isinstance(result, dict))
        check("daily_notes_found is 0", result.get("daily_notes_found") == 0)
        check("has message", "message" in result)
        check("empty intentions", result.get("stated_intentions") == [])
    finally:
        thinking_mod.search_notes = orig_search


# ---------------------------------------------------------------------------
# Test: trace_idea
# ---------------------------------------------------------------------------

def test_trace_idea() -> None:
    print("\n--- trace_idea ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            "Early.md": "First mention of portfolio construction here.",
            "Middle.md": "More about portfolio construction methodology.",
            "Recent.md": "Latest portfolio construction framework.",
        })

        vault_dir = vault

        # Set mtimes at different dates.
        _set_mtime(vault_dir, "Early.md", 90)
        _set_mtime(vault_dir, "Middle.md", 30)
        _set_mtime(vault_dir, "Recent.md", 1)

        import obsidian_connector.thinking as thinking_mod
        orig_search = thinking_mod.search_notes
        orig_load = thinking_mod._load_or_build_index

        def mock_search(query, vault=None):
            results = []
            for fname in ["Early.md", "Middle.md", "Recent.md"]:
                fp = vault_dir / fname
                content = fp.read_text()
                if query.lower() in content.lower():
                    results.append({
                        "file": fname,
                        "matches": [{"line": 1, "text": content[:100]}],
                    })
            return results

        def mock_load(vault=None):
            return build_note_index(str(vault_dir))

        thinking_mod.search_notes = mock_search
        thinking_mod._load_or_build_index = mock_load

        try:
            result = trace_idea("portfolio construction", max_notes=20)

            check("returns dict", isinstance(result, dict))
            check("has topic", result.get("topic") == "portfolio construction")
            check("has timeline", isinstance(result.get("timeline"), list))
            check("has phases", isinstance(result.get("phases"), list))
            check("total_mentions == 3", result.get("total_mentions") == 3)

            timeline = result.get("timeline", [])
            check("timeline has 3 entries", len(timeline) == 3)

            # First mention should be the earliest.
            first = result.get("first_mention")
            check("first_mention exists", first is not None)
            if first:
                check("first mention file is Early.md", first.get("file") == "Early.md")

            latest = result.get("latest_mention")
            check("latest_mention exists", latest is not None)
            if latest:
                check("latest mention file is Recent.md", latest.get("file") == "Recent.md")

            # Phases: with 30+ day gap between Early and Middle, should have revival.
            phases = result.get("phases", [])
            check("has phases", len(phases) >= 1)
        finally:
            thinking_mod.search_notes = orig_search
            thinking_mod._load_or_build_index = orig_load


# ---------------------------------------------------------------------------
# Test: deep_ideas
# ---------------------------------------------------------------------------

def test_deep_ideas() -> None:
    print("\n--- deep_ideas ---")

    with tempfile.TemporaryDirectory() as tmp:
        vault = _make_vault(tmp, {
            # Orphan with #idea tag (should be found).
            "Forgotten.md": "# Forgotten\n\n#idea\n\nSome idea I had once.",
            # High-backlink dead end.
            "Hub.md": "# Hub\n\nReferenced by many.",
            "Ref1.md": "Points to [[Hub]]",
            "Ref2.md": "Also links to [[Hub]]",
            "Ref3.md": "And another [[Hub]] reference",
            # Rare tag pair.
            "TagA.md": "#aviation #finance\n\nAircraft leasing.",
            "TagB.md": "#aviation\n\nAviation operations.",
            # Unresolved link.
            "HasBroken.md": "See [[Nonexistent Topic]] for details.",
        })
        vault_dir = vault

        import obsidian_connector.thinking as thinking_mod
        orig_load = thinking_mod._load_or_build_index

        def mock_load(vault=None):
            return build_note_index(str(vault_dir))

        thinking_mod._load_or_build_index = mock_load

        try:
            result = deep_ideas(max_ideas=10)

            check("returns dict", isinstance(result, dict))
            check("has ideas", isinstance(result.get("ideas"), list))
            check("has vault_health", "vault_health" in result)

            ideas = result.get("ideas", [])
            check("found ideas", len(ideas) > 0)

            # Check idea types that should be present.
            types_found = {idea["type"] for idea in ideas}
            check(
                "found forgotten_idea type",
                "forgotten_idea" in types_found,
            )
            check(
                "found convergence_point type",
                "convergence_point" in types_found,
            )
            check(
                "found unresolved_link type",
                "unresolved_link" in types_found,
            )

            # Vault health.
            health = result.get("vault_health", {})
            check("orphan_pct is a float", isinstance(health.get("orphan_pct"), float))
            check("unresolved_count > 0", health.get("unresolved_count", 0) > 0)

            # Priority ordering: high should come first.
            if len(ideas) >= 2:
                priority_map = {"high": 0, "medium": 1, "low": 2}
                first_priority = priority_map.get(ideas[0].get("priority"), 3)
                check("high priority ideas come first", first_priority <= 1)
        finally:
            thinking_mod._load_or_build_index = orig_load


def test_deep_ideas_empty_vault() -> None:
    print("\n--- deep_ideas (empty vault) ---")

    import obsidian_connector.thinking as thinking_mod
    orig_load = thinking_mod._load_or_build_index

    def mock_load(vault=None):
        return None

    thinking_mod._load_or_build_index = mock_load

    try:
        result = deep_ideas()

        check("returns dict", isinstance(result, dict))
        check("ideas is empty", result.get("ideas") == [])
        check("has message", "message" in result)
    finally:
        thinking_mod._load_or_build_index = orig_load


# ---------------------------------------------------------------------------
# Test: trace_idea with no results
# ---------------------------------------------------------------------------

def test_trace_no_results() -> None:
    print("\n--- trace_idea (no results) ---")

    import obsidian_connector.thinking as thinking_mod
    orig_search = thinking_mod.search_notes

    def mock_search(query, vault=None):
        return []

    thinking_mod.search_notes = mock_search

    try:
        result = trace_idea("nonexistent topic xyzzy")

        check("returns dict", isinstance(result, dict))
        check("total_mentions is 0", result.get("total_mentions") == 0)
        check("timeline is empty", result.get("timeline") == [])
        check("first_mention is None", result.get("first_mention") is None)
    finally:
        thinking_mod.search_notes = orig_search


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_ghost_voice_profile()
    test_ghost_low_confidence()
    test_drift_analysis()
    test_drift_no_daily_notes()
    test_trace_idea()
    test_trace_no_results()
    test_deep_ideas()
    test_deep_ideas_empty_vault()

    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
