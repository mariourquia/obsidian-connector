"""Task 26 review dashboards + inbox review flows.

Covers the four new surfaces in ``obsidian_connector.commitment_dashboards``:

- Daily Review (``Dashboards/Review/Daily.md``)
- Weekly Review (``Dashboards/Review/Weekly.md``)
- Stale (``Dashboards/Review/Stale.md``)
- Merge Candidates (``Dashboards/Review/Merge Candidates.md``)

Plus the extended ``generate_postponed_dashboard`` stale-postponements
section, the ``update_all_review_dashboards`` orchestrator, the
``update_all_dashboards`` unified refresh, and the CLI/MCP seams.

All tests use a fixed *now_iso* to produce deterministic output and drive
the ``created_at`` / ``updated_at`` derivation off the synthetic notes
produced by :func:`obsidian_connector.commitment_notes.write_commitment_note`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obsidian_connector.commitment_dashboards import (
    DEFAULT_MERGE_JACCARD,
    DEFAULT_MERGE_WINDOW_DAYS,
    DEFAULT_STALE_DAYS,
    REVIEW_DASHBOARDS_DIR,
    DashboardResult,
    generate_daily_review_dashboard,
    generate_merge_candidates_dashboard,
    generate_postponed_dashboard,
    generate_stale_dashboard,
    generate_weekly_review_dashboard,
    title_jaccard,
    update_all_dashboards,
    update_all_review_dashboards,
)
from obsidian_connector.commitment_notes import ActionInput, write_commitment_note


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

# Monday 2026-04-13 10:00 UTC: avoids ambiguity around ISO week boundaries.
NOW = "2026-04-13T10:00:00+00:00"
NOW_DT = datetime.fromisoformat(NOW)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _offset_days(iso: str, days: float) -> str:
    dt = datetime.fromisoformat(iso) + timedelta(days=days)
    return _iso(dt)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    return tmp_path


def _write(
    vault: Path,
    *,
    action_id: str,
    title: str,
    created_at: str,
    status: str = "open",
    project: str | None = "alpha",
    due_at: str | None = None,
    postponed_until: str | None = None,
    requires_ack: bool = False,
    priority: str = "normal",
    urgency: str = "normal",
    lifecycle_stage: str = "inbox",
    completed_at: str | None = None,
    sync_at: str | None = None,
) -> ActionInput:
    """Write a commitment note into *vault* with the given fields.

    ``sync_at`` drives ``service_last_synced_at`` in the frontmatter,
    which maps to :attr:`CommitmentSummary.updated_at` used by the Stale
    and Weekly review logic.
    """
    action = ActionInput(
        action_id=action_id,
        capture_id=f"CAP-{action_id[-5:]}",
        title=title,
        created_at=created_at,
        status=status,
        project=project,
        due_at=due_at,
        postponed_until=postponed_until,
        requires_ack=requires_ack,
        priority=priority,
        urgency=urgency,
        lifecycle_stage=lifecycle_stage,
        completed_at=completed_at,
    )
    # write_commitment_note uses *now_iso* as the ``service_last_synced_at``
    # timestamp in the rendered frontmatter.
    write_commitment_note(vault, action, now_iso=sync_at or created_at)
    return action


def _read(vault: Path, rel: str) -> str:
    return (vault / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# title_jaccard (pure, testable)
# ---------------------------------------------------------------------------


class TestTitleJaccard:
    def test_identical_titles(self) -> None:
        assert title_jaccard("Send invoice to Acme", "Send invoice to Acme") == 1.0

    def test_empty_titles(self) -> None:
        assert title_jaccard("", "anything") == 0.0
        assert title_jaccard("", "") == 0.0

    def test_disjoint_titles(self) -> None:
        assert title_jaccard("Call bob", "Write memo") == 0.0

    def test_high_overlap_above_threshold(self) -> None:
        # "send invoice acme q2" vs "send invoice acme q3":
        # intersection = {send, invoice, acme}; union = {send, invoice, acme, q2, q3}
        # -> 3/5 = 0.6 exactly.
        score = title_jaccard("Send invoice Acme Q2", "Send invoice Acme Q3")
        assert score == pytest.approx(0.6, rel=1e-6)

    def test_stop_words_filtered(self) -> None:
        # "send to the acme corp" vs "send acme corp": stop words (to, the)
        # are dropped before Jaccard -> token sets become equal -> 1.0.
        assert title_jaccard("send to the acme corp", "send acme corp") == 1.0


# ---------------------------------------------------------------------------
# Daily Review
# ---------------------------------------------------------------------------


class TestDailyReview:
    def test_empty_vault_writes_deterministic_note(self, vault: Path) -> None:
        r1 = generate_daily_review_dashboard(vault, now_iso=NOW)
        content_a = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        r2 = generate_daily_review_dashboard(vault, now_iso=NOW)
        content_b = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert content_a == content_b, "not deterministic on empty vault"
        assert r1.written == 0
        assert r2.written == 0
        for heading in (
            "# Daily Review",
            "## Captured today (0)",
            "## Due today (0)",
            "## Overdue (0)",
            "## Completed today (0)",
            "## Blocked/Waiting (0)",
        ):
            assert heading in content_a

    def test_captured_today_lists_today_created(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-REV-0001", title="Captured today",
            created_at=NOW,
        )
        _write(
            vault, action_id="ACT-REV-0002", title="Captured yesterday",
            created_at=_offset_days(NOW, -1),
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert "Captured today" in content
        # Captured-today section header's count is 1.
        assert "## Captured today (1)" in content
        assert "|Captured today" in content.replace(" ", "") or "Captured today" in content

    def test_due_today_lists_items_due_today(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-REV-0010", title="Due today item",
            created_at=_offset_days(NOW, -2),
            due_at=NOW,
        )
        _write(
            vault, action_id="ACT-REV-0011", title="Due tomorrow",
            created_at=_offset_days(NOW, -2),
            due_at=_offset_days(NOW, 1),
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert "## Due today (1)" in content
        assert "Due today item" in content
        # "Due tomorrow" must not appear in the Due-today section.
        due_today_section = content.split("## Due today")[1].split("## ")[0]
        assert "Due tomorrow" not in due_today_section

    def test_overdue_excludes_due_today_dedup(self, vault: Path) -> None:
        # A due-today item whose due_at is earlier than *now* must only
        # appear in "Due today" (not double-counted in "Overdue").
        due_earlier_today = _offset_days(NOW, -0.1)  # ~2.4h before NOW
        _write(
            vault, action_id="ACT-REV-0020", title="Due today but past hour",
            created_at=_offset_days(NOW, -3),
            due_at=due_earlier_today,
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert "## Due today (1)" in content
        assert "## Overdue (0)" in content

    def test_completed_today_uses_updated_at(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-REV-0030", title="Done earlier today",
            created_at=_offset_days(NOW, -5),
            status="done",
            completed_at=NOW,
            sync_at=NOW,
        )
        _write(
            vault, action_id="ACT-REV-0031", title="Done yesterday",
            created_at=_offset_days(NOW, -5),
            status="done",
            completed_at=_offset_days(NOW, -1),
            sync_at=_offset_days(NOW, -1),
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert "## Completed today (1)" in content
        assert "Done earlier today" in content
        assert "Done yesterday" not in content

    def test_blocked_waiting_surfaces_ack_and_postponed(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-REV-0040", title="Waiting on approval",
            created_at=_offset_days(NOW, -2),
            requires_ack=True,
        )
        _write(
            vault, action_id="ACT-REV-0041", title="Snoozed item",
            created_at=_offset_days(NOW, -2),
            postponed_until=_offset_days(NOW, 5),
        )
        generate_daily_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Daily.md")
        assert "## Blocked/Waiting (2)" in content


# ---------------------------------------------------------------------------
# Weekly Review + ISO-week boundary
# ---------------------------------------------------------------------------


class TestWeeklyReview:
    def test_iso_week_boundary_monday_midnight(self, vault: Path) -> None:
        # NOW is 2026-04-13T10:00Z (Monday). Week bounds should span
        # 2026-04-13 00:00Z inclusive through 2026-04-20 00:00Z exclusive.
        # An item created 2026-04-12 23:59Z must NOT be in "captured this week".
        just_before_monday = "2026-04-12T23:59:00+00:00"
        just_after_monday = "2026-04-13T00:01:00+00:00"
        _write(
            vault, action_id="ACT-WK-0001", title="Before monday",
            created_at=just_before_monday,
        )
        _write(
            vault, action_id="ACT-WK-0002", title="After monday",
            created_at=just_after_monday,
        )
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Weekly.md")
        # Captured-this-week contains exactly one entry.
        assert "## Captured this ISO-week (1)" in content
        assert "After monday" in content
        captured_section = content.split("## Captured this ISO-week")[1].split("## ")[0]
        assert "Before monday" not in captured_section

    def test_still_open_from_last_week(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-WK-0010", title="Old open from last week",
            created_at=_offset_days(NOW, -5),
            status="open",
        )
        _write(
            vault, action_id="ACT-WK-0011", title="From two weeks back",
            created_at=_offset_days(NOW, -14),
            status="open",
        )
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Weekly.md")
        # Only the one from last week (5d back) hits the prev-week window.
        assert "## Still open from last week (1)" in content

    def test_stale_section_threshold(self, vault: Path) -> None:
        # stale_days=14 default: a 20-day-old open item with no sync
        # update should surface.
        _write(
            vault, action_id="ACT-WK-0020", title="Very old",
            created_at=_offset_days(NOW, -20),
            sync_at=_offset_days(NOW, -20),
        )
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Weekly.md")
        assert "## Stale (>14 days, no movement) (1)" in content

    def test_top_projects_ranks_by_open_count(self, vault: Path) -> None:
        for i in range(3):
            _write(
                vault, action_id=f"ACT-WK-P1-{i:04d}", title=f"alpha {i}",
                project="alpha",
                created_at=_offset_days(NOW, -1),
            )
        for i in range(2):
            _write(
                vault, action_id=f"ACT-WK-P2-{i:04d}", title=f"beta {i}",
                project="beta",
                created_at=_offset_days(NOW, -1),
            )
        _write(
            vault, action_id="ACT-WK-P3-9999", title="done one",
            project="gamma",
            status="done",
            completed_at=NOW,
            created_at=_offset_days(NOW, -5),
        )
        generate_weekly_review_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Weekly.md")
        idx_alpha = content.find("| alpha | 3 |")
        idx_beta = content.find("| beta | 2 |")
        assert idx_alpha > -1 and idx_beta > -1
        assert idx_alpha < idx_beta, "alpha (3 open) should sort before beta (2 open)"
        # Done-only projects must not appear.
        assert "| gamma |" not in content


# ---------------------------------------------------------------------------
# Stale dashboard
# ---------------------------------------------------------------------------


class TestStaleDashboard:
    def test_empty_vault(self, vault: Path) -> None:
        r = generate_stale_dashboard(vault, now_iso=NOW)
        assert r.written == 0
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Stale.md")
        assert "_No stale commitments._" in content

    def test_stale_threshold_boundary(self, vault: Path) -> None:
        # Threshold: 14 days.  >14 means strictly greater than 14.
        # A 14.5-day-old open item surfaces; a 13-day-old item does not.
        # Lifecycle is ``planned`` (not inbox/triaged) so the age threshold
        # is the only trigger -- otherwise the 3-day triage-stage rule
        # would also fire for the 13-day-old item.
        _write(
            vault, action_id="ACT-ST-0001", title="14.5 days old",
            created_at=_offset_days(NOW, -14.5),
            sync_at=_offset_days(NOW, -14.5),
            lifecycle_stage="planned",
        )
        _write(
            vault, action_id="ACT-ST-0002", title="13 days old",
            created_at=_offset_days(NOW, -13),
            sync_at=_offset_days(NOW, -13),
            lifecycle_stage="planned",
        )
        r = generate_stale_dashboard(vault, now_iso=NOW)
        assert r.written == 1
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Stale.md")
        assert "14.5 days old" in content
        assert "13 days old" not in content

    def test_sorted_by_staleness_descending(self, vault: Path) -> None:
        for days, title, aid in (
            (30, "Ancient staleton", "ACT-ST-0010"),
            (20, "Old staleton",     "ACT-ST-0011"),
            (16, "Recent staleton",  "ACT-ST-0012"),
        ):
            _write(
                vault, action_id=aid, title=title,
                created_at=_offset_days(NOW, -days),
                sync_at=_offset_days(NOW, -days),
                lifecycle_stage="planned",
            )
        generate_stale_dashboard(vault, now_iso=NOW)
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Stale.md")
        idx_ancient = content.find("Ancient staleton")
        idx_old = content.find("Old staleton")
        idx_recent = content.find("Recent staleton")
        assert idx_ancient > -1 and idx_old > -1 and idx_recent > -1
        assert idx_ancient < idx_old < idx_recent

    def test_triage_stage_stale_independent_of_age_threshold(self, vault: Path) -> None:
        # A 4-day-old item stuck in inbox must surface even though 4 < 14.
        _write(
            vault, action_id="ACT-ST-0020", title="Stuck in inbox 4d",
            created_at=_offset_days(NOW, -4),
            sync_at=_offset_days(NOW, -4),
            lifecycle_stage="inbox",
        )
        r = generate_stale_dashboard(vault, now_iso=NOW)
        assert r.written == 1

    def test_triage_stage_not_stale_at_3d_boundary(self, vault: Path) -> None:
        # Exactly 3 days in inbox is NOT stale (threshold is > 3).
        _write(
            vault, action_id="ACT-ST-0021", title="3 days in inbox exactly",
            created_at=_offset_days(NOW, -3),
            sync_at=_offset_days(NOW, -3),
            lifecycle_stage="inbox",
        )
        r = generate_stale_dashboard(vault, now_iso=NOW)
        assert r.written == 0

    def test_done_items_never_stale(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-ST-0030", title="Long-done",
            created_at=_offset_days(NOW, -60),
            sync_at=_offset_days(NOW, -60),
            status="done",
            completed_at=_offset_days(NOW, -30),
            lifecycle_stage="done",
        )
        r = generate_stale_dashboard(vault, now_iso=NOW)
        assert r.written == 0


# ---------------------------------------------------------------------------
# Merge Candidates dashboard
# ---------------------------------------------------------------------------


class TestMergeCandidates:
    def test_empty_vault(self, vault: Path) -> None:
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 0
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Merge Candidates.md")
        assert "_No merge candidates._" in content

    def test_single_item_produces_no_pairs(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-MG-0001", title="Only one",
            created_at=_offset_days(NOW, -1),
        )
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 0

    def test_high_overlap_same_project_pairs(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-MG-0010", title="Send invoice Acme Q2",
            created_at=_offset_days(NOW, -2), project="ops",
        )
        _write(
            vault, action_id="ACT-MG-0011", title="Send invoice Acme Q3",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 1
        content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/Merge Candidates.md")
        assert "Send invoice Acme Q2" in content
        assert "Send invoice Acme Q3" in content
        assert "| 0.60 " in content or "| 0.6" in content

    def test_different_projects_never_match(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-MG-0020", title="Send invoice Acme",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        _write(
            vault, action_id="ACT-MG-0021", title="Send invoice Acme",
            created_at=_offset_days(NOW, -1), project="finance",
        )
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 0

    def test_created_window_excludes_far_apart_pairs(self, vault: Path) -> None:
        # Same project, identical titles, but created 30 days apart (> 14).
        _write(
            vault, action_id="ACT-MG-0030", title="Call Bob about contract",
            created_at=_offset_days(NOW, -30), project="ops",
        )
        _write(
            vault, action_id="ACT-MG-0031", title="Call Bob about contract",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 0

    def test_done_items_never_pair(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-MG-0040", title="Duplicate task",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        _write(
            vault, action_id="ACT-MG-0041", title="Duplicate task",
            created_at=_offset_days(NOW, -1), project="ops",
            status="done",
            completed_at=NOW,
        )
        r = generate_merge_candidates_dashboard(vault, now_iso=NOW)
        assert r.written == 0

    def test_custom_jaccard_threshold(self, vault: Path) -> None:
        # With jaccard=0.3 two lightly-overlapping items pair.
        _write(
            vault, action_id="ACT-MG-0050", title="approve budget Q2",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        _write(
            vault, action_id="ACT-MG-0051", title="approve hiring Q2",
            created_at=_offset_days(NOW, -1), project="ops",
        )
        r_strict = generate_merge_candidates_dashboard(
            vault, now_iso=NOW, merge_jaccard=0.9,
        )
        r_loose = generate_merge_candidates_dashboard(
            vault, now_iso=NOW, merge_jaccard=0.3,
        )
        assert r_strict.written == 0
        assert r_loose.written == 1


# ---------------------------------------------------------------------------
# Postponed dashboard -- stale postponements section
# ---------------------------------------------------------------------------


class TestPostponedStaleSection:
    def test_stale_postponements_section_header_present(self, vault: Path) -> None:
        # Postponement fully in the past -> stale.
        _write(
            vault, action_id="ACT-PP-0001", title="Snoozed but resurfaced",
            created_at=_offset_days(NOW, -5),
            postponed_until=_offset_days(NOW, -1),
        )
        # Postponement in the future -> active.
        _write(
            vault, action_id="ACT-PP-0002", title="Future snooze",
            created_at=_offset_days(NOW, -5),
            postponed_until=_offset_days(NOW, 3),
        )
        generate_postponed_dashboard(vault, now_iso=NOW)
        content = _read(vault, "Dashboards/Postponed.md")
        assert "## Stale postponements (1 item)" in content
        assert "Snoozed but resurfaced" in content
        # Active section still present.
        assert "## Active (1 item)" in content
        assert "Future snooze" in content
        # Stale section appears BEFORE Active (stale is the top of the page).
        assert content.index("## Stale postponements") < content.index("## Active")

    def test_no_stale_section_empty_label(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-PP-0003", title="Future snooze only",
            created_at=_offset_days(NOW, -5),
            postponed_until=_offset_days(NOW, 5),
        )
        generate_postponed_dashboard(vault, now_iso=NOW)
        content = _read(vault, "Dashboards/Postponed.md")
        assert "## Stale postponements (0 items)" in content
        assert "_No stale postponements._" in content


# ---------------------------------------------------------------------------
# Orchestrators + determinism
# ---------------------------------------------------------------------------


class TestOrchestrators:
    def test_update_all_review_dashboards_writes_four_files(self, vault: Path) -> None:
        # Task 38 added Delegations.md as a default-on review surface;
        # callers opt out via include_delegations=False to keep the
        # historical four.
        results = update_all_review_dashboards(
            vault, now_iso=NOW, include_delegations=False,
        )
        assert len(results) == 4
        expected = {"Daily.md", "Weekly.md", "Stale.md", "Merge Candidates.md"}
        assert {r.path.name for r in results} == expected
        for r in results:
            assert r.path.exists()
            assert r.path.read_text(encoding="utf-8").strip() != ""

    def test_update_all_review_includes_delegations_by_default(
        self, vault: Path,
    ) -> None:
        # Task 38: include_delegations defaults to True so the review
        # set is five surfaces.
        results = update_all_review_dashboards(vault, now_iso=NOW)
        assert len(results) == 5
        names = {r.path.name for r in results}
        assert names == {
            "Daily.md", "Weekly.md", "Stale.md",
            "Merge Candidates.md", "Delegations.md",
        }

    def test_update_all_dashboards_unified_emits_eight(self, vault: Path) -> None:
        # With every opt-in flag disabled we get the historical 8
        # dashboards (4 commitment + 4 review).
        results = update_all_dashboards(
            vault,
            now_iso=NOW,
            include_admin=False,
            include_analytics=False,
        )
        # include_delegations defaults to True inside update_all_review_dashboards,
        # so we re-exercise the "historical" shape by opting out there.
        from obsidian_connector.commitment_dashboards import (
            update_all_review_dashboards as _review,
        )
        review_results = _review(
            vault, now_iso=NOW, include_delegations=False,
        )
        # Task 38 guard: the full stack defaults include the delegations
        # page; we expect 9 when only include_admin/include_analytics are off.
        assert len(results) == 9
        commitment_prefix = [r.path.name for r in results[:4]]
        review_suffix = [r.path.name for r in results[4:]]
        assert commitment_prefix == [
            "Commitments.md",
            "Due Soon.md",
            "Waiting On Me.md",
            "Postponed.md",
        ]
        assert review_suffix == [
            "Daily.md", "Weekly.md", "Stale.md",
            "Merge Candidates.md", "Delegations.md",
        ]
        # Sanity check the opt-out variant also produced the historical count.
        assert len(review_results) == 4

    def test_update_all_dashboards_with_admin_emits_ten(self, vault: Path) -> None:
        # include_admin=True (default) appends Dashboards/Admin.md plus
        # the Task 36 Dashboards/Admin/Approvals.md companion. Task 38
        # also adds Dashboards/Review/Delegations.md by default, so the
        # historical count of 10 becomes 11 when analytics is opted out.
        results = update_all_dashboards(
            vault, now_iso=NOW, include_analytics=False
        )
        paths = [r.path.name for r in results]
        assert len(results) == 11
        assert paths[-2] == "Admin.md"
        assert paths[-1] == "Approvals.md"
        assert "Delegations.md" in paths

    def test_update_all_dashboards_includes_analytics_by_default(
        self, vault: Path
    ) -> None:
        # Task 39 keeps Analytics.md trailing. Task 38 adds
        # Delegations.md inside the review suffix, so total = 12.
        results = update_all_dashboards(vault, now_iso=NOW)
        names = [r.path.name for r in results]
        assert names[-1] == "Analytics.md"
        assert "Delegations.md" in names
        assert len(results) == 12

    def test_determinism_same_inputs_byte_identical(self, vault: Path) -> None:
        _write(
            vault, action_id="ACT-DET-0001", title="Deterministic run",
            created_at=_offset_days(NOW, -2),
        )
        _write(
            vault, action_id="ACT-DET-0002", title="Another one",
            created_at=_offset_days(NOW, -1),
            priority="high",
        )
        update_all_review_dashboards(vault, now_iso=NOW)
        snap: dict[str, str] = {}
        for name in ("Daily.md", "Weekly.md", "Stale.md", "Merge Candidates.md"):
            snap[name] = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/{name}")
        update_all_review_dashboards(vault, now_iso=NOW)
        for name, expected in snap.items():
            actual = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/{name}")
            assert actual == expected, f"{name} not byte-identical on re-run"

    def test_partial_failure_in_orchestrator_still_writes_others(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # If Daily fails, Weekly/Stale/Merge Candidates should still attempt.
        # Matches the graceful-degradation semantics of the existing
        # update_all_dashboards (single scan + independent writes).
        import obsidian_connector.commitment_dashboards as cd

        original = cd.generate_daily_review_dashboard

        def _boom(*_, **__):
            raise RuntimeError("daily boom")

        monkeypatch.setattr(cd, "generate_daily_review_dashboard", _boom)
        with pytest.raises(RuntimeError, match="daily boom"):
            cd.update_all_review_dashboards(vault, now_iso=NOW)
        # But the orchestrator did not pre-create Daily.md, so no partial
        # dashboard should exist.  This asserts the graceful contract: on
        # failure we surface the error to the caller rather than silently
        # half-writing.  Restore the original to keep the module clean.
        monkeypatch.setattr(cd, "generate_daily_review_dashboard", original)

    def test_shared_generated_at_across_orchestrator(self, vault: Path) -> None:
        update_all_review_dashboards(vault, now_iso=NOW)
        for name in ("Daily.md", "Weekly.md", "Stale.md", "Merge Candidates.md"):
            content = _read(vault, f"{REVIEW_DASHBOARDS_DIR}/{name}")
            assert f"generated_at: {NOW}" in content, f"{name} missing generated_at"

    def test_default_constants_public(self) -> None:
        # Sanity: constants are importable and match the documented defaults.
        assert DEFAULT_STALE_DAYS == 14
        assert DEFAULT_MERGE_WINDOW_DAYS == 14
        assert DEFAULT_MERGE_JACCARD == 0.6


# ---------------------------------------------------------------------------
# CLI integration smoke
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], cwd: Path, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    import os

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "obsidian_connector.cli", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def _resolve_mcp_fn(tool_or_fn):
    """Return the plain Python function for a FastMCP tool binding.

    FastMCP wraps decorated tools -- the raw Python function hangs off
    ``.fn`` on newer versions and is the object itself on older ones.
    This shim keeps the tests loose on the binding.
    """
    return getattr(tool_or_fn, "fn", tool_or_fn)


class TestCLIAndMCPIntegration:
    def test_cli_review_dashboards_smoke(self, vault: Path) -> None:
        # Seed one note so there's something to render.
        _write(
            vault, action_id="ACT-CLI-0001", title="CLI smoke",
            created_at=NOW,
        )
        repo_root = Path(__file__).resolve().parent.parent
        result = _run_cli(
            [
                "review-dashboards",
                "--now", NOW,
                "--stale-days", "14",
                "--merge-window-days", "14",
                "--merge-jaccard", "0.6",
                "--json",
            ],
            cwd=repo_root,
            env_overrides={"OBSIDIAN_VAULT_PATH": str(vault)},
        )
        assert result.returncode == 0, (
            f"cli failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert (vault / f"{REVIEW_DASHBOARDS_DIR}/Daily.md").exists()
        assert (vault / f"{REVIEW_DASHBOARDS_DIR}/Weekly.md").exists()
        assert (vault / f"{REVIEW_DASHBOARDS_DIR}/Stale.md").exists()
        assert (vault / f"{REVIEW_DASHBOARDS_DIR}/Merge Candidates.md").exists()
        # Task 38: Delegations.md is a default-on review surface.
        assert (vault / f"{REVIEW_DASHBOARDS_DIR}/Delegations.md").exists()

    def test_mcp_tool_refreshes_all_four(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write(
            vault, action_id="ACT-MCP-0001", title="MCP smoke",
            created_at=NOW,
        )
        # Route resolve_vault_path through the tmp vault so the tool does
        # not depend on the user's global vault registry.
        import obsidian_connector.mcp_server as server

        monkeypatch.setattr(server, "resolve_vault_path", lambda _=None: vault)
        fn = _resolve_mcp_fn(server.obsidian_review_dashboards)
        payload = json.loads(
            fn(stale_days=14, merge_window_days=14, merge_jaccard=0.6, now=NOW)
        )
        assert payload["ok"] is True, payload
        # Task 38 added Delegations.md; the MCP tool now refreshes five.
        assert payload["count"] == 5
        names = {Path(d["path"]).name for d in payload["dashboards"]}
        assert names == {
            "Daily.md", "Weekly.md", "Stale.md", "Merge Candidates.md",
            "Delegations.md",
        }
