---
name: weekly
description: Run your weekly review. Checks drift, graduates ideas, audits vault health.
---

# Weekly Review

You are running the user's weekly review. This is a longer, more reflective workflow.

## Step 1: Context load

Call `obsidian_check_in` to get current state.

## Step 2: Drift analysis

Call `obsidian_drift` with:
- `lookback_days=7`
- For the `intention` parameter, check if the user has stated intentions in their vault. Search for "intention" or "goal" or "commitment" in recent notes. If found, use those. If not, ask the user: "What were your intentions for this week?"

Present the drift analysis: coverage percentage, gaps, surprises.

## Step 3: Idea graduation

Call `obsidian_graduate_candidates` with `lookback_days=7`.

If candidates found, present them and ask which to promote.
For each approved candidate, call `obsidian_graduate_execute`.

## Step 4: Vault health

Call `obsidian_vault_structure`.

Report:
- Orphan count (notes with no links in or out)
- Dead ends (linked but nonexistent notes)
- Top connected hubs

If orphan count is high, suggest linking strategies.

## Step 5: Write weekly summary

Call `obsidian_log_daily` with a summary section:

```
## Weekly Review
**Week of:** {date range}

### Drift
{drift summary}

### Graduated Ideas
{list of graduated notes, or "None this week"}

### Vault Health
{orphan count, dead ends, action items}

### Intentions for Next Week
{ask user or carry forward}
```

## Step 6: Set next week's intentions

Ask: "What are your intentions for next week?"

Log their response to the daily note as stated intentions (these feed future drift analysis).
