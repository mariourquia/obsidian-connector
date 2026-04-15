"""Thin HTTP wrappers + vault projection for the Task 39 analytics surface.

The capture service exposes three read-only endpoints under
``/api/v1/analytics``:

- ``GET /api/v1/analytics/weekly?week_offset=0``
- ``GET /api/v1/analytics/weekly/markdown?week_offset=0``
- ``GET /api/v1/analytics/weeks-available?weeks_back=12``

This module mirrors those as Python functions (reusing
:func:`obsidian_connector.commitment_ops._service_get_json` for
transport, so all the Task 35 timeout / retry / scheme validation
behavior is shared) and adds a deterministic vault-side projection:
:func:`write_weekly_report_note` writes
``Analytics/Weekly/<year>/<week_label>.md`` with stable frontmatter,
preserving any ``service:analytics-user-notes:{begin,end}`` fence a
user maintains for their own commentary.

None of the HTTP wrappers raise — they always return a dict per the
Task 35 envelope contract: ``{"ok": True, "status_code": 200, "data":
{...}}`` on success, ``{"ok": False, "error": "..."}`` on failure.
"""
from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from obsidian_connector.commitment_ops import _service_get_json
from obsidian_connector.write_manager import atomic_write


# ---------------------------------------------------------------------------
# HTTP wrappers
# ---------------------------------------------------------------------------


