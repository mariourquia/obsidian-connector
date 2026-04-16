"""Dashboard generation for commitment visibility.

Four Markdown dashboards in ``Dashboards/`` aggregating commitment state:

  Dashboards/Commitments.md    -- Open by project + done table
  Dashboards/Due Soon.md       -- Overdue + due-within-N-days
  Dashboards/Waiting On Me.md  -- Open items requiring acknowledgement
  Dashboards/Postponed.md      -- Open items with postponed_until set

Task 26 adds four *review* surfaces under ``Dashboards/Review/`` that help
with inbox triage, stale-work spotting, and merge candidate review:

  Dashboards/Review/Daily.md            -- Today's slice: captured / due /
                                           overdue / completed / blocked
  Dashboards/Review/Weekly.md           -- ISO-week slice + still-open-from-
                                           last-week + stale + top projects
  Dashboards/Review/Stale.md            -- Any open commitment with no
                                           movement past a threshold
  Dashboards/Review/Merge Candidates.md -- Heuristic-only duplicate pair
                                           suggestions (token Jaccard >= 0.6)

Each public function reads the current ``Commitments/`` tree, renders the
dashboard, and writes it via :func:`atomic_write`.  Repeated calls with the
same vault state and the same *now_iso* produce byte-for-byte identical output
(deterministic and idempotent).  Only ``generated_at`` in the frontmatter
changes between live runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# _scan_commitments is an intentional package-internal dependency: it returns
# CommitmentSummary objects which the renderer uses directly, avoiding a
# round-trip through dict serialisation.
from obsidian_connector.commitment_notes import format_source_label
from obsidian_connector.commitment_ops import CommitmentSummary, _scan_commitments
from obsidian_connector.write_manager import atomic_write

DASHBOARDS_DIR = "Dashboards"
REVIEW_DASHBOARDS_DIR = f"{DASHBOARDS_DIR}/Review"

_DASHBOARD_COMMITMENTS_PATH = f"{DASHBOARDS_DIR}/Commitments.md"
_DASHBOARD_DUE_SOON_PATH = f"{DASHBOARDS_DIR}/Due Soon.md"
_DASHBOARD_WAITING_ON_ME_PATH = f"{DASHBOARDS_DIR}/Waiting On Me.md"
_DASHBOARD_POSTPONED_PATH = f"{DASHBOARDS_DIR}/Postponed.md"

_DASHBOARD_DAILY_REVIEW_PATH = f"{REVIEW_DASHBOARDS_DIR}/Daily.md"
_DASHBOARD_WEEKLY_REVIEW_PATH = f"{REVIEW_DASHBOARDS_DIR}/Weekly.md"
_DASHBOARD_STALE_PATH = f"{REVIEW_DASHBOARDS_DIR}/Stale.md"
_DASHBOARD_MERGE_CANDIDATES_PATH = f"{REVIEW_DASHBOARDS_DIR}/Merge Candidates.md"
_DASHBOARD_PATTERNS_PATH = f"{REVIEW_DASHBOARDS_DIR}/Patterns.md"
_DASHBOARD_DELEGATIONS_PATH = f"{REVIEW_DASHBOARDS_DIR}/Delegations.md"
_DASHBOARD_ADMIN_PATH = f"{DASHBOARDS_DIR}/Admin.md"
_DASHBOARD_APPROVALS_PATH = f"{DASHBOARDS_DIR}/Admin/Approvals.md"
_DASHBOARD_ANALYTICS_PATH = f"{DASHBOARDS_DIR}/Analytics.md"
_DASHBOARD_COACHING_PATH = f"{REVIEW_DASHBOARDS_DIR}/Coaching.md"
_ANALYTICS_BASE_DIR = "Analytics/Weekly"

# Task 40: human labels for each recommendation code. Kept near the
# module top so a grep for the code string finds the label too.
_COACHING_CODE_LABELS: dict[str, str] = {
    "CONSIDER_CANCEL": "Consider cancel",
    "CONSIDER_DELEGATE": "Consider delegate",
    "CONSIDER_MERGE": "Consider merge",
    "CONSIDER_RECLAIM": "Consider reclaim",
    "CONSIDER_RESCHEDULE": "Consider reschedule",
    "CONSIDER_UNBLOCK": "Consider unblock",
}

_TOOL = "obsidian-connector/dashboards"

# Defaults for the review surfaces.  Kept as module-level constants so the
# MCP tool, CLI subcommand, and orchestrator all agree on the same values.
DEFAULT_STALE_DAYS = 14
DEFAULT_MERGE_WINDOW_DAYS = 14
DEFAULT_MERGE_JACCARD = 0.6
_TRIAGE_STAGE_STALE_DAYS = 3  # >3d in inbox/triaged counts as stale too


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DashboardResult:
    """Outcome of a single dashboard write."""

    path: Path
    written: int  # number of commitment entries rendered into the dashboard


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _now_display(iso: str) -> str:
    """Human-readable UTC timestamp from ISO string, e.g. ``2026-04-12 10:00 UTC``."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        return iso


def _fmt_date(iso: str | None, fallback: str = "no due date") -> str:
    """Return ``YYYY-MM-DD`` from an ISO timestamp, or *fallback*."""
    if not iso:
        return fallback
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return iso[:10] if len(iso) >= 10 else fallback


def _try_parse_dt(iso: str | None) -> datetime | None:
    """Parse an ISO timestamp; return ``None`` on failure."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _wikilink(s: CommitmentSummary) -> str:
    """Wikilink for list items: ``[[vault/path|Title]]``."""
    target = s.path[:-3] if s.path.endswith(".md") else s.path
    return f"[[{target}|{s.title}]]"


def _wikilink_table(s: CommitmentSummary) -> str:
    """Table-safe wikilink: pipe replaced with ``\\|`` for Markdown tables."""
    target = s.path[:-3] if s.path.endswith(".md") else s.path
    return f"[[{target}\\|{s.title}]]"


def _project_label(project: str | None) -> str:
    return project if project else "\u2014"  # em dash


def _frontmatter(dashboard_id: str, now_iso: str) -> str:
    return (
        "---\n"
        "type: dashboard\n"
        f"dashboard: {dashboard_id}\n"
        f"generated_at: {now_iso}\n"
        "---"
    )


def _list_line(s: CommitmentSummary, *, show_project: bool = False) -> str:
    """Checkbox list line for a single commitment."""
    parts: list[str] = []
    if s.due_at:
        parts.append(f"due {_fmt_date(s.due_at)}")
    else:
        parts.append("no due date")
    if show_project:
        parts.append(_project_label(s.project))
    if s.priority != "normal":
        parts.append(s.priority)
    return "- [ ] " + _wikilink(s) + " \u00b7 " + " \u00b7 ".join(parts)


# ---------------------------------------------------------------------------
# Sorting keys
# ---------------------------------------------------------------------------

def _key_due(s: CommitmentSummary) -> tuple[str, str]:
    # due_at ascending; None sorts last via "1" prefix vs "0" + value.
    return ("1" if s.due_at is None else "0" + s.due_at, s.title)


def _key_project_then_due(s: CommitmentSummary) -> tuple[str, str, str]:
    # Named projects alphabetically (case-insensitive), None last.
    return (
        "1" if s.project is None else "0" + s.project.lower(),
        s.due_at or "9999-99-99",
        s.title,
    )


def _key_postponed(s: CommitmentSummary) -> tuple[str, str]:
    return (s.postponed_until or "", s.title)


# ---------------------------------------------------------------------------
# Render: Commitments.md
# ---------------------------------------------------------------------------

def _render_commitments_md(items: list[CommitmentSummary], now_iso: str) -> str:
    open_items = sorted(
        [i for i in items if i.status == "open"],
        key=_key_project_then_due,
    )
    done_items = sorted(
        [i for i in items if i.status == "done"],
        key=lambda s: s.path,
    )

    lines: list[str] = [
        _frontmatter("commitments", now_iso),
        "",
        "# Commitments",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        "",
        f"## Open ({len(open_items)})",
        "",
    ]

    if not open_items:
        lines += ["_No open commitments._", ""]
    else:
        # Build project groups preserving the sort order established above.
        project_order: list[str | None] = []
        seen: set = set()
        for s in open_items:
            key = s.project
            if key not in seen:
                seen.add(key)
                project_order.append(key)

        for project in project_order:
            group = [s for s in open_items if s.project == project]
            header = project if project else "No Project"
            lines.append(f"### {header} ({len(group)})")
            lines.append("")
            for s in group:
                lines.append(_list_line(s))
            lines.append("")

    lines.append(f"## Done ({len(done_items)})")
    lines.append("")

    if not done_items:
        lines += ["_No completed commitments._", ""]
    else:
        lines += ["| Title | Project |", "|-------|---------|"]
        for s in done_items:
            lines.append(f"| {_wikilink_table(s)} | {_project_label(s.project)} |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render: Due Soon.md
# ---------------------------------------------------------------------------

def _render_due_soon_md(
    items: list[CommitmentSummary],
    now_iso: str,
    within_days: int,
) -> str:
    now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    cutoff = now + timedelta(days=within_days)

    overdue: list[CommitmentSummary] = []
    upcoming: list[CommitmentSummary] = []
    for s in items:
        if s.status != "open" or not s.due_at:
            continue
        due = _try_parse_dt(s.due_at)
        if due is None or due > cutoff:
            continue
        if due < now:
            overdue.append(s)
        else:
            upcoming.append(s)

    overdue.sort(key=_key_due)
    upcoming.sort(key=_key_due)

    days_label = f"{within_days} day{'s' if within_days != 1 else ''}"
    lines: list[str] = [
        _frontmatter("due-soon", now_iso),
        "",
        "# Due Soon",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        f"_Open commitments due within {days_label}._",
        "",
        f"## Overdue ({len(overdue)})",
        "",
    ]

    if not overdue:
        lines += ["_No overdue commitments._", ""]
    else:
        for s in overdue:
            lines.append(_list_line(s, show_project=True))
        lines.append("")

    lines.append(f"## Due within {days_label} ({len(upcoming)})")
    lines.append("")

    if not upcoming:
        lines += ["_No upcoming commitments in this window._", ""]
    else:
        for s in upcoming:
            lines.append(_list_line(s, show_project=True))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render: Waiting On Me.md
# ---------------------------------------------------------------------------

def _render_waiting_on_me_md(items: list[CommitmentSummary], now_iso: str) -> str:
    waiting = sorted(
        [i for i in items if i.status == "open" and i.requires_ack],
        key=_key_due,
    )
    n = len(waiting)
    item_label = f"{n} item{'s' if n != 1 else ''}"

    lines: list[str] = [
        _frontmatter("waiting-on-me", now_iso),
        "",
        "# Waiting On Me",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        "_Open commitments that require your explicit acknowledgement._",
        "",
        f"## ({item_label})",
        "",
    ]

    if not waiting:
        lines += ["_No commitments waiting for acknowledgement._", ""]
    else:
        for s in waiting:
            lines.append(_list_line(s, show_project=True))
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render: Postponed.md
# ---------------------------------------------------------------------------

def _render_postponed_md(items: list[CommitmentSummary], now_iso: str) -> str:
    now = _try_parse_dt(now_iso)
    all_postponed = [i for i in items if i.status == "open" and i.postponed_until]
    stale_postponed: list[CommitmentSummary] = []
    active_postponed: list[CommitmentSummary] = []
    for s in all_postponed:
        pu = _try_parse_dt(s.postponed_until)
        if now is not None and pu is not None and pu < now:
            stale_postponed.append(s)
        else:
            active_postponed.append(s)
    stale_postponed.sort(key=_key_postponed)
    active_postponed.sort(key=_key_postponed)

    n_stale = len(stale_postponed)
    n_active = len(active_postponed)
    active_label = f"{n_active} item{'s' if n_active != 1 else ''}"
    stale_label = f"{n_stale} item{'s' if n_stale != 1 else ''}"

    lines: list[str] = [
        _frontmatter("postponed", now_iso),
        "",
        "# Postponed",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        "_Open commitments snoozed to a future date._",
        "",
        f"## Stale postponements ({stale_label})",
        "",
        "_Postponed_until is in the past but status is still open --"
        " revisit or reschedule._",
        "",
    ]

    if not stale_postponed:
        lines += ["_No stale postponements._", ""]
    else:
        lines += [
            "| Title | Project | Postponed Until | Priority |",
            "|-------|---------|-----------------|----------|",
        ]
        for s in stale_postponed:
            lines.append(
                f"| {_wikilink_table(s)}"
                f" | {_project_label(s.project)}"
                f" | {_fmt_date(s.postponed_until)}"
                f" | {s.priority} |"
            )
        lines.append("")

    lines.append(f"## Active ({active_label})")
    lines.append("")

    if not active_postponed:
        lines += ["_No postponed commitments._", ""]
    else:
        lines += [
            "| Title | Project | Postponed Until | Priority |",
            "|-------|---------|-----------------|----------|",
        ]
        for s in active_postponed:
            lines.append(
                f"| {_wikilink_table(s)}"
                f" | {_project_label(s.project)}"
                f" | {_fmt_date(s.postponed_until)}"
                f" | {s.priority} |"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Task 26 -- review dashboards (Daily / Weekly / Stale / Merge Candidates)
# ---------------------------------------------------------------------------

# Week starts Monday.  ``weekday()`` returns Monday==0, Sunday==6.
_MONDAY = 0


def _same_utc_date(a_iso: str | None, now: datetime) -> bool:
    """True when *a_iso* falls on the same UTC calendar date as *now*.

    Deterministic because both sides normalise to UTC before comparing.
    Invalid or empty timestamps return ``False``.
    """
    a = _try_parse_dt(a_iso)
    if a is None:
        return False
    a_utc = a.astimezone(timezone.utc)
    now_utc = now.astimezone(timezone.utc)
    return a_utc.date() == now_utc.date()


def _iso_week_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Return ``(week_start, week_end)`` for *now* as UTC datetimes.

    Week starts Monday 00:00 UTC and spans 7 days.  The returned tuple is
    ``[inclusive_start, exclusive_end)``.
    """
    now_utc = now.astimezone(timezone.utc)
    days_since_monday = (now_utc.weekday() - _MONDAY) % 7
    start = datetime(
        now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc
    ) - timedelta(days=days_since_monday)
    return start, start + timedelta(days=7)


