# manage-apple-notes — Project Plan

> **Handoff document for Claude Code implementation.**
> All folder names, note titles, and personal identifiers in this document are
> placeholders. Real names live in `config/taxonomy.local.yaml` (gitignored).

---

## Goal

Build a set of scripts and workflows that:

1. Perform a **one-time cleanup** of an existing Apple Notes library, reorganizing
   notes according to the Forever Notes framework.
2. Support **ongoing maintenance passes** — inbox processing, library audits, and
   archiving — that can be run manually or on a schedule.

The project is a **public open-source repo**. No personal note content, folder
names, or identifying information should ever be committed.

---

## Repository Layout

Create the following structure at `~/Projects/manage-apple-notes/`:

```
manage-apple-notes/
├── README.md
├── PLAN.md                          # This file
├── pyproject.toml                   # Python project config, deps, entry point
├── .gitignore
├── .git-hooks/
│   └── pre-commit                   # Safety hook — blocks accidental data commits
│
├── scripts/
│   ├── __init__.py
│   ├── cli.py                       # Unified 'notes' CLI entry point (typer)
│   ├── export/
│   │   └── export-notes.applescript # Dump all notes to data/exports/
│   ├── classify/
│   │   ├── __init__.py
│   │   └── classify_notes.py        # Send export to Claude, write proposal
│   ├── execute/
│   │   └── apply-proposal.applescript  # Read approved proposal, move notes
│   └── maintenance/
│       ├── __init__.py
│       ├── process_inbox.py         # Classify and propose moves for Inbox notes
│       └── audit.py                 # Find stale, duplicate, orphaned notes
│
├── prompts/
│   ├── classify-notes.md            # Prompt template: bulk classification
│   ├── process-inbox.md             # Prompt template: inbox triage
│   └── audit.md                     # Prompt template: library audit
│
├── config/
│   ├── taxonomy.example.yaml        # Generic Forever Notes folder template
│   ├── settings.example.yaml        # Paths, model, batch size, etc.
│   ├── taxonomy.local.yaml          # GITIGNORED — your actual folder names
│   └── settings.local.yaml          # GITIGNORED — your personal settings
│
├── docs/
│   ├── forever-notes-framework.md   # Framework reference
│   └── runbooks/
│       ├── one-time-cleanup.md
│       ├── inbox-processing.md
│       └── audit.md
│
└── data/                            # ENTIRELY GITIGNORED
    ├── exports/                     # Raw dumps from Apple Notes
    ├── proposals/                   # Classification proposals (JSON)
    ├── reports/                     # Maintenance pass outputs
    └── archive/                     # Old proposals and reports
```

---

## Privacy and Git Safety

### .gitignore (root)

```gitignore
# Private config — contains personal folder names and paths
config/*.local.*

# All personal data — note exports, proposals, reports
data/

# Convenience: any file explicitly marked private
*.private.md
PRIVATE*.md

# macOS
.DS_Store

# Python
__pycache__/
*.pyc
.venv/
```

### data/.gitignore

Create `data/.gitignore` with content:
```
*
!.gitignore
```

This ensures the `data/` directory exists in the repo (via the `.gitignore` file
itself) but every file inside is blocked, including in subdirectories.

### Pre-commit Hook

Create `.git-hooks/pre-commit` (chmod +x):

```bash
#!/usr/bin/env bash
# Blocks commits that may contain personal note data.

set -e

ERRORS=0

# Block any file from data/
if git diff --cached --name-only | grep -q '^data/'; then
  echo "ERROR: Staged files found inside data/ — this directory is private."
  ERRORS=$((ERRORS + 1))
fi

# Block large JSON files (likely note exports)
while IFS= read -r file; do
  if [[ "$file" == *.json ]]; then
    size=$(git cat-file -s "$(git ls-files --error-unmatch --stage "$file" \
      2>/dev/null | awk '{print $2}')" 2>/dev/null || echo 0)
    if [ "$size" -gt 10240 ]; then  # 10 KB threshold
      echo "ERROR: Large JSON file staged: $file (${size} bytes) — likely an export."
      ERRORS=$((ERRORS + 1))
    fi
  fi
done < <(git diff --cached --name-only)

# Block *.local.* config files
if git diff --cached --name-only | grep -q '\.local\.'; then
  echo "ERROR: A *.local.* config file is staged — these are private."
  ERRORS=$((ERRORS + 1))
fi

if [ "$ERRORS" -gt 0 ]; then
  echo ""
  echo "Commit blocked. Review staged files with: git diff --cached --name-only"
  exit 1
fi

exit 0
```

Activate with: `git config core.hooksPath .git-hooks`

Add this step to README.md under "Setup".

---

## Config Files

