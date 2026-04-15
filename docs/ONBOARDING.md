# Connector Onboarding (Task 34)

Walks a new install from a blank machine to a working obsidian-connector
paired with the obsidian-capture-service. Read top to bottom once; the
same six steps are available programmatically via `obsx onboarding`.

Companion doc: the capture-service side is at
[`../obsidian-capture-service/docs/onboarding/ONBOARDING.md`](../../obsidian-capture-service/docs/onboarding/ONBOARDING.md).
If you are starting from the iPhone / Mac ingest side, open that one
first — most of the steps below depend on the capture service already
running.

## CLI command

```bash
obsx onboarding          # human-readable walkthrough
obsx onboarding --json   # machine-readable payload (stable contract)
```

The JSON payload is the single source of truth — both this doc and the
connector's CLI render from `obsidian_connector.onboarding.get_onboarding_payload()`.

## Step 1: Vault setup

Ensure the target Obsidian vault exists. For a fresh machine, scaffold
project tracking / Dashboards / Commitments:

```bash
obsx init
```

## Step 2: Capture-service URL

Point the connector at the Mac-side service. Default for local dev is
`http://127.0.0.1:8787`; for a laptop on Tailscale use the tailnet DNS
name.

```bash
export OBSIDIAN_CAPTURE_SERVICE_URL="http://100.x.y.z:8787"
```

## Step 3: Bearer token

Match the token the capture-service wizard generated:

```bash
export OBSIDIAN_CAPTURE_SERVICE_TOKEN="paste-token-here"
```

## Step 4: MCP registration

The editable install exposes `obsidian-connector-mcp` on `$PATH`. For
Claude Desktop, add an entry to `claude_desktop_config.json` pointing at
the console script. See `docs/setup-guide.md` for the full config
template; a quick sanity check:

```bash
which obsidian-connector-mcp
obsidian-connector-mcp --help
```

## Step 5: First sync

Run an initial sync so the vault picks up git state and any existing
commitments:

```bash
obsx sync-projects
```

## Step 6: Verify

```bash
obsx doctor
```

Green output here means the connector sees the vault, the capture
service, and the token. Head back to the capture-service side to run
`python -m app.verify_install` for the full end-to-end probe.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `obsx: command not found` | Re-activate the venv or re-run `pip install -e .`. |
| `OBSIDIAN_CAPTURE_SERVICE_URL unset` warnings | Export the var or put it in `~/.obsidian-connector/config.json`. |
| Bearer token rejected | Compare against `.env` on the capture service side; re-run its `setup_wizard --install`. |
| MCP server cannot find the package | Confirm `which obsidian-connector-mcp` resolves to the venv, or set `PYTHONPATH` in the Desktop config. |
| Vault doctor reports "not found" | Check `OBSIDIAN_VAULT` env var and `~/.obsidian-connector/config.json`. |

## Related docs

- `docs/setup-guide.md` — full install and Desktop config.
- `docs/INSTALL-SURFACES.md` — distribution matrix.
- `TOOLS_CONTRACT.md` — MCP tool envelope + error taxonomy.
- `CHANGELOG.md` — per-release notes.
