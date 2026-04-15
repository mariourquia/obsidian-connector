"""Vault import / migration tools for legacy notes (Task 43).

Connector-side companion to the service-side Task 43 contract (PR #23
in ``obsidian-capture-service`` -- merge ``496bb35``). Provides four
pure phases plus a Markdown report renderer:

1. :func:`scan_markdown_files` walks a vault root and yields
   :class:`FileCandidate` rows in deterministic (sorted) path order.
2. :func:`classify_candidate` is a deterministic rule-based classifier
   that decides whether each candidate is a live capture, an
   already-managed system note, or unknown.
3. :func:`plan_import` groups classified candidates into actionable
   buckets (``to_import_as_capture``, ``to_skip_already_managed``,
   ``to_skip_size_out_of_range``, ``to_skip_unknown_kind``) plus a
   ``warnings`` list. Refuses cleanly if more than ``max_files``
   candidates are found.
4. :func:`execute_import` POSTs each entry in ``to_import_as_capture``
   to ``/api/v1/ingest/text`` with a deterministic idempotency key
   (``vault-import-<sha256[:16]>``) so re-runs collapse on the
   service-side dedup substrate. **Defaults to dry-run.** Requires
   ``dry_run=False`` AND ``confirm=True`` to actually issue HTTP
   requests; either alone yields a no-op result with a ``dry_run`` flag
   so the call site cannot accidentally mutate.
5. :func:`write_import_report` renders the result as a Markdown report
   under ``Analytics/Import/<timestamp>.md``.

Safety rails enforced by this module:

- Hard cap ``max_files`` (default 1000) refuses cleanly on overflow.
- ``dry_run=True`` default at the function boundary; CLI mirrors this
  via ``--dry-run`` default-on plus a required ``--yes`` flag.
- ``execute_import`` is non-fatal per file: a single POST failure does
  not abort the rest of the batch.
- HTTP throttle (``throttle_seconds``) between posts.

No LLM, no embeddings, no schema changes.

The transport layer reuses
:func:`obsidian_connector.commitment_ops._service_post_json` and the
shared :data:`SERVICE_REQUEST_TIMEOUT_SECONDS` env knob -- so the
Task 35 hardening (timeout, scheme allowlist, no-raise envelope) is
inherited automatically.
"""
from __future__ import annotations

import dataclasses
import fnmatch
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from obsidian_connector.write_manager import atomic_write


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILES: int = 1000
DEFAULT_MIN_SIZE: int = 10
DEFAULT_MAX_SIZE: int = 100_000
DEFAULT_THROTTLE_SECONDS: float = 0.1
DEFAULT_SOURCE_APP: str = "vault_import"
IDEMPOTENCY_KEY_PREFIX: str = "vault-import-"
INGEST_TEXT_PATH: str = "/api/v1/ingest/text"

# Folders considered already managed by the system (Commitments, Entities,
# generated dashboards, generated analytics, archive). Matched as POSIX
# path-prefix segments against the vault-relative path.
_MANAGED_PREFIXES: tuple[str, ...] = (
    "Commitments/",
    "Entities/",
    "Dashboards/",
    "Analytics/",
    "Archive/",
)

# Frontmatter ``type:`` values that mark a note as already managed.
_MANAGED_FRONTMATTER_TYPES: frozenset[str] = frozenset({
    "commitment",
    "entity",
})

# Tags that signal "ready to be imported as a capture" (high confidence).
_READY_CAPTURE_TAGS: frozenset[str] = frozenset({"capture"})

# Lower-confidence ready tags. Same bucket, different label.
_READY_CAPTURE_LOW_CONF_TAGS: frozenset[str] = frozenset({
    "idea",
    "todo",
    "action",
})

_DEFAULT_REPORT_BASE_DIR: str = "Analytics/Import"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileCandidate:
    """One Markdown file picked up by :func:`scan_markdown_files`.

    All fields are derived deterministically from the file content +
    stat info; re-scanning the same on-disk state produces identical
    rows.
    """

    path: Path  # absolute path on disk
    relative_path: str  # POSIX path relative to the scan root
    size_bytes: int
    modified_at: str  # ISO-8601 UTC, no microseconds
    title_guess: str
    content_sha256: str  # full hex digest of the file body
    has_frontmatter: bool
    frontmatter_dict: dict[str, object] = field(default_factory=dict)
    body_preview: str = ""  # first 280 chars of body without frontmatter


