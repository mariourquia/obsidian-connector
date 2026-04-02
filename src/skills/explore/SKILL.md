---
name: explore
description: Create a new Obsidian vault for any topic and seed it with an initial knowledge base from web research. Use when the user wants to explore a new idea, start a research project, or create a dedicated space for a tangent they want to investigate later.
---

# Explore a New Topic

> **Tip:** You can also use `/new-vault topic` for a unified vault creation experience.

Create a dedicated Obsidian vault for a topic and seed it with real
knowledge from web research so the user has something to work with
immediately.

## Steps

### 1. Understand the topic

Ask one clarifying question if needed, but don't over-interrogate.
The user wants to start exploring, not write a brief.

Determine:
- **Topic name** (becomes the vault name)
- **3-5 subtopics** worth researching (suggest if the user doesn't specify)
- **Why they're interested** (one sentence, for the vault description)

### 2. Create the vault

Call `obsidian_create_vault` with:
- **name**: the topic (e.g., "Aviation Data Systems")
- **description**: why they're interested
- **seed_topics**: pipe-separated subtopics to create research stubs

This creates the vault alongside their existing vaults with:
- `Home.md` (index with links to all topics)
- `Research/{topic}.md` stubs with key questions
- `Cards/`, `Inbox/`, `daily/` directories

### 3. Research and seed

For each seed topic, do actual research:

1. Search the web for the topic
2. Read 2-3 top results
3. Synthesize key findings into a structured note
4. Call `obsidian_seed_vault` to save the note

Each seed note should include:
- **Overview**: 2-3 paragraph summary of the topic
- **Key concepts**: bulleted list of important terms/ideas
- **Resources**: links to the sources you read
- **Open questions**: what's worth exploring further
- **Connections**: how this relates to the user's other interests

### 4. Report what was created

Tell the user:
- Where the vault was created
- How many notes were seeded
- The top 2-3 most interesting findings from the research
- How to open it in Obsidian
- That they can discard it with `obsidian_discard_vault` if it's not useful

### 5. Offer next steps

- "Want me to go deeper on any of these topics?"
- "Want me to connect this to your other vaults?"
- "Want me to set up a research plan for this?"

## When to use

- "I want to explore..." / "I'm curious about..."
- "Create a vault for..." / "Start a research project on..."
- "I had this tangent about... set up a space for it"
- "Let me look into..." / "I want to learn about..."
- User describes a topic they want to investigate but not build yet

## Design principle

Speed of thought. The vault should exist within 30 seconds with
real content the user can immediately read and build on. If the
research takes too long, create the vault first with stubs, then
seed notes as research completes.
