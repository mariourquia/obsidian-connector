# Security Policy

## Supported Versions

| Version | Supported          |
|---------|-------------------|
| 0.1.x   | Yes               |

## Reporting a Vulnerability

If you discover a security vulnerability in obsidian-connector, please report
it responsibly.

**Email:** 60152193+mariourquia@users.noreply.github.com

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Impact assessment (what an attacker could do)
- Suggested fix (if you have one)

**Response timeline:**
- Acknowledgement within 48 hours
- Assessment within 7 days
- Fix or mitigation plan within 14 days for confirmed issues

**Please do not** open a public GitHub issue for security vulnerabilities.

## Security Model

obsidian-connector is designed as a **local-only** tool with no network access.
The threat model assumes a trusted local user on a single machine.

### What we defend against

- **Path traversal**: `graduate_execute` validates titles and target folders
  against directory escape. All vault reads are confined to the vault root.
- **Command injection**: Subprocess calls use list-based arguments (no
  `shell=True`). The `obsidian_bin` config rejects shell metacharacters.
- **SQL injection**: All SQLite queries use parameterized placeholders.
- **osascript injection**: Notification strings are escaped before AppleScript
  interpolation.
- **Secret leakage**: No secrets are stored, transmitted, or hardcoded. No
  network calls are made.

### What is out of scope

- Attacks requiring physical access to the machine
- Compromise of the Obsidian desktop application itself
- Malicious vault content designed to exploit Markdown parsers (this tool
  reads Markdown as plain text, not rendered HTML)
- Denial of service via extremely large vaults (performance, not security)

## Dependencies

| Dependency | Purpose               | Trust basis                  |
|------------|----------------------|------------------------------|
| `mcp`      | MCP server protocol  | PyPI package, pinned range   |
| Python 3.11+ | Runtime            | System Python or venv        |
| SQLite     | Graph index storage  | Python stdlib                |

No other runtime dependencies. No native extensions.