@dataclass(frozen=True)
class PlannedImport:
    """One file scheduled for ingest. Subset of :class:`FileCandidate`
    plus the classifier label."""

    candidate: FileCandidate
    classification: str  # ``ready_capture`` (always for this dataclass)
    confidence: str  # ``high`` or ``low``
    idempotency_key: str


@dataclass(frozen=True)
class ImportPlan:
    """Output of :func:`plan_import` -- deterministic + frozen."""

    root: Path
    total_scanned: int
    to_import_as_capture: tuple[PlannedImport, ...]
    to_skip_already_managed: tuple[FileCandidate, ...]
    to_skip_size_out_of_range: tuple[FileCandidate, ...]
    to_skip_unknown_kind: tuple[FileCandidate, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ImportFileResult:
    """One per-file outcome from :func:`execute_import`."""

    relative_path: str
    idempotency_key: str
    ok: bool
    capture_id: str | None
    duplicate: bool | None
    status_code: int | None
    error: str | None
    import_metadata_echoed: bool


@dataclass(frozen=True)
class ImportResult:
    """Aggregate outcome of :func:`execute_import`."""

    plan: ImportPlan
    dry_run: bool
    started_at: str  # ISO-8601 UTC
    finished_at: str  # ISO-8601 UTC
    posted: tuple[ImportFileResult, ...]
    succeeded: int
    failed: int
    duplicates: int
    service_url: str | None


# ---------------------------------------------------------------------------
# Helpers (frontmatter, hashing, classification)
# ---------------------------------------------------------------------------


_FRONTMATTER_FENCE_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_KEY_VALUE_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_TAG_TOKEN_RE = re.compile(r"#([A-Za-z][A-Za-z0-9_/-]*)")


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str, bool]:
    """Parse the leading ``---`` fenced YAML-like block.

    Returns ``(frontmatter_dict, body, has_frontmatter)``. We use a
    deliberately tiny YAML subset (string keys, scalar / inline-list
    values) so the import scan does not depend on a YAML library and
    is deterministic across environments. Unknown / nested constructs
    surface as raw strings -- the classifier only inspects ``type``
    and ``tags`` so this is fine.
    """
    if not text.startswith("---"):
        return {}, text, False
    m = _FRONTMATTER_FENCE_RE.match(text)
    if not m:
        return {}, text, False
    raw = m.group(1)
    body = text[m.end():]
    fm: dict[str, object] = {}
    list_key: str | None = None
    list_acc: list[str] = []
    for line in raw.splitlines():
        stripped = line.rstrip()
        if not stripped:
            list_key = None
            continue
        if list_key is not None and stripped.startswith("  - "):
            list_acc.append(stripped[4:].strip().strip('"').strip("'"))
            fm[list_key] = list(list_acc)
            continue
        if list_key is not None and stripped.startswith("- "):
            list_acc.append(stripped[2:].strip().strip('"').strip("'"))
            fm[list_key] = list(list_acc)
            continue
        list_key = None
        list_acc = []
        kv = _KEY_VALUE_LINE_RE.match(stripped)
        if not kv:
            continue
        key = kv.group(1).strip()
        value = kv.group(2).strip()
        if value == "":
            # Possibly a list header.
            list_key = key
            list_acc = []
            fm[key] = []
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            items = [
                p.strip().strip('"').strip("'")
                for p in inner.split(",")
                if p.strip()
            ]
            fm[key] = items
            continue
        # Strip surrounding quotes.
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        fm[key] = value
    return fm, body, True


def _frontmatter_tags(fm: dict[str, object]) -> set[str]:
    """Extract a normalized set of frontmatter ``tags`` (strings, no '#')."""
    raw = fm.get("tags")
    if raw is None:
        return set()
    out: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, str):
                continue
            tag = item.strip().lstrip("#").lower()
            if tag:
                out.add(tag)
    elif isinstance(raw, str):
        for token in re.split(r"[,\s]+", raw):
            tag = token.strip().lstrip("#").lower()
            if tag:
                out.add(tag)
    return out


