# manage-apple-notes

Scripts and workflows for organizing Apple Notes using the [Forever Notes](https://forevernotesframework.com) framework (a PARA-style taxonomy).

The pipeline is: **export → discover themes → AI classify → human review → apply**. Nothing touches your notes until you approve a proposal.

## Prerequisites

- macOS with Apple Notes
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
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both files with your actual Apple Notes folder names

# 4. Install Python dependencies and create virtual environment
uv sync

# 5. Set your API key / provider URL
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY for cloud, or set OLLAMA_BASE_URL for local
```

## Quick Reference

See [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) for the full walkthrough.

```bash
# Initial library setup (one-time, two-pass)
uv run notes export              # export from Apple Notes
uv run notes discover            # map thematic clusters → data/theme-maps/
# → HUMAN: review theme map, add subfolders to taxonomy.local.yaml
uv run notes classify            # classify notes → data/proposals/
# → HUMAN: review proposal JSON
uv run notes apply --dry-run     # preview moves
uv run notes apply               # apply approved moves

# Ongoing
uv run notes inbox               # triage Inbox captures
uv run notes audit               # quality report (stale, stub, duplicate)
```

All commands accept `--dry-run` to preview without making changes.

## Privacy

This is a public repo. Your note content and folder names never leave your machine unencrypted:

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` are gitignored
- `.env` (your API keys) is gitignored; only `.env.example` is committed
- The entire `data/` directory is gitignored
- A pre-commit hook blocks accidental commits of private files

See `config/taxonomy.example.yaml` and `config/settings.example.yaml` for the committed templates.

## Folder Taxonomy

| Folder | Purpose |
|--------|---------|
| Inbox | Temporary capture, not yet processed |
| Fleeting | Quick thoughts, to be processed or discarded |
| Literature | Notes tied to a specific source (book, article, talk) |
| Permanent | Atomic, evergreen concepts in your own words |
| Projects | Notes tied to a specific active project |
| Areas | Ongoing responsibilities and reference |
| Resources | Reference material, how-tos, collections |
| Archive | Inactive, completed, or outdated notes |
| Review | Needs human triage (used during cleanup) |

## License

MIT
