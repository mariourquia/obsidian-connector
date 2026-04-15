"""Task 29: source-aware provenance UX polish.

Covers the pure-function provenance label contract and its rendering in
commitment notes and Daily/Weekly review dashboards. Three areas:

1. ``format_source_label`` -- every known tuple, cloud-queue suffix,
   fallbacks, and missing/whitespace input handling.
2. Commitment note rendering -- every known tuple produces a ``Captured:``
   row with the right label, and legacy notes (no source fields) still
   render cleanly.
3. Review dashboards -- Daily and Weekly surfaces show a ``By source``
   Markdown table with the correct per-label counts on a synthetic vault.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obsidian_connector.commitment_dashboards import (
    REVIEW_DASHBOARDS_DIR,
    generate_daily_review_dashboard,
    generate_weekly_review_dashboard,
)
from obsidian_connector.commitment_notes import (
    ActionInput,
    format_source_label,
    render_commitment_note,
    write_commitment_note,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Monday 2026-04-13 10:00 UTC -- same anchor as test_review_dashboards so
# ISO-week boundaries are unambiguous.
NOW = "2026-04-13T10:00:00+00:00"


def _base_action(**kwargs) -> ActionInput:
    defaults = dict(
        action_id="act_01HT29",
        capture_id="cap_01HT29",
        title="Ship Task 29",
        created_at=NOW,
        status="open",
    )
    defaults.update(kwargs)
    return ActionInput(**defaults)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


def _write(
    vault: Path,
    *,
    action_id: str,
    title: str,
    source_app: str | None,
    source_entrypoint: str | None,
    created_at: str = NOW,
    status: str = "open",
) -> ActionInput:
    """Helper used by the dashboard tests -- writes one commitment note."""
    action = ActionInput(
        action_id=action_id,
        capture_id=f"CAP-{action_id[-5:]}",
        title=title,
        created_at=created_at,
        status=status,
        source_app=source_app,
        source_entrypoint=source_entrypoint,
    )
    write_commitment_note(vault, action, now_iso=created_at)
    return action


# ---------------------------------------------------------------------------
# 1. format_source_label -- pure function contract
# ---------------------------------------------------------------------------


class TestFormatSourceLabel:
    def test_wispr_flow_action_button(self):
        assert (
            format_source_label("wispr_flow", "action_button")
            == "Captured via Wispr Flow (Action Button)"
        )

    def test_wispr_flow_share_sheet(self):
        assert (
            format_source_label("wispr_flow", "share_sheet")
            == "Captured via Wispr Flow (Share Sheet)"
        )

    def test_wispr_flow_unknown_entrypoint(self):
        # Unknown entrypoint on a known app falls back to the base label.
        assert (
            format_source_label("wispr_flow", "some_new_flow")
            == "Captured via Wispr Flow"
        )

    def test_ios_share_sheet(self):
        assert (
            format_source_label("ios_share_sheet", "share_sheet")
            == "Captured via iOS Share Sheet"
        )

    def test_ios_share_sheet_no_entrypoint(self):
        # ios_share_sheet renders the same friendly label regardless of
        # entrypoint -- the entrypoint is always "share_sheet" in practice.
        assert (
            format_source_label("ios_share_sheet", None)
            == "Captured via iOS Share Sheet"
        )

    def test_apple_notes_tag(self):
        assert (
            format_source_label("apple_notes", "apple_notes_tag")
            == "Captured from Apple Notes (#capture)"
        )

    def test_apple_notes_without_entrypoint(self):
        # Only ``apple_notes_tag`` triggers the #capture suffix; other
        # entrypoints still get the "from Apple Notes" base label.
        assert (
            format_source_label("apple_notes", None)
            == "Captured from Apple Notes"
        )

    def test_queue_poller_suffix_on_wispr_flow(self):
        # Task 29: cloud-queue drained captures carry
        # ``source_entrypoint='queue_poller'`` but should preserve the
        # upstream app identity in the label.
        assert (
            format_source_label("wispr_flow", "queue_poller")
            == "Captured via Wispr Flow (via cloud queue)"
        )

    def test_queue_poller_suffix_on_ios_share_sheet(self):
        assert (
            format_source_label("ios_share_sheet", "queue_poller")
            == "Captured via iOS Share Sheet (via cloud queue)"
        )

    def test_queue_poller_only(self):
        # Edge case: queue_poller entrypoint with no recorded source_app
        # collapses to the transport label.
        assert (
            format_source_label(None, "queue_poller")
            == "Captured via cloud queue"
        )

    def test_queue_poller_as_source_app(self):
        # Edge case: queue_poller accidentally recorded as source_app --
        # still renders as the cloud-queue transport (no upstream known).
        assert (
            format_source_label("queue_poller", None)
            == "Captured via cloud queue"
        )

    def test_unknown_source_and_entrypoint(self):
        assert format_source_label(None, None) == "Unknown source"

    def test_empty_strings_degrade_to_unknown(self):
        # Whitespace-only / empty strings should behave like None so
        # callers need not sanitise frontmatter-parsed values.
        assert format_source_label("", "") == "Unknown source"
        assert format_source_label("   ", "   ") == "Unknown source"

    def test_fallback_for_unknown_source_app(self):
        # Unrecognised apps still get a friendly, never-empty label.
        assert (
            format_source_label("my_new_capture_source", "action_button")
            == "Captured from my_new_capture_source"
        )

    def test_is_pure_deterministic(self):
        # Same inputs -> same output, repeatedly.
        calls = [
            format_source_label("wispr_flow", "action_button") for _ in range(5)
        ]
        assert calls == ["Captured via Wispr Flow (Action Button)"] * 5


# ---------------------------------------------------------------------------
# 2. Commitment note rendering -- Captured: row
# ---------------------------------------------------------------------------


class TestCommitmentCapturedRow:
    def test_renders_captured_row_for_wispr_action_button(self):
        action = _base_action(
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        rendered = render_commitment_note(action)
        assert "- Captured: Captured via Wispr Flow (Action Button)" in rendered

    def test_renders_captured_row_for_wispr_share_sheet(self):
        action = _base_action(
            source_app="wispr_flow",
            source_entrypoint="share_sheet",
        )
        rendered = render_commitment_note(action)
        assert "- Captured: Captured via Wispr Flow (Share Sheet)" in rendered

    def test_renders_captured_row_for_ios_share_sheet(self):
        action = _base_action(
            source_app="ios_share_sheet",
            source_entrypoint="share_sheet",
        )
        rendered = render_commitment_note(action)
        assert "- Captured: Captured via iOS Share Sheet" in rendered

    def test_renders_captured_row_for_apple_notes(self):
        action = _base_action(
            source_app="apple_notes",
            source_entrypoint="apple_notes_tag",
        )
        rendered = render_commitment_note(action)
        assert "- Captured: Captured from Apple Notes (#capture)" in rendered

    def test_renders_captured_row_for_queue_drained(self):
        action = _base_action(
            source_app="wispr_flow",
            source_entrypoint="queue_poller",
        )
        rendered = render_commitment_note(action)
        assert (
            "- Captured: Captured via Wispr Flow (via cloud queue)"
            in rendered
        )

    def test_renders_captured_row_for_legacy_missing_source(self):
        # Legacy notes pre-Task 27 have no source fields -- still get a
        # well-formed "Captured: Unknown source" row (backward compatible).
        action = _base_action()
        rendered = render_commitment_note(action)
        assert "- Captured: Unknown source" in rendered

    def test_existing_source_line_still_present(self):
        # Backwards compatibility: the raw "- Source:" line introduced in
        # Task 27 must remain alongside the new human label.
        action = _base_action(
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        rendered = render_commitment_note(action)
        assert "- Source: wispr_flow via action_button" in rendered
        assert "- Captured: Captured via Wispr Flow (Action Button)" in rendered


# ---------------------------------------------------------------------------
# 3. Dashboards -- "By source" subsection
# ---------------------------------------------------------------------------


class TestDailyBySource:
    def test_empty_vault_shows_empty_by_source_with_zero_count(
        self, vault: Path
    ) -> None:
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Daily.md").read_text(
            encoding="utf-8"
        )
        assert "## By source (0)" in content
        assert (
            "_No sources to group (nothing captured today)._"
            in content
        )

    def test_counts_each_source_label(self, vault: Path) -> None:
        # Capture three today: 2 wispr + 1 apple_notes.
        _write(
            vault,
            action_id="act_01aa",
            title="Alpha one",
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        _write(
            vault,
            action_id="act_01ab",
            title="Alpha two",
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        _write(
            vault,
            action_id="act_01ac",
            title="Apple tagged capture",
            source_app="apple_notes",
            source_entrypoint="apple_notes_tag",
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Daily.md").read_text(
            encoding="utf-8"
        )

        # Subsection header + table shape.
        assert "## By source (2)" in content
        assert "| Source | Count |" in content
        # Count rows: wispr with 2 first (count-desc ordering), apple
        # notes with 1 second.
        assert "| Captured via Wispr Flow (Action Button) | 2 |" in content
        assert "| Captured from Apple Notes (#capture) | 1 |" in content
        # Row ordering (count desc, label asc): wispr row precedes apple.
        wispr_idx = content.index(
            "| Captured via Wispr Flow (Action Button) | 2 |"
        )
        apple_idx = content.index(
            "| Captured from Apple Notes (#capture) | 1 |"
        )
        assert wispr_idx < apple_idx

    def test_ignores_captures_from_other_days(self, vault: Path) -> None:
        # Today: one wispr capture. Yesterday: one apple_notes. Only
        # today's row should contribute to the Daily By-source count.
        _write(
            vault,
            action_id="act_today01",
            title="Today capture",
            source_app="wispr_flow",
            source_entrypoint="action_button",
        )
        yesterday = (
            datetime.fromisoformat(NOW) - timedelta(days=1)
        ).isoformat()
        _write(
            vault,
            action_id="act_yday01",
            title="Yesterday capture",
            source_app="apple_notes",
            source_entrypoint="apple_notes_tag",
            created_at=yesterday,
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Daily.md").read_text(
            encoding="utf-8"
        )
        assert "## By source (1)" in content
        assert "| Captured via Wispr Flow (Action Button) | 1 |" in content
        # Yesterday's apple_notes row must not appear in today's by-source.
        assert (
            "| Captured from Apple Notes (#capture) | 1 |" not in content
        )


class TestWeeklyBySource:
    def test_empty_vault_shows_empty_by_source(self, vault: Path) -> None:
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Weekly.md").read_text(
            encoding="utf-8"
        )
        assert "## By source (0)" in content
        assert (
            "_No sources to group (nothing captured this week)._"
            in content
        )

    def test_counts_the_full_week(self, vault: Path) -> None:
        # NOW = Monday 2026-04-13. The current ISO-week includes Mon..Sun
        # of that week. Put two captures inside the window, one outside.
        inside_a = NOW  # Monday
        inside_b = (
            datetime.fromisoformat(NOW) + timedelta(days=2)
        ).isoformat()  # Wednesday
        outside = (
            datetime.fromisoformat(NOW) - timedelta(days=3)
        ).isoformat()  # previous Friday (last week)

        _write(
            vault,
            action_id="act_wk_a",
            title="Week capture A",
            source_app="ios_share_sheet",
            source_entrypoint="share_sheet",
            created_at=inside_a,
        )
        _write(
            vault,
            action_id="act_wk_b",
            title="Week capture B",
            source_app="ios_share_sheet",
            source_entrypoint="share_sheet",
            created_at=inside_b,
        )
        _write(
            vault,
            action_id="act_wk_c",
            title="Last week capture",
            source_app="wispr_flow",
            source_entrypoint="action_button",
            created_at=outside,
        )

        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Weekly.md").read_text(
            encoding="utf-8"
        )

        assert "## By source (1)" in content
        assert "| Captured via iOS Share Sheet | 2 |" in content
        # The previous-week wispr capture must not be counted here.
        assert (
            "| Captured via Wispr Flow (Action Button) | 1 |" not in content
        )

    def test_cloud_queue_suffix_shows_through(self, vault: Path) -> None:
        # Drained via cloud queue -- suffix should appear in the count table.
        _write(
            vault,
            action_id="act_queue01",
            title="Queue drained",
            source_app="wispr_flow",
            source_entrypoint="queue_poller",
        )
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = (vault / f"{REVIEW_DASHBOARDS_DIR}/Weekly.md").read_text(
            encoding="utf-8"
        )
        assert (
            "| Captured via Wispr Flow (via cloud queue) | 1 |" in content
        )
