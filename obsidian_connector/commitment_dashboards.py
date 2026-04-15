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


def update_all_review_dashboards(
    vault_root: Path,
    now_iso: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    merge_window_days: int = DEFAULT_MERGE_WINDOW_DAYS,
    merge_jaccard: float = DEFAULT_MERGE_JACCARD,
    *,
    include_patterns: bool = False,
    service_url: str | None = None,
    token: str | None = None,
) -> list[DashboardResult]:
    """Generate or update all four review dashboards.

    All four are given the same *ts* timestamp so ``generated_at`` is
    consistent across the set.  Each generator writes independently via
    :func:`atomic_write` -- a later generator can still succeed if an
    earlier one raises, matching the graceful-degradation semantics of
    :func:`update_all_dashboards`.

    Returns a list in this order: Daily, Weekly, Stale, Merge Candidates
    (plus Patterns when ``include_patterns=True``). The Patterns
    dashboard is opt-in because it contacts the capture service and we
    don't want every ``obsx review-dashboards`` run to touch the
    network when the operator only wants the local review surfaces.
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
) -> list[DashboardResult]:
    """Generate or update all dashboards atomically (commitment + review).

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

    Returns
    -------
    list[DashboardResult]
        Commitment dashboards first (Commitments, Due Soon, Waiting On Me,
        Postponed), followed by the four review dashboards (Daily, Weekly,
        Stale, Merge Candidates).  Callers can index either half; the
        length grew from 4 to 8 in Task 26 but the prefix is stable.
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
    return commitment_results + review_results


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
]
