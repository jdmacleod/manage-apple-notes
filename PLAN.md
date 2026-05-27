# manage-apple-notes — Project Plan

> **Handoff document for Claude Code implementation.**
> All folder names, note titles, and personal identifiers in this document are
> placeholders. Real names live in `config/taxonomy.local.yaml` (gitignored).

---

## Goal

Build a set of scripts and workflows that:

1. Perform a **one-time cleanup** of an existing Apple Notes library, reorganizing
   notes according to the Forever Notes framework — including a nested folder
   hierarchy where appropriate within top-level categories.
2. Support **ongoing maintenance passes** — inbox processing, library audits, and
   archiving — that can be run manually or on a schedule.

The project is a **public open-source repo**. No personal note content, folder
names, or identifying information should ever be committed.

---

## Design Philosophy: Two Dimensions of Organization

The Forever Notes framework uses two orthogonal dimensions:

- **Top-level category** — the *nature* of a note (is it evergreen knowledge,
  an active project reference, a captured source?). This maps to the standard
  Forever Notes categories: Inbox, Fleeting, Literature, Permanent, Projects,
  Areas, Resources, Archive.

- **Theme / domain** — the *subject matter* of a note (which area of life or
  work it belongs to). This maps to subfolders within a top-level category.

A note about sleep science belongs in `Permanent/Health`. A book summary on the
same topic belongs in `Literature/Health`. The theme is consistent; the nature
differs. Both dimensions need to be discovered and applied during migration.

### When subfolders are warranted

A subfolder is worth creating when a theme has enough notes that scrolling
through a flat list creates navigation friction (roughly 8–10+ notes), and when
the theme is stable enough that notes will keep accumulating there. **Permanent**
and **Resources** almost always develop meaningful subfolders. **Areas** maps
naturally to one subfolder per ongoing responsibility. **Projects** gets one
subfolder per active project.

**Inbox** and **Fleeting** should remain flat — they are staging areas, not
permanent homes. **Review** stays flat. **Archive** may preserve the subfolder
structure of whatever it archives.

### Why theme discovery must come before classification

If you classify each note individually and then try to invent subfolders, you
get arbitrary groupings that don't reflect the actual shape of your library.
The correct sequence is: **discover themes first, then classify into them.**
This produces a controlled vocabulary of subfolder names, preventing the sprawl
of slightly-different names for the same concept.

---

## Repository Layout

```
manage-apple-notes/
├── README.md
├── PLAN.md                          # This file
├── pyproject.toml                   # Python project config, deps, entry point
├── .env.example                     # Environment variable template (committed)
├── .gitignore
├── .git-hooks/
│   └── pre-commit                   # Safety hook — blocks accidental data commits
│
├── scripts/
│   ├── __init__.py
│   ├── cli.py                       # Unified 'notes' CLI entry point (typer)
│   ├── providers.py                 # LLM provider abstraction (Anthropic + Ollama)
│   ├── export/
│   │   └── export-notes.applescript # Dump all notes to data/exports/
│   ├── classify/
│   │   ├── __init__.py
│   │   ├── discover_themes.py       # Pass 1: find natural clusters in the library
│   │   └── classify_notes.py        # Pass 2: classify notes using approved theme map
│   ├── execute/
│   │   └── apply-proposal.applescript  # Read approved proposal, move notes
│   └── maintenance/
│       ├── __init__.py
│       ├── process_inbox.py         # Classify and propose moves for Inbox notes
│       └── audit.py                 # Find stale, duplicate, orphaned notes
│
├── prompts/
│   ├── discover-themes.md           # Prompt template: theme/cluster discovery
│   ├── classify-notes.md            # Prompt template: bulk classification
│   ├── process-inbox.md             # Prompt template: inbox triage
│   └── audit.md                     # Prompt template: library audit
│
├── config/
│   ├── taxonomy.example.yaml        # Generic Forever Notes folder template
│   ├── settings.example.yaml        # Paths, model, batch size, etc.
│   ├── taxonomy.local.yaml          # GITIGNORED — your actual folder names + subfolders
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
    ├── theme-maps/                  # Theme discovery output (Pass 1)
    ├── proposals/                   # Classification proposals (Pass 2)
    ├── reports/                     # Maintenance pass outputs
    └── archive/                     # Old proposals and reports
```

