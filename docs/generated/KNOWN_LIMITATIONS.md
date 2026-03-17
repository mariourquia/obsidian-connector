---
title: "Known Limitations: v0.2.0"
status: draft
# generated, do not edit
owner: mariourquia
last_reviewed: "2026-03-16"
---

# Known Limitations: obsidian-connector v0.2.0

> Last updated: 2026-03-16

## Platform Limitations

| Platform | Status    | Notes                                                    |
|----------|-----------|----------------------------------------------------------|
| macOS    | Supported | Tested on macOS-latest in CI. .dmg installer available.  |
| Linux    | Supported | Tested on ubuntu-latest in CI. `install-linux.sh` available. |
| Windows  | Supported | Tested on windows-latest in CI. `Install.ps1` available. PowerShell notifications require WinRT. |
| ARM64    | Partial   | macOS ARM tested (CI uses arm64 runners). Linux ARM not tested. |

## Runtime Dependencies

| Dependency | Constraint | Limitation |
|---|---|---|
| Obsidian desktop app | v1.4+ with CLI plugin | Required for 22 of 29 MCP tools. Graph, doctor, and uninstall work offline. |
| Python | >=3.11 | Python 3.10 and below not supported. |
| `mcp` package | >=1.0.0,<2.0.0 | MCP 2.x not tested. Range pinned in pyproject.toml. |

## Feature Limitations

- **Daily note format**: Assumes `YYYY-MM-DD.md` naming convention. Custom daily note formats (from Obsidian Daily Notes or Periodic Notes plugins) are not supported. Planned for v0.3.0.
- **Frontmatter parser**: Does not handle all YAML edge cases. Inline YAML arrays (`tags: [a, b]`), flow sequences, multi-line values, and complex nested structures may parse incorrectly. Tags specified as `tags: [foo, bar]` instead of the block sequence form will not be extracted.
- **`%%comment%%` blocks**: Obsidian-style comment blocks are not masked from tag and link extraction. Comments containing `[[links]]` or `#tags` will be indexed.
- **Open loop detection**: Uses custom `OL:` marker convention. No Obsidian plugin support. No standard task-style `- [ ] OL:` format.
- **Drift analysis**: Intention-vs-behavior comparison uses regex-based extraction. Semantic matching planned for a future release.
- **`emerge_ideas` clustering**: Clusters ideas by folder path, not by semantic similarity. Notes in the same folder are grouped together regardless of content. Semantic clustering (e.g., via embeddings) is not implemented.
- **`challenge_belief` negation detection**: Uses regex-based negation detection (pattern matching for "not", "no", "never", etc.) rather than LLM-based reasoning. Subtle counter-evidence or nuanced disagreement may be missed.

## Performance Limitations

- No benchmarks on vaults >10,000 notes. Graph operations may be slow on very large vaults.
- SQLite index rebuild scans the entire vault directory. Incremental updates detect changes via mtime but initial build scales linearly with vault size.
- Cold start for the MCP server includes Python interpreter startup + package import (~1-2s).

## Architecture Limitations

- **cli.py** (1,599 LOC) and **workflows.py** (1,594 LOC) are monolithic files. Refactoring into submodules planned for v0.3.0.
- **Single maintainer**: Bus factor of 1.
- **No plugin system**: Third-party extensions not supported.

## Edge Cases

- Unicode filenames with combining characters have not been tested.
- Vault paths containing spaces work on macOS and Linux; not verified on Windows.
- Symlinked vault directories are not explicitly supported. Behavior is undefined.
- Empty vaults (no notes) will return empty results from search/graph tools but should not error.

## Unsupported Configurations

- Proxy environments not tested.
- Network-mounted filesystems (NFS, SMB) not tested as vault locations.
- Obsidian Sync conflicts not handled (the tool reads the local filesystem state).
- Multiple Obsidian vaults open simultaneously: the tool resolves one vault at a time. Concurrent vault operations are not supported.

## Experimental Features

- **check_in MCP tool**: Stable, but ritual detection (morning/evening sentinel headings) depends on specific heading formats in daily notes.
- **Thinking tools** (ghost, drift, trace, ideas): Use regex-based extraction. Results are heuristic, not semantic. Quality depends on note structure and writing conventions.