def _in_range(iso: str | None, start: datetime, end: datetime) -> bool:
    dt = _try_parse_dt(iso)
    if dt is None:
        return False
    dt_utc = dt.astimezone(timezone.utc)
    return start <= dt_utc < end


_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "the", "to", "of", "for", "in", "on", "at",
        "with", "by", "from", "is", "are", "it", "this", "that", "be",
        "or", "as", "into", "vs", "via", "re", "do", "does",
    }
)


def _title_tokens(title: str) -> frozenset[str]:
    """Lowercase, alphanumeric, stop-word-filtered token set.

    Pure function -- stable across runs.  Single-character tokens are
    kept only if they are digits (e.g. a version number like ``"v2"``).
    """
    if not title:
        return frozenset()
    tokens: set[str] = set()
    for raw in _TOKEN_SPLIT_RE.split(title.lower()):
        if not raw or raw in _STOP_WORDS:
            continue
        if len(raw) == 1 and not raw.isdigit():
            continue
        tokens.add(raw)
    return frozenset(tokens)


def title_jaccard(a: str, b: str) -> float:
    """Token-Jaccard similarity between two titles.

    Returns ``0.0`` when either title has no tokens after filtering.
    Public for testing the merge heuristic in isolation.
    """
    ta = _title_tokens(a)
    tb = _title_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    if union == 0:
        return 0.0
    return inter / union


def _age_days(iso: str | None, now: datetime) -> float | None:
    dt = _try_parse_dt(iso)
    if dt is None:
        return None
    delta = now.astimezone(timezone.utc) - dt.astimezone(timezone.utc)
    return delta.total_seconds() / 86400.0


def _stale_age_days(s: CommitmentSummary, now: datetime) -> float:
    """Effective staleness in days.

    Prefers ``updated_at`` (``service_last_synced_at``), falls back to
    ``created_at``, then to ``now`` (yielding 0.0).  Used to sort the
    Stale dashboard in descending order and to test against the
    configurable threshold.
    """
    for iso in (s.updated_at, s.created_at):
        age = _age_days(iso, now)
        if age is not None:
            return age
    return 0.0


def _is_stale_triage_stage(s: CommitmentSummary, now: datetime) -> bool:
    """True when *s* is in ``inbox`` or ``triaged`` longer than 3 days.

    Uses ``created_at`` as the entry point.  Missing ``created_at``
    conservatively returns ``False`` (don't surface a note we can't age).
    """
    if s.lifecycle_stage not in ("inbox", "triaged"):
        return False
    age = _age_days(s.created_at, now)
    if age is None:
        return False
    return age > _TRIAGE_STAGE_STALE_DAYS


def _key_stale_desc(now: datetime):
    """Sort key factory: staleness descending, title ascending."""

    def _key(s: CommitmentSummary) -> tuple[float, str]:
        return (-_stale_age_days(s, now), s.title)

    return _key


def _is_blocked(s: CommitmentSummary) -> bool:
    """Heuristic for the Daily dashboard's Blocked/Waiting section.

    Task 26 predates a first-class ``blocked`` lifecycle stage -- the
    product today encodes "needs external motion" via ``requires_ack``
    or ``postponed_until``.  Both count.
    """
    if s.status != "open":
        return False
    return bool(s.requires_ack or s.postponed_until)


def _list_line_compact(s: CommitmentSummary) -> str:
    """Checkbox list line tailored for review surfaces.

    Adds lifecycle_stage + urgency after the due-date/project facet so a
    reviewer can scan the triage state without opening the note.
    """
    parts: list[str] = []
    if s.due_at:
        parts.append(f"due {_fmt_date(s.due_at)}")
    else:
        parts.append("no due date")
    parts.append(_project_label(s.project))
    if s.lifecycle_stage and s.lifecycle_stage != "inbox":
        parts.append(s.lifecycle_stage)
    if s.urgency and s.urgency != "normal":
        parts.append(s.urgency)
    if s.priority != "normal":
        parts.append(s.priority)
    return "- [ ] " + _wikilink(s) + " \u00b7 " + " \u00b7 ".join(parts)


def _by_source_counts(
    items: list[CommitmentSummary],
) -> list[tuple[str, int]]:
    """Return ``[(label, count), ...]`` grouped by human source label.

    Uses :func:`format_source_label` to canonicalise the grouping key so
    the Daily and Weekly review surfaces show the same provenance
    vocabulary the commitment notes render. Ordering: count descending,
    label ascending -- deterministic across runs.
    """
    counts: dict[str, int] = {}
    for s in items:
        label = format_source_label(s.source_app, s.source_entrypoint)
        counts[label] = counts.get(label, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def _render_by_source_table(
    counts: list[tuple[str, int]],
    empty_label: str,
) -> list[str]:
    """Render a small Markdown table for a By-source subsection.

    Returns the lines (without a trailing empty line) so callers can
    slot the block into an existing section list.
    """
    if not counts:
        return [f"_{empty_label}_"]
    out: list[str] = ["| Source | Count |", "|--------|------:|"]
    for label, n in counts:
        out.append(f"| {label} | {n} |")
    return out


def _render_daily_review_md(
    items: list[CommitmentSummary],
    now_iso: str,
) -> str:
    now = _try_parse_dt(now_iso) or datetime.now(timezone.utc)

    captured_today = sorted(
        [i for i in items if _same_utc_date(i.created_at, now)],
        key=_key_due,
    )
    due_today = sorted(
        [
            i for i in items
            if i.status == "open" and _same_utc_date(i.due_at, now)
        ],
        key=_key_due,
    )
    overdue = sorted(
        [
            i for i in items
            if i.status == "open"
            and i.due_at
            and (_try_parse_dt(i.due_at) or now) < now
        ],
        key=_key_due,
    )
    # Exclude items that also appear in overdue-today (due today + now past)
    # from both sections -- prefer the "Due today" bucket when the date matches.
    due_today_ids = {i.action_id for i in due_today}
    overdue = [i for i in overdue if i.action_id not in due_today_ids]
    completed_today = sorted(
        [
            i for i in items
            if i.status == "done" and _same_utc_date(i.updated_at, now)
        ],
        key=_key_due,
    )
    blocked = sorted(
        [i for i in items if _is_blocked(i)],
        key=_key_due,
    )

    today_label = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        _frontmatter("daily-review", now_iso),
        "",
        "# Daily Review",
        "",
        f"_Last updated: {_now_display(now_iso)} ({today_label})_",
        "_Today's inbox slice: captured, due, overdue, completed, blocked._",
        "",
    ]

    def _section(header: str, group: list[CommitmentSummary], empty: str) -> None:
        lines.append(f"## {header} ({len(group)})")
        lines.append("")
        if not group:
            lines.append(f"_{empty}_")
            lines.append("")
            return
        for s in group:
            lines.append(_list_line_compact(s))
        lines.append("")

    _section("Captured today", captured_today, "Nothing captured yet today.")
    _section("Due today", due_today, "Nothing due today.")
    _section("Overdue", overdue, "No overdue commitments.")
    _section(
        "Completed today",
        completed_today,
        "No commitments completed today yet.",
    )
    _section("Blocked/Waiting", blocked, "Nothing blocked or waiting.")

    # Task 29: provenance subsection. Counts only today's captures so the
    # By-source view matches the "Captured today" slice above.
    captured_counts = _by_source_counts(captured_today)
    lines.append(f"## By source ({len(captured_counts)})")
    lines.append("")
    lines.extend(
        _render_by_source_table(
            captured_counts,
            "No sources to group (nothing captured today).",
        )
    )
    lines.append("")

    return "\n".join(lines)