---

## Privacy and Git Safety

### .gitignore (root)

```gitignore
# Private config — contains personal folder names and paths
config/*.local.*

# All personal data — note exports, theme maps, proposals, reports
data/

# Convenience: any file explicitly marked private
*.private.md
PRIVATE*.md

# Environment variables — may contain API keys
.env

# macOS
.DS_Store

# Python
__pycache__/
*.pyc
.venv/
```

### Pre-commit Hook

`.git-hooks/pre-commit` blocks: `data/`, `*.local.*` config, large JSON files (>10KB),
and `.env` files (`.env.example` is explicitly allowed). Activate with:

```bash
git config core.hooksPath .git-hooks
```

---

## Config Files

### config/taxonomy.example.yaml

The taxonomy supports nested subfolders. The top-level keys are fixed Forever
Notes categories. The `subfolders` list under each category is populated after
the theme discovery pass and lives in `taxonomy.local.yaml` only.

Categories without a `subfolders` key (inbox, fleeting, review) remain flat.

```yaml
# Forever Notes folder taxonomy — generic template.
# Copy to taxonomy.local.yaml and fill in your actual folder names and subfolders.
#
# Subfolders are discovered during the theme discovery pass (notes discover).
# Add them to taxonomy.local.yaml before running notes classify (Pass 2).
# Categories without a subfolders key remain flat.

forever_notes:
  inbox:
    folder: "[YOUR_INBOX_FOLDER]"          # keep flat

  fleeting:
    folder: "[YOUR_FLEETING_FOLDER]"       # keep flat

  literature:
    folder: "[YOUR_LITERATURE_FOLDER]"
    subfolders: []                         # e.g. ["Health", "Technology", "History"]

  permanent:
    folder: "[YOUR_PERMANENT_FOLDER]"
    subfolders: []                         # e.g. ["Health", "Writing", "Philosophy"]

  projects:
    folder: "[YOUR_PROJECTS_FOLDER]"
    subfolders: []                         # one subfolder per active project

  areas:
    folder: "[YOUR_AREAS_FOLDER]"
    subfolders: []                         # one subfolder per area of life/work

  resources:
    folder: "[YOUR_RESOURCES_FOLDER]"
    subfolders: []                         # e.g. ["Recipes", "Coding", "Finance"]

  archive:
    folder: "[YOUR_ARCHIVE_FOLDER]"
    subfolders: []                         # mirror of old structure where useful

  review:
    folder: "[YOUR_REVIEW_FOLDER]"         # keep flat
```

### config/settings.example.yaml

```yaml
# General settings — copy to settings.local.yaml and customize.

# provider: "anthropic" (default, cloud) or "ollama" (local)
llm:
  provider: "anthropic"
  model: "claude-opus-4-6"          # or claude-sonnet-4-6 for cost/speed tradeoff
  batch_size: 20                    # notes per API call during classification
  theme_discovery_sample: 50        # notes per batch during theme discovery

# Ollama / llama.cpp example:
# llm:
#   provider: "ollama"
#   model: "llama3"                 # overridden by OLLAMA_MODEL env var if set
#   batch_size: 5
#   theme_discovery_sample: 20

paths:
  exports_dir: "data/exports"
  theme_maps_dir: "data/theme-maps"
  proposals_dir: "data/proposals"
  reports_dir: "data/reports"

export:
  include_body: true
  max_body_chars: 2000              # truncate long notes for classification
  skip_empty: true

thresholds:
  min_notes_for_subfolder: 8       # themes with fewer notes stay flat in parent
  stale_days: 180                   # notes unmodified longer than this → flag for archive
  stub_chars: 50                    # notes shorter than this → flag as stub
  inbox_stale_days: 7               # inbox notes older than this → stale
  fleeting_stale_days: 30           # fleeting notes older than this → stale
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
  "body": "Plain text body",
  "folder": "Current folder name",
  "parent_folder": "Parent folder name, or empty string if top-level",
  "folder_path": "Parent Folder/Current Folder",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-03-20T14:22:00Z",
  "word_count": 142
}
```

