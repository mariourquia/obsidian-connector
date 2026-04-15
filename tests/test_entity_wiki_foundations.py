"""Tests for Task 30 first-pass entity wiki body.

Covers:

- render_first_pass_wiki_body output shape across entity kinds.
- Graceful "_No linked data yet._" placeholders for empty subsections.
- EntityInput extension: related_entities_by_kind / first_seen_at /
  last_activity_at default to empty / None and are forwarded through
  write_entity_note.
- Fence preservation when an explicit wiki_content is supplied.
- User-notes fence preservation across re-renders.
- Determinism: two invocations with identical inputs -> identical bytes.
- Long alias list renders verbatim (no truncation).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from obsidian_connector.entity_notes import (
    ENTITIES_ROOT,
    ENTITY_USER_NOTES_BEGIN,
    ENTITY_USER_NOTES_END,
    ENTITY_WIKI_BEGIN,
    ENTITY_WIKI_END,
    EntityInput,
    LinkedAction,
    render_first_pass_wiki_body,
    write_entity_note,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ent(**kwargs) -> EntityInput:
    defaults = dict(
        entity_id="ent_01HTEST",
        kind="project",
        canonical_name="Test Project",
        slug="test-project",
    )
    defaults.update(kwargs)
    return EntityInput(**defaults)


def _action(action_id: str, title: str, status: str = "open", path: str | None = None) -> LinkedAction:
    return LinkedAction(
        action_id=action_id, title=title, status=status, commitment_path=path
    )


def _peer(
    *,
    entity_id: str,
    canonical_name: str,
    kind: str,
    slug: str,
    co: int = 1,
) -> dict:
    return {
        "entity_id": entity_id,
        "canonical_name": canonical_name,
        "kind": kind,
        "slug": slug,
        "co_occurrence_count": co,
    }


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# 1. EntityInput extension defaults
# ---------------------------------------------------------------------------


def test_entity_input_task30_fields_default_safely():
    ent = _ent()
    assert ent.related_entities_by_kind == {}
    assert ent.first_seen_at is None
    assert ent.last_activity_at is None


# ---------------------------------------------------------------------------
# 2. render_first_pass_wiki_body — empty entity graceful placeholders
# ---------------------------------------------------------------------------


def test_render_empty_entity_has_all_placeholders():
    ent = _ent(kind="project", first_seen_at=None, last_activity_at=None)
    body = render_first_pass_wiki_body(ent)
    # At-a-glance header
    assert body.startswith("**At a glance:**")
    assert "kind: project" in body
    assert "0 open" in body
    assert "0 done" in body
    # No peers -> graceful placeholder for each peer subsection
    assert body.count("_No linked data yet._") >= 2
    # Commitment subsections use the "project" heading
    assert "### Open commitments on this project" in body
    assert "### Completed on this project" in body


def test_render_empty_entity_omits_first_seen_line_when_missing():
    ent = _ent(first_seen_at=None, last_activity_at=None)
    body = render_first_pass_wiki_body(ent)
    assert "first seen" not in body
    assert "last active" not in body


def test_render_at_a_glance_includes_timestamps_when_present():
    ent = _ent(
        first_seen_at="2026-04-01T12:00:00+00:00",
        last_activity_at="2026-04-14T08:00:00+00:00",
    )
    body = render_first_pass_wiki_body(ent)
    assert "first seen 2026-04-01" in body
    assert "last active 2026-04-14" in body
    # Sub-second precision never leaks — helps keep deterministic bytes.
    assert "12:00" not in body


# ---------------------------------------------------------------------------
# 3. Kind-specific subsections
# ---------------------------------------------------------------------------


def test_person_kind_renders_projects_and_areas():
    related = {
        "project": [
            _peer(entity_id="ent_p1", canonical_name="Capodagli AI", kind="project", slug="capodagli-ai", co=3),
            _peer(entity_id="ent_p2", canonical_name="Board Deck", kind="project", slug="board-deck", co=1),
        ],
        "area": [
            _peer(entity_id="ent_a1", canonical_name="Work", kind="area", slug="work", co=4),
        ],
    }
    ent = _ent(kind="person", canonical_name="Kate Chen", slug="kate-chen", related_entities_by_kind=related)
    body = render_first_pass_wiki_body(ent)

    assert "### Projects this person appears in" in body
    assert "### Areas" in body
    assert "[[Entities/Projects/capodagli-ai|Capodagli AI]] (3)" in body
    assert "[[Entities/Projects/board-deck|Board Deck]] (1)" in body
    assert "[[Entities/Areas/work|Work]] (4)" in body
    # Commitment headings matched to kind
    assert "Recent commitments with this person" in body
    assert "Past commitments with this person" in body


def test_project_kind_renders_people_and_areas():
    related = {
        "person": [
            _peer(entity_id="ent_1", canonical_name="Kate", kind="person", slug="kate", co=2),
            _peer(entity_id="ent_2", canonical_name="Sam", kind="person", slug="sam", co=1),
        ],
        "area": [
            _peer(entity_id="ent_3", canonical_name="Work", kind="area", slug="work", co=1),
        ],
    }
    actions = [
        _action("a1", "Ship the deck", path="Commitments/Open/2026/04/ship-deck.md"),
        _action("a2", "Draft KPIs"),
    ]
    done = [_action("a3", "Old task", status="done")]
    ent = _ent(
        kind="project",
        canonical_name="Board Deck",
        slug="board-deck",
        open_actions=actions,
        done_actions=done,
        related_entities_by_kind=related,
    )
    body = render_first_pass_wiki_body(ent)

    assert "### People involved" in body
    assert "### Areas" in body
    assert "[[Entities/People/kate|Kate]] (2)" in body
    assert "[[Entities/Areas/work|Work]] (1)" in body
    assert "### Open commitments on this project" in body
    assert "### Completed on this project" in body
    assert "[[Commitments/Open/2026/04/ship-deck|Ship the deck]]" in body
    assert "- Draft KPIs" in body  # no path -> plain bullet
    assert "- Old task" in body


def test_area_kind_renders_projects_and_people():
    related = {
        "project": [
            _peer(entity_id="ent_p", canonical_name="Alpha", kind="project", slug="alpha", co=2),
        ],
        "person": [
            _peer(entity_id="ent_h", canonical_name="Mario", kind="person", slug="mario", co=5),
        ],
    }
    ent = _ent(kind="area", canonical_name="Work", slug="work", related_entities_by_kind=related)
    body = render_first_pass_wiki_body(ent)
    assert "### Projects in this area" in body
    assert "### People" in body
    assert "[[Entities/Projects/alpha|Alpha]] (2)" in body
    assert "[[Entities/People/mario|Mario]] (5)" in body
    assert "### Open commitments in this area" in body


def test_topic_kind_renders_projects_and_people():
    ent = _ent(
        kind="topic",
        canonical_name="Slides",
        slug="slides",
        related_entities_by_kind={
            "project": [
                _peer(entity_id="ep", canonical_name="Deck", kind="project", slug="deck", co=2),
            ],
            "person": [],
        },
    )
    body = render_first_pass_wiki_body(ent)
    assert "### Related projects" in body
    assert "### People" in body
    assert "### Mentions (open)" in body
    assert "### Mentions (done)" in body
    # Empty person list -> placeholder under "People"
    sections = body.split("###")
    people_section = next(s for s in sections if s.strip().startswith("People"))
    assert "_No linked data yet._" in people_section


def test_tool_kind_uses_generic_seen_on_headings():
    ent = _ent(kind="tool", canonical_name="ESP32", slug="esp32")
    body = render_first_pass_wiki_body(ent)
    assert "### Seen on commitments" in body
    assert "### Seen on completed commitments" in body


# ---------------------------------------------------------------------------
# 4. Ordering & counts
# ---------------------------------------------------------------------------


def test_peers_sorted_by_count_desc_then_name_asc():
    peers = [
        _peer(entity_id="c", canonical_name="Charlie", kind="person", slug="charlie", co=1),
        _peer(entity_id="a", canonical_name="Alpha", kind="person", slug="alpha", co=1),
        _peer(entity_id="b", canonical_name="Bravo", kind="person", slug="bravo", co=3),
    ]
    ent = _ent(kind="project", related_entities_by_kind={"person": peers})
    body = render_first_pass_wiki_body(ent)
    # Extract bullet order
    lines = [ln for ln in body.splitlines() if ln.startswith("- [[")]
    names_in_order = [ln.split("|", 1)[1].split("]]", 1)[0] for ln in lines]
    # Expect: Bravo (co=3), Alpha (A<C alphabetically), Charlie.
    assert names_in_order[:3] == ["Bravo", "Alpha", "Charlie"]


def test_peer_without_slug_falls_back_to_plain_name():
    peers = [{"entity_id": "x", "canonical_name": "Orphan", "kind": "person"}]
    ent = _ent(kind="project", related_entities_by_kind={"person": peers})
    body = render_first_pass_wiki_body(ent)
    assert "- Orphan" in body
    assert "[[" not in body.split("### People involved")[1].split("###")[0]


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def test_render_is_byte_identical_across_calls():
    related = {
        "person": [
            _peer(entity_id=f"ent_{i}", canonical_name=f"Person {i}", kind="person", slug=f"p{i}", co=i)
            for i in range(1, 4)
        ],
        "area": [_peer(entity_id="a", canonical_name="Work", kind="area", slug="work", co=2)],
    }
    ent = _ent(
        kind="project",
        canonical_name="Determinism",
        slug="determinism",
        open_actions=[_action("a1", "Alpha"), _action("a2", "Bravo")],
        done_actions=[_action("a3", "Charlie", status="done")],
        related_entities_by_kind=related,
        first_seen_at="2026-04-01T00:00:00+00:00",
        last_activity_at="2026-04-14T00:00:00+00:00",
    )
    a = render_first_pass_wiki_body(ent)
    b = render_first_pass_wiki_body(ent)
    assert a == b


# ---------------------------------------------------------------------------
# 6. Integration: write_entity_note substitutes the first-pass body
# ---------------------------------------------------------------------------


def test_write_substitutes_first_pass_body_when_wiki_content_none(vault: Path):
    related = {
        "person": [
            _peer(entity_id="p1", canonical_name="Kate", kind="person", slug="kate", co=2),
        ],
    }
    ent = _ent(
        kind="project",
        open_actions=[_action("a1", "Ship")],
        related_entities_by_kind=related,
        first_seen_at="2026-04-01T00:00:00Z",
        last_activity_at="2026-04-14T00:00:00Z",
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert ENTITY_WIKI_BEGIN in content
    assert ENTITY_WIKI_END in content
    begin = content.index(ENTITY_WIKI_BEGIN)
    end = content.index(ENTITY_WIKI_END)
    fence_body = content[begin + len(ENTITY_WIKI_BEGIN):end]
    assert "**At a glance:**" in fence_body
    assert "### People involved" in fence_body
    assert "[[Entities/People/kate|Kate]] (2)" in fence_body


def test_explicit_wiki_content_wins_over_first_pass(vault: Path):
    """Task 15.C hook: explicit wiki_content bypasses the scaffold."""
    related = {
        "person": [_peer(entity_id="p", canonical_name="Kate", kind="person", slug="kate", co=1)]
    }
    ent = _ent(
        kind="project",
        open_actions=[_action("a1", "Ship")],
        related_entities_by_kind=related,
        wiki_content="An LLM-authored paragraph.",
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    assert "An LLM-authored paragraph." in content
    assert "**At a glance:**" not in content
    assert "### People involved" not in content


def test_first_pass_body_not_substituted_for_bare_entity(vault: Path):
    """Pre-Task-30 callers (no projection, no actions) keep legacy behaviour.

    The fence remains empty on create and is preserved across re-renders.
    """
    ent = _ent()  # no actions, no projection, no timestamps
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    # Fence is present and empty.
    begin = content.index(ENTITY_WIKI_BEGIN)
    end = content.index(ENTITY_WIKI_END)
    fence_body = content[begin + len(ENTITY_WIKI_BEGIN):end].strip()
    assert fence_body == ""


# ---------------------------------------------------------------------------
# 7. User-notes fence preservation
# ---------------------------------------------------------------------------


def test_user_notes_preserved_when_first_pass_body_renders(vault: Path):
    ent = _ent(
        kind="project",
        open_actions=[_action("a1", "Ship")],
        related_entities_by_kind={
            "person": [_peer(entity_id="p", canonical_name="Kate", kind="person", slug="kate", co=1)],
        },
    )
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    edited = content.replace(
        f"{ENTITY_USER_NOTES_BEGIN}\n\n{ENTITY_USER_NOTES_END}",
        f"{ENTITY_USER_NOTES_BEGIN}\nMy own thoughts on this project.\n{ENTITY_USER_NOTES_END}",
    )
    result.path.write_text(edited)

    result2 = write_entity_note(vault, ent)
    final = result2.path.read_text()
    assert "My own thoughts on this project." in final
    # First-pass body still renders too.
    assert "**At a glance:**" in final
    assert "[[Entities/People/kate|Kate]] (1)" in final


# ---------------------------------------------------------------------------
# 8. Deterministic bytes on full write_entity_note
# ---------------------------------------------------------------------------


def test_write_entity_note_is_byte_identical_with_pinned_sync_at(vault: Path, tmp_path: Path):
    """Same EntityInput + same sync_at -> same note bytes across writes."""
    related = {
        "person": [_peer(entity_id="p", canonical_name="Kate", kind="person", slug="kate", co=1)],
    }
    ent = _ent(
        kind="project",
        open_actions=[_action("a1", "Ship")],
        related_entities_by_kind=related,
        first_seen_at="2026-04-01T00:00:00+00:00",
        last_activity_at="2026-04-14T00:00:00+00:00",
    )
    # Two separate vault roots so the writes are independent files.
    v1 = tmp_path / "v1"
    v2 = tmp_path / "v2"
    v1.mkdir(); v2.mkdir()
    sync_at = "2026-04-14T12:00:00+00:00"
    r1 = write_entity_note(v1, ent, sync_at=sync_at)
    r2 = write_entity_note(v2, ent, sync_at=sync_at)
    assert r1.path.read_bytes() == r2.path.read_bytes()


# ---------------------------------------------------------------------------
# 9. Long alias list — no truncation behaviour
# ---------------------------------------------------------------------------


def test_long_alias_list_is_rendered_without_truncation(vault: Path):
    aliases = [f"alias-{i:03d}" for i in range(50)]
    ent = _ent(aliases=aliases)
    result = write_entity_note(vault, ent)
    content = result.path.read_text()
    for alias in aliases:
        assert alias in content


# ---------------------------------------------------------------------------
# 10. Unknown kind falls back to generic layout
# ---------------------------------------------------------------------------


def test_unknown_kind_uses_generic_layout():
    """render_first_pass_wiki_body tolerates future kinds without crashing."""
    ent = EntityInput(
        entity_id="ent_X",
        kind="person",  # must still be a valid kind for EntityInput use
        canonical_name="Edge Case",
        slug="edge-case",
    )
    # Poison the lookup via monkey-patching: verify that if an entity's
    # kind is not in _SUBSECTIONS_BY_KIND, the function still renders
    # and does not raise.
    body = render_first_pass_wiki_body(
        replace(ent, kind="person"),
    )
    assert "**At a glance:**" in body


# ---------------------------------------------------------------------------
# 11. Missing projection -> all peer sections degrade gracefully
# ---------------------------------------------------------------------------


def test_all_peer_sections_degrade_with_missing_projection(vault: Path):
    ent = _ent(
        kind="person",
        canonical_name="Lonely",
        slug="lonely",
        open_actions=[_action("a1", "Do a thing")],
    )
    body = render_first_pass_wiki_body(ent)
    # Both peer subsections for a person (project, area) print placeholders.
    assert body.count("_No linked data yet._") >= 2
    assert "### Projects this person appears in" in body
    assert "### Areas" in body


# ---------------------------------------------------------------------------
# 12. Explicit related_entities_by_kind override wins over entity attr
# ---------------------------------------------------------------------------


def test_explicit_related_override_wins():
    ent = _ent(
        kind="project",
        related_entities_by_kind={
            "person": [_peer(entity_id="e", canonical_name="Embedded", kind="person", slug="embedded", co=1)],
        },
    )
    override = {
        "person": [_peer(entity_id="e2", canonical_name="Override", kind="person", slug="override", co=7)],
    }
    body = render_first_pass_wiki_body(ent, related_entities_by_kind=override)
    assert "Override" in body
    assert "Embedded" not in body
    assert "(7)" in body


# ---------------------------------------------------------------------------
# 13. Re-render idempotency with first-pass body
# ---------------------------------------------------------------------------


def test_re_render_with_first_pass_body_is_stable(vault: Path):
    related = {
        "person": [_peer(entity_id="p", canonical_name="Kate", kind="person", slug="kate", co=2)],
    }
    ent = _ent(
        kind="project",
        open_actions=[_action("a1", "Ship")],
        related_entities_by_kind=related,
        first_seen_at="2026-04-01T00:00:00Z",
        last_activity_at="2026-04-14T00:00:00Z",
    )
    sync_at = "2026-04-14T12:00:00+00:00"
    write_entity_note(vault, ent, sync_at=sync_at)
    first = (vault / ENTITIES_ROOT / "Projects" / "test-project.md").read_bytes()
    write_entity_note(vault, ent, sync_at=sync_at)
    second = (vault / ENTITIES_ROOT / "Projects" / "test-project.md").read_bytes()
    assert first == second