def _render_weekly_review_md(
    items: list[CommitmentSummary],
    now_iso: str,
    stale_days: int,
) -> str:
    now = _try_parse_dt(now_iso) or datetime.now(timezone.utc)
    week_start, week_end = _iso_week_bounds(now)
    prev_week_start = week_start - timedelta(days=7)

    captured_week = sorted(
        [i for i in items if _in_range(i.created_at, week_start, week_end)],
        key=_key_due,
    )
    completed_week = sorted(
        [
            i for i in items
            if i.status == "done"
            and _in_range(i.updated_at, week_start, week_end)
        ],
        key=_key_due,
    )
    still_open_last_week = sorted(
        [
            i for i in items
            if i.status == "open"
            and _in_range(i.created_at, prev_week_start, week_start)
        ],
        key=_key_due,
    )

    # Stale: open AND age exceeds threshold.
    stale_items = sorted(
        [
            i for i in items
            if i.status == "open"
            and (
                _stale_age_days(i, now) > stale_days
                or _is_stale_triage_stage(i, now)
            )
        ],
        key=_key_stale_desc(now),
    )

    # Top projects by open volume.
    open_by_project: dict[str, int] = {}
    for s in items:
        if s.status != "open":
            continue
        key = s.project or "(no project)"
        open_by_project[key] = open_by_project.get(key, 0) + 1
    top_projects = sorted(
        open_by_project.items(),
        key=lambda kv: (-kv[1], kv[0].lower()),
    )[:10]

    iso_year, iso_week, _ = week_start.isocalendar()
    week_label = f"ISO {iso_year}-W{iso_week:02d}"

    lines: list[str] = [
        _frontmatter("weekly-review", now_iso),
        "",
        "# Weekly Review",
        "",
        f"_Last updated: {_now_display(now_iso)} ({week_label})_",
        f"_Week: {week_start.date().isoformat()} to"
        f" {(week_end - timedelta(days=1)).date().isoformat()}._",
        "",
    ]

    def _section(header: str, group: list[CommitmentSummary], empty: str) -> None:
        lines.append(f"## {header} ({len(group)})")
        lines.append("")
        if not group:
            lines.append(f"_{empty}_")
            lines.append("")
            return
        for s in group:
            lines.append(_list_line_compact(s))
        lines.append("")

    _section(
        "Captured this ISO-week",
        captured_week,
        "Nothing captured this week.",
    )
    _section(
        "Completed this ISO-week",
        completed_week,
        "Nothing completed this week.",
    )
    _section(
        "Still open from last week",
        still_open_last_week,
        "Nothing left open from last week.",
    )
    _section(
        f"Stale (>{stale_days} days, no movement)",
        stale_items,
        "No stale work.",
    )

    lines.append(f"## Top projects by open volume ({len(top_projects)})")
    lines.append("")
    if not top_projects:
        lines += ["_No open commitments._", ""]
    else:
        lines += ["| Project | Open |", "|---------|-----:|"]
        for project, n in top_projects:
            lines.append(f"| {project} | {n} |")
        lines.append("")

    # Task 29: provenance subsection. Counts the same "captured this week"
    # slice as the list section above so readers can match rows to counts.
    captured_counts = _by_source_counts(captured_week)
    lines.append(f"## By source ({len(captured_counts)})")
    lines.append("")
    lines.extend(
        _render_by_source_table(
            captured_counts,
            "No sources to group (nothing captured this week).",
        )
    )
    lines.append("")

    return "\n".join(lines)


def _render_stale_md(
    items: list[CommitmentSummary],
    now_iso: str,
    stale_days: int,
) -> str:
    now = _try_parse_dt(now_iso) or datetime.now(timezone.utc)
    stale_items = sorted(
        [
            i for i in items
            if i.status == "open"
            and (
                _stale_age_days(i, now) > stale_days
                or _is_stale_triage_stage(i, now)
            )
        ],
        key=_key_stale_desc(now),
    )

    n = len(stale_items)
    label = f"{n} item{'s' if n != 1 else ''}"

    lines: list[str] = [
        _frontmatter("stale", now_iso),
        "",
        "# Stale",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        f"_Open commitments with no movement in >{stale_days} days,"
        f" or stuck in inbox/triaged for >{_TRIAGE_STAGE_STALE_DAYS} days._",
        "",
        f"## ({label})",
        "",
    ]

    if not stale_items:
        lines += ["_No stale commitments._", ""]
        return "\n".join(lines)

    lines += [
        "| Age (days) | Title | Project | Lifecycle | Priority |",
        "|-----------:|-------|---------|-----------|----------|",
    ]
    for s in stale_items:
        age = _stale_age_days(s, now)
        lines.append(
            f"| {age:.1f}"
            f" | {_wikilink_table(s)}"
            f" | {_project_label(s.project)}"
            f" | {s.lifecycle_stage}"
            f" | {s.priority} |"
        )
    lines.append("")

    return "\n".join(lines)


@dataclass(frozen=True)
class _MergePair:
    """One candidate pair for review on Merge Candidates.md.

    Comparable so the render order is deterministic: score descending,
    then lexicographic path pair.
    """

    score: float
    a: CommitmentSummary
    b: CommitmentSummary


def _compute_merge_candidates(
    items: list[CommitmentSummary],
    now: datetime,
    window_days: int,
    jaccard: float,
) -> list[_MergePair]:
    """Pure heuristic pair-builder.

    Rules (all must hold):

    - Both commitments are ``status == "open"``.
    - Same ``project`` (both None counts as same -- "no project").
    - Titles share Jaccard similarity >= *jaccard*.
    - Their ``created_at`` timestamps are within *window_days* of each
      other.

    Pairs are deduplicated and ordered by descending score, then by the
    sorted path tuple for tie-break stability.
    """
    open_items = [i for i in items if i.status == "open"]
    window = timedelta(days=window_days)

    # Bucket by project for an O(p * n^2) lower bound instead of O(n^2).
    buckets: dict[str, list[CommitmentSummary]] = {}
    for s in open_items:
        buckets.setdefault(s.project or "", []).append(s)

    pairs: list[_MergePair] = []
    for group in buckets.values():
        n = len(group)
        for i in range(n):
            a = group[i]
            a_created = _try_parse_dt(a.created_at)
            for j in range(i + 1, n):
                b = group[j]
                b_created = _try_parse_dt(b.created_at)
                if a_created is not None and b_created is not None:
                    if abs(a_created - b_created) > window:
                        continue
                score = title_jaccard(a.title, b.title)
                if score + 1e-9 < jaccard:
                    continue
                # Canonicalise (a, b) by path to stabilise output ordering.
                if a.path <= b.path:
                    pairs.append(_MergePair(score=score, a=a, b=b))
                else:
                    pairs.append(_MergePair(score=score, a=b, b=a))

    pairs.sort(key=lambda p: (-p.score, p.a.path, p.b.path))
    return pairs


def _render_merge_candidates_md(
    items: list[CommitmentSummary],
    now_iso: str,
    window_days: int,
    jaccard: float,
) -> str:
    now = _try_parse_dt(now_iso) or datetime.now(timezone.utc)
    pairs = _compute_merge_candidates(items, now, window_days, jaccard)

    n = len(pairs)
    label = f"{n} pair{'s' if n != 1 else ''}"

    lines: list[str] = [
        _frontmatter("merge-candidates", now_iso),
        "",
        "# Merge Candidates",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        "_Heuristic duplicate suggestions -- same project, title token"
        f" Jaccard >= {jaccard:.2f}, created within {window_days} days of"
        " each other. Review manually; actual merge is a human decision._",
        "",
        f"## ({label})",
        "",
    ]

    if not pairs:
        lines += ["_No merge candidates._", ""]
        return "\n".join(lines)

    lines += [
        "| Score | A | B | Project |",
        "|------:|---|---|---------|",
    ]
    for p in pairs:
        project = p.a.project or p.b.project
        lines.append(
            f"| {p.score:.2f}"
            f" | {_wikilink_table(p.a)}"
            f" | {_wikilink_table(p.b)}"
            f" | {_project_label(project)} |"
        )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_commitments_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Commitments.md``.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    now_iso:
        ISO 8601 timestamp injected as ``generated_at``.  Defaults to UTC now.
        Inject a fixed value to produce deterministic output for tests.

    Returns
    -------
    DashboardResult
        ``path`` is the written file; ``written`` is the total number of
        commitment entries (open + done) rendered.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_commitments_md(items, ts)
    path = vault_root / _DASHBOARD_COMMITMENTS_PATH
    atomic_write(path, content, vault_root=vault_root, tool_name=_TOOL, inject_generated_by=False)
    return DashboardResult(path=path, written=len(items))