**Implementation notes:**
- Use ASCII 31/30 as field/record separators (safe for all note content)
- Capture `container of container` to build `parent_folder` and `folder_path`
- Python converts the delimited temp file to UTF-8 JSON via `json.dump`
- Skip notes in the "Recently Deleted" folder

---

### scripts/classify/discover_themes.py  *(Pass 1)*

**Purpose:** Analyze the exported library and discover the natural thematic
clusters. Writes a theme map to `data/theme-maps/themes-YYYY-MM-DD.json`
for human review before any classification begins.

**CLI:** `uv run notes discover [export_file] [--dry-run]`

**Inputs:**
- Export file: `data/exports/notes-YYYY-MM-DD.json` (or latest)
- Settings: `config/settings.local.yaml`
- Prompt template: `prompts/discover-themes.md`

**Algorithm:**
1. Extract lightweight summaries: `{id, title, body[:200], folder_path}`
2. Split into batches of `theme_discovery_sample` (default 50)
3. Send each batch to the LLM via `provider.classify_messages()`
4. Collect raw theme lists; send a synthesis call to merge/deduplicate
5. Flag themes below `min_notes_for_subfolder` as "flat" (no subfolder needed)
6. Write theme map JSON

**Output schema (data/theme-maps/themes-YYYY-MM-DD.json):**
```json
{
  "generated_at": "2024-03-20T15:00:00Z",
  "source_export": "data/exports/notes-2024-03-20.json",
  "total_notes": 347,
  "themes": [
    {
      "name": "Health",
      "estimated_count": 42,
      "suggested_subfolders_in": ["Permanent", "Literature", "Areas"],
      "notes": "Covers sleep, nutrition, fitness, mental health"
    },
    {
      "name": "Random Web Clips",
      "estimated_count": 6,
      "suggested_subfolders_in": [],
      "notes": "Below subfolder threshold — keep flat in Resources"
    }
  ],
  "existing_folders_analysed": [
    {
      "folder_path": "Work/Project X",
      "note_count": 18,
      "suggested_mapping": "Projects/Project X"
    }
  ]
}
```

**Human review step:** Open the theme map, edit/merge/rename themes, remove
themes that should stay flat, then add the approved subfolder names to
`config/taxonomy.local.yaml` before running Pass 2.

---

### scripts/classify/classify_notes.py  *(Pass 2)*

**Purpose:** Using the approved taxonomy (including subfolders), classify each
note into its `top-level folder / subfolder` destination.

**CLI:** `uv run notes classify [export_file] [--dry-run]`

**Output schema (data/proposals/proposal-YYYY-MM-DD.json):**
```json
{
  "generated_at": "...",
  "source_export": "...",
  "moves": [
    {
      "id": "x-coredata://...",
      "title": "Note title",
      "current_folder": "Old Folder",
      "proposed_folder": "Permanent",
      "proposed_subfolder": "Health",
      "proposed_folder_path": "Permanent/Health",
      "confidence": "high",
      "reason": "Atomic evergreen concept about sleep science"
    },
    {
      "id": "...",
      "title": "Another note",
      "current_folder": "Misc",
      "proposed_folder": "Resources",
      "proposed_subfolder": null,
      "proposed_folder_path": "Resources",
      "confidence": "high",
      "reason": "Reference material; no subfolder matches"
    }
  ],
  "needs_review": [...],
  "no_change": [...]
}
```

**Implementation notes:**
- Uses `_folder_name(entry)` / `_subfolders(entry)` helpers to read nested taxonomy
- `proposed_subfolder` is null when no subfolders are defined or no match
- LLM provider selected via `get_provider(settings)` from `scripts.providers`
- Prompt caching applied for Anthropic; not for Ollama

---

### scripts/execute/apply-proposal.applescript

**Purpose:** Read an approved proposal JSON and execute the moves in Apple Notes,
creating nested folder structure as needed.

**Usage:**
```bash
osascript scripts/execute/apply-proposal.applescript [--dry-run] <proposal.json>
```

