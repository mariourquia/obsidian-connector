---
name: idea
description: Quickly capture an idea to your daily note. Surfaces related context if found.
---

# Quick Idea Capture

You are capturing an idea for the user. This should be fast -- two seconds from thought to vault.

## Step 1: Parse the idea

The user's argument is the idea text. If no argument was provided, ask: "What's the idea?"

## Step 2: Log to daily note

Call `obsidian_log_daily` with:

```
- {HH:MM} {idea text}
```

Use the current time (24h format). Keep the format simple and scannable.

## Step 3: Surface related context (optional, fast)

If the idea mentions a recognizable topic (a project name, a domain, a person):
- Call `obsidian_search` with the most distinctive keyword from the idea
- If results come back, briefly mention: "Related: {note1}, {note2}. Want me to expand this into a research note?"

If no clear topic, skip this step. Speed matters more than completeness.

## Step 4: Confirm

"Logged." (Keep it brief. The user is in flow.)

If you surfaced related notes and the user wants to expand:
- Call `obsidian_create_note` with an appropriate template
- Or call `obsidian_log_daily` with a more detailed entry
