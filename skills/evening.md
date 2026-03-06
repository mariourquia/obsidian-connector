---
name: evening
description: Close your day. Reviews what you accomplished, surfaces remaining loops, and offers to graduate ideas.
---

# Evening Close

You are running the user's evening close workflow. Follow these steps exactly.

## Step 1: Check in

Call `obsidian_check_in`.

- If `completed_rituals` already includes `evening_close`, tell the user: "Your evening close already ran today. Want me to run it again?" If they say no, stop.

## Step 2: Review the day

Call these tools (in parallel if possible):
1. `obsidian_close_day` -- get day's activity, completed/remaining tasks, reflection prompts
2. `obsidian_graduate_candidates` with `lookback_days=1` -- ideas from today worth promoting

## Step 3: Synthesize the close

Compose a reflection covering:
- **What got done** -- completed tasks and key daily note entries
- **What's still open** -- remaining tasks and open loops
- **What to carry forward** -- suggest 1-3 items for tomorrow
- **Reflection prompts** -- present the reflection prompts from close_day
- **Graduate candidates** -- if any ideas are worth promoting, list them

## Step 4: Write to vault

Call `obsidian_log_daily` with the close formatted as:

```
## Day Close
**Generated:** {timestamp}

{close content}
```

## Step 5: Offer graduation

If graduate candidates were found:
"These ideas from today look worth promoting to standalone notes: {list}. Want me to graduate any of them?"

If the user says yes, call `obsidian_graduate_execute` for each selected idea.

## Step 6: End

"Day closed. Rest well."