**Implementation notes:**
- Python parser extracts 5 fields per move: `id, title, current_folder, proposed_folder, proposed_subfolder`
- When `proposed_subfolder` is set: check whether the subfolder exists inside the
  top-level folder; create it if not
- Move note to the correct folder (subfolder if set, top-level otherwise)
- Log: `[MOVED] "Title" → Permanent/Health`
- Summary: N moved, N skipped, N errors

---

### scripts/maintenance/process_inbox.py

**Purpose:** Classify only the Inbox folder notes and write a proposal.

Same pipeline as `classify_notes.py` but scoped to the inbox folder. Subfolder-aware —
uses the same taxonomy and prompt injection.

**CLI:** `uv run notes inbox [--dry-run]`

---

### scripts/maintenance/audit.py

**Purpose:** Analyze the full library for quality issues. Writes a report to
`data/reports/audit-YYYY-MM-DD.md`.

**CLI:** `uv run notes audit [--output <path>] [--dry-run]`

**Checks:**
- Notes not modified in `> stale_days` that are not in Archive
- Notes with body < `stub_chars` characters → stubs
- Notes with identical or near-identical titles → possible duplicates
- Inbox notes older than `inbox_stale_days`
- Fleeting notes older than `fleeting_stale_days`
- **Subfolder candidates** — flat top-level folders with `> min_notes_for_subfolder`
  notes; uses title-word grouping as a heuristic signal for human review

**Output:** Markdown report only — no automatic changes.

---

## Prompt Templates

### prompts/discover-themes.md

```markdown
You are analyzing a collection of Apple Notes to discover the natural thematic
clusters present in the library. This is a cartography pass — your goal is to
map what topics and domains exist, not to classify individual notes yet.

You will be given batches of notes (title + opening text). Across all batches,
identify the major themes. A theme is a coherent subject domain that multiple
notes share (e.g. "Health & Fitness", "Side Project: App Redesign", "Cooking").

For each theme, estimate:
- How many notes likely belong to it
- Which Forever Notes categories it might appear in (Permanent, Literature,
  Projects, Areas, Resources)
- A one-sentence description

Also note any existing folder names from the input that suggest structural
groupings worth preserving.

Return a JSON object:
{
  "themes": [
    {
      "name": "<short theme name>",
      "estimated_count": <integer>,
      "appears_in_categories": ["Permanent", "Literature"],
      "description": "<one sentence>"
    }
  ],
  "folder_observations": [
    {
      "folder_path": "<existing folder path>",
      "observation": "<note about this folder's contents or suggested mapping>"
    }
  ]
}

Notes sample:
{NOTES_JSON}
```

### prompts/classify-notes.md

```markdown
You are organizing notes in Apple Notes according to the Forever Notes framework.
The taxonomy has two levels: a top-level category (the nature of the note) and
an optional subfolder (the subject domain).

Available top-level categories and their subfolders:

Inbox: {INBOX} — temporary capture, no subfolders
Fleeting: {FLEETING} — quick thoughts, no subfolders
Literature: {LITERATURE} — notes tied to a specific source
  Subfolders: {LITERATURE_SUBFOLDERS}
Permanent: {PERMANENT} — atomic, evergreen concepts in your own words
  Subfolders: {PERMANENT_SUBFOLDERS}
Projects: {PROJECTS} — notes tied to a specific active project
  Subfolders: {PROJECTS_SUBFOLDERS}
Areas: {AREAS} — ongoing responsibilities
  Subfolders: {AREAS_SUBFOLDERS}
Resources: {RESOURCES} — reference material, how-tos, collections
  Subfolders: {RESOURCES_SUBFOLDERS}
Archive: {ARCHIVE} — inactive, completed, or outdated notes
  Subfolders: {ARCHIVE_SUBFOLDERS}
Review: {REVIEW} — use when classification is genuinely unclear, no subfolders

For each note, return a JSON array with one object per note:
{
  "id": "<the id field from input>",
  "proposed_folder": "<exact top-level folder name>",
  "proposed_subfolder": "<exact subfolder name, or null if none applies>",
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}

Use null for proposed_subfolder when: no subfolders are defined for the target
category, or the note's theme doesn't clearly match any listed subfolder.
Use "Review" (with null subfolder) when the note is too short or ambiguous.

Notes to classify:
{NOTES_JSON}
```