def generate_due_soon_dashboard(
    vault_root: Path,
    within_days: int = 7,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Due Soon.md``.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    within_days:
        Window size in days.  Defaults to 7.
    now_iso:
        ISO 8601 reference timestamp.  Defaults to UTC now.

    Returns
    -------
    DashboardResult
        ``written`` is the number of items rendered (overdue + upcoming combined).
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_due_soon_md(items, ts, within_days)
    path = vault_root / _DASHBOARD_DUE_SOON_PATH

    # Count entries that appear in the rendered output.
    now = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    cutoff = now + timedelta(days=within_days)
    written = sum(
        1 for s in items
        if s.status == "open"
        and _try_parse_dt(s.due_at) is not None
        and _try_parse_dt(s.due_at) <= cutoff  # type: ignore[operator]
    )

    atomic_write(path, content, vault_root=vault_root, tool_name=_TOOL, inject_generated_by=False)
    return DashboardResult(path=path, written=written)


def generate_waiting_on_me_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Waiting On Me.md``.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    now_iso:
        ISO 8601 reference timestamp.  Defaults to UTC now.

    Returns
    -------
    DashboardResult
        ``written`` is the number of open commitments with ``requires_ack=True``.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_waiting_on_me_md(items, ts)
    path = vault_root / _DASHBOARD_WAITING_ON_ME_PATH
    written = sum(1 for i in items if i.status == "open" and i.requires_ack)
    atomic_write(path, content, vault_root=vault_root, tool_name=_TOOL, inject_generated_by=False)
    return DashboardResult(path=path, written=written)


def generate_postponed_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Postponed.md``.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    now_iso:
        ISO 8601 reference timestamp.  Defaults to UTC now.

    Returns
    -------
    DashboardResult
        ``written`` is the number of open commitments with ``postponed_until`` set.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_postponed_md(items, ts)
    path = vault_root / _DASHBOARD_POSTPONED_PATH
    written = sum(1 for i in items if i.status == "open" and i.postponed_until)
    atomic_write(path, content, vault_root=vault_root, tool_name=_TOOL, inject_generated_by=False)
    return DashboardResult(path=path, written=written)


def generate_daily_review_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Daily.md``.

    Sections: Captured today, Due today, Overdue, Completed today,
    Blocked/Waiting.  ``DashboardResult.written`` counts the total items
    rendered across all sections (a single item can appear in at most one
    section after overdue/due-today dedup).
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_daily_review_md(items, ts)
    path = vault_root / _DASHBOARD_DAILY_REVIEW_PATH
    now = _try_parse_dt(ts) or datetime.now(timezone.utc)
    captured = {i.action_id for i in items if _same_utc_date(i.created_at, now)}
    due_today = {
        i.action_id for i in items
        if i.status == "open" and _same_utc_date(i.due_at, now)
    }
    overdue = {
        i.action_id for i in items
        if i.status == "open"
        and i.due_at
        and (_try_parse_dt(i.due_at) or now) < now
    } - due_today
    completed = {
        i.action_id for i in items
        if i.status == "done" and _same_utc_date(i.updated_at, now)
    }
    blocked = {i.action_id for i in items if _is_blocked(i)}
    written = len(captured | due_today | overdue | completed | blocked)
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=written)


def generate_weekly_review_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Weekly.md``.

    Sections: Captured this ISO-week, Completed this ISO-week, Still open
    from last week, Stale (>*stale_days* days, no movement), Top projects
    by open volume.  ``DashboardResult.written`` is the total count of
    commitment items surfaced across the list sections (top-projects
    table is a summary, not per-item, so excluded from the count).
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_weekly_review_md(items, ts, stale_days)
    path = vault_root / _DASHBOARD_WEEKLY_REVIEW_PATH

    now = _try_parse_dt(ts) or datetime.now(timezone.utc)
    week_start, week_end = _iso_week_bounds(now)
    prev_week_start = week_start - timedelta(days=7)

    captured_ids = {
        i.action_id for i in items
        if _in_range(i.created_at, week_start, week_end)
    }
    completed_ids = {
        i.action_id for i in items
        if i.status == "done"
        and _in_range(i.updated_at, week_start, week_end)
    }
    still_open_ids = {
        i.action_id for i in items
        if i.status == "open"
        and _in_range(i.created_at, prev_week_start, week_start)
    }
    stale_ids = {
        i.action_id for i in items
        if i.status == "open"
        and (
            _stale_age_days(i, now) > stale_days
            or _is_stale_triage_stage(i, now)
        )
    }
    written = len(captured_ids | completed_ids | still_open_ids | stale_ids)
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=written)


def generate_stale_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Stale.md``.

    An open commitment is stale when its ``updated_at`` (or
    ``created_at`` fallback) is older than *stale_days*, OR its
    ``lifecycle_stage`` is ``inbox``/``triaged`` and older than 3 days.
    Items are sorted by staleness descending.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_stale_md(items, ts, stale_days)
    path = vault_root / _DASHBOARD_STALE_PATH

    now = _try_parse_dt(ts) or datetime.now(timezone.utc)
    written = sum(
        1 for i in items
        if i.status == "open"
        and (
            _stale_age_days(i, now) > stale_days
            or _is_stale_triage_stage(i, now)
        )
    )
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=written)


def generate_merge_candidates_dashboard(
    vault_root: Path,
    now_iso: str | None = None,
    merge_window_days: int = DEFAULT_MERGE_WINDOW_DAYS,
    merge_jaccard: float = DEFAULT_MERGE_JACCARD,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Merge Candidates.md``.

    Heuristic-only (no embeddings).  Pairs two open commitments when
    they share a project, their titles' token-Jaccard >= *merge_jaccard*,
    and they were created within *merge_window_days* of each other.
    ``DashboardResult.written`` counts the number of candidate pairs.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    items = _scan_commitments(vault_root)
    content = _render_merge_candidates_md(
        items, ts, merge_window_days, merge_jaccard,
    )
    path = vault_root / _DASHBOARD_MERGE_CANDIDATES_PATH

    now = _try_parse_dt(ts) or datetime.now(timezone.utc)
    pairs = _compute_merge_candidates(items, now, merge_window_days, merge_jaccard)
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=len(pairs))


# ---------------------------------------------------------------------------
# Task 31: Patterns dashboard
# ---------------------------------------------------------------------------


