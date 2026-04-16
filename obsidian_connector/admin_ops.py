"""Thin HTTP wrappers for the Task 44 capture-service admin endpoints.

Five read-only endpoints under ``/api/v1/admin`` are mirrored here as
Python functions. They reuse the same transport helper
(:func:`obsidian_connector.commitment_ops._service_get_json`) so all
the Task 35 timeout / retry / scheme validation behavior is shared.

- :func:`get_queue_health` -> ``/api/v1/admin/queue-health``
- :func:`list_delivery_failures` -> ``/api/v1/admin/delivery-failures``
- :func:`list_pending_approvals` -> ``/api/v1/admin/pending-approvals``
- :func:`list_stale_sync_devices` -> ``/api/v1/admin/stale-sync-devices``
- :func:`get_system_health` -> ``/api/v1/admin/system-health``

All functions are tolerant to missing keys so a connector pointing at
an older capture service never crashes. They always return a dict.
Never raises.
"""
from __future__ import annotations

import urllib.parse

from obsidian_connector.commitment_ops import _service_get_json, _service_post_json


# ---------------------------------------------------------------------------
# Individual endpoint wrappers
# ---------------------------------------------------------------------------


def get_queue_health(
    *,
    since_hours: int = 24,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/admin/queue-health?since_hours=...``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{enabled, reachable, counts, oldest_pending_age_seconds,
    error_rate, since_hours, window_done, window_failed}``. When the
    queue poller is off on the service side, ``enabled`` is ``False``
    and the counts are empty. Never raises.
    """
    params = [("since_hours", str(int(since_hours)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/admin/queue-health?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_delivery_failures(
    *,
    since_hours: int = 24,
    limit: int = 100,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/admin/delivery-failures``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{since_hours, limit, items: [...]}`` where each item
    carries ``delivery_id``, ``action_id``, ``channel``, ``attempt``,
    ``status``, ``last_error``, ``scheduled_at``, ``dispatched_at``,
    ``action_title``. Never raises.
    """
    params = [
        ("since_hours", str(int(since_hours))),
        ("limit", str(int(limit))),
    ]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/admin/delivery-failures?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_pending_approvals(
    *,
    limit: int = 100,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/admin/pending-approvals?limit=...``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{limit, items: [...]}`` where each item carries
    ``delivery_id``, ``action_id``, ``channel``, ``target``, ``status``,
    ``scheduled_at``, ``delivery_created_at``, ``action_title``,
    ``action_priority``, ``action_lifecycle_stage``. Never raises.
    """
    params = [("limit", str(int(limit)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/admin/pending-approvals?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def list_stale_sync_devices(
    *,
    threshold_hours: int = 24,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/admin/stale-sync-devices?threshold_hours=...``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{threshold_hours, items: [...]}`` where each item
    carries ``device_id``, ``last_synced_at``, ``hours_since_last_sync``,
    ``platform``, ``app_version``, ``pending_ops_count``. Never raises.
    """
    params = [("threshold_hours", str(int(threshold_hours)))]
    query = urllib.parse.urlencode(params)
    path = f"/api/v1/admin/stale-sync-devices?{query}"
    return _service_get_json(path, service_url=service_url, token=token)


def get_system_health(
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/admin/system-health``.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is the composite summary: ``{overall_status, generated_at,
    doctor: {counts, checks}, queue, deliveries, approvals, devices}``.
    All nested keys are optional on older service versions — callers
    should tolerate missing keys with ``.get()``. Never raises.
    """
    return _service_get_json(
        "/api/v1/admin/system-health",
        service_url=service_url,
        token=token,
    )


# ---------------------------------------------------------------------------
# Task 42: cross-device management wrappers
# ---------------------------------------------------------------------------


def list_mobile_devices(
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``GET /api/v1/mobile/devices`` on the capture service.

    Returns the :func:`_service_get_json` envelope. On success the
    payload is ``{ok, devices: [{device_id, device_label, platform,
    app_version, first_seen_at, last_sync_at, pending_ops_count,
    last_cursor}, ...]}`` sorted ``last_sync_at DESC NULLS LAST``.
    Never raises.
    """
    return _service_get_json(
        "/api/v1/mobile/devices",
        service_url=service_url,
        token=token,
    )


def forget_mobile_device(
    device_id: str,
    *,
    service_url: str | None = None,
    token: str | None = None,
) -> dict:
    """Call ``POST /api/v1/mobile/devices/{device_id}/forget``.

    Atomic on the service side: drops the device row and supersedes
    its pending ops inside a single transaction. Idempotent on a
    missing device id (the service returns ``{deleted: False}``).

    Returns the :func:`_service_post_json` envelope. On success the
    payload is ``{ok, device_id, deleted, cancelled_ops}``. Never
    raises. A blank or non-string ``device_id`` short-circuits to
    ``{"ok": False, "error": "..."}`` before any HTTP call so the
    caller never wastes a round-trip.
    """
    if not device_id or not isinstance(device_id, str):
        return {"ok": False, "error": "device_id must be a non-empty string"}

    import urllib.parse

    quoted = urllib.parse.quote(device_id, safe="")
    path = f"/api/v1/mobile/devices/{quoted}/forget"
    return _service_post_json(path, service_url=service_url, token=token)


__all__ = [
    "get_queue_health",
    "list_delivery_failures",
    "list_pending_approvals",
    "list_stale_sync_devices",
    "get_system_health",
    "list_mobile_devices",
    "forget_mobile_device",
]
