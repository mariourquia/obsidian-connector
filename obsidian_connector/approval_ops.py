"""Thin HTTP wrappers for the Task 36 approval UX endpoints.

Four endpoints on the capture service are mirrored here as Python
functions. They reuse the same transport helpers
(``obsidian_connector.commitment_ops._service_get_json`` and
``_service_post_json``) so Task 35 timeout / auth / scheme behavior
is shared with every other service wrapper in the connector.

- :func:`get_delivery_detail` -> ``GET /api/v1/deliveries/{id}``
- :func:`bulk_approve_deliveries` -> ``POST /api/v1/deliveries/bulk-approve``
- :func:`bulk_reject_deliveries`  -> ``POST /api/v1/deliveries/bulk-reject``
- :func:`get_approval_digest` -> ``GET /api/v1/deliveries/approval-digest``

All four are tolerant to missing keys and transport failures so a
connector pointing at an older capture service never crashes. They
always return a dict envelope.

The ``approved`` / ``rejected`` / ``skipped`` lists always surface on
the bulk response so the CLI can render a per-delivery outcome even
when every input id fell into the skip bucket.
"""
from __future__ import annotations

import urllib.parse

from obsidian_connector.commitment_ops import (
    _service_get_json,
    _service_post_json,
)


__all__ = [
    "get_delivery_detail",
    "bulk_approve_deliveries",
    "bulk_reject_deliveries",
    "get_approval_digest",
]


def get_delivery_detail(
    delivery_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/deliveries/{delivery_id}``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload shape is ``{ok, delivery: {...}, action: {...} | None,
    risk_factors: [...], approval_history: [...]}``. A 404 surfaces as
    ``{ok: False, status_code: 404, error: "..."}``. Never raises.

    Args:
        delivery_id: Server-side delivery id (``dlv_...``).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
        token: Overrides ``OBSIDIAN_CAPTURE_SERVICE_TOKEN``.
    """
    if not delivery_id or not isinstance(delivery_id, str):
        return {"ok": False, "error": "delivery_id must be a non-empty string"}
    quoted = urllib.parse.quote(delivery_id, safe="")
    path = f"/api/v1/deliveries/{quoted}"
    return _service_get_json(path, service_url=service_url, token=token)


def bulk_approve_deliveries(
    delivery_ids: list[str] | tuple[str, ...],
    *,
    note: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/deliveries/bulk-approve``.

    Batches single-row approvals. Returns the
    :func:`_service_post_json` envelope. On success the payload shape
    is ``{ok, decision: "approved", requested, approved: [...],
    rejected: [], skipped: [{delivery_id, reason, detail}]}``. The
    server caps the batch at ``MAX_BULK_APPROVAL_IDS`` (default 50) —
    exceeding returns a 400 surfaced as ``{ok: False, status_code:
    400, error: "..."}``. Per-row skips do not abort the batch.

    Args:
        delivery_ids: Non-empty sequence of delivery ids.
        note: Optional reason recorded on every audit row (max 500 chars).
        service_url: Overrides ``OBSIDIAN_CAPTURE_SERVICE_URL``.
        token: Overrides ``OBSIDIAN_CAPTURE_SERVICE_TOKEN``.
    """
    return _bulk_call(
        "/api/v1/deliveries/bulk-approve",
        delivery_ids=delivery_ids,
        note=note,
        service_url=service_url,
        token=token,
    )


def bulk_reject_deliveries(
    delivery_ids: list[str] | tuple[str, ...],
    *,
    note: str | None = None,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/deliveries/bulk-reject``. Mirror of bulk-approve."""
    return _bulk_call(
        "/api/v1/deliveries/bulk-reject",
        delivery_ids=delivery_ids,
        note=note,
        service_url=service_url,
        token=token,
    )


def get_approval_digest(
    *,
    since_hours: int = 24,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/deliveries/approval-digest?since_hours=...``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload shape is ``{ok, since_hours, pending_total,
    counts_by_channel, counts_by_urgency, oldest_pending_age_seconds,
    top_pending: [...], recent_decisions_count, generated_at}``.
    """
    params = [("since_hours", str(int(since_hours)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/deliveries/approval-digest?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bulk_call(
    path: str,
    *,
    delivery_ids: list[str] | tuple[str, ...],
    note: str | None,
    service_url: str | None,
    token: str | None,
) -> dict:
    """Shared implementation for bulk-approve + bulk-reject."""
    if not delivery_ids:
        return {
            "ok": False,
            "error": "delivery_ids must be a non-empty list of strings",
        }
    ids = [str(d) for d in delivery_ids]
    if not all(ids):
        return {
            "ok": False,
            "error": "delivery_ids must be a non-empty list of strings",
        }
    body: dict = {"delivery_ids": ids}
    if note is not None:
        body["note"] = str(note)
    return _service_post_json(
        path, body=body, service_url=service_url, token=token,
    )
