"""Dashboard generation for commitment visibility.

Four Markdown dashboards in ``Dashboards/`` aggregating commitment state:

  Dashboards/Commitments.md    -- Open by project + done table
  Dashboards/Due Soon.md       -- Overdue + due-within-N-days
  Dashboards/Waiting On Me.md  -- Open items requiring acknowledgement
  Dashboards/Postponed.md      -- Open items with postponed_until set

Each public function reads the current ``Commitments/`` tree, renders the
dashboard, and writes it via :func:`atomic_write`.  Repeated calls with the
same vault state and the same *now_iso* produce byte-for-byte identical output
(deterministic and idempotent).  Only ``generated_at`` in the frontmatter
changes between live runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# _scan_commitments is an intentional package-internal dependency: it returns
# CommitmentSummary objects which the renderer uses directly, avoiding a
# round-trip through dict serialisation.
from obsidian_connector.commitment_ops import CommitmentSummary, _scan_commitments
from obsidian_connector.write_manager import atomic_write

DASHBOARDS_DIR = "Dashboards"

_DASHBOARD_COMMITMENTS_PATH = f"{DASHBOARDS_DIR}/Commitments.md"
_DASHBOARD_DUE_SOON_PATH = f"{DASHBOARDS_DIR}/Due Soon.md"
_DASHBOARD_WAITING_ON_ME_PATH = f"{DASHBOARDS_DIR}/Waiting On Me.md"
_DASHBOARD_POSTPONED_PATH = f"{DASHBOARDS_DIR}/Postponed.md"

_TOOL = "obsidian-connector/dashboards"


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
    postponed = sorted(
        [i for i in items if i.status == "open" and i.postponed_until],
        key=_key_postponed,
    )
    n = len(postponed)
    item_label = f"{n} item{'s' if n != 1 else ''}"

    lines: list[str] = [
        _frontmatter("postponed", now_iso),
        "",
        "# Postponed",
        "",
        f"_Last updated: {_now_display(now_iso)}_",
        "_Open commitments snoozed to a future date._",
        "",
        f"## ({item_label})",
        "",
    ]

    if not postponed:
        lines += ["_No postponed commitments._", ""]
    else:
        lines += [
            "| Title | Project | Postponed Until | Priority |",
            "|-------|---------|-----------------|----------|",
        ]
        for s in postponed:
            lines.append(
                f"| {_wikilink_table(s)}"
                f" | {_project_label(s.project)}"
                f" | {_fmt_date(s.postponed_until)}"
                f" | {s.priority} |"
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


def update_all_dashboards(
    vault_root: Path,
    within_days: int = 7,
    now_iso: str | None = None,
) -> list[DashboardResult]:
    """Generate or update all four commitment dashboards atomically.

    A single scan of ``Commitments/`` is not shared across the four calls
    to keep each generator independent, but all four are given the same
    *ts* timestamp so ``generated_at`` is consistent.

    Parameters
    ----------
    vault_root:
        Absolute path to the Obsidian vault root.
    within_days:
        Window for the Due Soon dashboard.  Defaults to 7.
    now_iso:
        ISO 8601 timestamp shared across all four dashboards.  Defaults to UTC now.

    Returns
    -------
    list[DashboardResult]
        One result per dashboard, in order:
        Commitments, Due Soon, Waiting On Me, Postponed.
    """
    vault_root = Path(vault_root)
    ts = now_iso or datetime.now(timezone.utc).isoformat()
    return [
        generate_commitments_dashboard(vault_root, now_iso=ts),
        generate_due_soon_dashboard(vault_root, within_days=within_days, now_iso=ts),
        generate_waiting_on_me_dashboard(vault_root, now_iso=ts),
        generate_postponed_dashboard(vault_root, now_iso=ts),
    ]


__all__ = [
    "DASHBOARDS_DIR",
    "DashboardResult",
    "generate_commitments_dashboard",
    "generate_due_soon_dashboard",
    "generate_postponed_dashboard",
    "generate_waiting_on_me_dashboard",
    "update_all_dashboards",
]
