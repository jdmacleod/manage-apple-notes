# manage-apple-notes

Scripts and workflows for organizing Apple Notes using AI-powered classification into a user-defined folder taxonomy — PARA, Zettelkasten-influenced, or custom. Optional [Forever Notes](https://forevernotesframework.com) structural features (Hub notes, tags) are available in strict mode.

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
# Use taxonomy.example.yaml (Forever Notes / Zettelkasten) or taxonomy.para.yaml (PARA method)
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both files with your actual Apple Notes folder names.
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
# → HUMAN: review theme map, add subfolders to taxonomy.local.yaml
uv run notes classify            # classify notes → data/proposals/
# → HUMAN: review proposal JSON
uv run notes apply --dry-run     # preview moves
uv run notes apply               # apply approved moves
uv run notes dedup               # detect duplicates → data/dedup-proposals/
# → HUMAN: review dedup proposal
uv run notes apply-dedup         # preview deletions (dry-run by default)
uv run notes apply-dedup --execute  # delete confirmed duplicates

# Ongoing
uv run notes backup              # timestamped backup to data/backups/
uv run notes inbox               # triage Inbox captures
uv run notes audit               # quality report (stale, stub, duplicate)
uv run notes sync-hubs           # update ✱ Home and ✱ Hub notes (strict mode only)

# Recovery
uv run notes restore             # recreate notes lost during apply
uv run notes repair-restored     # fix formatting after an iCloud Recently Deleted restore
```

Most commands accept `--dry-run` to preview without making changes. `apply-dedup` is a dry-run by default; pass `--execute` to apply deletions.

> **Backup scope:** `notes backup` saves a text-only snapshot — note titles, plaintext body, and folder paths. Images, attachments, sketches, and formatting are not captured. For full media backup, use Time Machine or a clone utility (CCC, SuperDuper) to back up `~/Library/Group Containers/group.com.apple.notes/`.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) | Full step-by-step workflow |
| [docs/para-method.md](docs/para-method.md) | PARA method overview, taxonomy designs, and guidance for generating taxonomy.local.yaml |
| [docs/forever-notes-framework.md](docs/forever-notes-framework.md) | Forever Notes loose/strict modes, Hub notes, and sync-hubs usage |
| [docs/security-considerations.md](docs/security-considerations.md) | Data flow, cloud vs. local LLM, Apple Notes MCP guidance |
| [docs/technical-notes.md](docs/technical-notes.md) | Apple Notes platform behavior, LLM findings, local model recommendations |
| [docs/references.md](docs/references.md) | Web references: Apple Notes platform, note organisation frameworks, security, LLM providers, Apple Notes MCP servers |

## Privacy

This is a public repo. Your note content and folder names never leave your machine unencrypted:

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` are gitignored
- `.env` (your API keys) is gitignored; only `.env.example` is committed
- The entire `data/` directory is gitignored
- A pre-commit hook blocks accidental commits of private files

See `config/taxonomy.example.yaml` (Forever Notes / Zettelkasten), `config/taxonomy.para.yaml` (PARA method), and `config/settings.example.yaml` for the committed templates.

## Default Folder Taxonomy

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

This is the default Zettelkasten-influenced taxonomy. For the PARA method (Inbox, Projects, Areas, Resources, Archive), see [`config/taxonomy.para.yaml`](config/taxonomy.para.yaml) and [`docs/para-method.md`](docs/para-method.md).

## Forever Notes

This project optionally supports the [Forever Notes framework](https://forevernotesframework.com).
See [myforevernotes.com](https://www.myforevernotes.com/docs/home) for the full framework docs.

Two operating modes are available, set via `forever_notes_mode` in `settings.local.yaml`:

| Mode | What it does |
|------|-------------|
| `loose` (default) | Folder taxonomy, theme discovery, classification, deduplication |
| `strict` | Everything in loose, plus ✱ Hub notes per theme, a ✱ Home root note, and tags on classified notes |

Strict mode is **additive** — it does not change folder structure or how classification works.
See [`docs/forever-notes-framework.md`](docs/forever-notes-framework.md) for details.

## License

MIT