### config/taxonomy.example.yaml

```yaml
# Forever Notes folder taxonomy — generic template.
# Copy to taxonomy.local.yaml and fill in your actual folder names.

forever_notes:
  inbox: "[YOUR_INBOX_FOLDER]"          # e.g. "Inbox" or "Quick Capture"
  fleeting: "[YOUR_FLEETING_FOLDER]"    # Temporary captures not yet processed
  literature: "[YOUR_LITERATURE_FOLDER]" # Source-linked notes
  permanent: "[YOUR_PERMANENT_FOLDER]"  # Atomic evergreen concepts
  projects: "[YOUR_PROJECTS_FOLDER]"    # Active project notes
  areas: "[YOUR_AREAS_FOLDER]"          # Ongoing responsibilities
  resources: "[YOUR_RESOURCES_FOLDER]"  # Reference material
  archive: "[YOUR_ARCHIVE_FOLDER]"      # Inactive / completed
  review: "[YOUR_REVIEW_FOLDER]"        # Needs human triage (used during cleanup)
```

### config/settings.example.yaml

```yaml
# General settings — copy to settings.local.yaml and customize.

claude:
  model: "claude-opus-4-6"   # or claude-sonnet-4-6 for cost/speed tradeoff
  batch_size: 20              # Notes per API call during bulk classification

paths:
  exports_dir: "data/exports"
  proposals_dir: "data/proposals"
  reports_dir: "data/reports"

export:
  include_body: true
  max_body_chars: 2000        # Truncate long notes for classification
  skip_empty: true
```

---

## Scripts Specification

### scripts/export/export-notes.applescript

**Purpose:** Dump all notes from Apple Notes to a JSON file at
`data/exports/notes-YYYY-MM-DD.json`.

**Output schema per note:**
```json
{
  "id": "x-coredata://...",
  "title": "Note title",
  "body": "Plain text body (truncated to max_body_chars if configured)",
  "folder": "Current folder name",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-03-20T14:22:00Z",
  "word_count": 142
}
```

**Implementation notes:**
- Use AppleScript's `tell application "Notes"` to iterate all notes
- For body text: use `plaintext` property of each note (strips HTML)
- Write output via `do shell script "cat > ..."` or pipe to Python for JSON encoding
- Skip notes in the Trash folder

### scripts/classify/classify_notes.py

**Purpose:** Read an export file, classify each note against the taxonomy,
write a proposal JSON to `data/proposals/`.

**Inputs:**
- Export file: `data/exports/notes-YYYY-MM-DD.json`
- Taxonomy: `config/taxonomy.local.yaml` (fallback: `taxonomy.example.yaml`)
- Settings: `config/settings.local.yaml` (fallback: `settings.example.yaml`)
- Prompt template: `prompts/classify-notes.md`

**Output schema (data/proposals/proposal-YYYY-MM-DD.json):**
```json
{
  "generated_at": "2024-03-20T15:00:00Z",
  "source_export": "data/exports/notes-2024-03-20.json",
  "moves": [
    {
      "id": "x-coredata://...",
      "title": "Note title",
      "current_folder": "Old Folder",
      "proposed_folder": "Permanent",
      "confidence": "high",
      "reason": "Atomic concept with clear definition"
    }
  ],
  "needs_review": [
    {
      "id": "x-coredata://...",
      "title": "Ambiguous note",
      "current_folder": "Misc",
      "reason": "Unclear purpose — too short to classify"
    }
  ],
  "no_change": [
    {
      "id": "x-coredata://...",
      "title": "Already correct",
      "current_folder": "Archive"
    }
  ]
}
```

**Implementation notes:**
- Batch notes in groups of `batch_size` (default 20) to stay within context limits
- Use the Anthropic Python SDK (`anthropic` package)
- Inject the taxonomy folder names into the prompt at runtime
- `confidence` values: `high`, `medium`, `low`
- Notes with `low` confidence or flagged ambiguous go to `needs_review`
- Print a summary to stdout: total notes, move count, needs_review count

### scripts/execute/apply-proposal.applescript

**Purpose:** Read an approved proposal JSON and execute the moves in Apple Notes.

**Inputs:**
- Proposal file path (passed as argument)
- Only processes entries in `moves` array (not `needs_review`)

