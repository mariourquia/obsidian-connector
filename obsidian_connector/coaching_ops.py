"""Thin HTTP wrappers for the Task 40 capture-service coaching endpoints.

Two read-only endpoints under ``/api/v1/coaching`` are mirrored here as
Python functions. They reuse the same transport helper
(:func:`obsidian_connector.commitment_ops._service_get_json`) so all
the Task 35 timeout / retry / scheme validation behavior is shared.

- :func:`get_action_recommendations` -> ``/api/v1/coaching/action/{id}``
- :func:`list_review_recommendations` -> ``/api/v1/coaching/review``

Both functions are tolerant to missing keys so a connector pointing at
an older capture service never crashes. They always return the
standard :func:`_service_get_json` envelope. Never raises.
"""
from __future__ import annotations

import urllib.parse

from obsidian_connector.commitment_ops import _service_get_json


# ---------------------------------------------------------------------------
# Individual endpoint wrappers
# ---------------------------------------------------------------------------


def get_action_recommendations(
    action_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/coaching/action/{action_id}`` (Task 40).

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, action_id, recommendations: [{code, label,
    action_verb, confidence, rationale, suggested_inputs}, ...]}``. The
    recommendation list is sorted alphabetically by ``code`` so the
    response is byte-identical for identical DB state.

    Error surfaces match the server side: 404 (unknown action) and
    409 (terminal action) surface as ``{ok: False, status_code: 404}``
    / ``{ok: False, status_code: 409}``. Never raises.
    """
    if not action_id or not isinstance(action_id, str):
        return {"ok": False, "error": "action_id must be a non-empty string"}
    quoted = urllib.parse.quote(action_id, safe="")
    path = f"/api/v1/coaching/action/{quoted}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_review_recommendations(
    *,
    since_days: int = 7,
    limit: int = 50,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/coaching/review`` (Task 40).

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, since_days, limit, items: [{action_id, title,
    urgency, impact_score, recommendations: [...]}, ...]}``. Items are
    sorted by ``(impact_score DESC, action_id ASC)``.

    Args:
        since_days: Rolling window against ``actions.updated_at``
            (server-side bounds: ``[1, 365]``). Default 7.
        limit: Max items (server caps at 200). Default 50.
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
        token: Overrides ``OBSIDIAN_CAPTURE_SERVICE_TOKEN``.

    Never raises.
    """
    params: list[tuple[str, str]] = [
        ("since_days", str(int(since_days))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/coaching/review?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


__all__ = [
    "get_action_recommendations",
    "list_review_recommendations",
]