def _body_tags(body: str) -> set[str]:
    """Find inline ``#tag`` tokens in the body. Lowercased, no '#'.

    Skip code-fence regions to avoid false positives from things like
    ``#include`` in a C snippet. Coarse skip: blocks fenced with triple
    backticks are dropped before tokenization.
    """
    if not body:
        return set()
    cleaned: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    return {m.group(1).lower() for m in _TAG_TOKEN_RE.finditer(text)}


def _title_guess(fm: dict[str, object], body: str, fallback: str) -> str:
    """Best-effort title for the candidate.

    Order: frontmatter ``title`` -> first H1 in body -> stem of file
    path. Truncated to 200 chars.
    """
    raw = fm.get("title")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:200]
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# ") and len(s) > 2:
            return s[2:].strip()[:200]
        if s and not s.startswith("#"):
            break
    return (fallback or "").strip()[:200]


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _modified_at(path: Path) -> str:
    """Return the file mtime as ISO-8601 UTC (seconds resolution)."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0)
    return dt.isoformat()


def _matches_any_glob(
    rel: str,
    patterns: Iterable[str] | None,
) -> bool:
    if not patterns:
        return False
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


# ---------------------------------------------------------------------------
# Phase 1: scan
# ---------------------------------------------------------------------------


def scan_markdown_files(
    root: Path,
    *,
    include_globs: Iterable[str] | None = None,
    exclude_globs: Iterable[str] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> Iterator[FileCandidate]:
    """Walk ``root`` and yield :class:`FileCandidate` for every ``*.md``.

    Deterministic: paths are sorted lexicographically before iteration
    so two runs against the same vault produce identical output order.

    ``include_globs`` and ``exclude_globs`` are matched against the
    POSIX vault-relative path (``"Inbox/2024/old.md"``) using
    :func:`fnmatch.fnmatch`. ``exclude_globs`` wins over ``include``.

    ``max_files`` is a soft cap on yielded rows -- the iterator stops
    after that many. :func:`plan_import` enforces a hard cap (refuses
    to plan if more would have been yielded).
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return
    paths = sorted(p for p in root.rglob("*.md") if p.is_file())
    yielded = 0
    for path in paths:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if exclude_globs and _matches_any_glob(rel, exclude_globs):
            continue
        if include_globs and not _matches_any_glob(rel, include_globs):
            continue
        if yielded >= max_files:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = len(text.encode("utf-8", errors="replace"))
        fm, body, has_fm = _parse_frontmatter(text)
        title = _title_guess(fm, body, path.stem)
        sha = _content_sha256(text)
        preview = body.lstrip()[:280]
        yield FileCandidate(
            path=path,
            relative_path=rel,
            size_bytes=size_bytes,
            modified_at=_modified_at(path),
            title_guess=title,
            content_sha256=sha,
            has_frontmatter=has_fm,
            frontmatter_dict=dict(fm),
            body_preview=preview,
        )
        yielded += 1


# ---------------------------------------------------------------------------
# Phase 2: classify
# ---------------------------------------------------------------------------


