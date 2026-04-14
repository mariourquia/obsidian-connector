# Rollback & Uninstall Guide: obsidian-connector

Covers rolling back from 0.9.0 to 0.8.3 and fully uninstalling the package.

## Rollback to Previous Version (0.8.3)

### pip

```bash
pip install obsidian-connector==0.8.3
```

If you used any optional extras, include them in the rollback too:

```bash
pip install 'obsidian-connector[scheduling,live,semantic]==0.8.3'
```

Note: `[tui]` and `[graphify]` are new in 0.9.0. They do not exist on 0.8.3;
if you are rolling back and used the Textual dashboard from a 0.9.0 install,
textual was previously a runtime dependency in 0.8.3 and earlier, so it will
be re-pulled automatically by the base install.

### macOS DMG

1. Download the prior DMG from the GitHub Release page:
   ```bash
   gh release download v0.8.3 -p 'obsidian-connector-0.8.3.dmg'
   ```
2. Mount and run `Install.command`. The DMG installer detects the existing
   0.9.0 install and will downgrade the `.venv`.
3. Verify:
   ```bash
   obsx --version
   # Expected: 0.8.3
   ```

### Windows MSI

1. Uninstall 0.9.0 via Add/Remove Programs.
2. Download `obsidian-connector-0.8.3.msi` from the GitHub Release page.
3. Run the 0.8.3 MSI.

### MCPB

Reinstall the prior MCPB archive through your MCPB-compatible host's install
command.

### Claude Code plugin

Use the plugin marketplace's version rollback flow, or side-load the 0.8.3
`builds/claude-code/` contents from a clone of the repo checked out at the
`v0.8.3` tag.

## Complete Uninstall

### Remove the Package

```bash
# pip
pip uninstall obsidian-connector

# macOS (DMG install location under Applications or ~/Applications)
#   Drag the app bundle to Trash, then remove the .venv:
rm -rf ~/Library/Application\ Support/obsidian-connector

# Windows
#   Uninstall via Add/Remove Programs, then:
rmdir /s %APPDATA%\obsidian-connector
```

### Clean Up Configuration

```bash
# macOS
rm -rf "$HOME/Library/Application Support/obsidian-connector"
rm -rf "$HOME/Library/Logs/obsidian-connector"
rm -rf "$HOME/Library/Caches/obsidian-connector"
rm -f  "$HOME/.config/obsidian-connector/config.json"

# Linux
rm -rf ~/.config/obsidian-connector
rm -rf ~/.cache/obsidian-connector
rm -rf ~/.local/share/obsidian-connector

# Windows
rmdir /s %APPDATA%\obsidian-connector
rmdir /s %LOCALAPPDATA%\obsidian-connector
```

### Clean Up MCP Client Registration

If you registered obsidian-connector as an MCP server in Claude Desktop,
Claude Code, or another MCP host, remove it from that client's configuration:

- **Claude Desktop (macOS)**:
  `~/Library/Application Support/Claude/claude_desktop_config.json` -- remove
  the `obsidian-connector` entry under `mcpServers`.
- **Claude Desktop (Windows)**:
  `%APPDATA%\Claude\claude_desktop_config.json` -- same edit.
- **Claude Code**: remove the plugin via your plugin marketplace UI, or delete
  the plugin directory from your Claude Code plugins folder.

### Clean Up Data

The connector reads and writes under the user-configured vault root. **These
files are your Obsidian notes and should not be removed when uninstalling the
connector.** The connector does not create a separate database outside the
vault; the index store lives at `<vault-root>/.obsidian-connector/index.db`.

To remove connector-generated data while preserving your vault:

```bash
# Index store and session logs
rm -rf "<your-vault-root>/.obsidian-connector"

# Auto-generated files carrying the "do not edit" callout (use vault-guardian
# output; check before deleting):
# Typical locations: Reports/, Inbox/Project Ideas/, Project Tracking/
```

### Verify Removal

```bash
# Confirm CLI is gone
which obsx && echo "still installed" || echo "removed"
which obsidian-connector && echo "still installed" || echo "removed"

# Confirm no orphaned config
ls ~/.config/obsidian-connector* 2>/dev/null && echo "config remains" || echo "clean"
```

## Data Migration Notes

- Data format changes between 0.8.3 and 0.9.0: none. The index store schema
  (SQLite) and the vault-on-disk schema (Markdown notes with frontmatter) are
  compatible across both versions.
- Backward compatibility: 0.8.3 can read vault and index artifacts produced by
  0.9.0, because 0.9.0 does not introduce any new persisted fields that 0.8.3
  treats as required. The `related` fence on commitment notes and the `wiki`
  fence on entity notes are Markdown-only; 0.8.3 ignores them.
- Recommended backup before rollback:
  ```bash
  tar czf obsidian-connector-rollback-backup-$(date +%Y%m%d).tar.gz \
      "<your-vault-root>/.obsidian-connector" \
      "<your-vault-root>/Reports" \
      "<your-vault-root>/Inbox/Agent Drafts" 2>/dev/null || true
  ```