---

## Phased Implementation

### Phase 1 — Scaffold and Safety ✅

Directory structure, git, `.gitignore`, pre-commit hook, config examples, README.

### Phase 2 — Export ✅

`export-notes.applescript` with ASCII-delimited temp file → Python UTF-8 JSON conversion.

### Phase 2a — Theme Discovery *(new)*

1. Implement `discover_themes.py` with `notes discover` CLI command
2. Write `prompts/discover-themes.md`
3. Document in `docs/runbooks/one-time-cleanup.md` through the theme review step

**Human checkpoint:** Review theme map → edit `taxonomy.local.yaml` to add discovered
subfolders → approve before proceeding to Phase 2b.

### Phase 2b — Classify and Execute *(subfolder-aware upgrade)*

1. Update `classify_notes.py`: nested taxonomy reads, subfolder in proposals
2. Update `apply-proposal.applescript`: subfolder creation and 5-field move logic
3. Update `prompts/classify-notes.md`: subfolder placeholders
4. Update `process_inbox.py`: nested taxonomy reads
5. Complete `docs/runbooks/one-time-cleanup.md`

**Human checkpoints:** Review proposal JSON → approve → dry-run → execute.

### Phase 3 — Maintenance Scripts ✅ (partial upgrade needed)

1. Update `audit.py`: nested taxonomy reads + subfolder candidate detection
2. Update runbooks for audit

### Phase 4 — Scheduling (optional)

Document scheduling via cron or launchd.

---

## Setup Instructions

```bash
# 1. Clone
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes

# 2. Activate pre-commit hook (blocks accidental data commits)
git config core.hooksPath .git-hooks

# 3. Copy and fill in personal config (gitignored)
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both — add your Apple Notes folder names.
# Leave subfolders as [] until after the theme discovery pass.

# 4. Install Python dependencies and create virtual environment
uv sync

# 5. Set your API key / provider URL
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY for cloud, or set OLLAMA_BASE_URL for local
```

### taxonomy.local.yaml schema (after clean-cut migration)

Each category uses the nested dict format — flat strings are no longer supported:

```yaml
forever_notes:
  inbox:
    folder: "Inbox"
  permanent:
    folder: "Notes"
    subfolders: ["Health", "Technology"]   # add after theme discovery
  # ... etc.
```

---

## Key Design Decisions

**Two-pass classification, not one.** Classifying notes directly into a
predefined taxonomy imposes structure before you know what's in your library.
Discovering themes first (Pass 1) lets the actual content determine the subfolder
structure, rather than the other way around.

**Subfolders as a second dimension, not a deeper hierarchy.** The structure is
at most two levels deep: `Category/Theme`. Three or more levels creates
navigation friction that outweighs any organizational benefit.

**Theme map as a human-reviewed artifact.** The theme discovery output is not
fed automatically into classification — it must be reviewed and edited first.
This is the most consequential decision in the migration: the subfolder names
you approve become permanent fixtures of your taxonomy.

**LLM provider abstraction.** `scripts/providers.py` supports Anthropic (cloud)
and Ollama / llama.cpp (local) via a duck-typed `LLMProvider` protocol. Provider
and model are selected from `settings.local.yaml` and env vars (`OLLAMA_BASE_URL`,
`OLLAMA_MODEL`). Anthropic uses prompt caching; Ollama does not.

**`.env` for credentials.** `python-dotenv` loads `.env` at CLI startup.
`ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL` are read from there.
`.env` is gitignored; `.env.example` is committed.

**AppleScript for reads and writes, not SQLite.** The NoteStore.sqlite schema is
undocumented and changes between macOS versions. AppleScript uses the Notes app's
own APIs and is safe across upgrades.

**JSON proposals as an intermediate step.** Bulk moves are hard to undo. The
proposal file lets you inspect, edit, and selectively approve before anything is
touched in Notes.

**Note ID caveat.** Apple Notes `x-coredata://` IDs can change across iCloud sync
conflicts or device migrations. Scripts match on ID but fall back to title + folder,
logging any ambiguities.
