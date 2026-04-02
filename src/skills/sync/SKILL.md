---
name: sync
description: Sync project state to your Obsidian vault and generate a session summary.
---

# /sync -- Sync Projects to Vault

You handle explicit manual project sync operations.

## Default behavior
1. Call `obsidian_sync_projects` to sync all tracked repos
2. Call `obsidian_running_todo` to update the running TODO
3. If the user has been working on something this session, offer to log a session entry via `obsidian_log_session`
4. Present a summary:
   - Projects synced (count)
   - Active threads
   - Open TODOs
   - Session logged (if applicable)

## Keep it concise
The sync should feel like a quick checkpoint, not a long review.
One summary paragraph, then a bullet list of key items.
