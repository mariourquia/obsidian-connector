---
name: float
description: Float an idea to the right project in the Obsidian vault. Auto-routes by keyword matching or accepts an explicit project target. Use when the user has a thought, tangent, or idea they want captured but not immediately acted on.
---

# Float Idea

> **Tip:** You can also use `/capture route` for a unified capture experience.

Capture an idea and route it to the right project's idea file in the vault.
For ideas about projects that don't exist yet, offer to create an inception card.

## Steps

### 1. Parse the idea

The user's message IS the idea. Extract:
- The core idea text
- Any project mentioned (explicitly or by context)

### 2. Route or create

**If the idea is about an existing project:**

Call `obsidian_float_idea` with the idea text. If the user mentioned a
project name, pass it as the `project` parameter. Otherwise, omit it
and let auto-routing match keywords.

The tool routes to `Inbox/Ideas/{project}.md` and timestamps the entry.

Tell the user: "Floated to {project}." (Keep it brief -- they're in flow.)

**If the idea is about a NEW project that doesn't exist yet:**

Ask: "This sounds like a new project idea. Want me to create an inception
card for it?"

If yes, call `obsidian_incubate_project` with:
- **name**: a concise project name
- **description**: what the user described
- **why**: why it matters (if they said)
- **tags**: relevant domain tags
- **related_projects**: any existing projects it connects to

The card goes to `Inbox/Project Ideas/{slug}.md`.

### 3. Offer connections (optional, only if natural)

If the idea clearly connects to existing vault content, briefly mention:
"This connects to your work on {project}. Want me to search for related notes?"

If it's a standalone thought, just confirm and move on.

## When to use

- User says "I had an idea about..."
- User says "float this to..." or "save this thought"
- User mentions a tangent they want to capture
- User describes something they might want to build someday
- Mid-conversation side thoughts that shouldn't be lost

## Tone

Brief. The user is mid-thought. Don't break their flow with long responses.
"Floated to AMOS." is better than a paragraph.
