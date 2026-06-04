# manage-apple-notes

[![CI](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml/badge.svg)](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jdmacleod/manage-apple-notes/graph/badge.svg)](https://codecov.io/gh/jdmacleod/manage-apple-notes)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AI-powered organization for Apple Notes. The pipeline is **export → discover → classify → human review → apply** — nothing touches your notes until you approve a proposal.

## Quickstart

> macOS 26+ · Apple Silicon · Apple Intelligence enabled in System Settings → Apple Intelligence & Siri

```bash
# 1. Install uv (if you haven't already)
# https://docs.astral.sh/uv/getting-started/installation/

# 2. Clone and install
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes
git config core.hooksPath .git-hooks   # blocks accidental data commits
uv sync

# 3. Pick a framework and name your folders (takes ~2 minutes)
uv run notes setup

# 4. Build the on-device inference bridge (requires Xcode 26)
make -C swift/apple-llm build

# 5. Grant Automation permission
# System Settings → Privacy & Security → Automation → enable Notes for your terminal app.

# 6. Run the pipeline
uv run notes export
uv run notes classify
# Review data/proposals/proposal-YYYY-MM-DD.json, then:
uv run notes move --dry-run
uv run notes move
```

`notes setup` asks a few questions and writes `config/taxonomy.local.yaml` and `config/settings.local.yaml` for you. It picks from PARA, GTD, or Zettelkasten based on your answers and (optionally) your existing note library.

Not on Apple Silicon or macOS 26+? See [GUIDE.md](GUIDE.md) for Anthropic API, Ollama, and AWS-Ollama provider options.

## Provider comparison

Benchmarked on a 390-note library (2024 M4 MacBook Pro). Anthropic not yet timed.

| Provider | Note content leaves device | Setup | Discover | Classify | Cost |
|---|---|---|---|---|---|
| **Apple Intelligence** *(default)* | Never | Medium | 12 min | 60 min | $0 |
| Anthropic API | Yes — Anthropic's servers | Low | — | — | TBD |
| Ollama (local, gemma-4-E4B) | Never | Medium | 15 min | 60 min | $0 |
| AWS-Ollama (g5.xlarge, gpt-oss:20b) | Never (your EC2, SSH tunnel) | High | 11 min | 20 min | $1 |

## Commands

See [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) for the full walkthrough.

```bash
# First-time setup
uv run notes export              # export from Apple Notes
uv run notes setup               # interactive wizard — pick framework, name folders

# Initial library setup
uv run notes backup              # safety backup → data/backups/
uv run notes discover            # map thematic clusters → data/theme-maps/
uv run notes draft               # generate taxonomy draft → data/taxonomy-drafts/
# → HUMAN: review draft, copy to config/taxonomy.local.yaml
uv run notes classify            # classify notes → data/proposals/
# → HUMAN: review proposal JSON
uv run notes move --dry-run      # preview moves
uv run notes move                # apply approved proposal
uv run notes dedup               # detect duplicates → data/dedup-proposals/
# → HUMAN: review dedup proposal
uv run notes purge --execute     # delete confirmed duplicates
uv run notes sync-hubs           # update ✱ Home and Hub notes (strict mode only)

# Ongoing
uv run notes triage              # triage Inbox → data/proposals/
uv run notes audit               # quality report (stale, stub, duplicate)
uv run notes sync-hubs           # update ✱ Home and Hub notes (strict mode only)

# Recovery
uv run notes restore             # recreate notes lost during a move (Note: can only recreate text notes!)
```

Most commands accept `--dry-run`. `purge` is dry-run by default; pass `--execute` to apply.

> **Backup scope:** `notes backup` saves text only — titles, plaintext body, folder paths. Images and attachments are not captured. For full media backup use Time Machine or a clone of `~/Library/Group Containers/group.com.apple.notes/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality requirements, and how to submit a pull request.

## Documentation

- [GUIDE.md](GUIDE.md) — full setup for all providers, AWS CDK, Apple Intelligence build steps, privacy details
- [docs/setup.md](docs/setup.md) — framework comparison, corpus signals, manual config editing
- [docs/para-method.md](docs/para-method.md) — PARA method guide (two taxonomy designs)
- [docs/gtd-method.md](docs/gtd-method.md) — GTD method guide (two taxonomy designs)
- [docs/forever-notes-framework.md](docs/forever-notes-framework.md) — Forever Notes / Zettelkasten framework reference
- [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) — step-by-step workflow
- [docs/](docs/) — technical notes, security considerations, runbooks

## License

MIT