def _render_patterns_md(
    *,
    now_iso: str,
    postponements: list[dict] | None,
    blockers: list[dict] | None,
    recurring_by_kind: dict[str, list[dict]] | None,
    service_error: str | None,
) -> str:
    """Render the Patterns review dashboard markdown.

    Pure; takes already-fetched payloads. When ``service_error`` is set
    the body contains a banner + whatever local sections we can still
    render (all omitted sections render as an empty bullet with "No data
    from service.").
    """
    fm = _frontmatter("patterns", now_iso)
    lines: list[str] = [fm, "", "# Patterns", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append("")
    if service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}. "
            "Showing no pattern data for this run."
        )
        lines.append("")

    # Postponement loops
    lines.append("## Postponement loops")
    lines.append("")
    if postponements:
        lines.append(
            "| Title | Count | Slipped (days) | Last reason | Last postponed |"
        )
        lines.append("|---|---:|---:|---|---|")
        for item in postponements:
            title = (item.get("title") or "").replace("|", "\\|")
            count = int(item.get("count") or 0)
            slipped = int(item.get("cumulative_days_slipped") or 0)
            last_reason = (
                (item.get("last_reason") or "").replace("|", "\\|").strip()
            ) or "—"
            last_at = _fmt_date(item.get("last_postponed_at"), fallback="—")
            lines.append(
                f"| {title} | {count} | {slipped} | {last_reason} | {last_at} |"
            )
    else:
        lines.append("- No repeated postponements detected in the window.")
    lines.append("")

    # Blocker clusters
    lines.append("## Blocker clusters")
    lines.append("")
    if blockers:
        for item in blockers:
            title = (item.get("title") or "untitled").strip()
            count = int(item.get("blocks_count") or 0)
            downstream = item.get("downstream_action_ids") or []
            oldest = _fmt_date(item.get("oldest_edge_at"), fallback="—")
            ds_preview = ", ".join(downstream[:5])
            suffix = "…" if len(downstream) > 5 else ""
            lines.append(
                f"- **{title}** — blocks {count} "
                f"(since {oldest}): {ds_preview}{suffix}"
            )
    else:
        lines.append("- No open blockers in the window.")
    lines.append("")

    # Recurring unfinished
    lines.append("## Recurring unfinished")
    lines.append("")
    by_kind = recurring_by_kind or {}
    for kind in ("project", "person", "area"):
        label = kind.capitalize()
        lines.append(f"### By {label}")
        lines.append("")
        items = by_kind.get(kind) or []
        if items:
            for item in items:
                name = (item.get("canonical_name") or "").strip() or "—"
                open_count = int(item.get("open_count") or 0)
                median_age = int(item.get("median_age_days") or 0)
                lines.append(
                    f"- **{name}** — {open_count} open "
                    f"(median age {median_age}d)"
                )
        else:
            lines.append(
                f"- No recurring unfinished {label.lower()}s in the window."
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_patterns_dashboard(
    vault_root: Path,
    *,
    now_iso: str | None = None,
    postponements_since_days: int = 30,
    blockers_since_days: int = 60,
    recurring_since_days: int = 90,
    limit: int = 20,
    service_url: str | None = None,
    token: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Patterns.md``.

    Pulls the three Task 31 pattern lenses from the capture service
    when reachable. If the service is unreachable, writes a banner
    at the top of the dashboard and leaves each section empty.
    """
    # Local import avoids a circular import at module load.
    from obsidian_connector.commitment_ops import (
        list_blocker_clusters,
        list_recurring_unfinished,
        list_repeated_postponements,
    )

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()

    postponements: list[dict] | None = None
    blockers: list[dict] | None = None
    recurring_by_kind: dict[str, list[dict]] = {}
    service_error: str | None = None

    pp_env = list_repeated_postponements(
        since_days=postponements_since_days,
        limit=limit,
        service_url=service_url,
        token=token,
    )
    if pp_env.get("ok"):
        postponements = (pp_env.get("data") or {}).get("items") or []
    else:
        service_error = service_error or str(pp_env.get("error") or "error")

    bl_env = list_blocker_clusters(
        since_days=blockers_since_days,
        limit=limit,
        service_url=service_url,
        token=token,
    )
    if bl_env.get("ok"):
        blockers = (bl_env.get("data") or {}).get("items") or []
    else:
        service_error = service_error or str(bl_env.get("error") or "error")

    for kind in ("project", "person", "area"):
        env = list_recurring_unfinished(
            by=kind,
            since_days=recurring_since_days,
            limit=limit,
            service_url=service_url,
            token=token,
        )
        if env.get("ok"):
            recurring_by_kind[kind] = (env.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(env.get("error") or "error")
            recurring_by_kind[kind] = []

    content = _render_patterns_md(
        now_iso=ts,
        postponements=postponements,
        blockers=blockers,
        recurring_by_kind=recurring_by_kind,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_PATTERNS_PATH

    written = (
        (len(postponements or []))
        + (len(blockers or []))
        + sum(len(v) for v in recurring_by_kind.values())
    )
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=written)


# ---------------------------------------------------------------------------
# Task 38: Delegations review dashboard
# ---------------------------------------------------------------------------


def _render_delegations_md(
    *,
    now_iso: str,
    threshold_days: int,
    stale_items: list[dict] | None,
    open_counts: list[tuple[str, int]] | None,
    service_configured: bool,
    service_error: str | None,
) -> str:
    """Render ``Dashboards/Review/Delegations.md``.

    Pure function. Always produces a document. When the capture
    service is not configured, the header banner explains the gap and
    both sections render a polite "no data" note. When the service is
    configured but unreachable, the error surfaces once at the top and
    sections fall through to whatever the partial fetch returned.

    Two sections:

    - **Stale delegations (> N days)**: per-person buckets from
      ``list_stale_delegations``. Each bucket shows the count + oldest
      ``delegated_at`` + up to three sample items.
    - **Open delegations**: per-person counts across every person who
      currently has at least one open delegated action, sorted
      alphabetically (case-insensitive). Sourced from
      ``list_stale_delegations`` with ``threshold_days=1`` so the
      service returns every active bucket, including fresh ones.
    """
    fm = _frontmatter("delegations", now_iso)
    lines: list[str] = [fm, "", "# Delegations", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append("")

    if not service_configured:
        lines.append(
            "> Capture service not configured. Set "
            "`OBSIDIAN_CAPTURE_SERVICE_URL` (and optionally "
            "`OBSIDIAN_CAPTURE_SERVICE_TOKEN`) to populate the "
            "delegation surfaces. All sections below are empty for "
            "this run."
        )
        lines.append("")
    elif service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}. "
            "Sections below show whatever the service returned before "
            "the error."
        )
        lines.append("")

    # Stale delegations
    lines.append(f"## Stale delegations (>{int(threshold_days)} days)")
    lines.append("")
    if stale_items:
        lines.append("| Person | Stale count | Oldest delegated | Sample titles |")
        lines.append("|---|---:|---|---|")
        for bucket in stale_items:
            name = str(bucket.get("canonical_name") or "?").replace("|", "\\|")
            count = int(bucket.get("count") or 0)
            oldest = _fmt_date(
                bucket.get("oldest_delegated_at"), fallback="\u2014",
            )
            samples = (bucket.get("items") or [])[:3]
            titles = ", ".join(
                str(s.get("title") or "(no title)").replace("|", "\\|")
                for s in samples
            )
            if not titles:
                titles = "\u2014"
            lines.append(
                f"| {name} | {count} | {oldest} | {titles} |"
            )
    else:
        lines.append("- No stale delegations in the window.")
    lines.append("")

    # Open delegations (per-person counts, alphabetical)
    lines.append("## Open delegations")
    lines.append("")
    if open_counts:
        lines.append("| Person | Open count |")
        lines.append("|---|---:|")
        for name, count in open_counts:
            safe_name = str(name or "?").replace("|", "\\|")
            lines.append(f"| {safe_name} | {int(count)} |")
    else:
        lines.append("- No open delegations.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_delegation_dashboard(
    vault_root: Path,
    *,
    service_url: str | None = None,
    token: str | None = None,
    threshold_days: int = 14,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Delegations.md`` (Task 38).

    Pulls ``GET /api/v1/patterns/stale-delegations`` twice:

    1. With the configured ``threshold_days`` (default 14) for the
       "Stale delegations" section.
    2. With ``threshold_days=1`` for the "Open delegations" section so
       every person with at least one open delegated action is listed,
       regardless of how fresh it is.

    When no service URL is configured (neither argument nor
    environment var), writes the dashboard with a "service not
    configured" banner and empty sections so operators still see the
    page. Never raises. ``DashboardResult.written`` counts the number
    of stale buckets rendered.
    """
    import os as _os

    from obsidian_connector.commitment_ops import list_stale_delegations

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    resolved_url = service_url or _os.environ.get(
        "OBSIDIAN_CAPTURE_SERVICE_URL"
    )
    service_configured = bool(resolved_url)

    stale_items: list[dict] | None = None
    open_counts: list[tuple[str, int]] | None = None
    service_error: str | None = None

    if service_configured:
        stale = list_stale_delegations(
            threshold_days=int(threshold_days),
            limit=200,
            service_url=service_url,
            token=token,
        )
        if stale.get("ok"):
            stale_items = (stale.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(stale.get("error") or "error")

        all_open = list_stale_delegations(
            threshold_days=1,
            limit=200,
            service_url=service_url,
            token=token,
        )
        if all_open.get("ok"):
            buckets = (all_open.get("data") or {}).get("items") or []
            pairs: list[tuple[str, int]] = []
            for bucket in buckets:
                name = str(bucket.get("canonical_name") or "")
                count = int(bucket.get("count") or 0)
                if not name or count <= 0:
                    continue
                pairs.append((name, count))
            pairs.sort(key=lambda t: (t[0].lower(), t[0]))
            open_counts = pairs
        else:
            service_error = service_error or str(
                all_open.get("error") or "error"
            )

    content = _render_delegations_md(
        now_iso=ts,
        threshold_days=int(threshold_days),
        stale_items=stale_items,
        open_counts=open_counts,
        service_configured=service_configured,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_DELEGATIONS_PATH
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=len(stale_items or []))


# ---------------------------------------------------------------------------
# Task 44: Admin dashboard
# ---------------------------------------------------------------------------


def _render_admin_md(
    *,
    now_iso: str,
    system_health_payload: dict | None,
    queue_health_payload: dict | None,
    delivery_failures_items: list[dict] | None,
    pending_approvals_items: list[dict] | None,
    stale_devices_items: list[dict] | None,
    service_configured: bool,
    service_error: str | None,
    mobile_devices_items: list[dict] | None = None,
) -> str:
    """Render the admin dashboard markdown.

    Pure function. Always produces a document, even when the service
    isn't configured — in that case the header banner explains the
    gap and every section renders a polite "no data" note. When the
    service is configured but unreachable, the error is surfaced
    once at the top and the sections fall through to empty.
    """
    fm = _frontmatter("admin", now_iso)
    lines: list[str] = [fm, "", "# Admin", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append("")

    if not service_configured:
        lines.append(
            "> Capture service not configured. Set "
            "`OBSIDIAN_CAPTURE_SERVICE_URL` (and optionally "
            "`OBSIDIAN_CAPTURE_SERVICE_TOKEN`) to populate the admin "
            "surfaces. All sections below are empty for this run."
        )
        lines.append("")
    elif service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}. "
            "Sections below show whatever the service returned before "
            "the error."
        )
        lines.append("")

    # System health summary
    lines.append("## System health summary")
    lines.append("")
    if system_health_payload:
        overall = str(system_health_payload.get("overall_status") or "?").upper()
        doctor = system_health_payload.get("doctor") or {}
        counts = doctor.get("counts") or {}
        lines.append(f"- **Overall status**: {overall}")
        lines.append(
            f"- Doctor: {int(counts.get('ok', 0))} ok, "
            f"{int(counts.get('warn', 0))} warn, "
            f"{int(counts.get('fail', 0))} fail, "
            f"{int(counts.get('skip', 0))} skip"
        )
        queue_summary = system_health_payload.get("queue") or {}
        if queue_summary:
            lines.append(
                f"- Queue: enabled={bool(queue_summary.get('enabled'))}, "
                f"reachable={bool(queue_summary.get('reachable'))}, "
                f"error_rate={float(queue_summary.get('error_rate', 0.0)):.2%}"
            )
        fails = [
            c for c in (doctor.get("checks") or [])
            if c.get("status") == "fail"
        ]
        for check in fails:
            lines.append(
                f"  - FAIL: **{check.get('name', '?')}** — "
                f"{check.get('summary', '')}"
            )
    else:
        lines.append("- No system-health data from service.")
    lines.append("")

    # Queue health
    lines.append("## Queue health")
    lines.append("")
    if queue_health_payload:
        if not queue_health_payload.get("enabled"):
            lines.append(
                "- Cloud queue is disabled on the service side "
                "(no `DATABASE_URL` or queue poller off). Cloud "
                "capture relay is inactive."
            )
        else:
            counts = queue_health_payload.get("counts") or {}
            if counts:
                items = [
                    f"{status}={count}"
                    for status, count in sorted(counts.items())
                ]
                lines.append(f"- Counts: {', '.join(items)}")
            else:
                lines.append("- Counts: (empty)")
            age = queue_health_payload.get("oldest_pending_age_seconds")
            if age is not None:
                lines.append(f"- Oldest pending age: {int(age)}s")
            lines.append(
                f"- Error rate (last "
                f"{int(queue_health_payload.get('since_hours', 24))}h): "
                f"{float(queue_health_payload.get('error_rate', 0.0)):.2%}"
            )
            if queue_health_payload.get("error"):
                lines.append(
                    f"- Error: {queue_health_payload.get('error')}"
                )
    else:
        lines.append("- No queue-health data from service.")
    lines.append("")

    # Delivery failures
    lines.append("## Recent delivery failures")
    lines.append("")
    if delivery_failures_items:
        lines.append("| Channel | Action | Attempt | Scheduled | Error |")
        lines.append("|---|---|---:|---|---|")
        for item in delivery_failures_items:
            channel = str(item.get("channel") or "?").replace("|", "\\|")
            title = str(item.get("action_title") or "—").replace("|", "\\|")
            attempt = int(item.get("attempt") or 0)
            scheduled = _fmt_date(item.get("scheduled_at"), fallback="—")
            err = (item.get("last_error") or "—").split("\n")[0][:80]
            err = err.replace("|", "\\|")
            lines.append(
                f"| {channel} | {title} | {attempt} | {scheduled} | {err} |"
            )
    else:
        lines.append("- No delivery failures in the window.")
    lines.append("")

    # Pending approvals
    lines.append("## Pending approvals")
    lines.append("")
    if pending_approvals_items:
        lines.append("| Channel | Action | Priority | Scheduled |")
        lines.append("|---|---|---|---|")
        for item in pending_approvals_items:
            channel = str(item.get("channel") or "?").replace("|", "\\|")
            title = str(item.get("action_title") or "—").replace("|", "\\|")
            priority = str(item.get("action_priority") or "—").replace("|", "\\|")
            scheduled = _fmt_date(item.get("scheduled_at"), fallback="—")
            lines.append(
                f"| {channel} | {title} | {priority} | {scheduled} |"
            )
    else:
        lines.append("- No deliveries awaiting approval.")
    lines.append("")

    # Stale sync devices
    lines.append("## Stale sync devices")
    lines.append("")
    if stale_devices_items:
        lines.append("| Device | Platform | Last sync | Hours stale | Pending ops |")
        lines.append("|---|---|---|---:|---:|")
        for item in stale_devices_items:
            device = str(item.get("device_id") or "?").replace("|", "\\|")
            label = str(item.get("device_label") or "").replace("|", "\\|")
            device_display = f"{label} ({device})" if label else device
            platform = str(item.get("platform") or "—").replace("|", "\\|")
            last = _fmt_date(item.get("last_synced_at"), fallback="never")
            hours = item.get("hours_since_last_sync")
            hours_str = f"{hours:.1f}" if hours is not None else "—"
            pending = int(item.get("pending_ops_count") or 0)
            lines.append(
                f"| {device_display} | {platform} | {last} | {hours_str} | {pending} |"
            )
    else:
        lines.append("- All devices are fresh.")
    lines.append("")

    # Mobile devices (Task 42) -- every registered device, not just stale ones
    lines.append("## Mobile devices")
    lines.append("")
    if mobile_devices_items:
        lines.append(
            "| Device | Label | Platform | App | Last sync | "
            "Pending ops | First seen |"
        )
        lines.append("|---|---|---|---|---|---:|---|")
        for item in mobile_devices_items:
            device = str(item.get("device_id") or "?").replace("|", "\\|")
            label = str(item.get("device_label") or "—").replace("|", "\\|")
            platform = str(item.get("platform") or "—").replace("|", "\\|")
            version = str(item.get("app_version") or "—").replace("|", "\\|")
            last = _fmt_date(item.get("last_sync_at"), fallback="never")
            pending = int(item.get("pending_ops_count") or 0)
            first_seen = _fmt_date(item.get("first_seen_at"), fallback="—")
            lines.append(
                f"| {device} | {label} | {platform} | {version} | "
                f"{last} | {pending} | {first_seen} |"
            )
    elif mobile_devices_items is None and not service_configured:
        lines.append("- (service not configured)")
    else:
        lines.append("- No mobile devices registered yet.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_admin_dashboard(
    vault_root: Path,
    *,
    service_url: str | None = None,
    token: str | None = None,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Admin.md`` (Task 44).

    Pulls the composite ``/api/v1/admin/system-health`` endpoint plus
    the four list endpoints, renders a single admin page. When no
    service URL is configured (neither argument nor environment var),
    writes a dashboard with a "service not configured" banner and
    empty sections so operators still see the page and understand why
    it's blank.

    Never raises. Returns a :class:`DashboardResult` whose ``written``
    count sums the list items surfaced across the four list sections.
    """
    import os as _os

    from obsidian_connector.admin_ops import (
        get_queue_health,
        get_system_health,
        list_delivery_failures,
        list_mobile_devices,
        list_pending_approvals,
        list_stale_sync_devices,
    )

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    resolved_url = service_url or _os.environ.get("OBSIDIAN_CAPTURE_SERVICE_URL")
    service_configured = bool(resolved_url)

    sh_payload: dict | None = None
    q_payload: dict | None = None
    f_items: list[dict] | None = None
    a_items: list[dict] | None = None
    d_items: list[dict] | None = None
    m_items: list[dict] | None = None
    service_error: str | None = None

    if service_configured:
        sh = get_system_health(service_url=service_url, token=token)
        if sh.get("ok"):
            sh_payload = sh.get("data") or {}
        else:
            service_error = service_error or str(sh.get("error") or "error")

        q = get_queue_health(service_url=service_url, token=token)
        if q.get("ok"):
            q_payload = q.get("data") or {}
        else:
            service_error = service_error or str(q.get("error") or "error")

        f = list_delivery_failures(service_url=service_url, token=token)
        if f.get("ok"):
            f_items = (f.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(f.get("error") or "error")

        a = list_pending_approvals(service_url=service_url, token=token)
        if a.get("ok"):
            a_items = (a.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(a.get("error") or "error")

        d = list_stale_sync_devices(service_url=service_url, token=token)
        if d.get("ok"):
            d_items = (d.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(d.get("error") or "error")

        m = list_mobile_devices(service_url=service_url, token=token)
        if m.get("ok"):
            m_items = (m.get("data") or {}).get("devices") or []
        else:
            service_error = service_error or str(m.get("error") or "error")

    content = _render_admin_md(
        now_iso=ts,
        system_health_payload=sh_payload,
        queue_health_payload=q_payload,
        delivery_failures_items=f_items,
        pending_approvals_items=a_items,
        stale_devices_items=d_items,
        mobile_devices_items=m_items,
        service_configured=service_configured,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_ADMIN_PATH
    written = (
        (len(f_items or []))
        + (len(a_items or []))
        + (len(d_items or []))
        + (len(m_items or []))
    )
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=written)


# ---------------------------------------------------------------------------
# Task 36: Approvals dashboard
# ---------------------------------------------------------------------------


def _render_approvals_md(
    *,
    now_iso: str,
    digest_payload: dict | None,
    detail_rows: list[dict] | None,
    recent_history_rows: list[dict] | None,
    service_configured: bool,
    service_error: str | None,
) -> str:
    """Render ``Dashboards/Admin/Approvals.md``.

    Pure function. Always produces a document — when the service is
    not configured the header banner explains the gap and every
    section renders a polite "no data" note. When the service is
    configured but unreachable, the error surfaces once at the top
    and the sections fall through to whatever the partial fetch
    returned before failure.

    The ``detail_rows`` input is a list of dicts where each row has
    the delivery + action + risk_factors shape of the
    ``/api/v1/deliveries/{id}`` endpoint. ``recent_history_rows`` is
    a list of ``approval_history`` entries from the same source,
    enriched with ``delivery_id`` and ``action_title`` so the table
    can be rendered without another round-trip.
    """
    fm = _frontmatter("approvals", now_iso)
    lines: list[str] = [fm, "", "# Approvals", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append("")

    if not service_configured:
        lines.append(
            "> Capture service not configured. Set "
            "`OBSIDIAN_CAPTURE_SERVICE_URL` (and optionally "
            "`OBSIDIAN_CAPTURE_SERVICE_TOKEN`) to populate the "
            "approval surfaces. All sections below are empty for "
            "this run."
        )
        lines.append("")
    elif service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}. "
            "Sections below show whatever the service returned "
            "before the error."
        )
        lines.append("")

    # Digest block
    lines.append("## Approval digest")
    lines.append("")
    if digest_payload:
        pending_total = int(digest_payload.get("pending_total", 0) or 0)
        since_hours = int(digest_payload.get("since_hours", 24) or 24)
        lines.append(f"- **Pending total**: {pending_total}")
        age = digest_payload.get("oldest_pending_age_seconds")
        if age is not None:
            lines.append(f"- Oldest pending age: {int(age)}s")
        counts_ch = digest_payload.get("counts_by_channel") or {}
        if counts_ch:
            parts = ", ".join(
                f"{ch}={counts_ch[ch]}" for ch in sorted(counts_ch.keys())
            )
            lines.append(f"- By channel: {parts}")
        counts_ug = digest_payload.get("counts_by_urgency") or {}
        if counts_ug:
            parts = ", ".join(
                f"{u}={counts_ug[u]}" for u in sorted(counts_ug.keys())
            )
            lines.append(f"- By urgency: {parts}")
        recent = int(digest_payload.get("recent_decisions_count", 0) or 0)
        lines.append(
            f"- Recent decisions (last {since_hours}h): {recent}"
        )
    else:
        lines.append("- No digest data from service.")
    lines.append("")

    # Pending approvals table (with risk factors, urgency, age)
    lines.append("## Pending approvals with risk factors")
    lines.append("")
    if detail_rows:
        lines.append("| Delivery | Action | Channel | Urgency | Scheduled | Risk factors |")
        lines.append("|---|---|---|---|---|---|")
        for row in _order_approvals_for_dashboard(detail_rows):
            delivery = row.get("delivery", {}) or {}
            action = row.get("action") or {}
            risks = row.get("risk_factors", []) or []
            did = str(delivery.get("delivery_id") or "?").replace("|", "\\|")
            title = str(
                action.get("title") or "\u2014"
            ).replace("|", "\\|")
            channel = str(delivery.get("channel") or "?").replace("|", "\\|")
            urgency = str(
                action.get("urgency") or "normal"
            ).replace("|", "\\|")
            scheduled = _fmt_date(
                delivery.get("scheduled_at"), fallback="\u2014",
            )
            risks_cell = (
                ", ".join(risks).replace("|", "\\|") if risks else "\u2014"
            )
            lines.append(
                f"| {did} | {title} | {channel} | {urgency}"
                f" | {scheduled} | {risks_cell} |"
            )
    else:
        lines.append("- No deliveries awaiting approval.")
    lines.append("")

    # Recent decisions (last 24h window sourced from approval_history)
    lines.append("## Recent decisions (last 24h)")
    lines.append("")
    if recent_history_rows:
        lines.append("| Decided | Decision | Delivery | Action | Channel |")
        lines.append("|---|---|---|---|---|")
        for row in recent_history_rows:
            decided = _fmt_date(row.get("decided_at"), fallback="\u2014")
            decision = str(row.get("decision") or "?").replace("|", "\\|")
            did = str(row.get("delivery_id") or "?").replace("|", "\\|")
            title = str(
                row.get("action_title") or "\u2014"
            ).replace("|", "\\|")
            channel = str(row.get("channel") or "?").replace("|", "\\|")
            lines.append(
                f"| {decided} | {decision} | {did} | {title} | {channel} |"
            )
    else:
        lines.append("- No approve/reject decisions in the window.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _order_approvals_for_dashboard(rows: list[dict]) -> list[dict]:
    """Order pending-approval rows by (urgency DESC, age ASC).

    Urgency order is ``critical > elevated > normal > low``. Inside
    each bucket the oldest ``scheduled_at`` comes first. Rows with no
    action payload or no scheduled_at sort last inside their bucket.
    """
    urgency_rank = {"critical": 0, "elevated": 1, "normal": 2, "low": 3}

    def _key(row: dict) -> tuple[int, str, str]:
        action = row.get("action") or {}
        u = str(action.get("urgency") or "normal")
        delivery = row.get("delivery", {}) or {}
        sched = str(delivery.get("scheduled_at") or "9999-12-31T00:00:00+00:00")
        did = str(delivery.get("delivery_id") or "~")
        return (urgency_rank.get(u, 4), sched, did)

    return sorted(rows, key=_key)


def generate_approval_dashboard(
    vault_root: Path,
    *,
    service_url: str | None = None,
    token: str | None = None,
    now_iso: str | None = None,
    since_hours: int = 24,
) -> DashboardResult:
    """Generate or update ``Dashboards/Admin/Approvals.md`` (Task 36).

    Pulls ``/api/v1/deliveries/approval-digest``, then
    ``/api/v1/admin/pending-approvals`` for the delivery id list, and
    for each id fetches ``/api/v1/deliveries/{id}`` so the dashboard
    can render the full approval context (action title + urgency +
    risk factors + recent history). When the service URL isn't
    configured, writes a "service not configured" banner + empty
    sections. Never raises.

    ``DashboardResult.written`` counts the number of pending rows
    rendered in the middle section (the actionable work).
    """
    import os as _os

    from obsidian_connector.admin_ops import list_pending_approvals
    from obsidian_connector.approval_ops import (
        get_approval_digest,
        get_delivery_detail,
    )

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    resolved_url = service_url or _os.environ.get("OBSIDIAN_CAPTURE_SERVICE_URL")
    service_configured = bool(resolved_url)

    digest_payload: dict | None = None
    detail_rows: list[dict] = []
    recent_history_rows: list[dict] = []
    service_error: str | None = None

    if service_configured:
        d = get_approval_digest(
            since_hours=since_hours,
            service_url=service_url, token=token,
        )
        if d.get("ok"):
            digest_payload = d.get("data") or {}
        else:
            service_error = service_error or str(d.get("error") or "error")

        listing = list_pending_approvals(
            service_url=service_url, token=token,
        )
        if listing.get("ok"):
            items = (listing.get("data") or {}).get("items") or []
        else:
            items = []
            service_error = service_error or str(listing.get("error") or "error")

        for item in items:
            delivery_id = item.get("delivery_id")
            if not delivery_id:
                continue
            detail = get_delivery_detail(
                delivery_id, service_url=service_url, token=token,
            )
            if not detail.get("ok"):
                service_error = service_error or str(detail.get("error") or "error")
                continue
            data = detail.get("data") or {}
            detail_rows.append(data)
            # Collect the last 24h of decisions across every row we see.
            for h in (data.get("approval_history") or []):
                enriched = dict(h)
                enriched["delivery_id"] = delivery_id
                action = data.get("action") or {}
                enriched["action_title"] = action.get("title")
                recent_history_rows.append(enriched)

    # Order recent decisions by decided_at DESC so the newest is on top.
    recent_history_rows.sort(
        key=lambda r: str(r.get("decided_at") or ""), reverse=True,
    )

    content = _render_approvals_md(
        now_iso=ts,
        digest_payload=digest_payload,
        detail_rows=detail_rows,
        recent_history_rows=recent_history_rows,
        service_configured=service_configured,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_APPROVALS_PATH
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=len(detail_rows))


def _render_analytics_md(
    *,
    now_iso: str,
    weeks_items: list[dict] | None,
    this_week_payload: dict | None,
    present_labels: set[str],
    service_configured: bool,
    service_error: str | None,
) -> str:
    """Render ``Dashboards/Analytics.md`` (Task 39).

    Pure function. Always produces a document. Sections are stable so
    diffs are minimal week over week.
    """
    fm = _frontmatter("analytics", now_iso)
    lines: list[str] = [fm, "", "# Analytics", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append("")

    if not service_configured:
        lines.append(
            "> Capture service not configured. Set "
            "`OBSIDIAN_CAPTURE_SERVICE_URL` (and optionally "
            "`OBSIDIAN_CAPTURE_SERVICE_TOKEN`) to populate the analytics "
            "surface."
        )
        lines.append("")
    elif service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}."
        )
        lines.append("")

    # --- This week so far --------------------------------------------------
    lines.append("## This week so far")
    lines.append("")
    if this_week_payload:
        window = this_week_payload.get("window") or {}
        captures = this_week_payload.get("captures") or {}
        ac = this_week_payload.get("actions_created") or {}
        ad = this_week_payload.get("actions_completed") or {}
        ap = this_week_payload.get("actions_postponed") or {}
        health = this_week_payload.get("health_snapshot") or {}
        lines.append(f"- **Week**: {window.get('week_label', '?')}")
        lines.append(f"- **Captures**: {int(captures.get('total', 0))}")
        lines.append(
            f"- **Actions**: {int(ac.get('total', 0))} created,"
            f" {int(ad.get('total', 0))} completed,"
            f" {int(ap.get('count', 0))} postponed"
        )
        overall = str(health.get("overall_status") or "unknown")
        lines.append(
            f"- **Health**: `{overall}`"
            f" · pending approvals: {int(health.get('pending_approvals', 0))}"
            f" · delivery failures: {int(health.get('delivery_failures', 0))}"
        )
    else:
        lines.append("- (live report unavailable)")
    lines.append("")

    # --- Past weeks index --------------------------------------------------
    lines.append("## Past weeks")
    lines.append("")
    items = weeks_items or []
    if not items:
        lines.append("- (no weeks available)")
    else:
        for item in items:
            label = item.get("week_label") or "?"
            start = item.get("start_iso") or "?"
            end = item.get("end_iso") or "?"
            if label in present_labels:
                year = label.split("-W")[0] if "-W" in label else ""
                rel = (
                    f"{_ANALYTICS_BASE_DIR}/{year}/{label}.md"
                    if year
                    else f"{_ANALYTICS_BASE_DIR}/{label}.md"
                )
                lines.append(f"- [[{rel}|{label}]] · {start} → {end}")
            else:
                lines.append(f"- {label} · {start} → {end} · (not written)")
    lines.append("")
    return "\n".join(lines)


def _present_week_labels(
    vault_root: Path, *, base_dir: str = _ANALYTICS_BASE_DIR
) -> set[str]:
    """Return the set of ISO-week labels whose note already exists.

    Scans ``<vault_root>/<base_dir>/<year>/*.md`` — cheap glob over a
    folder that only holds weekly reports, so no full-vault walk.
    Silently tolerates a missing base dir.
    """
    root = Path(vault_root) / base_dir
    if not root.exists():
        return set()
    found: set[str] = set()
    for year_dir in root.iterdir():
        if not year_dir.is_dir():
            continue
        for note in year_dir.glob("*.md"):
            found.add(note.stem)
    return found


def generate_analytics_index_dashboard(
    vault_root: Path,
    *,
    service_url: str | None = None,
    token: str | None = None,
    now_iso: str | None = None,
    weeks_back: int = 12,
) -> DashboardResult:
    """Generate or update ``Dashboards/Analytics.md`` (Task 39).

    Lists the past ``weeks_back`` ISO-week windows with links to each
    weekly report note when present in the vault, plus a live
    "this week so far" subsection from the service. When the service
    URL isn't configured the dashboard still renders (with a banner)
    so operators see the page.

    Never raises. Returns a :class:`DashboardResult`.
    """
    import os as _os

    from obsidian_connector.analytics_ops import (
        get_weekly_report,
        list_weeks_available,
    )

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    resolved_url = service_url or _os.environ.get(
        "OBSIDIAN_CAPTURE_SERVICE_URL"
    )
    service_configured = bool(resolved_url)

    weeks_items: list[dict] | None = None
    this_week_payload: dict | None = None
    service_error: str | None = None

    if service_configured:
        w = list_weeks_available(
            weeks_back=weeks_back, service_url=service_url, token=token
        )
        if w.get("ok"):
            weeks_items = (w.get("data") or {}).get("items") or []
        else:
            service_error = service_error or str(w.get("error") or "error")

        r = get_weekly_report(
            week_offset=0, service_url=service_url, token=token
        )
        if r.get("ok"):
            this_week_payload = r.get("data") or {}
        else:
            service_error = service_error or str(r.get("error") or "error")

    present_labels = _present_week_labels(vault_root)
    content = _render_analytics_md(
        now_iso=ts,
        weeks_items=weeks_items,
        this_week_payload=this_week_payload,
        present_labels=present_labels,
        service_configured=service_configured,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_ANALYTICS_PATH
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    return DashboardResult(path=path, written=len(weeks_items or []))


# ---------------------------------------------------------------------------
# Task 40: Review coaching dashboard
# ---------------------------------------------------------------------------


def _render_coaching_md(
    *,
    now_iso: str,
    since_days: int,
    items: list[dict] | None,
    service_configured: bool,
    service_error: str | None,
) -> str:
    """Render ``Dashboards/Review/Coaching.md`` (Task 40).

    Pure function. Always produces a document. Groups the review
    recommendations by code so the operator can scan by action verb
    rather than per-action. A header banner surfaces the service
    state when it's not configured or unreachable.
    """
    fm = _frontmatter("coaching", now_iso)
    lines: list[str] = [fm, "", "# Review coaching", ""]
    lines.append(f"_Generated at {_now_display(now_iso)}._")
    lines.append(f"_Window: last {int(since_days)} day(s)._")
    lines.append("")

    if not service_configured:
        lines.append(
            "> Capture service not configured. Set "
            "`OBSIDIAN_CAPTURE_SERVICE_URL` (and optionally "
            "`OBSIDIAN_CAPTURE_SERVICE_TOKEN`) to populate the review "
            "coaching surface. All sections below are empty for this "
            "run."
        )
        lines.append("")
    elif service_error:
        lines.append(
            f"> Capture service unreachable: {service_error}. "
            "Sections below show whatever the service returned before "
            "the error."
        )
        lines.append("")

    # Bucket items by recommendation code so each section collapses
    # multiple actions sharing the same verb. Iterating in the fixed
    # alphabetical order of ``_COACHING_CODE_LABELS`` keeps section
    # order stable across runs.
    buckets: dict[str, list[tuple[dict, dict]]] = {
        code: [] for code in _COACHING_CODE_LABELS
    }
    items_list = items or []
    for item in items_list:
        for rec in item.get("recommendations") or []:
            code = rec.get("code")
            if code in buckets:
                buckets[code].append((item, rec))

    any_rendered = False
    for code, label in _COACHING_CODE_LABELS.items():
        rows = buckets.get(code) or []
        lines.append(f"## {label} ({len(rows)})")
        lines.append("")
        if not rows:
            lines.append("- (no candidates)")
            lines.append("")
            continue
        any_rendered = True
        for item, rec in rows:
            title = str(item.get("title") or "(untitled)").strip()
            aid = str(item.get("action_id") or "?")
            verb = str(rec.get("action_verb") or "?")
            rec_label = str(rec.get("label") or "").strip()
            lines.append(f"- **{title}** — verb `{verb}`")
            if rec_label:
                lines.append(f"    - why: {rec_label}")
            lines.append(f"    - action id: `{aid}`")
        lines.append("")

    if service_configured and not any_rendered and not service_error:
        # The service responded but there's nothing actionable in the
        # window. Make that obvious so operators know the empty
        # dashboard is not a bug.
        lines.append("_No review recommendations in the current window._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_coaching_dashboard(
    vault_root: Path,
    *,
    service_url: str | None = None,
    token: str | None = None,
    since_days: int = 7,
    limit: int = 100,
    now_iso: str | None = None,
) -> DashboardResult:
    """Generate or update ``Dashboards/Review/Coaching.md`` (Task 40).

    Pulls ``GET /api/v1/coaching/review`` once and renders each
    recommendation code as its own section. When no service URL is
    configured, writes the dashboard with a "service not configured"
    banner and empty sections so operators still see the page. Never
    raises. ``DashboardResult.written`` counts the number of
    recommendation rows rendered.
    """
    import os as _os

    from obsidian_connector.coaching_ops import list_review_recommendations

    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    resolved_url = service_url or _os.environ.get(
        "OBSIDIAN_CAPTURE_SERVICE_URL"
    )
    service_configured = bool(resolved_url)

    items: list[dict] | None = None
    service_error: str | None = None

    if service_configured:
        payload = list_review_recommendations(
            since_days=int(since_days),
            limit=int(limit),
            service_url=service_url,
            token=token,
        )
        if payload.get("ok"):
            items = (payload.get("data") or {}).get("items") or []
        else:
            service_error = str(payload.get("error") or "error")

    content = _render_coaching_md(
        now_iso=ts,
        since_days=int(since_days),
        items=items,
        service_configured=service_configured,
        service_error=service_error,
    )
    path = vault_root / _DASHBOARD_COACHING_PATH
    atomic_write(
        path, content, vault_root=vault_root, tool_name=_TOOL,
        inject_generated_by=False,
    )
    # Count the total number of recommendation rows rendered.
    written = 0
    for item in (items or []):
        written += len(item.get("recommendations") or [])
    return DashboardResult(path=path, written=written)


def update_all_review_dashboards(
    vault_root: Path,
    now_iso: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    merge_window_days: int = DEFAULT_MERGE_WINDOW_DAYS,
    merge_jaccard: float = DEFAULT_MERGE_JACCARD,
    *,
    include_patterns: bool = False,
    include_delegations: bool = True,
    include_coaching: bool = True,
    delegation_threshold_days: int = 14,
    coaching_since_days: int = 7,
    service_url: str | None = None,
    token: str | None = None,
) -> list[DashboardResult]:
    """Generate or update the review dashboards.

    All surfaces are given the same *ts* timestamp so ``generated_at``
    is consistent across the set.  Each generator writes independently
    via :func:`atomic_write` -- a later generator can still succeed if
    an earlier one raises, matching the graceful-degradation semantics
    of :func:`update_all_dashboards`.

    Returns a list in this order: Daily, Weekly, Stale, Merge
    Candidates, Delegations (when ``include_delegations=True``, the
    default; flip off for local-only review runs that should not touch
    the network), Coaching (when ``include_coaching=True``, the
    default; Task 40), plus Patterns when ``include_patterns=True``.
    The Patterns dashboard is opt-in because it contacts the capture
    service for three pattern lenses; the Delegations and Coaching
    dashboards are default-on because they are the primary surfaces
    for the Task 38 waiting-on workflow and the Task 40 review
    coaching loop, but when the service URL is not configured they
    still render locally with a "service not configured" banner so
    the files exist in the vault.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    results = [
        generate_daily_review_dashboard(vault_root, now_iso=ts),
        generate_weekly_review_dashboard(
            vault_root, now_iso=ts, stale_days=stale_days,
        ),
        generate_stale_dashboard(
            vault_root, now_iso=ts, stale_days=stale_days,
        ),
        generate_merge_candidates_dashboard(
            vault_root,
            now_iso=ts,
            merge_window_days=merge_window_days,
            merge_jaccard=merge_jaccard,
        ),
    ]
    if include_delegations:
        try:
            results.append(
                generate_delegation_dashboard(
                    vault_root,
                    service_url=service_url,
                    token=token,
                    threshold_days=delegation_threshold_days,
                    now_iso=ts,
                )
            )
        except Exception:
            # Non-fatal: if delegation generation raises despite the
            # wrapper's envelope contract, drop it and let the rest of
            # the set complete.
            pass
    if include_coaching:
        try:
            results.append(
                generate_coaching_dashboard(
                    vault_root,
                    service_url=service_url,
                    token=token,
                    since_days=coaching_since_days,
                    now_iso=ts,
                )
            )
        except Exception:
            # Non-fatal: if coaching generation raises despite the
            # wrapper's envelope contract, drop it and let the rest of
            # the set complete.
            pass
    if include_patterns:
        results.append(
            generate_patterns_dashboard(
                vault_root,
                now_iso=ts,
                service_url=service_url,
                token=token,
            )
        )
    return results


def update_all_dashboards(
    vault_root: Path,
    within_days: int = 7,
    now_iso: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    merge_window_days: int = DEFAULT_MERGE_WINDOW_DAYS,
    merge_jaccard: float = DEFAULT_MERGE_JACCARD,
    *,
    include_admin: bool = True,
    include_analytics: bool = True,
    service_url: str | None = None,
    token: str | None = None,
) -> list[DashboardResult]:
    """Generate or update all dashboards atomically (commitment + review + admin).

    A single scan of ``Commitments/`` is not shared across calls to keep
    each generator independent, but every dashboard is stamped with the
    same *ts* timestamp so ``generated_at`` is consistent across the set.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    within_days:
        Window for the Due Soon dashboard.  Defaults to 7.
    now_iso:
        ISO 8601 timestamp shared across all dashboards.  Defaults to UTC now.
    stale_days:
        Threshold (days) for Weekly and Stale review surfaces.  Default 14.
    merge_window_days:
        Max days between two items' created_at for the merge heuristic.
    merge_jaccard:
        Minimum title token-Jaccard similarity for the merge heuristic.
    include_admin:
        Render ``Dashboards/Admin.md`` (Task 44). Default True. When the
        service URL isn't configured the admin dashboard still renders
        with a "service not configured" banner instead of silently
        skipping, so operators see the page.
    service_url:
        Capture-service base URL override for the admin dashboard.
    token:
        Capture-service bearer token override for the admin dashboard.

    Returns
    -------
    list[DashboardResult]
        Commitment dashboards first (Commitments, Due Soon, Waiting On Me,
        Postponed), followed by the four review dashboards (Daily, Weekly,
        Stale, Merge Candidates), then optionally the Admin dashboard.
        Callers can index either half; the prefix is stable.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    commitment_results = [
        generate_commitments_dashboard(vault_root, now_iso=ts),
        generate_due_soon_dashboard(vault_root, within_days=within_days, now_iso=ts),
        generate_waiting_on_me_dashboard(vault_root, now_iso=ts),
        generate_postponed_dashboard(vault_root, now_iso=ts),
    ]
    review_results = update_all_review_dashboards(
        vault_root,
        now_iso=ts,
        stale_days=stale_days,
        merge_window_days=merge_window_days,
        merge_jaccard=merge_jaccard,
    )
    results = commitment_results + review_results
    if include_admin:
        try:
            results.append(
                generate_admin_dashboard(
                    vault_root,
                    service_url=service_url,
                    token=token,
                    now_iso=ts,
                )
            )
        except Exception:
            # Non-fatal: admin dashboard hits the network. If the call
            # crashes despite the admin_ops wrappers, drop it and let
            # the rest of the set complete.
            pass
        # Task 36: approvals dashboard rides on the same flag. Separate
        # try so an approvals-side failure never masks the admin page.
        try:
            results.append(
                generate_approval_dashboard(
                    vault_root,
                    service_url=service_url,
                    token=token,
                    now_iso=ts,
                )
            )
        except Exception:
            pass
    if include_analytics:
        # Task 39: analytics index dashboard. Independent try so a
        # service error never masks the other dashboards.
        try:
            results.append(
                generate_analytics_index_dashboard(
                    vault_root,
                    service_url=service_url,
                    token=token,
                    now_iso=ts,
                )
            )
        except Exception:
            pass
    return results


__all__ = [
    "DASHBOARDS_DIR",
    "REVIEW_DASHBOARDS_DIR",
    "DEFAULT_STALE_DAYS",
    "DEFAULT_MERGE_WINDOW_DAYS",
    "DEFAULT_MERGE_JACCARD",
    "DashboardResult",
    "generate_commitments_dashboard",
    "generate_daily_review_dashboard",
    "generate_due_soon_dashboard",
    "generate_merge_candidates_dashboard",
    "generate_postponed_dashboard",
    "generate_stale_dashboard",
    "generate_waiting_on_me_dashboard",
    "generate_weekly_review_dashboard",
    "title_jaccard",
    "update_all_dashboards",
    "update_all_review_dashboards",
    "generate_admin_dashboard",
    "generate_approval_dashboard",
    "generate_analytics_index_dashboard",
    "generate_delegation_dashboard",
    "generate_coaching_dashboard",
]
