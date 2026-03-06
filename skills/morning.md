---
name: morning
description: Run your morning briefing. Reads daily note, surfaces open loops and delegations, writes a briefing to your vault.
---

# Morning Briefing

You are running the user's morning briefing workflow. Follow these steps exactly.

## Step 1: Check in

Call the `obsidian_check_in` MCP tool (or use the Python API `check_in()` via Bash).

- If `completed_rituals` already includes `morning_briefing`, tell the user: "Your morning briefing already ran today. Want me to run it again?" If they say no, stop.
- Note the `time_of_day`, `open_loop_count`, `pending_delegations`, and `unreviewed_drafts` for later.

## Step 2: Read today's state

Call these tools (in parallel if possible):
1. `obsidian_today` -- get the daily note content and open tasks
2. `obsidian_open_loops` -- get all open loops
3. `obsidian_delegations` -- get pending @claude: instructions

## Step 3: Synthesize the briefing

Compose a conversational briefing covering:
- **Date and time context** (e.g. "It's Tuesday morning")
- **Daily note summary** -- what's already on today's note
- **Open tasks** -- count and top 5 most important
- **Open loops** -- count and the ones that seem most urgent
- **Pending delegations** -- any @claude: instructions to act on
- **Unreviewed drafts** -- any agent drafts waiting for review

Keep it concise. Lead with the most actionable items.

## Step 4: Write to vault

Call `obsidian_log_daily` with the briefing formatted as:

```
## Morning Briefing
**Generated:** {timestamp}

{briefing content}
```

This sentinel heading (`## Morning Briefing`) is how the system knows the briefing has run.

## Step 5: Offer interaction

After presenting the briefing, ask:
"Anything you want to triage, capture, or change before starting your day?"

If the user responds:
- **Defer a task**: Log a note about deferral to the daily note
- **Log an idea**: Call `obsidian_log_daily` with the idea
- **Act on a delegation**: Execute the delegation instruction
- **Create a note**: Call `obsidian_create_note`
- **Nothing**: Wish them a good day and end