def classify_candidate(fc: FileCandidate) -> dict:
    """Deterministic classifier for one :class:`FileCandidate`.

    Returns a dict shaped:

    ``{"classification": "ready_capture" | "already_managed" | "unknown",
       "reason": "...", "confidence": "high" | "low"}``

    Rules in order:

    1. Frontmatter ``type: commitment`` -> ``already_managed`` (the note
       was already minted by the capture service).
    2. Frontmatter ``type: entity`` -> ``already_managed`` (semantic
       memory entity note).
    3. Path under ``Commitments/``, ``Entities/``, ``Dashboards/``,
       ``Analytics/``, or ``Archive/`` -> ``already_managed``.
    4. ``#capture`` tag in body or frontmatter ``tags`` -> ``ready_capture``
       (high confidence).
    5. ``#idea`` / ``#todo`` / ``#action`` tag -> ``ready_capture``
       (low confidence).
    6. Small file (< 300 bytes) without any tags -> ``unknown``.
    7. Otherwise -> ``unknown``.
    """
    fm = fc.frontmatter_dict or {}
    fm_type = fm.get("type")
    if isinstance(fm_type, str) and fm_type.strip().lower() in _MANAGED_FRONTMATTER_TYPES:
        return {
            "classification": "already_managed",
            "reason": f"frontmatter type={fm_type.strip().lower()!r}",
            "confidence": "high",
        }
    rel = fc.relative_path
    for prefix in _MANAGED_PREFIXES:
        if rel == prefix.rstrip("/") or rel.startswith(prefix):
            return {
                "classification": "already_managed",
                "reason": f"path under {prefix!r}",
                "confidence": "high",
            }
    fm_tags = _frontmatter_tags(fm)
    body_tag_set = _body_tags(fc.body_preview or "")
    all_tags = fm_tags | body_tag_set
    if all_tags & _READY_CAPTURE_TAGS:
        return {
            "classification": "ready_capture",
            "reason": "has #capture tag",
            "confidence": "high",
        }
    if all_tags & _READY_CAPTURE_LOW_CONF_TAGS:
        hit = sorted(all_tags & _READY_CAPTURE_LOW_CONF_TAGS)[0]
        return {
            "classification": "ready_capture",
            "reason": f"has #{hit} tag",
            "confidence": "low",
        }
    if fc.size_bytes < 300 and not all_tags:
        return {
            "classification": "unknown",
            "reason": "small note (<300B) without tags",
            "confidence": "low",
        }
    return {
        "classification": "unknown",
        "reason": "no capture tag and not under a managed folder",
        "confidence": "low",
    }


# ---------------------------------------------------------------------------
# Phase 3: plan
# ---------------------------------------------------------------------------


def _build_idempotency_key(content_sha256: str) -> str:
    """Deterministic key per the Task 43 service-side contract."""
    return f"{IDEMPOTENCY_KEY_PREFIX}{content_sha256[:16]}"