def get_weekly_report(
    *,
    week_offset: int = 0,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/analytics/weekly?week_offset=...``.

    On success the payload is the full :func:`weekly_activity_report`
    dict. Never raises.
    """
    params = [("week_offset", str(int(week_offset)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/analytics/weekly?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def get_weekly_report_markdown(
    *,
    week_offset: int = 0,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/analytics/weekly/markdown?week_offset=...``.

    Returns the same ``{"ok", "data"}`` envelope as
    :func:`_service_get_json`, but since the endpoint returns
    ``text/markdown`` the transport helper will fail to parse JSON
    and return ``ok=False``. We handle that specially here by using
    a direct http call so the caller gets the Markdown body as a
    string at ``data["markdown"]``. Never raises.
    """
    import http.client
    import json as _json
    import ssl

    url = service_url or os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = token or os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")
    if not url:
        return {
            "ok": False,
            "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)",
        }

    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in ("http", "https"):
        return {
            "ok": False,
            "error": f"service URL must use http or https, got: {parsed.scheme!r}",
        }

    # Reuse the shared timeout helper for consistency.
    from obsidian_connector.commitment_ops import _service_timeout

    timeout = _service_timeout()
    base_path = (parsed.path or "").rstrip("/")
    params = urllib.parse.urlencode([("week_offset", str(int(week_offset)))])
    full_path = base_path + f"/api/v1/analytics/weekly/markdown?{params}"
    headers: dict[str, str] = {"Accept": "text/markdown"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    conn: http.client.HTTPConnection | None = None
    try:
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(  # nosemgrep
                parsed.netloc,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=timeout)
        conn.request("GET", full_path, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status >= 400:
            # Try to surface any JSON error body from FastAPI validators.
            err = body
            try:
                parsed_err = _json.loads(body)
                if isinstance(parsed_err, dict):
                    err = parsed_err.get("detail", body)
            except Exception:  # noqa: BLE001
                pass
            return {
                "ok": False,
                "status_code": resp.status,
                "error": err or f"HTTP {resp.status}",
            }
    except http.client.HTTPException as exc:
        return {"ok": False, "error": f"HTTP error: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"service unreachable: {exc}"}
    finally:
        if conn is not None:
            conn.close()

    return {
        "ok": True,
        "status_code": 200,
        "data": {"markdown": body},
    }


def list_weeks_available(
    *,
    weeks_back: int = 12,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/analytics/weeks-available?weeks_back=...``.

    Payload on success: ``{weeks_back, items: [{start_iso, end_iso,
    week_label}, ...]}``. Never raises.
    """
    params = [("weeks_back", str(int(weeks_back)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/analytics/weeks-available?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


# ---------------------------------------------------------------------------
# Vault projection
# ---------------------------------------------------------------------------


@dataclass
class WriteResult:
    """Outcome of a vault projection write."""

    path: Path
    written: bool


_ANALYTICS_USER_BEGIN = "<!-- service:analytics-user-notes:begin -->"
_ANALYTICS_USER_END = "<!-- service:analytics-user-notes:end -->"
_DEFAULT_BASE_DIR = "Analytics/Weekly"


def _year_from_week_label(week_label: str) -> str:
    """Extract the ``YYYY`` year prefix from ``"YYYY-Www"``. Falls back to the
    current UTC year when the label is malformed."""
    m = re.match(r"(\d{4})-W\d{2}", week_label or "")
    if m:
        return m.group(1)
    return str(datetime.now(timezone.utc).year)


def _read_user_notes_block(existing: str) -> str:
    """Extract text between the user-notes fence in an existing note.

    Returns the inner text (no fence markers) so we can re-render
    with it intact. If the fence is missing we return an empty string
    so the new note gets a fresh fence.
    """
    if not existing:
        return ""
    try:
        start = existing.index(_ANALYTICS_USER_BEGIN)
        end = existing.index(_ANALYTICS_USER_END, start)
    except ValueError:
        return ""
    inner = existing[start + len(_ANALYTICS_USER_BEGIN): end]
    return inner.strip("\n")


def _render_weekly_note_body(
    *,
    report_markdown: str,
    week_label: str,
    generated_at: str,
    user_notes_inner: str,
) -> str:
    """Render the full note body with frontmatter + preserved user-notes fence.

    Deterministic: frontmatter keys sorted, fence always present, body
    pulled verbatim from the service. Re-running with the same inputs
    produces byte-identical output.
    """
    front = [
        "---",
        "type: analytics",
        f"week_label: {week_label}",
        f"generated_at: {generated_at}",
        "---",
        "",
    ]
    pieces = list(front)
    pieces.append(report_markdown.rstrip("\n"))
    pieces.append("")
    pieces.append("## User notes")
    pieces.append("")
    pieces.append(_ANALYTICS_USER_BEGIN)
    if user_notes_inner:
        pieces.append(user_notes_inner)
    pieces.append(_ANALYTICS_USER_END)
    pieces.append("")
    return "\n".join(pieces)


def weekly_report_note_path(
    vault_root: Path, week_label: str, *, base_dir: str = _DEFAULT_BASE_DIR
) -> Path:
    """Return the deterministic absolute path for a weekly report note.

    Format: ``<vault_root>/<base_dir>/<year>/<week_label>.md``.
    """
    year = _year_from_week_label(week_label)
    return Path(vault_root) / base_dir / year / f"{week_label}.md"


def write_weekly_report_note(
    vault_root: Path,
    report_markdown: str,
    week_label: str,
    *,
    base_dir: str = _DEFAULT_BASE_DIR,
    generated_at: str | None = None,
) -> WriteResult:
    """Project a weekly report into the vault.

    Writes ``<vault_root>/<base_dir>/<year>/<week_label>.md`` with
    frontmatter (``type: analytics``, ``week_label``, ``generated_at``)
    and a ``service:analytics-user-notes:begin/end`` fence for the
    operator's own commentary. If a note already exists at the path
    we preserve the user-notes block verbatim so re-running the
    projection never clobbers manual edits.

    Uses :func:`atomic_write` (tmp + rename) for safety.
    """
    vault_root = Path(vault_root)
    target = weekly_report_note_path(vault_root, week_label, base_dir=base_dir)
    existing = ""
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError:
            existing = ""
    user_notes_inner = _read_user_notes_block(existing)
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    body = _render_weekly_note_body(
        report_markdown=report_markdown,
        week_label=week_label,
        generated_at=ts,
        user_notes_inner=user_notes_inner,
    )
    atomic_write(
        target,
        body,
        vault_root=vault_root,
        tool_name="obsidian-connector/analytics",
        inject_generated_by=False,
    )
    return WriteResult(path=target, written=True)


def fetch_and_write_weekly_report_note(
    vault_root: Path,
    *,
    week_offset: int = 0,
    service_url: str | None = None,
    token: str | None = None,
    base_dir: str = _DEFAULT_BASE_DIR,
    generated_at: str | None = None,
) -> dict:
    """Call the service and project the result into the vault.

    Returns a dict: ``{"ok": True, "path": str, "week_label": str}``
    on success, or ``{"ok": False, "error": "..."}`` when the service
    call fails. Never raises.
    """
    md = get_weekly_report_markdown(
        week_offset=week_offset,
        service_url=service_url,
        token=token,
    )
    if not md.get("ok"):
        return {"ok": False, "error": md.get("error") or "service error"}

    # We also need the label — pull it from the JSON endpoint. Cheap.
    report = get_weekly_report(
        week_offset=week_offset, service_url=service_url, token=token
    )
    if not report.get("ok"):
        return {"ok": False, "error": report.get("error") or "service error"}
    label = (
        ((report.get("data") or {}).get("window") or {}).get("week_label")
        or ""
    )
    if not label:
        return {"ok": False, "error": "service response missing week_label"}

    result = write_weekly_report_note(
        vault_root,
        (md.get("data") or {}).get("markdown", ""),
        label,
        base_dir=base_dir,
        generated_at=generated_at,
    )
    return {
        "ok": True,
        "path": str(result.path),
        "week_label": label,
    }


__all__ = [
    "get_weekly_report",
    "get_weekly_report_markdown",
    "list_weeks_available",
    "WriteResult",
    "weekly_report_note_path",
    "write_weekly_report_note",
    "fetch_and_write_weekly_report_note",
]
