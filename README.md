# manage-apple-notes

Scripts and workflows for organizing Apple Notes using the [Forever Notes](https://forevernotesframework.com) framework (a PARA-style taxonomy).

The pipeline is: **export → AI classify → human review → apply**. Nothing touches your notes until you approve a proposal.

## Prerequisites

- macOS with Apple Notes
- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- An [Anthropic API key](https://console.anthropic.com)

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

# 5. Set your API key
export ANTHROPIC_API_KEY=sk-...
```

## One-Time Cleanup

See [docs/runbooks/one-time-cleanup.md](docs/runbooks/one-time-cleanup.md) for the full walkthrough. In brief:

```bash
# Step 1: Export all notes to data/exports/
osascript scripts/export/export-notes.applescript

# Step 2: Classify with Claude (writes data/proposals/proposal-YYYY-MM-DD.json)
uv run notes classify

# Step 3: Review and edit the proposal JSON, then dry-run
osascript scripts/execute/apply-proposal.applescript --dry-run data/proposals/proposal-YYYY-MM-DD.json

# Step 4: Apply approved moves
osascript scripts/execute/apply-proposal.applescript data/proposals/proposal-YYYY-MM-DD.json
```

## Ongoing Maintenance

```bash
# Process Inbox — classify and propose moves for new captures
uv run notes inbox

# Audit — find stale, duplicate, and orphaned notes (report only, no changes)
uv run notes audit
```

## Privacy

This is a public repo. Your note content and folder names never leave your machine unencrypted:

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` are gitignored
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
