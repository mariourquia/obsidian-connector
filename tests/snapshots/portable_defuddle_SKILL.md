---
name: defuddle
description: Extract clean markdown content from web pages using the Defuddle CLI, removing clutter and navigation to save tokens. Use instead of WebFetch when the user provides a URL to read or analyze, for online documentation, articles, blog posts, or any standard web page.
---

> **Portable skill** -- This skill works with any AI agent (Codex, OpenCode, Gemini, etc.).
> It does not require the obsidian-connector MCP server.

# Defuddle

Extract the main content from web pages and convert to clean Markdown. Removes
navigation, ads, sidebars, footers, and comments. Built by the Obsidian team.

## Prerequisites

- Node.js v18+ installed
- `npx` available (comes with npm)
- Or install globally: `npm install -g defuddle`

## Commands

### Extract as Markdown (default choice)

```bash
npx defuddle parse <url> --md
```

### Extract as JSON (includes metadata)

```bash
npx defuddle parse <url> --json
```

JSON output includes: `content`, `title`, `author`, `description`, `domain`,
`site`, `favicon`, `image`, `language`, `published`, `wordCount`, `parseTime`.

### Save to file

```bash
npx defuddle parse <url> --md -o output.md
```

### Extract specific metadata property

```bash
npx defuddle parse <url> -p title
npx defuddle parse <url> -p author
npx defuddle parse <url> -p description
npx defuddle parse <url> -p domain
npx defuddle parse <url> -p published
```

### Parse a local HTML file

```bash
npx defuddle parse page.html --md
```

## When to Use

- Reading an article, blog post, or documentation page
- Clipping web content to save in the vault
- Extracting text from a URL the user provided
- Minimizing token usage when processing web pages (removes clutter)
- Converting web content to Obsidian-compatible Markdown

## When NOT to Use

- Pages requiring authentication or login
- API endpoints returning JSON/XML (use curl or fetch directly)
- Pages that are already Markdown or plain text
- Dynamic single-page apps that require JavaScript interaction

## Workflow: Clip to Vault

```bash
# 1. Extract the content
npx defuddle parse "https://example.com/article" --md -o /tmp/clip.md

# 2. Read the extracted content
cat /tmp/clip.md

# 3. Save to vault (via obsidian CLI or obsidian-connector MCP)
obsidian create path="Inbox/article-title.md" content="$(cat /tmp/clip.md)"
```

## Troubleshooting

- **"npx: command not found"**: Install Node.js from https://nodejs.org
- **First run is slow**: `npx` downloads the package on first use (~2-3 seconds)
- **Empty output**: The page may block automated access. Try a different URL.
- **For faster repeated use**: `npm install -g defuddle` then use `defuddle parse` (no npx)

## Site-Specific Extractors

Defuddle includes optimized extractors for:
- Twitter/X (via FxTwitter API)
- Reddit
- Hacker News
- ChatGPT conversations
- Grok conversations

These return cleaner output than the generic extractor for those platforms.
