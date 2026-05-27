# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repo contains scripts and workflows for organizing Apple Notes using the **Forever Notes framework** (a PARA-style taxonomy with Inbox, Fleeting, Literature, Permanent, Projects, Areas, Resources, Archive, and Review folders). The implementation plan lives in `PLAN.md`.

## Privacy — Hard Constraints

This is a **public open-source repo**. Personal note content, folder names, and paths must never be committed:

- `config/*.local.*` — gitignored; contains your actual folder names and paths
- `data/` — entirely gitignored; contains note exports, proposals, and reports
- Always use `config/taxonomy.example.yaml` and `config/settings.example.yaml` as the committed templates

A pre-commit hook at `.git-hooks/pre-commit` blocks accidental commits of `data/`, `*.local.*` config files, and large JSON files. Activate it with:

```bash
git config core.hooksPath .git-hooks
```

## Setup

```bash
# Copy and fill in personal config (gitignored)
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml

# Set API key / Ollama URL (gitignored)
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY or set OLLAMA_BASE_URL

# Install Python deps and create virtual environment
uv sync
```

## Running Scripts

```bash
# 1. Export notes from Apple Notes
osascript scripts/export/export-notes.applescript

# 2. Classify exported notes (reads most recent export in data/exports/)
uv run notes classify

# 3. Dry-run the proposal to preview moves
osascript scripts/execute/apply-proposal.applescript --dry-run data/proposals/proposal-YYYY-MM-DD.json

# 4. Apply an approved proposal
osascript scripts/execute/apply-proposal.applescript data/proposals/proposal-YYYY-MM-DD.json

# Maintenance — inbox triage only
uv run notes inbox

# Maintenance — audit report
uv run notes audit
```

## Architecture

The pipeline has three stages, separated by human review:

```
Apple Notes → [export-notes.applescript] → data/exports/notes-YYYY-MM-DD.json
                                                          ↓
                                          [classify-notes.py] (Claude API)
                                                          ↓
                                          data/proposals/proposal-YYYY-MM-DD.json
                                                          ↓
                                          ← HUMAN REVIEWS AND EDITS HERE →
                                                          ↓
                                          [apply-proposal.applescript]
                                                          ↓
                                                    Apple Notes (moved)
```

**AppleScript for reads and writes** (not SQLite) — the NoteStore.sqlite schema is undocumented and changes between macOS versions. Writing via AppleScript goes through Notes app APIs and is safe across upgrades.

**JSON proposals as an intermediate step** — bulk moves are hard to undo. The proposal file lets the user inspect, edit, and selectively approve before anything is touched in Notes.

**Note ID caveat** — Apple Notes `x-coredata://` IDs can change across iCloud sync conflicts or device migrations. Scripts match on ID but must gracefully fall back to title + folder, logging any ambiguities.

## Config Files

| File | Committed | Purpose |
|------|-----------|---------|
| `config/taxonomy.example.yaml` | Yes | Generic folder template |
| `config/settings.example.yaml` | Yes | Provider, model, batch size, paths |
| `.env.example` | Yes | Environment variable template |
| `config/taxonomy.local.yaml` | **No** | Your actual folder names |
| `config/settings.local.yaml` | **No** | Your personal settings |
| `.env` | **No** | API keys and provider URLs |

Python scripts resolve config by loading `*.local.*` if present, falling back to `*.example.*`.

## Proposal JSON Schema

The `moves` array drives `apply-proposal.applescript`. The `needs_review` array is human-only; the script ignores it. `confidence` values: `high`, `medium`, `low` — low-confidence notes go to `needs_review`.

## Phased Implementation Status

See `PLAN.md` for the full spec. Implementation phases:

1. **Phase 1** — Scaffold, `.gitignore`, pre-commit hook, config examples, README
2. **Phase 2** — `export-notes.applescript`, `classify-notes.py`, `apply-proposal.applescript`
3. **Phase 3** — `process-inbox.py`, `audit.py`, runbooks
4. **Phase 4** — Scheduling via cron or launchd (optional)
