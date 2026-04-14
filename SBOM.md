# Software Bill of Materials (SBOM)

Generated: 2026-04-13
Package: obsidian-connector v0.9.0
Python: >=3.11

## Audit Status

```
pip-audit: 0 known vulnerabilities
```

Regenerate this section with: `pip-audit -r requirements.txt` (or against the
installed environment).

## Direct Dependencies

| Package | Version         | License | Purpose                             |
|---------|-----------------|---------|-------------------------------------|
| mcp     | >=1.0.0,<2.0.0  | MIT     | MCP server protocol                 |
| pyyaml  | >=6.0.0         | MIT     | YAML parsing (frontmatter, manifests) |

## Optional Dependencies

| Package                | Version         | License | Purpose                                   | Install Extra |
|------------------------|-----------------|---------|-------------------------------------------|---------------|
| pyyaml                 | >=6.0,<7.0      | MIT     | Schedule config parsing                   | `scheduling`  |
| textual                | >=1.0.0         | MIT     | Interactive `obsx` TUI dashboard          | `tui`         |
| watchdog               | >=4.0,<5.0      | Apache-2.0 | Filesystem watch for live sync         | `live`        |
| sentence-transformers  | >=3.0,<4.0      | Apache-2.0 | Local embeddings for semantic search   | `semantic`    |
| networkx               | >=3.0,<4.0      | BSD-3-Clause | Knowledge-graph build / cluster / analyze | `graphify` |
| pytest                 | >=8.0,<9.0      | MIT     | Test runner                               | `dev`         |

## Transitive Runtime Dependencies (via mcp)

| Package | Pinned At | License |
|---------|-----------|---------|
| anyio | 4.12.1 | MIT |
| httpx | 0.28.1 | BSD |
| httpx-sse | 0.4.3 | MIT |
| jsonschema | 4.26.0 | MIT |
| pydantic | 2.12.5 | MIT |
| pydantic-settings | 2.13.1 | MIT |
| PyJWT | 2.12.1 | MIT |
| python-multipart | 0.0.22 | Apache-2.0 |
| sse-starlette | 3.3.2 | BSD-3-Clause |
| starlette | 0.52.1 | BSD-3-Clause |
| typing-inspection | 0.4.2 | MIT |
| typing_extensions | 4.15.0 | PSF-2.0 |
| uvicorn | 0.42.0 | BSD-3-Clause |

## Standard Library Only (no external deps)

These modules use only the Python standard library:

- `obsidian_connector.client` (subprocess, json, os)
- `obsidian_connector.graph` (os, re, pathlib)
- `obsidian_connector.index_store` (sqlite3, json)
- `obsidian_connector.audit` (json, datetime, pathlib)
- `obsidian_connector.config` (os, json, pathlib)
- `obsidian_connector.thinking` (re, collections, datetime)
- `obsidian_connector.workflows` (os, re, datetime, pathlib)
- `obsidian_connector.platform` (os, subprocess, pathlib, platform)
- `obsidian_connector.file_backend` (os, re, pathlib, tempfile)
- `obsidian_connector.uninstall` (json, os, shutil, tempfile, pathlib)

Only `mcp_server.py` imports the `mcp` package.

## Regenerating This File

```bash
source .venv/bin/activate
pip install pip-audit pip-licenses
pip-audit                                    # Check for CVEs
pip-licenses --format=markdown --with-urls   # License table
```
