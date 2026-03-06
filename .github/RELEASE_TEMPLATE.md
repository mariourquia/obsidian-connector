# Release Template -- obsidian-connector

> Reuse this template for every release. Copy the sections below into the
> GitHub release body. Fill in the blanks, delete inapplicable sections.

---

```
+----------------------------------------------------------+
|              obsidian-connector vX.Y.Z                   |
|     Turn Claude into your second brain.                  |
+----------------------------------------------------------+
```

## Highlights

<!-- 2-4 bullet points. Lead with user impact, not implementation. -->

- **Headline feature**: One sentence.
- **Headline feature**: One sentence.

## What's New

### Features

<!-- Group by user workflow, not file changed. -->

| Feature | Description | Environment |
|---------|-------------|-------------|
| `feature_name` | What it does for the user | CLI / Desktop / Both |

### Improvements

<!-- Non-feature changes that affect UX. -->

- Improvement description

### Bug Fixes

<!-- Skip if none. -->

- Fix description (#issue)

## Installation

```bash
# Fresh install
git clone https://github.com/mariourquia/obsidian-connector.git
cd obsidian-connector
./scripts/install.sh

# Upgrade from previous version
git pull origin main
./scripts/install.sh
```

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Obsidian | 1.12+ (CLI enabled) |
| macOS | 13+ (Ventura) |
| Claude Desktop | Latest (for MCP) |
| Claude Code | Latest (for skills/hooks) |

## Security

### Review Status

<!-- Always include. Update per release. -->

- [ ] Input validation: CLI args, MCP params, file paths
- [ ] Shell execution: subprocess calls sanitized
- [ ] File system: no path traversal possible
- [ ] SQL injection: parameterized queries only
- [ ] Secrets: no hardcoded credentials
- [ ] Dependencies: no known CVEs

### Permissions Model

<!-- Describe what the tool can access. -->

- **Reads**: Vault markdown files, Obsidian app IPC
- **Writes**: Daily note (append only), Agent Drafts folder, audit log
- **Network**: None (100% local)
- **Credentials**: None stored or transmitted

### Guardrails

<!-- What prevents misuse or accidents. -->

- Guardrail description

## Known Limitations

<!-- Be honest. Users trust transparent projects. -->

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Description | What it means for the user | How to work around it |

## Risks

<!-- What could go wrong. Frame as "if X, then Y". -->

- **Risk**: Description. **Mitigation**: How it's handled.

## Compatibility

| Environment | Status | Notes |
|-------------|--------|-------|
| macOS 13+ | Supported | Primary platform |
| Linux | Untested | CLI may work, scheduling won't |
| Windows | Unsupported | No Obsidian CLI on Windows |

## Testing

<!-- What was verified before this release. -->

```
Test Suite                   Assertions   Status
─────────────────────────────────────────────────
smoke_test.py                8            PASS
checkin_test.py              19           PASS
mcp_launch_smoke.sh          3            PASS
workflow_test.py             N            PASS
docs-lint                    0 errors     PASS
```

## Upgrade Notes

<!-- Skip for v0.1.0. Required for all subsequent releases. -->

### Breaking Changes

- None

### Migration Steps

1. Step

## Full Changelog

**Compare**: [`vPREV...vX.Y.Z`](https://github.com/mariourquia/obsidian-connector/compare/vPREV...vX.Y.Z)

---

<!-- Footer -->
```
Built with care in New York.
100% local. Your vault never leaves your machine.
```
