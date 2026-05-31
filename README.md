# manage-apple-notes

[![CI](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml/badge.svg)](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jdmacleod/manage-apple-notes/graph/badge.svg)](https://codecov.io/gh/jdmacleod/manage-apple-notes)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Scripts and workflows for organizing Apple Notes using AI-powered classification into a user-defined folder taxonomy — PARA, Zettelkasten-influenced, or custom. Optional [Forever Notes](https://forevernotesframework.com) structural features (Hub notes, tags) are available in strict mode.

The pipeline is: **export → discover themes → AI classify → human review → apply**. Nothing touches your notes until you approve a proposal.

Set `reorganization_mode` in `settings.local.yaml` to control how aggressively the pipeline proposes changes — from `"conservative"` (only high-confidence moves for notes outside Inbox/Fleeting) through `"standard"` (default) to `"full"` (reclassify from scratch).

## Prerequisites

- macOS with Apple Notes
- **Terminal Automation permission** — export, move, restore, and hub-sync commands run AppleScript via `osascript`, which requires your terminal app to be allowed to control Notes. Grant it in **System Settings → Privacy & Security → Automation** — enable the Notes checkbox under your terminal app (Terminal, iTerm2, etc.). macOS will prompt the first time a script runs; if the prompt never appears, open System Settings and add it manually.
- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- An LLM provider: an [Anthropic API key](https://console.anthropic.com) (cloud) **or** [Ollama](https://ollama.com) running locally

## Setup

```bash
# 1. Clone
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes

# 2. Activate pre-commit hook (blocks accidental data commits)
git config core.hooksPath .git-hooks

# 3. Copy and fill in personal config (these files are gitignored)
# Use taxonomy.example.yaml (Forever Notes / Zettelkasten) or taxonomy.para.yaml (PARA method)
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both files with your actual Apple Notes folder names.
# Taxonomy files use "taxonomy:" as the root key — if upgrading from an earlier version,
# rename "forever_notes:" to "taxonomy:" in your taxonomy.local.yaml.
# If all your taxonomy folders live inside a single container folder in Apple Notes
# (e.g. "Library"), set toplevel_folder.enabled: true and update toplevel_folder.name
# in settings.local.yaml to match.

# 4. Install Python dependencies and create virtual environment
uv sync

# 5. Set your API key / provider URL
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY for cloud, or set OLLAMA_BASE_URL for local
```

## Quick Reference

See [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) for the full walkthrough.

```bash
# Initial library setup (one-time)
uv run notes export              # export from Apple Notes
uv run notes backup              # safety backup before bulk changes → data/backups/
uv run notes discover            # map thematic clusters → data/theme-maps/
uv run notes draft               # generate editable taxonomy YAML → data/taxonomy-drafts/
# → HUMAN: review draft, copy to config/taxonomy.local.yaml
uv run notes classify            # classify notes → data/proposals/
# → HUMAN: review proposal JSON
uv run notes move --dry-run      # preview moves
uv run notes move                # move notes per approved proposal
uv run notes dedup               # detect duplicates → data/dedup-proposals/
# → HUMAN: review dedup proposal
uv run notes purge               # preview deletions (dry-run by default)
uv run notes purge --execute     # delete confirmed duplicates
uv run notes export              # refresh after deletions
uv run notes sync-hubs           # create ✱ Home and ✱ Hub notes (strict mode only)

# Ongoing
uv run notes backup              # timestamped backup to data/backups/
uv run notes triage              # triage Inbox captures → data/proposals/
# → HUMAN: review proposal JSON
uv run notes move                # move notes per approved proposal
uv run notes audit               # quality report (stale, stub, duplicate)
uv run notes export              # refresh before hub sync
uv run notes sync-hubs           # update ✱ Home and ✱ Hub notes (strict mode only)

# Recovery
uv run notes restore             # recreate notes lost during move
uv run notes repair              # fix formatting after an iCloud Recently Deleted restore
```

Most commands accept `--dry-run` to preview without making changes. `purge` is a dry-run by default; pass `--execute` to apply deletions.

> **Backup scope:** `notes backup` saves a text-only snapshot — note titles, plaintext body, and folder paths. Images, attachments, sketches, and formatting are not captured. For full media backup, use Time Machine or a clone utility (CCC, SuperDuper) to back up `~/Library/Group Containers/group.com.apple.notes/`.

Full documentation lives in the [`docs/`](docs/) directory.

## Privacy, Cost, and Speed

**LLM provider choice affects what leaves your device.** Pick the option that matches your comfort level:

| Provider | Note content sent off-device? | Setup complexity | Cost | Speed |
|----------|-------------------------------|------------------|------|-------|
| [Anthropic API](https://console.anthropic.com) | Yes — note text is sent to Anthropic's servers for inference and is subject to [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) | Low — API key only | Pay per use with token credits | Fast |
| [Ollama](https://ollama.com) (local) | No — inference runs entirely on your machine | Medium — install Ollama, pull a model | No cost, model runs locally | Slower, but depends on your hardware |

Regardless of provider, this repo is public and personal data is kept out of git:

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` are gitignored
- `.env` (your API keys) is gitignored; only `.env.example` is committed
- The entire `data/` directory (exports, proposals, reports) is gitignored
- A pre-commit hook blocks accidental commits of private files

See [`config/taxonomy.example.yaml`](config/taxonomy.example.yaml) (Forever Notes / Zettelkasten), [`config/taxonomy.para.yaml`](config/taxonomy.para.yaml) (PARA method), and [`config/settings.example.yaml`](config/settings.example.yaml) for the committed templates.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality requirements, and how to submit a pull request.

## License

MIT
