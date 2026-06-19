# obsidian_connector/creation_next.py
"""Explainable next-action engine for the Creation Vault OS (Task 3).

Produces ranked, reasoned ``Recommendation`` dicts that answer:
"What should Mario (or an agent) work on next?"

Candidates come from:
- Backlog items with status ready/in_progress/blocked.
- Repos whose classification warrants action (waiting-on-pr-review,
  blocked-by-tests, needs-sync, behind, stale).

Each candidate is scored via ``score_item`` (pure; no I/O), which
multiplies per-factor normalized signals by configurable weights and
returns the total plus a named factor breakdown.  ``next_actions``
assembles candidates, scores, sorts deterministically, and returns the
top N ``Recommendation`` dicts.

See docs/architecture/creation-dashboard.md §5 for the Recommendation
shape and §§ Global/Project/Repo explanation of the three scope levels.

Read-only contract: never appends events, never materializes notes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Weight defaults
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "urgency": 2.0,
    "impact": 1.5,
    "dependency_unlock": 2.5,
    "stale_age": 0.8,
    "user_emphasis": 1.2,
    "deadline": 1.8,
    "unfinished_session": 1.0,
    "repo_readiness": 1.3,
}

# Repo classifications that indicate the repo is ready for the next task
_READY_CLASSIFICATIONS = frozenset({"clean-and-ready", "ready-for-next-agent"})

# Repo classifications that produce a candidate action
_ACTIONABLE_CLASSIFICATIONS = frozenset({
    "waiting-on-pr-review",
    "blocked-by-tests",
    "needs-sync",
    "behind",
    "stale",
})

# Backlog statuses to include as candidates (skip done/archived/idea)
_CANDIDATE_STATUSES = frozenset({"ready", "in_progress", "blocked"})

# Priority order for numeric ranking: P0 = 0, P1 = 1, ...
_PRIORITY_NUM: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


# ---------------------------------------------------------------------------
# load_weights
# ---------------------------------------------------------------------------

def load_weights(vault: "str | Path | None") -> dict[str, float]:
    """Read ``creation/dashboard-weights.json`` from the vault and merge over
    ``DEFAULT_WEIGHTS``.  Returns defaults when the file is absent, empty,
    or malformed JSON.
    """
    weights = dict(DEFAULT_WEIGHTS)
    if vault is None:
        return weights
    try:
        config_path = Path(vault) / "creation" / "dashboard-weights.json"
        if not config_path.is_file():
            return weights
        raw = config_path.read_text(encoding="utf-8").strip()
        if not raw:
            return weights
        overrides = json.loads(raw)
        if isinstance(overrides, dict):
            for key, val in overrides.items():
                if key in weights and isinstance(val, (int, float)):
                    weights[key] = float(val)
    except Exception:
        # Any I/O or JSON error → fall back to defaults
        pass
    return weights


# ---------------------------------------------------------------------------
# score_item  (pure — no I/O)
# ---------------------------------------------------------------------------

def score_item(
    item: dict,
    *,
    repo_status: "Any | None" = None,
    signals: "dict | None" = None,
    weights: dict,
) -> "tuple[float, list[tuple[str, float]]]":
    """Score a candidate backlog item (or repo-derived action) against weights.

    Parameters
    ----------
    item:
        A backlog item dict (or synthetic dict for repo candidates) with at
        least the fields produced by ``list_backlog``.
    repo_status:
        Optional ``RepoStatus`` for the item's primary repo.  If supplied,
        its ``classification`` drives the ``repo_readiness`` signal.
    signals:
        Caller-supplied float signals (0..1 each) for the ephemeral factors
        that cannot be derived from the backlog item alone:
        ``stale_age``, ``user_emphasis``, ``deadline``,
        ``unfinished_session``.  Missing keys default to 0.
    weights:
        Weight dict (use ``load_weights`` or ``DEFAULT_WEIGHTS``).

    Returns
    -------
    (total, factors)
        ``total`` is the weighted sum.
        ``factors`` is ``[(name, contribution), ...]`` sorted by contribution
        descending, containing only non-zero entries.
    """
    signals = signals or {}

    # --- normalize each signal to [0, 1] ------------------------------------

    # urgency: 0-10 int
    norm_urgency = min(1.0, max(0.0, float(item.get("urgency", 5)) / 10.0))

    # impact: 0-10 int
    norm_impact = min(1.0, max(0.0, float(item.get("impact", 5)) / 10.0))

    # dependency_unlock: how many items this unblocks.  The caller supplies a
    # pre-computed count via signals["dependency_unlock_count"]; default is 0
    # when the key is absent.  No fallback computation is performed here.
    n_unblocked = float(signals.get("dependency_unlock_count", 0))
    norm_dep_unlock = min(1.0, n_unblocked / 3.0)

    # stale_age, user_emphasis, deadline, unfinished_session: caller-supplied
    norm_stale = min(1.0, max(0.0, float(signals.get("stale_age", 0.0))))
    norm_emphasis = min(1.0, max(0.0, float(signals.get("user_emphasis", 0.0))))
    norm_deadline = min(1.0, max(0.0, float(signals.get("deadline", 0.0))))
    norm_session = min(1.0, max(0.0, float(signals.get("unfinished_session", 0.0))))

    # repo_readiness: 1.0 if repo is ready, 0.3 if not, 0.0 if unknown
    if repo_status is not None:
        classification = getattr(repo_status, "classification", "unknown")
        norm_repo = 1.0 if classification in _READY_CLASSIFICATIONS else 0.3
    else:
        norm_repo = 0.5  # neutral when no repo status provided

    normalized: dict[str, float] = {
        "urgency": norm_urgency,
        "impact": norm_impact,
        "dependency_unlock": norm_dep_unlock,
        "stale_age": norm_stale,
        "user_emphasis": norm_emphasis,
        "deadline": norm_deadline,
        "unfinished_session": norm_session,
        "repo_readiness": norm_repo,
    }

    # --- weighted sum -------------------------------------------------------
    total = 0.0
    raw_factors: list[tuple[str, float]] = []
    for key, norm_val in normalized.items():
        w = float(weights.get(key, 0.0))
        contribution = w * norm_val
        total += contribution
        if contribution > 0.0:
            raw_factors.append((key, contribution))

    # Sort by contribution descending
    raw_factors.sort(key=lambda t: t[1], reverse=True)

    return total, raw_factors


# ---------------------------------------------------------------------------
# _reason_labels  (pure)
# ---------------------------------------------------------------------------

_FACTOR_LABELS: dict[str, str] = {
    "urgency": "urgency",
    "impact": "impact",
    "dependency_unlock": "dependency unlock",
    "stale_age": "stale context",
    "user_emphasis": "user emphasis",
    "deadline": "deadline",
    "unfinished_session": "unfinished session",
    "repo_readiness": "repo ready",
}

# Priority label to include in reason strings
_PRIORITY_LABEL: dict[str, str] = {
    "P0": "P0 priority",
    "P1": "P1 priority",
    "P2": "P2 priority",
    "P3": "P3 priority",
}


def _reason_strings(
    item: dict,
    factors: "list[tuple[str, float]]",
    *,
    blocked: bool = False,
    needs_decision: bool = False,
    extra: "list[str] | None" = None,
) -> list[str]:
    """Build human-readable reason list from scored factors."""
    reasons: list[str] = []

    # Priority label first if P0/P1
    prio = item.get("priority", "")
    if prio in ("P0", "P1"):
        reasons.append(_PRIORITY_LABEL.get(prio, prio))

    # Top named factors (up to 3)
    for name, _contribution in factors[:3]:
        label = _FACTOR_LABELS.get(name, name)
        reasons.append(label)

    # Special flags
    if blocked:
        reasons.append("blocked — resolve before proceeding")
    if needs_decision:
        reasons.append("requires Mario decision")
    if extra:
        reasons.extend(extra)

    # Always at least one reason
    if not reasons:
        reasons.append("candidate")

    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped


# ---------------------------------------------------------------------------
# next_actions
# ---------------------------------------------------------------------------

def next_actions(
    vault: "str | Path",
    *,
    scope: str = "global",
    project: "str | None" = None,
    repo: "str | None" = None,
    github_root: "str | Path | None" = None,
    now_iso: str,
    limit: int = 10,
    runner: "Callable | None" = None,
) -> list[dict]:
    """Build, score, and rank next-action recommendations.

    Parameters
    ----------
    vault:
        Vault root path.
    scope:
        "global" | "project" | "repo".
    project:
        Filter to a specific project slug (used when scope="project").
    repo:
        Filter to a specific repo dir_name (used when scope="repo").
    github_root:
        Root directory of local git repos.  Defaults to ``~/dev``.
    now_iso:
        ISO8601 timestamp used as the current time for repo_status calls.
    limit:
        Maximum number of recommendations to return.
    runner:
        Injectable subprocess runner passed through to ``repo_status``.
        Pass a mock in tests to stay offline.

    Returns
    -------
    list[dict]
        Each dict has the Recommendation shape from creation-dashboard.md §5:
        scope, project, repo, backlog_id, action, reason (list[str]),
        confidence, requires_mario_decision, suggested_workflow, context_pack.
    """
    from obsidian_connector import creation_backlog as cb
    from obsidian_connector import creation_repo_status as crs
    from obsidian_connector import creation_projects as cp

    vault_path = Path(vault)
    if github_root is None:
        github_root = Path.home() / "dev"
    else:
        github_root = Path(github_root)

    weights = load_weights(vault_path)

    # --- collect backlog items (filtered by scope) ---------------------------
    all_items = cb.list_backlog(vault_path)

    # Apply project filter
    if project is not None:
        all_items = [i for i in all_items if i.get("project") == project]

    # Apply repo filter: keep items whose repos list includes the target repo
    if repo is not None:
        all_items = [i for i in all_items
                     if repo in (i.get("repos") or [])]

    # Only candidate statuses
    candidate_items = [i for i in all_items
                       if i.get("status") in _CANDIDATE_STATUSES]

    # --- collect repo entries (filtered by scope) ----------------------------
    try:
        all_projects = cp.list_projects(vault_path)
    except Exception:
        all_projects = []

    # For project-scoped: only repos in that project
    if project is not None:
        proj_obj = next((p for p in all_projects if p.slug == project), None)
        if proj_obj is not None:
            target_repos = set(proj_obj.repos)
            repo_entries = cp.project_repo_entries(vault_path, proj_obj)
        else:
            target_repos = set()
            repo_entries = []
    elif repo is not None:
        # Single repo scope: find which project(s) contain it
        repo_entries = []
        for proj_obj in all_projects:
            if repo in proj_obj.repos:
                repo_entries.extend(cp.project_repo_entries(vault_path, proj_obj))
        # Deduplicate by dir_name
        seen_dirs: set[str] = set()
        deduped_entries = []
        for entry in repo_entries:
            if entry.dir_name not in seen_dirs:
                seen_dirs.add(entry.dir_name)
                deduped_entries.append(entry)
        repo_entries = [e for e in deduped_entries if e.dir_name == repo]
    else:
        # Global: all repos
        repo_entries = []
        for proj_obj in all_projects:
            repo_entries.extend(cp.project_repo_entries(vault_path, proj_obj))
        # Deduplicate
        seen_dirs2: set[str] = set()
        repo_entries_deduped = []
        for entry in repo_entries:
            if entry.dir_name not in seen_dirs2:
                seen_dirs2.add(entry.dir_name)
                repo_entries_deduped.append(entry)
        repo_entries = repo_entries_deduped

    # --- build repo status map (best-effort; offline-safe) -------------------
    repo_status_map: dict[str, "crs.RepoStatus"] = {}
    _runner_kwargs: dict = {}
    if runner is not None:
        _runner_kwargs["runner"] = runner

    for entry in repo_entries:
        try:
            rs = crs.repo_status(
                entry,
                github_root=github_root,
                now_iso=now_iso,
                with_prs=True,
                with_tests=False,
                with_build=False,
                **_runner_kwargs,
            )
            repo_status_map[entry.dir_name] = rs
        except Exception:
            pass

    # --- build candidates ---------------------------------------------------
    # Candidate: {"item": dict, "rs": RepoStatus|None, "signals": dict,
    #             "action_str": str, "project_slug": str, "repo_dir": str,
    #             "backlog_id": str|None, "blocked": bool, "is_repo_candidate": bool}

    candidates: list[dict] = []

    # 1. Backlog item candidates
    for item in candidate_items:
        item_status = item.get("status", "")
        repos_list: list[str] = item.get("repos") or []
        primary_repo = repos_list[0] if repos_list else None
        rs = repo_status_map.get(primary_repo) if primary_repo else None

        action_str = item.get("next_action") or item.get("title") or item["id"]
        is_blocked = item_status == "blocked"

        candidates.append({
            "item": item,
            "rs": rs,
            "signals": {},
            "action_str": action_str,
            "project_slug": item.get("project", ""),
            "repo_dir": primary_repo or "",
            "backlog_id": item["id"],
            "blocked": is_blocked,
            "is_repo_candidate": False,
            "needs_mario_decision": bool(item.get("needs_decision", False)),
        })

    # 2. Repo-derived candidates (from actionable classifications)
    for dir_name, rs in repo_status_map.items():
        if rs.classification not in _ACTIONABLE_CLASSIFICATIONS:
            continue

        # Don't duplicate if there's already a backlog item for this repo
        # (we always add repo candidates; they score independently)
        classification = rs.classification
        action_str = rs.next_action or f"Repo action: {dir_name}"

        # Build a synthetic item for scoring
        synthetic_item: dict[str, Any] = {
            "urgency": 5,
            "impact": 5,
            "priority": "P2",
            "needs_decision": False,
        }

        # Adjust urgency/impact by classification severity
        if classification in ("needs-sync", "blocked-by-tests"):
            synthetic_item["urgency"] = 7
            synthetic_item["impact"] = 6
            synthetic_item["priority"] = "P1"
        elif classification == "waiting-on-pr-review":
            synthetic_item["urgency"] = 6
            synthetic_item["impact"] = 7

        # For blocked-by-tests, dampen score via signals
        signals: dict[str, float] = {}
        is_blocked = classification == "blocked-by-tests"
        if is_blocked:
            signals["repo_readiness"] = 0.0  # override to dampen

        # Determine project slug from repo_status_map key
        proj_slug = ""
        for proj_obj in all_projects:
            if dir_name in proj_obj.repos:
                proj_slug = proj_obj.slug
                break

        candidates.append({
            "item": synthetic_item,
            "rs": rs,
            "signals": signals,
            "action_str": action_str,
            "project_slug": proj_slug,
            "repo_dir": dir_name,
            "backlog_id": None,
            "blocked": is_blocked,
            "is_repo_candidate": True,
            "needs_mario_decision": False,
        })

    # --- score all candidates ------------------------------------------------
    # Each entry: (damped_total, tie_key, factors, cand)
    # score_item is called exactly once per candidate; factors are stored and
    # reused during reason-building to avoid a redundant second call.
    scored: list[tuple[float, str, list, dict]] = []
    for cand in candidates:
        total, factors = score_item(
            cand["item"],
            repo_status=cand["rs"],
            signals=cand["signals"],
            weights=weights,
        )
        # Dampen blocked candidates further (halve the score)
        if cand["blocked"]:
            total *= 0.5

        # Repo candidates use dir_name as tie-key (stable identifier);
        # backlog items use backlog_id.
        if cand["is_repo_candidate"]:
            tie_key = cand["repo_dir"]
        else:
            tie_key = cand["backlog_id"] or cand["action_str"]
        scored.append((total, tie_key, factors, cand))

    # Sort: score desc, then tie_key asc (deterministic)
    scored.sort(key=lambda t: (-t[0], t[1]))

    # --- build Recommendation dicts ------------------------------------------
    results: list[dict] = []

    # Compute max score for confidence normalization
    max_score = scored[0][0] if scored else 1.0
    if max_score <= 0.0:
        max_score = 1.0

    for total, _tie_key, factors, cand in scored[:limit]:
        # Reuse the factors already computed during scoring — no second call.
        is_blocked = cand["blocked"]

        reason = _reason_strings(
            cand["item"],
            factors,
            blocked=is_blocked,
            needs_decision=cand["needs_mario_decision"],
        )

        # Append repo-specific reason if this is a repo candidate
        if cand["is_repo_candidate"] and cand["rs"] is not None:
            rs_blockers = list(cand["rs"].blockers)
            if rs_blockers:
                reason.append(rs_blockers[0])

        confidence = min(1.0, total / max_score) if max_score > 0 else 0.0

        rec: dict[str, Any] = {
            "scope": scope,
            "project": cand["project_slug"] or None,
            "repo": cand["repo_dir"] or None,
            "backlog_id": cand["backlog_id"],
            "action": cand["action_str"],
            "reason": reason,
            "confidence": round(confidence, 4),
            "requires_mario_decision": cand["needs_mario_decision"],
            "suggested_workflow": None,  # best-effort; v0 leaves as None
            "context_pack": None,        # best-effort; v0 leaves as None
        }
        results.append(rec)

    return results