**Implementation notes:**
- For each move: find note by `id`, move to target folder
- Create target folder if it doesn't already exist
- Print a log line for each move: `[MOVED] "Note Title" → Target Folder`
- Print a summary at the end: N moved, N skipped (not found), N errors
- On error for any individual note: log and continue (don't abort the whole run)

**Safety:** The operator should review the proposal JSON before running this
script. Provide a `--dry-run` flag that prints what would happen without
making changes.

### scripts/maintenance/process_inbox.py

**Purpose:** Export only the Inbox folder, classify, and write a proposal.

Same pipeline as `classify-notes.py` but scoped to the configured inbox folder.
Designed to be run frequently (daily or a few times per week).

### scripts/maintenance/audit.py

**Purpose:** Analyze the full library for quality issues. Writes a report to
`data/reports/audit-YYYY-MM-DD.md` (human-readable Markdown, not a proposal).

**Checks to include:**
- Notes not modified in > 180 days that are not in Archive → flag for archiving
- Notes with body length < 50 characters → stub notes, flag for deletion or expansion
- Notes with identical or near-identical titles → possible duplicates
- Notes in the Inbox older than 7 days → stale captures
- Notes in Fleeting older than 30 days → should be processed or deleted

**Output:** Markdown report with sections per check, listing note titles and
current folders. No automatic changes — human reviews and decides.

---

## Prompt Templates

### prompts/classify-notes.md

````markdown
You are organizing notes in Apple Notes according to the Forever Notes framework.

The available target folders are:
- Inbox: {INBOX} — temporary capture, not yet processed
- Fleeting: {FLEETING} — quick thoughts, to be processed or discarded
- Literature: {LITERATURE} — notes tied to a specific source (book, article, talk)
- Permanent: {PERMANENT} — atomic, evergreen concepts in your own words
- Projects: {PROJECTS} — notes tied to a specific active project
- Areas: {AREAS} — ongoing responsibilities and reference for areas of life/work
- Resources: {RESOURCES} — reference material, how-tos, collections
- Archive: {ARCHIVE} — inactive, completed, or outdated notes
- Review: {REVIEW} — use this when classification is genuinely unclear

For each note below, return a JSON array with one object per note:
{
  "id": "<the id field from the input>",
  "proposed_folder": "<exact folder name from the list above>",
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}

Classify based on content and current folder context. Use "Review" for notes
that are too short, too ambiguous, or clearly belong to a category not
representable in this taxonomy. Prefer "high" confidence only when the
classification is obvious.

Notes to classify:
{NOTES_JSON}
````

---

## Phased Implementation

### Phase 1 — Scaffold and Safety (implement first)

1. Create the full directory structure
2. Initialize git repo, write `.gitignore`, create `data/.gitignore`
3. Install pre-commit hook
4. Write `config/taxonomy.example.yaml` and `config/settings.example.yaml`
5. Write README.md with setup instructions including hook activation
6. Verify: `git status` shows no private files after adding real local configs

### Phase 2 — Export and Classify (one-time cleanup)

1. Implement `export-notes.applescript`
2. Implement `classify-notes.py` with Anthropic SDK
3. Implement `apply-proposal.applescript` with `--dry-run` support
4. Write `docs/runbooks/one-time-cleanup.md`
5. Test end-to-end on a small subset (e.g., 20 notes) before full run

### Phase 3 — Maintenance Scripts

1. Implement `process_inbox.py`
2. Implement `audit.py`
3. Write runbooks for each
4. (Optional) Add a shell wrapper `run.sh` that presents a menu for common tasks

### Phase 4 — Scheduling (optional)

1. Document how to schedule `process-inbox.py` via cron or macOS launchd
2. Alternatively, create an Apple Shortcut that triggers the inbox script
   and surfaces a notification with the proposal summary

---

## Setup Instructions (for README.md)

```bash
# 1. Clone
git clone https://github.com/[USERNAME]/manage-apple-notes.git
cd manage-apple-notes

# 2. Activate pre-commit hook
git config core.hooksPath .git-hooks

# 3. Copy and fill in personal config
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both files with your actual Apple Notes folder names

# 4. Install Python dependencies and create virtual environment
# Requires uv: https://docs.astral.sh/uv/ (brew install uv)
uv sync

# 5. Set your API key
export ANTHROPIC_API_KEY=sk-...
```

---

## Key Design Decisions

**Why AppleScript for writes, not SQLite?** The NoteStore.sqlite format is
undocumented and changes between macOS versions. Writing via AppleScript goes
through the Notes app's own APIs and is safe across upgrades.

**Why JSON proposals as an intermediate step?** The human review step is
essential. Bulk moves are difficult to undo. The proposal file lets you inspect,
edit, and selectively approve before anything is touched in Notes.

**Why keep prompt templates in the repo?** The templates contain no personal
data — they use placeholders. Committing them lets others adapt the framework
for their own taxonomies, which is the value of open-sourcing this.

**Why not store note IDs as stable identifiers?** Apple Notes `x-coredata://`
IDs can change if notes are synced across devices or if iCloud sync has a
conflict. Scripts should match on ID but gracefully fall back to title + folder
for lookup, logging any ambiguities.

