# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repo contains scripts and workflows for organizing Apple Notes using AI-powered classification into a user-defined, PARA-style folder taxonomy (Inbox, Fleeting, Literature, Permanent, Projects, Areas, Resources, Archive, and Review). Optional [Forever Notes](https://forevernotesframework.com) structural features (Hub notes, ✱ Home, tags) are available when `forever_notes_mode: strict` is set. The implementation plan lives in `PLAN.md`.

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

## Code Quality

Python formatting and linting use **ruff**; type checking uses **mypy**. Both are configured
in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]` and installed as dev dependencies.

```bash
uv run ruff check scripts/        # lint — must pass with zero errors
uv run ruff format scripts/       # format in place
uv run mypy scripts/              # type check — address new errors introduced by your change
```

Run `ruff check` and fix any errors before committing. `ruff format` is non-negotiable for
changed files. Mypy errors in files you haven't touched don't need to be fixed in the same
PR, but errors introduced by new code should be resolved.

Key rules in effect: `E`/`F` (pyflakes/pycodestyle), `I` (isort), `UP` (pyupgrade),
`B` (bugbear), `SIM` (simplify). `E501` (line length) is enforced by the formatter, not
the linter. `SIM108` (ternary) is suppressed — explicit `if/else` is preferred.

## Running Scripts

The full workflow uses only `notes` commands:

```bash
uv run notes export              # export from Apple Notes
uv run notes discover            # discover themes → data/theme-maps/
uv run notes classify            # classify notes → data/proposals/
uv run notes move --dry-run      # preview moves (uses latest proposal)
uv run notes move                # move notes per approved proposal
uv run notes triage              # triage Inbox notes only
uv run notes audit               # quality report → data/reports/
```

All commands accept `--dry-run` to preview without side effects.
See `docs/runbooks/main-workflow.md` for the full step-by-step workflow.

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
4. **Phase 3b** — `deduplicate_notes.py`, `apply-dedup-proposal.applescript`
5. **Phase 4** — Scheduling via cron or launchd (optional)

## Documentation Update Pass

At the end of any work turn that modifies code, review and update as needed:

- **`docs/security-considerations.md`** — if changes affect data flow, LLM provider handling, new external dependencies, or how note content is transmitted or stored.
- **`docs/technical-notes.md`** — if changes introduce new Apple Notes/macOS platform behavior findings, changes to batch/context handling, or model compatibility updates.

If neither file needs updating, note that explicitly before closing the turn.