def plan_import(
    root: Path,
    *,
    include_globs: Iterable[str] | None = None,
    exclude_globs: Iterable[str] | None = None,
    min_size: int = DEFAULT_MIN_SIZE,
    max_size: int = DEFAULT_MAX_SIZE,
    max_files: int = DEFAULT_MAX_FILES,
) -> ImportPlan:
    """Scan + classify + bucket candidates into an :class:`ImportPlan`.

    Hard refuses with :class:`ValueError` if more than ``max_files``
    candidates exist (so an operator pointed at the wrong directory
    cannot accidentally enqueue a million-file import).
    """
    root = Path(root)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"import root not found or not a directory: {root}")
    if max_files <= 0:
        raise ValueError("max_files must be a positive integer")

    # Hard overflow guard: scan one past the cap so we can refuse cleanly.
    overflow_cap = max_files + 1
    candidates: list[FileCandidate] = []
    for fc in scan_markdown_files(
        root,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        max_files=overflow_cap,
    ):
        candidates.append(fc)
        if len(candidates) > max_files:
            raise ValueError(
                f"vault has more than max_files={max_files} markdown files; "
                "narrow include/exclude globs or raise max_files"
            )

    to_capture: list[PlannedImport] = []
    skip_managed: list[FileCandidate] = []
    skip_size: list[FileCandidate] = []
    skip_unknown: list[FileCandidate] = []
    warnings: list[str] = []

    for fc in candidates:
        # Size filter applies first so tiny / huge legacy files don't
        # masquerade as ready captures.
        if fc.size_bytes < min_size or fc.size_bytes > max_size:
            skip_size.append(fc)
            continue
        verdict = classify_candidate(fc)
        cls = verdict.get("classification")
        if cls == "already_managed":
            skip_managed.append(fc)
            continue
        if cls == "ready_capture":
            confidence = str(verdict.get("confidence") or "low")
            key = _build_idempotency_key(fc.content_sha256)
            to_capture.append(
                PlannedImport(
                    candidate=fc,
                    classification="ready_capture",
                    confidence=confidence,
                    idempotency_key=key,
                )
            )
            continue
        skip_unknown.append(fc)

    # Warnings: duplicate content hashes (would collapse on the service
    # side; surface to the operator so they can prune obvious dupes).
    seen: dict[str, str] = {}
    for plan in to_capture:
        sha = plan.candidate.content_sha256
        if sha in seen:
            warnings.append(
                f"duplicate content_sha256 in to_import_as_capture: "
                f"{plan.candidate.relative_path!r} matches {seen[sha]!r}"
            )
        else:
            seen[sha] = plan.candidate.relative_path

    return ImportPlan(
        root=root,
        total_scanned=len(candidates),
        to_import_as_capture=tuple(to_capture),
        to_skip_already_managed=tuple(skip_managed),
        to_skip_size_out_of_range=tuple(skip_size),
        to_skip_unknown_kind=tuple(skip_unknown),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Phase 4: execute (POST to /api/v1/ingest/text)
# ---------------------------------------------------------------------------


def _build_ingest_text_body(
    plan: PlannedImport,
    *,
    source_app: str,
) -> dict:
    """Build the JSON body for ``/api/v1/ingest/text``.

    Carries the import metadata under ``context.extra`` per the
    service-side contract so the response echoes
    ``import_metadata: {source_path, source_modified_at}``. Also sets
    ``context.entrypoint = "vault_import"`` which is the secondary
    trigger.
    """
    fc = plan.candidate
    # The service caps text at 8000 chars on the IngestTextRequest model;
    # truncate at 7500 to leave headroom and avoid 422s on huge legacy
    # notes.
    text = fc.body_preview if fc.body_preview else ""
    if not text:
        # Re-read body from disk only if the preview was truncated to
        # nothing (rare -- body_preview is the lstripped first 280
        # chars, sufficient as a payload).
        try:
            full = fc.path.read_text(encoding="utf-8")
            _, body, _ = _parse_frontmatter(full)
            text = body.strip() or full.strip() or fc.title_guess or fc.relative_path
        except (OSError, UnicodeDecodeError):
            text = fc.title_guess or fc.relative_path
    text = (text or "").strip()
    if len(text) > 7500:
        text = text[:7500].rstrip()
    if not text:
        text = fc.title_guess or fc.relative_path

    extra: dict[str, object] = {
        "source_path": fc.relative_path,
        "source_modified_at": fc.modified_at,
        "source_sha256": fc.content_sha256,
        "title_guess": fc.title_guess,
        "import_confidence": plan.confidence,
    }
    return {
        "source_app": source_app,
        "text": text,
        "context": {
            "entrypoint": "vault_import",
            "capture_mode": "import",
            "extra": extra,
        },
    }


def _envelope_to_result(plan: PlannedImport, envelope: dict) -> ImportFileResult:
    """Map a ``_service_post_json`` envelope onto :class:`ImportFileResult`."""
    if envelope.get("ok"):
        data = envelope.get("data") or {}
        meta = data.get("import_metadata") or {}
        echoed = bool(
            isinstance(meta, dict)
            and meta.get("source_path") == plan.candidate.relative_path
        )
        return ImportFileResult(
            relative_path=plan.candidate.relative_path,
            idempotency_key=plan.idempotency_key,
            ok=True,
            capture_id=data.get("capture_id"),
            duplicate=bool(data.get("duplicate")),
            status_code=int(envelope.get("status_code") or 200),
            error=None,
            import_metadata_echoed=echoed,
        )
    return ImportFileResult(
        relative_path=plan.candidate.relative_path,
        idempotency_key=plan.idempotency_key,
        ok=False,
        capture_id=None,
        duplicate=None,
        status_code=envelope.get("status_code"),
        error=str(envelope.get("error") or "unknown error"),
        import_metadata_echoed=False,
    )


def _post_ingest_text_with_key(
    plan: PlannedImport,
    *,
    service_url: str | None,
    token: str | None,
    source_app: str,
) -> ImportFileResult:
    """Direct ``http.client`` POST so we can attach ``X-Idempotency-Key``.

    Mirrors :func:`obsidian_connector.commitment_ops._service_post_json`
    behavior (timeout, scheme allowlist, no-raise envelope) but adds
    the import-required idempotency header. Never raises.
    """
    import http.client
    import json as _json
    import os
    import ssl
    import urllib.parse

    from obsidian_connector.commitment_ops import _service_timeout

    url = service_url or os.getenv("OBSIDIAN_CAPTURE_SERVICE_URL")
    key = token or os.getenv("OBSIDIAN_CAPTURE_SERVICE_TOKEN")
    timeout = _service_timeout()
    if not url:
        return _envelope_to_result(
            plan,
            {
                "ok": False,
                "error": "service not configured (set OBSIDIAN_CAPTURE_SERVICE_URL)",
            },
        )
    parsed = urllib.parse.urlparse(url.rstrip("/"))
    if parsed.scheme not in ("http", "https"):
        return _envelope_to_result(
            plan,
            {
                "ok": False,
                "error": f"service URL must use http or https, got: {parsed.scheme!r}",
            },
        )
    base_path = (parsed.path or "").rstrip("/")
    full_path = base_path + INGEST_TEXT_PATH
    body = _build_ingest_text_body(plan, source_app=source_app)
    body_bytes = _json.dumps(body).encode("utf-8")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Idempotency-Key": plan.idempotency_key,
    }
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
        conn.request("POST", full_path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        if resp.status >= 400:
            return _envelope_to_result(
                plan,
                {
                    "ok": False,
                    "status_code": resp.status,
                    "error": raw or f"HTTP {resp.status}",
                },
            )
        try:
            data = _json.loads(raw) if raw else {}
        except (ValueError, _json.JSONDecodeError) as exc:
            return _envelope_to_result(
                plan,
                {"ok": False, "error": f"service response malformed: {exc}"},
            )
        return _envelope_to_result(
            plan,
            {"ok": True, "status_code": resp.status, "data": data},
        )
    except http.client.HTTPException as exc:
        return _envelope_to_result(
            plan, {"ok": False, "error": f"HTTP error: {exc}"}
        )
    except OSError as exc:
        return _envelope_to_result(
            plan, {"ok": False, "error": f"service unreachable: {exc}"}
        )
    finally:
        if conn is not None:
            conn.close()


def execute_import(
    plan: ImportPlan,
    *,
    service_url: str | None = None,
    token: str | None = None,
    source_app: str = DEFAULT_SOURCE_APP,
    throttle_seconds: float = DEFAULT_THROTTLE_SECONDS,
    dry_run: bool = True,
    confirm: bool = False,
    sleep: object = None,
    monotonic: object = None,
) -> ImportResult:
    """Execute a planned import.

    Safety contract:

    - ``dry_run=True`` (the default) -- never POSTs. Returns an
      :class:`ImportResult` with empty ``posted`` and zero
      success/failure counts.
    - ``dry_run=False`` AND ``confirm=False`` -- still treated as a
      dry-run (the call site forgot the safety opt-in). Logged in
      ``warnings`` of the wrapped plan via the ``finished_at`` notes.
    - ``dry_run=False`` AND ``confirm=True`` -- POSTs each entry in
      ``plan.to_import_as_capture`` to ``/api/v1/ingest/text`` with a
      deterministic ``X-Idempotency-Key`` so re-runs collapse on the
      server-side dedup substrate.

    Per-file failures are non-fatal: the failing :class:`ImportFileResult`
    records the error and the loop continues.

    ``sleep`` and ``monotonic`` are injection points for tests so the
    throttle path can be exercised without real wall-clock waits.
    """
    sleep_fn = sleep if callable(sleep) else time.sleep
    mono_fn = monotonic if callable(monotonic) else time.monotonic
    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if dry_run or not confirm:
        finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return ImportResult(
            plan=plan,
            dry_run=True,
            started_at=started,
            finished_at=finished,
            posted=(),
            succeeded=0,
            failed=0,
            duplicates=0,
            service_url=service_url,
        )

    posted: list[ImportFileResult] = []
    succeeded = 0
    failed = 0
    duplicates = 0
    last_post_at: float | None = None
    throttle = max(0.0, float(throttle_seconds or 0.0))

    for plan_item in plan.to_import_as_capture:
        if last_post_at is not None and throttle > 0:
            elapsed = mono_fn() - last_post_at
            wait = throttle - elapsed
            if wait > 0:
                sleep_fn(wait)
        result = _post_ingest_text_with_key(
            plan_item,
            service_url=service_url,
            token=token,
            source_app=source_app,
        )
        last_post_at = mono_fn()
        posted.append(result)
        if result.ok:
            succeeded += 1
            if result.duplicate:
                duplicates += 1
        else:
            failed += 1

    finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return ImportResult(
        plan=plan,
        dry_run=False,
        started_at=started,
        finished_at=finished,
        posted=tuple(posted),
        succeeded=succeeded,
        failed=failed,
        duplicates=duplicates,
        service_url=service_url,
    )


# ---------------------------------------------------------------------------
# Phase 5: write report
# ---------------------------------------------------------------------------


def default_report_path(
    vault_root: Path,
    *,
    base_dir: str = _DEFAULT_REPORT_BASE_DIR,
    timestamp: str | None = None,
) -> Path:
    """Compute the default report path: ``Analytics/Import/<ts>.md``.

    ``timestamp`` defaults to ISO-8601 UTC seconds with colons replaced
    by hyphens so the path is filesystem-safe on every platform.
    """
    ts = timestamp or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    safe = ts.replace(":", "-")
    return Path(vault_root) / base_dir / f"{safe}.md"


def _render_report(result: ImportResult) -> str:
    """Render the import result as deterministic Markdown."""
    plan = result.plan
    lines: list[str] = [
        "---",
        "type: import-report",
        f"started_at: {result.started_at}",
        f"finished_at: {result.finished_at}",
        f"dry_run: {'true' if result.dry_run else 'false'}",
        f"root: {plan.root}",
        f"total_scanned: {plan.total_scanned}",
        f"to_import_as_capture: {len(plan.to_import_as_capture)}",
        f"to_skip_already_managed: {len(plan.to_skip_already_managed)}",
        f"to_skip_size_out_of_range: {len(plan.to_skip_size_out_of_range)}",
        f"to_skip_unknown_kind: {len(plan.to_skip_unknown_kind)}",
        f"posted: {len(result.posted)}",
        f"succeeded: {result.succeeded}",
        f"failed: {result.failed}",
        f"duplicates: {result.duplicates}",
        "---",
        "",
        "# Vault Import Report",
        "",
        f"- Root: `{plan.root}`",
        f"- Started: {result.started_at}",
        f"- Finished: {result.finished_at}",
        f"- Mode: **{'dry-run' if result.dry_run else 'executed'}**",
        f"- Service URL: `{result.service_url or '(env / not set)'}`",
        "",
        "## Summary",
        "",
        f"- Files scanned: {plan.total_scanned}",
        f"- Planned imports: {len(plan.to_import_as_capture)}",
        f"- Skipped (already managed): {len(plan.to_skip_already_managed)}",
        f"- Skipped (size out of range): {len(plan.to_skip_size_out_of_range)}",
        f"- Skipped (unknown kind): {len(plan.to_skip_unknown_kind)}",
        f"- Posted: {len(result.posted)}"
        f" -- succeeded: {result.succeeded},"
        f" failed: {result.failed},"
        f" duplicates collapsed: {result.duplicates}",
        "",
    ]

    if plan.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in plan.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Planned imports")
    lines.append("")
    if not plan.to_import_as_capture:
        lines.append("_(none)_")
        lines.append("")
    else:
        lines.append("| Path | Confidence | Bytes | Idempotency key |")
        lines.append("|------|------------|-------|-----------------|")
        for plan_item in plan.to_import_as_capture:
            fc = plan_item.candidate
            lines.append(
                f"| `{fc.relative_path}` | {plan_item.confidence}"
                f" | {fc.size_bytes} | `{plan_item.idempotency_key}` |"
            )
        lines.append("")

    if result.posted:
        lines.append("## Post results")
        lines.append("")
        lines.append("| Path | Status | capture_id | dup | echoed | error |")
        lines.append("|------|--------|------------|-----|--------|-------|")
        for r in result.posted:
            status = "ok" if r.ok else f"fail ({r.status_code or '-'})"
            cap = r.capture_id or "-"
            dup = "yes" if r.duplicate else "no"
            echo = "yes" if r.import_metadata_echoed else "no"
            err = (r.error or "").replace("|", "/").strip()
            if len(err) > 120:
                err = err[:117] + "..."
            lines.append(
                f"| `{r.relative_path}` | {status} | `{cap}` | {dup}"
                f" | {echo} | {err or '-'} |"
            )
        lines.append("")

    if plan.to_skip_already_managed:
        lines.append("## Skipped: already managed")
        lines.append("")
        for fc in plan.to_skip_already_managed:
            lines.append(f"- `{fc.relative_path}`")
        lines.append("")

    if plan.to_skip_size_out_of_range:
        lines.append("## Skipped: size out of range")
        lines.append("")
        for fc in plan.to_skip_size_out_of_range:
            lines.append(f"- `{fc.relative_path}` ({fc.size_bytes} bytes)")
        lines.append("")

    if plan.to_skip_unknown_kind:
        lines.append("## Skipped: unknown kind")
        lines.append("")
        for fc in plan.to_skip_unknown_kind:
            lines.append(f"- `{fc.relative_path}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_import_report(
    result: ImportResult,
    report_path: Path,
    *,
    vault_root: Path | None = None,
) -> Path:
    """Write the Markdown report to ``report_path`` via :func:`atomic_write`.

    Parents are created on demand. ``vault_root`` is passed through to
    :func:`atomic_write` for the ``ALLOWED_WRITE_ROOTS`` guard; when
    omitted we infer it from ``report_path`` by walking two levels up
    (the canonical layout is ``<vault>/Analytics/Import/<ts>.md``).
    """
    body = _render_report(result)
    target = Path(report_path)
    if vault_root is None:
        # Default layout: <vault>/Analytics/Import/<file>.md
        vault_root = target.parent.parent.parent
    atomic_write(
        target,
        body,
        vault_root=Path(vault_root),
        tool_name="obsidian-connector/import",
        inject_generated_by=False,
    )
    return target


# ---------------------------------------------------------------------------
# Convenience helpers (CLI / MCP)
# ---------------------------------------------------------------------------


def plan_to_dict(plan: ImportPlan) -> dict:
    """Render an :class:`ImportPlan` as a JSON-serializable dict.

    Stable shape so MCP / CLI consumers can rely on the field names.
    """
    return {
        "root": str(plan.root),
        "total_scanned": plan.total_scanned,
        "to_import_as_capture": [
            {
                "path": p.candidate.relative_path,
                "title_guess": p.candidate.title_guess,
                "size_bytes": p.candidate.size_bytes,
                "modified_at": p.candidate.modified_at,
                "content_sha256": p.candidate.content_sha256,
                "idempotency_key": p.idempotency_key,
                "confidence": p.confidence,
            }
            for p in plan.to_import_as_capture
        ],
        "to_skip_already_managed": [
            fc.relative_path for fc in plan.to_skip_already_managed
        ],
        "to_skip_size_out_of_range": [
            {"path": fc.relative_path, "size_bytes": fc.size_bytes}
            for fc in plan.to_skip_size_out_of_range
        ],
        "to_skip_unknown_kind": [
            fc.relative_path for fc in plan.to_skip_unknown_kind
        ],
        "warnings": list(plan.warnings),
    }


def result_to_dict(result: ImportResult) -> dict:
    """Render an :class:`ImportResult` as a JSON-serializable dict."""
    return {
        "dry_run": result.dry_run,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "service_url": result.service_url,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "duplicates": result.duplicates,
        "posted": [dataclasses.asdict(r) for r in result.posted],
        "plan": plan_to_dict(result.plan),
    }


__all__ = [
    "DEFAULT_MAX_FILES",
    "DEFAULT_MIN_SIZE",
    "DEFAULT_MAX_SIZE",
    "DEFAULT_THROTTLE_SECONDS",
    "DEFAULT_SOURCE_APP",
    "IDEMPOTENCY_KEY_PREFIX",
    "INGEST_TEXT_PATH",
    "FileCandidate",
    "PlannedImport",
    "ImportPlan",
    "ImportFileResult",
    "ImportResult",
    "scan_markdown_files",
    "classify_candidate",
    "plan_import",
    "execute_import",
    "default_report_path",
    "write_import_report",
    "plan_to_dict",
    "result_to_dict",
]
