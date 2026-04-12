"""Search result enrichment utilities for obsidian-connector."""

from __future__ import annotations

from obsidian_connector.client_fallback import ObsidianCLIError, read_note


def enrich_search_results(
    results: list[dict],
    vault: str | None = None,
    context_lines: int = 0,
    dedupe: bool = False,
    max_results: int | None = None,
) -> list[dict]:
    """Post-process raw search results from ``search_notes()``.

    Parameters
    ----------
    results:
        Raw list of dicts from ``search_notes()``.  Each dict has
        ``"file"`` (str) and ``"matches"`` (list of ``{"line": int, "text": str}``).
    vault:
        Vault name, passed through to ``read_note()`` when fetching context.
    context_lines:
        Number of lines to include before and after each match line.
        When > 0, each match dict gains ``context_before`` (list[str]) and
        ``context_after`` (list[str]) fields.
    dedupe:
        If True, keep only the first occurrence per file path.
    max_results:
        If set, truncate the result list to this many entries.

    Returns
    -------
    list[dict]
        The enriched (and possibly filtered) results.
    """
    enriched: list[dict] = list(results)

    # --- truncate -----------------------------------------------------------
    if max_results is not None and max_results >= 0:
        enriched = enriched[:max_results]

    # --- deduplicate --------------------------------------------------------
    if dedupe:
        seen: set[str] = set()
        unique: list[dict] = []
        for entry in enriched:
            file_key = entry.get("file", "")
            if file_key not in seen:
                seen.add(file_key)
                unique.append(entry)
        enriched = unique

    # --- add surrounding context lines --------------------------------------
    if context_lines > 0:
        # Cache file contents so we don't re-read the same note repeatedly.
        _content_cache: dict[str, list[str]] = {}

        for entry in enriched:
            file_path: str = entry.get("file", "")
            if file_path and file_path not in _content_cache:
                try:
                    raw = read_note(file_path, vault=vault)
                    _content_cache[file_path] = raw.split("\n")
                except ObsidianCLIError:
                    _content_cache[file_path] = []

            all_lines = _content_cache.get(file_path, [])
            total = len(all_lines)

            for match in entry.get("matches", []):
                # match["line"] is 1-based from the CLI output.
                line_idx = match.get("line", 0) - 1  # convert to 0-based

                # Compute before window.
                start_before = max(0, line_idx - context_lines)
                end_before = max(0, line_idx)
                match["context_before"] = (
                    all_lines[start_before:end_before] if total else []
                )

                # Compute after window.
                start_after = min(total, line_idx + 1)
                end_after = min(total, line_idx + 1 + context_lines)
                match["context_after"] = (
                    all_lines[start_after:end_after] if total else []
                )

    return enriched
