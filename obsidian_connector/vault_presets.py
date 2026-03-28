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
