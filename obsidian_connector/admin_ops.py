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

from obsidian_connector.commitment_ops import _service_get_json


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


__all__ = [
    "get_queue_health",
    "list_delivery_failures",
    "list_pending_approvals",
    "list_stale_sync_devices",
    "get_system_health",
]
