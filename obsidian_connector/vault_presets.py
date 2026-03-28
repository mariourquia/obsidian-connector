"""Vault presets for obsidian-connector.

Curated vault templates for common use cases. Each preset defines a
directory structure, starter notes with prompts, and a Home.md index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VaultPreset:
    """A curated vault template."""

    slug: str
    name: str
    description: str
    icon: str  # emoji for display
    directories: list[str] = field(default_factory=list)
    seed_notes: list[dict[str, str]] = field(default_factory=list)
    daily_template: str = ""  # template for daily notes


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------

PRESETS: dict[str, VaultPreset] = {}


def _register(preset: VaultPreset) -> VaultPreset:
    PRESETS[preset.slug] = preset
    return preset


# ---------------------------------------------------------------------------
# Journaling
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="journaling",
    name="Daily Journal",
    description="Daily journaling with guided prompts. AI helps you reflect, express, and process your day.",
    icon="📓",
    directories=["daily", "Reflections", "Gratitude", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Daily Journal Template",
            "tags": "template, journal",
            "content": (
                "## How I'm feeling\n\n\n\n"
                "## What happened today\n\n\n\n"
                "## What I'm grateful for\n\n1. \n2. \n3. \n\n"
                "## What's on my mind\n\n\n\n"
                "## One thing I want to remember\n\n\n"
            ),
        },
        {
            "folder": ".",
            "title": "Getting Started",
            "tags": "guide",
            "content": (
                "Welcome to your journal. This is a private space for your thoughts.\n\n"
                "## How to use this vault\n\n"
                "- **Daily notes**: Write in `daily/` using the template\n"
                "- **Reflections**: Longer pieces go in `Reflections/`\n"
                "- **Gratitude**: Capture what you're thankful for\n"
                "- **Just talk**: Tell Claude what's on your mind. It will help you\n"
                "  articulate your thoughts and save them here.\n\n"
                "## Prompts to try\n\n"
                "- \"I want to journal about my day\"\n"
                "- \"Help me process what happened at work\"\n"
                "- \"I'm feeling grateful for...\"\n"
                "- \"I need to think through a decision about...\"\n"
            ),
        },
    ],
    daily_template=(
        "## {{date}}\n\n"
        "### How I'm feeling\n\n\n\n"
        "### What happened\n\n\n\n"
        "### Grateful for\n\n1. \n2. \n3. \n\n"
        "### Notes\n\n\n"
    ),
))


# ---------------------------------------------------------------------------
# Mental Health
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="mental-health",
    name="Mental Health Journal",
    description="Thought records, emotion processing, CBT worksheets, and mood tracking. A safe space for mental wellness.",
    icon="🧠",
    directories=["daily", "Thought Records", "Mood Tracking", "Coping Strategies", "Wins", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Thought Record Template",
            "tags": "template, cbt, thought-record",
            "content": (
                "## Situation\n\nWhat happened? Where? When? Who was there?\n\n\n\n"
                "## Automatic Thoughts\n\nWhat went through my mind?\n\n\n\n"
                "## Emotions\n\nWhat did I feel? (Rate intensity 0-100)\n\n"
                "| Emotion | Intensity |\n|---------|----------|\n| | /100 |\n| | /100 |\n\n"
                "## Evidence FOR the thought\n\n- \n\n"
                "## Evidence AGAINST the thought\n\n- \n\n"
                "## Balanced Thought\n\nA more realistic way to see this:\n\n\n\n"
                "## How I feel now\n\nEmotions after reframing (0-100):\n\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Mood Check-In Template",
            "tags": "template, mood",
            "content": (
                "## Mood: \n\n"
                "**Energy**: Low / Medium / High\n"
                "**Anxiety**: Low / Medium / High\n"
                "**Overall**: 1 2 3 4 5 6 7 8 9 10\n\n"
                "## What's contributing to this mood?\n\n\n\n"
                "## What would help right now?\n\n\n\n"
                "## One kind thing I can do for myself\n\n\n"
            ),
        },
        {
            "folder": "Coping Strategies",
            "title": "My Coping Toolkit",
            "tags": "coping, strategies",
            "content": (
                "## When I'm anxious\n\n- \n\n"
                "## When I'm sad\n\n- \n\n"
                "## When I'm overwhelmed\n\n- \n\n"
                "## When I can't sleep\n\n- \n\n"
                "## People I can reach out to\n\n- \n\n"
                "## Things that always help\n\n- \n\n"
                "> Fill this in when you're feeling good. It's hard to\n"
                "> remember what helps when you're in the middle of it.\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Business Ideas
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="business-ideas",
    name="Business Ideas",
    description="Capture, evaluate, and develop business ideas. Market analysis, pitch drafts, competitive landscape.",
    icon="💡",
    directories=["Ideas", "Market Research", "Pitches", "Competitors", "Financial Models", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Business Idea Template",
            "tags": "template, idea",
            "content": (
                "## The Idea\n\nOne sentence:\n\n\n\n"
                "## Problem\n\nWhat problem does this solve? Who has this problem?\n\n\n\n"
                "## Solution\n\nHow does this solve it?\n\n\n\n"
                "## Target Market\n\nWho are the first 100 customers?\n\n\n\n"
                "## Revenue Model\n\nHow does this make money?\n\n\n\n"
                "## Why Now?\n\nWhat changed to make this possible/needed?\n\n\n\n"
                "## Competition\n\nWho else is doing this? Why is this different?\n\n\n\n"
                "## First Step\n\nWhat's the smallest thing I can do to test this?\n\n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="research",
    name="Research Hub",
    description="Literature notes, reading lists, methodology, and synthesis across any domain -- science, literature, sociology, and beyond.",
    icon="🔬",
    directories=["Literature Notes", "Reading List", "Methodology", "Synthesis", "Sources", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Literature Note Template",
            "tags": "template, literature",
            "content": (
                "## Source\n\n**Title**: \n**Author**: \n**Year**: \n**Type**: paper / book / article / talk\n\n"
                "## Summary\n\n\n\n"
                "## Key Claims\n\n1. \n2. \n3. \n\n"
                "## Methodology\n\n\n\n"
                "## Strengths\n\n- \n\n"
                "## Weaknesses / Limitations\n\n- \n\n"
                "## How This Connects\n\nRelated to: \n\n"
                "## Quotes\n\n> \n\n"
            ),
        },
        {
            "folder": "Reading List",
            "title": "To Read",
            "tags": "reading-list",
            "content": (
                "## Currently Reading\n\n- [ ] \n\n"
                "## Up Next\n\n- [ ] \n\n"
                "## Finished\n\n- [x] \n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Project Management
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="project-management",
    name="Project Management",
    description="Task tracking, sprint planning, retrospectives, and execution. Turn plans into action.",
    icon="📋",
    directories=["Projects", "Sprints", "Retrospectives", "Meeting Notes", "Decisions", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Project Brief Template",
            "tags": "template, project",
            "content": (
                "## Project Name\n\n\n\n"
                "## Goal\n\nWhat does success look like?\n\n\n\n"
                "## Scope\n\n### In scope\n- \n\n### Out of scope\n- \n\n"
                "## Timeline\n\n| Milestone | Date | Status |\n|-----------|------|--------|\n| | | |\n\n"
                "## Risks\n\n- \n\n"
                "## Open Questions\n\n- [ ] \n\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Retrospective Template",
            "tags": "template, retro",
            "content": (
                "## What went well\n\n- \n\n"
                "## What didn't go well\n\n- \n\n"
                "## What to change\n\n- \n\n"
                "## Action items\n\n- [ ] \n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Second Brain
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="second-brain",
    name="Second Brain",
    description="Zettelkasten-inspired knowledge management. Fleeting notes, literature notes, permanent notes, and a map of content.",
    icon="🧩",
    directories=["Fleeting", "Literature", "Permanent", "Maps of Content", "Inbox", "templates"],
    seed_notes=[
        {
            "folder": ".",
            "title": "Getting Started with Your Second Brain",
            "tags": "guide, zettelkasten",
            "content": (
                "## The method\n\n"
                "1. **Fleeting notes** (`Fleeting/`): Quick captures. Throw anything in here.\n"
                "2. **Literature notes** (`Literature/`): Summaries of things you read/watch/listen to.\n"
                "3. **Permanent notes** (`Permanent/`): Your own ideas, written in your own words. One idea per note.\n"
                "4. **Maps of Content** (`Maps of Content/`): Index notes that link related permanent notes.\n\n"
                "## Workflow\n\n"
                "- Capture everything in `Fleeting/` or `Inbox/`\n"
                "- Process fleeting notes into permanent notes daily\n"
                "- Link permanent notes to each other with [[wikilinks]]\n"
                "- Create Maps of Content when a cluster forms\n\n"
                "## Tips\n\n"
                "- One idea per permanent note\n"
                "- Write in your own words (not copy-paste)\n"
                "- Link generously -- connections create value\n"
                "- Review your inbox weekly\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Vacation Planning
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="vacation-planning",
    name="Vacation Planning",
    description="Itineraries, budgets, packing lists, bookings, and travel research. Plan trips without losing details.",
    icon="✈️",
    directories=["Trips", "Research", "Packing Lists", "Bookings", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Trip Template",
            "tags": "template, trip",
            "content": (
                "## Destination\n\n\n\n"
                "## Dates\n\n**From**: \n**To**: \n**Duration**: \n\n"
                "## Budget\n\n| Category | Estimated | Actual |\n"
                "|----------|-----------|--------|\n"
                "| Flights | | |\n| Accommodation | | |\n"
                "| Food | | |\n| Activities | | |\n"
                "| Transport | | |\n| **Total** | | |\n\n"
                "## Itinerary\n\n### Day 1\n\n- \n\n### Day 2\n\n- \n\n"
                "## Bookings\n\n- [ ] Flights\n- [ ] Hotel\n- [ ] Car rental\n- [ ] Activities\n\n"
                "## Packing\n\nSee [[Packing Lists/]]\n\n"
                "## Research\n\n- \n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Life Planning
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="life-planning",
    name="Life Planning",
    description="Goals, values, quarterly reviews, and long-term vision. Design your life intentionally.",
    icon="🗺️",
    directories=["Goals", "Values", "Quarterly Reviews", "Annual Reviews", "Vision", "templates"],
    seed_notes=[
        {
            "folder": "Values",
            "title": "My Values",
            "tags": "values, core",
            "content": (
                "## My core values\n\n"
                "1. \n2. \n3. \n4. \n5. \n\n"
                "## What each means to me\n\n\n\n"
                "## How I live them\n\n\n\n"
                "> Revisit this quarterly. Values evolve.\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Quarterly Review Template",
            "tags": "template, quarterly",
            "content": (
                "## Quarter: Q_ 20__\n\n"
                "## What I accomplished\n\n- \n\n"
                "## What I didn't get to\n\n- \n\n"
                "## What surprised me\n\n- \n\n"
                "## Am I living my values?\n\n\n\n"
                "## Next quarter priorities\n\n1. \n2. \n3. \n\n"
                "## One word for how this quarter felt\n\n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Budgeting
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="budgeting",
    name="Personal Budget",
    description="Expense tracking, financial goals, savings targets, debt payoff plans, and net worth tracking.",
    icon="💰",
    directories=["Monthly", "Goals", "Accounts", "Debt Payoff", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Monthly Budget Template",
            "tags": "template, budget",
            "content": (
                "## Month: \n\n"
                "### Income\n\n| Source | Amount |\n|--------|--------|\n| | |\n| **Total** | |\n\n"
                "### Fixed Expenses\n\n| Expense | Amount |\n|---------|--------|\n"
                "| Rent/Mortgage | |\n| Utilities | |\n| Insurance | |\n| Subscriptions | |\n| **Total** | |\n\n"
                "### Variable Expenses\n\n| Category | Budget | Actual |\n|----------|--------|--------|\n"
                "| Groceries | | |\n| Dining | | |\n| Transport | | |\n| Entertainment | | |\n| Personal | | |\n| **Total** | | |\n\n"
                "### Savings & Investments\n\n| Target | Amount |\n|--------|--------|\n| | |\n\n"
                "### Summary\n\n**Income - Expenses = **\n\n"
            ),
        },
        {
            "folder": "Goals",
            "title": "Financial Goals",
            "tags": "goals, financial",
            "content": (
                "## Short-term (< 1 year)\n\n- [ ] \n\n"
                "## Medium-term (1-5 years)\n\n- [ ] \n\n"
                "## Long-term (5+ years)\n\n- [ ] \n\n"
                "## Net Worth Target\n\n| Year | Target | Actual |\n|------|--------|--------|\n| | | |\n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Creative Writing
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="creative-writing",
    name="Creative Writing",
    description="Drafts, worldbuilding, character sheets, plot outlines, and writing prompts. A workshop for your stories.",
    icon="✍️",
    directories=["Drafts", "Characters", "Worldbuilding", "Outlines", "Prompts", "Published", "templates"],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Character Sheet Template",
            "tags": "template, character",
            "content": (
                "## Name\n\n\n\n"
                "## Role\n\nProtagonist / Antagonist / Supporting / Minor\n\n"
                "## Appearance\n\n\n\n"
                "## Personality\n\n\n\n"
                "## Backstory\n\n\n\n"
                "## Motivation\n\nWhat do they want? What do they need?\n\n\n\n"
                "## Conflict\n\nWhat stands in their way?\n\n\n\n"
                "## Arc\n\nHow do they change?\n\n\n\n"
                "## Voice\n\nHow do they talk? Catchphrases? Speech patterns?\n\n\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Story Outline Template",
            "tags": "template, outline",
            "content": (
                "## Title\n\n\n\n"
                "## Logline\n\nOne sentence:\n\n\n\n"
                "## Genre\n\n\n\n"
                "## Structure\n\n"
                "### Act 1 -- Setup\n\n\n\n"
                "### Act 2 -- Confrontation\n\n\n\n"
                "### Act 3 -- Resolution\n\n\n\n"
                "## Themes\n\n- \n\n"
                "## Setting\n\n\n\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Self-Expression
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="self-expression",
    name="Self-Expression",
    description="Art journaling, mood boards, manifestos, free writing, and personal philosophy. Express yourself without filters.",
    icon="🎨",
    directories=["Free Writing", "Manifestos", "Mood Boards", "Letters Never Sent", "Daily Pages", "templates"],
    seed_notes=[
        {
            "folder": ".",
            "title": "Welcome",
            "tags": "guide",
            "content": (
                "This vault is yours. No rules. No structure required.\n\n"
                "## Ideas for what to put here\n\n"
                "- **Free writing**: Set a timer for 10 minutes. Write without stopping.\n"
                "- **Letters never sent**: Write to someone. You don't have to send it.\n"
                "- **Manifestos**: What do you believe? What do you stand for?\n"
                "- **Mood boards**: Describe images, colors, textures, feelings.\n"
                "- **Daily pages**: Morning pages a la Julia Cameron. 3 pages, stream of consciousness.\n\n"
                "## How AI can help\n\n"
                "- \"Help me articulate what I'm feeling\"\n"
                "- \"I want to write about [topic] but don't know where to start\"\n"
                "- \"Read what I wrote and ask me questions about it\"\n"
                "- \"Help me turn this ramble into something coherent\"\n"
            ),
        },
    ],
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Poetry
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="poetry",
    name="Poetry",
    description="Draft poems, study craft, explore forms from haiku to free verse, and build toward a chapbook. A space for the music of language.",
    icon="🪶",
    directories=[
        "Drafts", "Finished Poems", "Reading Journal", "Craft Notes",
        "Craft Notes/Foundations", "Craft Notes/Intermediate", "Craft Notes/Advanced",
        "Collections", "Submissions", "Prompts", "templates",
    ],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Poem Draft Template",
            "tags": "template, poem, draft",
            "content": (
                "## Title (working)\n\n\n\n"
                "## Form\n\nFree verse / Sonnet / Haiku / Villanelle / Other:\n\n"
                "## Seed\n\nThe image, phrase, or feeling that started this:\n\n\n\n"
                "## Draft\n\n\n\n\n\n\n\n"
                "## Notes to Self\n\n"
                "- What is this poem trying to do?\n"
                "- Which lines feel alive? Which feel dead?\n"
                "- What am I avoiding saying?\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Reading Response Template",
            "tags": "template, reading",
            "content": (
                "## Poem Title\n\n\n## Poet\n\n\n## First Impression\n\n\n\n"
                "## Close Reading\n\n### Structure and Form\n\n\n### Sound\n\n\n"
                "### Imagery and Figurative Language\n\n\n### Turns and Surprises\n\n\n\n"
                "## What I Can Steal\n\nTechniques to try in my own work:\n\n- \n\n"
                "## Favorite Lines\n\n> \n"
            ),
        },
        {
            "folder": "Craft Notes/Foundations",
            "title": "What Makes a Poem",
            "tags": "craft, foundations",
            "content": (
                "A poem is not prose with line breaks. The line is the fundamental unit "
                "of meaning. Where a line breaks controls pacing, emphasis, and surprise.\n\n"
                "## Compression\n\nPoetry says in 14 lines what an essay takes 14 paragraphs "
                "to explore. This compression comes from imagery, figurative language, sound, "
                "and white space.\n\n"
                "## Poetry Does Not Require\n\n"
                "- Rhyme (free verse is the dominant contemporary mode)\n"
                "- A narrative\n- Obscurity\n- Elevated language\n\n"
                "The best poems are clear about their images even when mysterious about their meaning.\n"
            ),
        },
        {
            "folder": "Craft Notes/Foundations",
            "title": "Basic Forms -- Haiku, Sonnet, Free Verse",
            "tags": "craft, foundations, forms",
            "content": (
                "## Haiku\n\n3 lines: 5-7-5 syllables. Captures a single moment. Juxtaposes "
                "two images. The power is in what is NOT said.\n\n"
                "## Sonnet\n\n14 lines of iambic pentameter. Shakespearean (ABAB CDCD EFEF GG) "
                "or Petrarchan (ABBAABBA + sestet). The volta (turn) between octave and sestet "
                "is where the real poem happens.\n\n"
                "## Free Verse\n\nNo fixed meter or rhyme. The poet creates internal coherence "
                "through imagery, line breaks, rhythm, and emotional arc. Arguably harder than "
                "form because you must invent the structure each time.\n"
            ),
        },
        {
            "folder": "Craft Notes/Intermediate",
            "title": "Meter, Rhythm, and Sound Devices",
            "tags": "craft, intermediate, meter, sound",
            "content": (
                "## Metrical Feet\n\n"
                "- Iamb (da-DUM): most common in English. \"Shall I comPARE thee TO a SUMmer's DAY?\"\n"
                "- Trochee (DUM-da): falling, insistent. \"TI-ger, TI-ger, BUR-ning BRIGHT\"\n"
                "- Anapest (da-da-DUM): galloping. Limericks use this.\n"
                "- Dactyl (DUM-da-da): rolling, waltz-like.\n\n"
                "## Sound Devices\n\n"
                "- Alliteration: repeated initial consonants\n"
                "- Assonance: repeated vowel sounds within words\n"
                "- Consonance: repeated consonant sounds at word ends\n"
                "- Slant rhyme: similar but not identical sounds (moon/bone). Emily Dickinson's signature.\n\n"
                "The music is in the arrangement, not the vocabulary.\n"
            ),
        },
        {
            "folder": "Craft Notes/Advanced",
            "title": "Experimental Forms and Building a Chapbook",
            "tags": "craft, advanced, experimental, chapbook",
            "content": (
                "## Found Poetry\n\nTake language from non-poetic sources and arrange it into lines.\n\n"
                "## Erasure Poetry\n\nBlack out most of a printed page, leaving words that form a poem.\n\n"
                "## Concrete Poetry\n\nThe visual arrangement on the page IS part of the meaning.\n\n"
                "## Building a Chapbook\n\n"
                "A chapbook is 20-35 pages of connected poems. The poems need coherence -- "
                "shared theme, voice, or formal constraint. Order matters: the first poem "
                "sets the world, the last poem resonates as a closing statement.\n\n"
                "Submit to contests and open reading periods via Poets & Writers, Duotrope, "
                "and CLMP.\n"
            ),
        },
        {
            "folder": ".",
            "title": "Getting Started",
            "tags": "guide",
            "content": (
                "Welcome to your poetry workshop.\n\n"
                "- **Drafts/**: Poems in progress\n"
                "- **Craft Notes/**: Foundations, Intermediate, Advanced\n"
                "- **Reading Journal/**: Notes on poets you study\n"
                "- **Collections/**: Chapbook manuscripts\n\n"
                "Tell Claude: \"Give me a poetry prompt\" or \"Help me revise this draft.\"\n"
            ),
        },
    ],
    daily_template="## {{date}} -- Poetry Journal\n\n### Observations\n\n\n### Lines and Fragments\n\n- \n",
))


# ---------------------------------------------------------------------------
# Songwriting
# ---------------------------------------------------------------------------

_register(VaultPreset(
    slug="songwriting",
    name="Songwriting",
    description="Write lyrics, sketch melodies, learn song structure, and develop your craft from first verse to finished track. Includes AI-assisted production workflows.",
    icon="🎵",
    directories=[
        "Songs", "Songs/Drafts", "Songs/Finished", "Lyrics", "Chord Charts",
        "Ideas", "Craft Notes", "Craft Notes/Foundations", "Craft Notes/Intermediate",
        "Craft Notes/Advanced", "Co-Writes", "Production Notes", "Business", "templates",
    ],
    seed_notes=[
        {
            "folder": "templates",
            "title": "Song Draft Template",
            "tags": "template, song",
            "content": (
                "## Title (working)\n\n\n## Key / BPM\n\nKey: \nBPM: \n\n"
                "## Core Idea\n\nOne sentence:\n\n\n\n"
                "## Verse 1\n\n\n\n## Pre-Chorus\n\n\n\n## Chorus\n\n\n\n"
                "## Verse 2\n\n\n\n## Bridge\n\n\n\n## Final Chorus\n\n\n\n"
                "## Melody Notes\n\n\n## Production Ideas\n\n\n"
            ),
        },
        {
            "folder": "templates",
            "title": "Chord Chart Template",
            "tags": "template, chords",
            "content": (
                "## Song Title\n\n\n## Key\n\n\n## BPM\n\n\n"
                "```\nIntro:  | Am | F | C | G |\nVerse:  | Am | F | C | G |\n"
                "Chorus: | C  | G | Am | F |\nBridge: | F  | C | G  | Am |\n```\n"
            ),
        },
        {
            "folder": "Craft Notes/Foundations",
            "title": "Song Structure",
            "tags": "craft, foundations, structure",
            "content": (
                "## Building Blocks\n\n"
                "- **Verse**: Tells the story. Different lyrics, same melody each time.\n"
                "- **Chorus**: Emotional centerpiece. Contains the hook/title. Same lyrics each time.\n"
                "- **Pre-Chorus**: Builds anticipation between verse and chorus.\n"
                "- **Bridge**: Contrast. New melody, new chords, new perspective. Appears once.\n"
                "- **Outro**: How the song ends.\n\n"
                "## Common Structures\n\n"
                "- **ABABCB**: Verse/Chorus/Verse/Chorus/Bridge/Chorus (most common pop)\n"
                "- **AABA**: Verse/Verse/Bridge/Verse (jazz standards, Beatles)\n"
                "- **Through-composed**: No repeated sections (Bohemian Rhapsody)\n\n"
                "## Energy Arc\n\nVerse (moderate) -> Pre-Chorus (building) -> Chorus (peak) -> "
                "Bridge (contrast) -> Final Chorus (highest)\n"
            ),
        },
        {
            "folder": "Craft Notes/Foundations",
            "title": "Chord Progressions",
            "tags": "craft, foundations, chords",
            "content": (
                "## Essential Progressions\n\n"
                "**I-IV-V-I** (C-F-G-C): Blues, rock, country, folk. The foundation.\n\n"
                "**I-V-vi-IV** (C-G-Am-F): The most used pop progression. \"Let It Be,\" "
                "\"Someone Like You,\" \"No Woman No Cry.\"\n\n"
                "**vi-IV-I-V** (Am-F-C-G): Same chords, darker starting point. \"Numb,\" \"Africa.\"\n\n"
                "**ii-V-I** (Dm-G-C): Jazz cadence. Strong resolution.\n\n"
                "Most hit songs use 3-5 chords. Complexity is not the goal -- emotional effectiveness is.\n"
            ),
        },
        {
            "folder": "Craft Notes/Foundations",
            "title": "Lyric Writing Fundamentals",
            "tags": "craft, foundations, lyrics",
            "content": (
                "## Lyrics vs Poetry\n\n"
                "Lyrics are heard once in real time. Clarity > complexity. Melody carries meaning. "
                "Repetition is expected. Open vowels sustain on long notes.\n\n"
                "## Principles\n\n"
                "1. Write conversationally\n2. Show, don't tell (specific images > abstract statements)\n"
                "3. One theme per song\n4. Title in the chorus\n"
                "5. Verses = specific narrative, Chorus = universal emotion\n\n"
                "## Process\n\nConcept -> Free-write -> Identify chorus -> Build verses -> Revise for singability\n"
            ),
        },
        {
            "folder": "Craft Notes/Intermediate",
            "title": "Hooks, Rhyme, and Co-Writing",
            "tags": "craft, intermediate",
            "content": (
                "## Hooks\n\nMelodic, lyric, rhythmic, riff, or production. The element that "
                "grabs the listener. Write the chorus first -- the hook is the song's reason for existing.\n\n"
                "## Beyond Perfect Rhyme\n\n"
                "- Slant rhyme (home/stone): more natural, vastly more options\n"
                "- Internal rhyme: rhyme within lines for density\n"
                "- Multisyllabic rhyme: technical mastery (opportunity/community)\n"
                "- If you contort the lyric to land the rhyme, the rhyme is not worth it\n\n"
                "## Co-Writing\n\nMost hits are co-written. Bring ideas. Say \"yes, and.\" "
                "Build chorus first. Record a rough demo. Agree on splits.\n"
            ),
        },
        {
            "folder": "Craft Notes/Advanced",
            "title": "Production, AI Tools, and the Business",
            "tags": "craft, advanced, production, ai, business",
            "content": (
                "## Arrangement\n\nStart sparse, add layers. Verse (stripped) -> Chorus (full) -> "
                "Bridge (contrast) -> Final Chorus (everything). The vocal is the most important "
                "element -- leave room for it in the mid frequencies.\n\n"
                "## AI Tools (2025-2026)\n\n"
                "- **Suno/Udio**: Generate full song demos from text prompts\n"
                "- **ChordChord/AudioCipher**: Generate progressions and melodies as MIDI\n"
                "- Use AI for demos and exploration; your perspective and emotion are the art\n\n"
                "## Revenue Streams\n\n"
                "Streaming royalties, sync licensing (film/TV/ads -- can range $hundreds to $100K+), "
                "performance royalties (register with ASCAP/BMI), mechanical royalties.\n\n"
                "## Sync Tips\n\nOwn your masters. Build a catalog (20-50 songs). Tag metadata. "
                "Use sync libraries (Musicbed, Artlist, Songtradr).\n"
            ),
        },
        {
            "folder": ".",
            "title": "Getting Started",
            "tags": "guide",
            "content": (
                "Welcome to your songwriting workshop.\n\n"
                "- **Songs/**: Drafts and finished songs\n"
                "- **Craft Notes/**: Foundations, Intermediate, Advanced\n"
                "- **Ideas/**: Hooks, titles, fragments\n"
                "- **Co-Writes/**: Collaborative session notes\n\n"
                "Tell Claude: \"Help me write a chorus about...\" or \"What chord progression "
                "would work for a melancholy pop song?\"\n"
            ),
        },
    ],
    daily_template="## {{date}} -- Songwriting Log\n\n### Worked on\n\n\n### Ideas captured\n\n- \n",
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_presets() -> list[dict[str, str]]:
    """Return all available vault presets."""
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "icon": p.icon,
        }
        for p in PRESETS.values()
    ]


def get_preset(slug: str) -> VaultPreset | None:
    """Get a preset by slug."""
    return PRESETS.get(slug)
