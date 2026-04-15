"""Tests for Task 27 rich-metadata frontmatter schema on commitment notes.

Covers:
- ``ActionInput`` accepts the new fields with sensible defaults so
  callers that don't supply them still work.
- ``render_commitment_note`` emits the new YAML keys
  (``lifecycle_stage``, ``urgency``, ``source_app``, ``source_entrypoint``,
  ``people``, ``areas``) in a stable slot order.
- ``parse_frontmatter`` can round-trip the new keys.
- ``_action_from_content`` hydrates the new fields on reload and falls
  back to defaults when the note was written pre-Task 27.
- ``_dict_to_action_input`` tolerates the new keys from the service
  payload and defaults missing ones.
- Body metadata section surfaces the new fields.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from obsidian_connector.commitment_notes import (
    ActionInput,
    parse_frontmatter,
    render_commitment_note,
    write_commitment_note,
)
from obsidian_connector.commitment_ops import (
    _action_from_content,
    _dict_to_action_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_action(**kwargs) -> ActionInput:
    defaults = dict(
        action_id="act_01HT27",
        capture_id="cap_01HT27",
        title="Ship Task 27",
        created_at="2026-04-14T12:00:00+00:00",
        status="open",
    )
    defaults.update(kwargs)
    return ActionInput(**defaults)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# 1. ActionInput defaults
# ---------------------------------------------------------------------------

class TestActionInputDefaults:
    def test_default_urgency_normal(self):
        action = _base_action()
        assert action.urgency == "normal"

    def test_default_lifecycle_inbox(self):
        action = _base_action()
        assert action.lifecycle_stage == "inbox"

    def test_default_source_fields_none(self):
        action = _base_action()
        assert action.source_app is None
        assert action.source_entrypoint is None

    def test_default_buckets_empty(self):
        action = _base_action()
        assert action.people == []
        assert action.areas == []
        assert action.projects == []

    def test_accepts_all_new_fields(self):
        action = _base_action(
            urgency="elevated",
            lifecycle_stage="active",
            source_app="wispr_flow",
            source_entrypoint="action_button",
            people=["Kate Chen"],
            areas=["work"],
            projects=["Capodagli AI"],
        )
        assert action.urgency == "elevated"
        assert action.lifecycle_stage == "active"
        assert action.source_app == "wispr_flow"
        assert action.source_entrypoint == "action_button"
        assert action.people == ["Kate Chen"]
        assert action.areas == ["work"]


# ---------------------------------------------------------------------------
# 2. Frontmatter renderer
# ---------------------------------------------------------------------------

class TestFrontmatterRendering:
    def test_frontmatter_contains_all_new_keys(self):
        action = _base_action()
        rendered = render_commitment_note(action)
        fm = parse_frontmatter(rendered)
        for key in (
            "lifecycle_stage",
            "urgency",
            "people",
            "areas",
            "source_app",
            "source_entrypoint",
        ):
            assert key in fm, f"missing {key} in frontmatter: {fm.keys()}"

    def test_new_values_round_trip(self):
        action = _base_action(
            urgency="critical",
            lifecycle_stage="blocked",
            source_app="ios_share_sheet",
            source_entrypoint="share_sheet",
            people=["Kate Chen", "Sarah Lim"],
            areas=["work", "research"],
        )
        rendered = render_commitment_note(action)
        fm = parse_frontmatter(rendered)
        assert fm["urgency"] == "critical"
        assert fm["lifecycle_stage"] == "blocked"
        assert fm["source_app"] == "ios_share_sheet"
        assert fm["source_entrypoint"] == "share_sheet"
        assert "[Kate Chen, Sarah Lim]" in fm["people"]
        assert "[work, research]" in fm["areas"]

    def test_empty_lists_serialize_as_empty_flow(self):
        action = _base_action()
        rendered = render_commitment_note(action)
        fm = parse_frontmatter(rendered)
        assert fm["people"] == "[]"
        assert fm["areas"] == "[]"

    def test_field_order_is_stable(self):
        """urgency comes right after priority; lifecycle_stage after status."""
        action = _base_action()
        rendered = render_commitment_note(action)
        # Extract just the frontmatter lines.
        fm_section = rendered.split("---", 2)[1]
        keys_in_order = [
            line.split(":", 1)[0].strip()
            for line in fm_section.strip().splitlines()
            if ":" in line
        ]
        # Expected slot ordering for Task 27.
        assert keys_in_order.index("status") < keys_in_order.index("lifecycle_stage")
        assert keys_in_order.index("lifecycle_stage") < keys_in_order.index("priority")
        assert keys_in_order.index("priority") < keys_in_order.index("urgency")
        assert keys_in_order.index("urgency") < keys_in_order.index("due_at")
        source_note_idx = keys_in_order.index("source_note")
        assert keys_in_order.index("source_app") == source_note_idx + 1
        assert keys_in_order.index("source_entrypoint") > keys_in_order.index("source_app")

    def test_null_source_app_serializes_as_null(self):
        action = _base_action()  # defaults: source_app = None
        rendered = render_commitment_note(action)
        fm = parse_frontmatter(rendered)
        assert fm["source_app"] == "null"


# ---------------------------------------------------------------------------
# 3. Body metadata surfaces the new fields
# ---------------------------------------------------------------------------

class TestBodyMetadata:
    def test_body_lists_lifecycle_and_urgency(self):
        action = _base_action(
            lifecycle_stage="active",
            urgency="elevated",
        )
        rendered = render_commitment_note(action)
        assert "- Lifecycle: active" in rendered
        assert "- Urgency: elevated" in rendered

    def test_body_lists_people_and_areas(self):
        action = _base_action(
            people=["Kate Chen"],
            areas=["work"],
        )
        rendered = render_commitment_note(action)
        assert "- People: Kate Chen" in rendered
        assert "- Areas: work" in rendered

    def test_body_source_line_with_entrypoint(self):
        action = _base_action(
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        rendered = render_commitment_note(action)
        assert "- Source: wispr_flow via action_button" in rendered

    def test_body_source_line_without_entrypoint(self):
        action = _base_action(source_app="wispr_flow")
        rendered = render_commitment_note(action)
        assert "- Source: wispr_flow" in rendered
        # No trailing "via ..." when entrypoint is absent.
        assert "via" not in rendered.split("- Source:")[1].splitlines()[0]


# ---------------------------------------------------------------------------
# 4. Reconstruction from on-disk notes
# ---------------------------------------------------------------------------

class TestActionFromContent:
    def test_roundtrip_all_new_fields(self, vault: Path):
        original = _base_action(
            urgency="elevated",
            lifecycle_stage="active",
            source_app="wispr_flow",
            source_entrypoint="action_button",
            people=["Kate Chen", "Sarah Lim"],
            areas=["work"],
        )
        result = write_commitment_note(vault, original)
        content = result.path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        reconstructed = _action_from_content(content, fm)
        assert reconstructed.urgency == "elevated"
        assert reconstructed.lifecycle_stage == "active"
        assert reconstructed.source_app == "wispr_flow"
        assert reconstructed.source_entrypoint == "action_button"
        assert reconstructed.people == ["Kate Chen", "Sarah Lim"]
        assert reconstructed.areas == ["work"]

    def test_missing_new_fields_hydrate_to_defaults(self):
        """A pre-Task 27 commitment note (no new keys) hydrates with defaults."""
        legacy_content = (
            "---\n"
            "type: commitment\n"
            "action_id: act_old\n"
            "capture_id: cap_old\n"
            "title: Old note\n"
            "project: null\n"
            "status: open\n"
            "priority: normal\n"
            "due_at: null\n"
            "postponed_until: null\n"
            "requires_ack: false\n"
            "escalation_policy: null\n"
            "channels: []\n"
            "source_note: null\n"
            "service_last_synced_at: 2026-04-01T00:00:00+00:00\n"
            "---\n\n"
            "# Old note\n"
            "- Created: 2026-04-01T00:00:00+00:00\n"
        )
        fm = parse_frontmatter(legacy_content)
        action = _action_from_content(legacy_content, fm)
        assert action.urgency == "normal"
        assert action.lifecycle_stage == "inbox"
        assert action.source_app is None
        assert action.source_entrypoint is None
        assert action.people == []
        assert action.areas == []


# ---------------------------------------------------------------------------
# 5. _dict_to_action_input — service payload ingestion
# ---------------------------------------------------------------------------

class TestDictToActionInput:
    def test_task_27_keys_are_mapped(self):
        raw = {
            "action_id": "act_1",
            "urgency": "elevated",
            "lifecycle_stage": "active",
            "source_app": "apple_notes",
            "source_entrypoint": "apple_notes_tag",
            "people": ["Kate Chen"],
            "areas": ["work"],
            "projects": ["Capodagli AI"],
        }
        action = _dict_to_action_input(raw)
        assert action.urgency == "elevated"
        assert action.lifecycle_stage == "active"
        assert action.source_app == "apple_notes"
        assert action.source_entrypoint == "apple_notes_tag"
        assert action.people == ["Kate Chen"]
        assert action.areas == ["work"]
        assert action.projects == ["Capodagli AI"]

    def test_missing_task_27_keys_default_gracefully(self):
        """Pre-Task 27 service payload: defaults kick in."""
        raw = {"action_id": "act_pre"}
        action = _dict_to_action_input(raw)
        assert action.urgency == "normal"
        assert action.lifecycle_stage == "inbox"
        assert action.source_app is None
        assert action.source_entrypoint is None
        assert action.people == []
        assert action.areas == []
        assert action.projects == []

    def test_string_scalar_in_list_field_is_promoted(self):
        """A service payload that accidentally sends a string survives."""
        raw = {"action_id": "act_str", "people": "Solo Person"}
        action = _dict_to_action_input(raw)
        assert action.people == ["Solo Person"]

    def test_none_source_app_stays_none(self):
        raw = {"action_id": "act_none", "source_app": None}
        action = _dict_to_action_input(raw)
        assert action.source_app is None


# ---------------------------------------------------------------------------
# 6. Idempotent re-render preserves task 27 fields across writes
# ---------------------------------------------------------------------------

class TestIdempotentReRender:
    def test_re_render_keeps_rich_metadata(self, vault: Path):
        """Writing, then writing again must produce the same frontmatter."""
        original = _base_action(
            urgency="critical",
            lifecycle_stage="waiting",
            source_app="ios_share_sheet",
            source_entrypoint="share_sheet",
            people=["Mario"],
            areas=["life"],
        )
        first = write_commitment_note(vault, original, now_iso="2026-04-14T00:00:00+00:00")
        first_content = first.path.read_text(encoding="utf-8")
        write_commitment_note(vault, original, now_iso="2026-04-14T01:00:00+00:00")
        second_content = first.path.read_text(encoding="utf-8")
        # Frontmatter shape stable (sync_at changes, but new fields identical).
        fm1 = parse_frontmatter(first_content)
        fm2 = parse_frontmatter(second_content)
        for key in (
            "urgency",
            "lifecycle_stage",
            "source_app",
            "source_entrypoint",
            "people",
            "areas",
        ):
            assert fm1[key] == fm2[key], f"{key} changed between writes"

    def test_read_modify_write_preserves_rich_metadata(self, vault: Path):
        """Simulate the mark-done flow: read existing note, mutate status,
        write back. Rich metadata from the original note must survive."""
        from obsidian_connector.commitment_ops import mark_commitment_done

        original = _base_action(
            urgency="elevated",
            lifecycle_stage="active",
            source_app="wispr_flow",
            source_entrypoint="action_button",
            people=["Kate Chen"],
            areas=["work"],
        )
        write_commitment_note(vault, original)
        mark_commitment_done(vault, original.action_id)

        # Reload the (now Done/) file and inspect frontmatter.
        from obsidian_connector.commitment_notes import find_commitment_note

        path = find_commitment_note(vault, original.action_id)
        assert path is not None
        reloaded_content = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(reloaded_content)
        assert fm["status"] == "done"
        # Task 27 lifecycle transitions to 'done' on the done verb (mirrors service).
        assert fm["lifecycle_stage"] == "done"
        # Source + entity fields survive untouched.
        assert fm["source_app"] == "wispr_flow"
        assert fm["source_entrypoint"] == "action_button"
        assert "Kate Chen" in fm["people"]
        assert "work" in fm["areas"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
