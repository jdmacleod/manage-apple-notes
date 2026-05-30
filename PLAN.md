# manage-apple-notes — Project Plan

> **Handoff document for Claude Code implementation.**
> All folder names, note titles, and personal identifiers in this document are
> placeholders. Real names live in `config/taxonomy.local.yaml` (gitignored).
>
> Detailed specs for completed phases and embedded config examples live in
> [`PLAN-archive.md`](PLAN-archive.md).

---

## Goal

Build a set of scripts and workflows that:

1. Perform a **one-time cleanup** of an existing Apple Notes library, reorganizing
   notes according to a user-defined folder taxonomy — the Zettelkasten-influenced
   Forever Notes structure, the PARA method, or a custom variant — including a
   nested folder hierarchy where appropriate within top-level categories.
2. Support **ongoing maintenance passes** — inbox processing, library audits, and
   archiving — that can be run manually or on a schedule.

The project is a **public open-source repo**. No personal note content, folder
names, or identifying information should ever be committed.

---

## Design Philosophy: Two Dimensions of Organization

The folder taxonomy uses two orthogonal dimensions:

- **Top-level category** — the *nature* of a note (is it evergreen knowledge,
  an active project reference, a captured source?). This project supports two
  ready-to-use top-level structures:
  - **Forever Notes / Zettelkasten** — Inbox, Fleeting, Literature, Permanent,
    Projects, Areas, Resources, Archive, Review. Distinguishes note *type* at
    the top level (Literature for source-linked notes, Permanent for evergreen
    concepts in your own words). See `config/taxonomy.example.yaml`.
  - **PARA** — Inbox, Projects, Areas, Resources, Archive. Organises by
    *actionability* rather than type; differentiation lives inside Resources
    via subfolders (Ideas & Thinking, Learning & Reading, Reference).
    See `config/taxonomy.para.yaml` and `docs/para-method.md`.

- **Theme / domain** — the *subject matter* of a note (which area of life or
  work it belongs to). This maps to subfolders within a top-level category.

In the Forever Notes structure, a note about sleep science belongs in
`Permanent/Health` and a book summary on the same topic in `Literature/Health`.
In a PARA structure, both land in `Resources/Ideas & Thinking` or
`Resources/Learning & Reading` depending on form. The theme is consistent across
both systems; only the top-level nature dimension differs.

### When subfolders are warranted

A subfolder is worth creating when a theme has enough notes that scrolling
through a flat list creates navigation friction (roughly 8–10+ notes, matching
the `min_notes_for_subfolder` default), and when the theme is stable enough that
notes will keep accumulating there. In the Forever Notes structure, **Permanent**
and **Resources** almost always develop meaningful subfolders. In a PARA
structure, **Resources** carries the same differentiation internally (Ideas &
Thinking, Learning & Reading, Reference). **Areas** maps naturally to one
subfolder per ongoing responsibility in both systems. **Projects** gets one
subfolder per active project in both.

Staging categories (**Inbox** in both systems; **Fleeting** in the Forever Notes
structure) should remain flat. **Review** stays flat. **Archive** may preserve
the subfolder structure of whatever it archives.

Apple Notes supports up to five levels of folder nesting (one top-level folder
plus four subfolder levels), confirmed on iPhone 16e. With `toplevel_folder`
enabled, this project uses three levels: container → category → subfolder.

### Strict vs. Loose Forever Notes Mode

This project supports two operating modes, controlled by `forever_notes_mode` in settings:

- **Loose mode (default)** — Folders, subfolders, classification, deduplication.
  A clean, well-organised library. No structural notes required.

- **Strict mode** — Everything in loose mode, plus the Forever Notes structural
  layer: the **heavy asterisk (✱)** prefix on system notes, a **✱ Home** hub note
  as the root entry point, **✱ Hub** notes for each theme that serve as navigable
  cross-category indices, and **tags** applied to notes on classification. Follows
  the framework as documented at [myforevernotes.com](https://www.myforevernotes.com/docs/home).

Strict mode is **additive** — it does not change the folder structure or
classification behaviour. All loose-mode functionality is unchanged.

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
├── PLAN.md                          # This file (active plan)
├── PLAN-archive.md                  # Completed phase specs and config examples
├── CHANGELOG.md
├── pyproject.toml                   # Python project config, deps, entry point
├── .env.example                     # Environment variable template (committed)
├── .gitignore
├── .git-hooks/
│   └── pre-commit                   # Safety hook — blocks accidental data commits
│
├── scripts/
│   ├── __init__.py
│   ├── cli.py                       # Unified 'notes' CLI entry point (typer)
│   ├── config.py                    # Shared config: load_settings, load_taxonomy, find_latest_export
│   ├── json_utils.py                # Shared JSON parsing helpers for LLM response extraction
│   ├── providers.py                 # LLM provider abstraction (Anthropic + Ollama)
│   ├── folder_utils.py              # Taxonomy path utilities (enumerate_paths, folder_name, etc.)
│   ├── run_logger.py                # Structured run logging — one JSON file per execution
│   ├── export/
│   │   ├── export-notes.applescript # Dump all notes to data/exports/
│   │   └── run_export.py            # Python wrapper; export and backup commands
│   ├── classify/
│   │   ├── __init__.py
│   │   ├── discover_themes.py       # Discover thematic clusters (notes discover)
│   │   ├── draft_taxonomy.py        # Generate draft taxonomy YAML (notes draft)
│   │   ├── classify_notes.py        # Classify notes into the taxonomy (notes classify)
│   │   └── deduplicate_notes.py     # Detect duplicates, write dedup proposal (notes dedup)
│   ├── execute/
│   │   ├── run_apply.py             # Python wrapper for apply-proposal.applescript
│   │   ├── apply_dedup.py           # Python wrapper for apply-dedup-proposal.applescript
│   │   ├── apply-proposal.applescript          # Move notes per approved proposal
│   │   └── apply-dedup-proposal.applescript    # Delete notes per approved dedup proposal
│   ├── restore/
│   │   ├── run_restore.py           # Recreate notes from backup (notes restore)
│   │   └── restore-notes.applescript
│   ├── forever_notes/               # Strict mode only
│   │   ├── sync_hubs.py             # Create/update ✱ Home and ✱ Hub notes
│   │   └── sync-hubs.applescript    # AppleScript writer called by sync_hubs.py
│   └── maintenance/
│       ├── __init__.py
│       ├── process_inbox.py         # Triage Inbox notes, write proposal (notes triage)
│       ├── repair_restored_notes.py # Fix formatting after iCloud restore (notes repair)
│       └── audit.py                 # Library quality report (notes audit)
│
├── prompts/
│   ├── discover-themes.md           # Prompt template: theme/cluster discovery
│   ├── classify-notes.md            # Prompt template: bulk classification (and triage)
│   └── deduplicate-notes.md         # Prompt template: duplicate pair review
│
├── config/
│   ├── taxonomy.example.yaml        # Forever Notes / Zettelkasten taxonomy template
│   ├── taxonomy.para.yaml           # PARA method taxonomy template (alternative)
│   ├── settings.example.yaml        # Paths, model, batch size, toplevel_folder, etc.
│   ├── taxonomy.local.yaml          # GITIGNORED — your actual folder names + subfolders
│   └── settings.local.yaml          # GITIGNORED — your personal settings
│
├── docs/
│   ├── forever-notes-framework.md   # Forever Notes framework reference
│   ├── para-method.md               # PARA method taxonomy guidance
│   ├── security-considerations.md   # Data flow and privacy notes
│   ├── technical-notes.md           # AppleScript/macOS platform findings
│   └── runbooks/
│       └── main-workflow.md         # Consolidated step-by-step workflow
│
└── data/                            # ENTIRELY GITIGNORED
    ├── exports/                     # Raw dumps from Apple Notes
    ├── backups/                     # Timestamped text-only backups (notes backup)
    ├── theme-maps/                  # Theme discovery output (notes discover)
    ├── taxonomy-drafts/             # Draft taxonomy YAMLs (notes draft)
    ├── proposals/                   # Classification and triage proposals
    ├── dedup-proposals/             # Deduplication proposals (notes dedup)
    ├── reports/                     # Audit reports (notes audit)
    └── logs/                        # Run logs — one JSON file per command execution
```

---

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Scaffold, `.gitignore`, pre-commit hook, config examples, README | ✅ Complete |
| 2 | `export-notes.applescript`, `run_export.py`, export/backup commands | ✅ Complete |
| 2a | Theme discovery (`discover_themes.py`, `draft_taxonomy.py`) | ✅ Complete |
| 2b | Classification (`classify_notes.py`, `apply-proposal.applescript`) | ✅ Complete |
| 3 | Maintenance scripts: `audit.py`, `repair_restored_notes.py`, `run_restore.py` | ✅ Complete |
| 3b | Deduplication (`deduplicate_notes.py`, `apply-dedup-proposal.applescript`) | ✅ Complete |
| 3c | Hub setup (`sync_hubs.py`, `sync-hubs.applescript`) | ✅ Complete |
| 4 | Scheduling via cron or launchd | 🔲 Upcoming |

Detailed specs for completed phases are in [`PLAN-archive.md`](PLAN-archive.md).

---

## Phase 4 — Scheduling (optional)

Document how to run the maintenance workflow on a schedule via macOS launchd or
cron. The pipeline commands to schedule are:

```bash
uv run notes export
uv run notes classify --dry-run    # review before applying
uv run notes audit
```

For recurring inbox triage without a full classify pass:

```bash
uv run notes export
uv run notes triage
uv run notes move                  # apply the latest proposal
```

A launchd plist example and step-by-step setup guide belong in
`docs/runbooks/scheduling.md`.

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

**Shared infrastructure in `scripts/config.py` and `scripts/json_utils.py`.** Config
loading (`load_settings`, `load_taxonomy`, `find_latest_export`) and LLM response parsing
(`extract_json_array`, `extract_json_object`, `is_context_overflow`) are extracted into
dedicated modules. All classify/maintenance scripts import from these; `classify_notes.py`
is a pure classification module, not a utility hub.

**AppleScript for reads and writes, not SQLite.** The NoteStore.sqlite schema is
undocumented and changes between macOS versions. AppleScript uses the Notes app's
own APIs and is safe across upgrades.

**JSON proposals as an intermediate step.** Bulk moves are hard to undo. The
proposal file lets you inspect, edit, and selectively approve before anything is
touched in Notes.

**Note ID caveat.** Apple Notes `x-coredata://` IDs can change across iCloud sync
conflicts or device migrations. Scripts match on ID but fall back to title + folder,
logging any ambiguities.

**Why deduplicate after classification, not before.** Running dedup on the
post-classification state provides a richer signal: two notes heading to the same
`proposed_folder_path` are far more likely to be true duplicates than two notes in
different categories that happen to share a theme. Running dedup before classification
loses this placement context entirely.

**Three-pass funnel, not a single LLM call.** Sending every note pair to the LLM
would be O(n²) in cost and time. The algorithmic passes (exact hash, fuzzy title +
content similarity) eliminate the vast majority of non-duplicates cheaply, so the LLM
only reviews pairs that have already cleared two similarity thresholds. For a library of
a few hundred notes this typically reduces the LLM review set to under 20 candidate pairs.

**Why no merge resolution.** Merging note content via AppleScript would produce plain
text — Apple Notes stores notes as HTML internally, and any merge would silently strip
formatting, attachments, and links. Notes where both sides contain unique content are
flagged as `review` so the user can merge manually in the Notes app with full fidelity.

**Deletion safety: `--execute` required.** Deletions are harder to undo than moves.
The apply-dedup script defaults to dry-run and requires an explicit `--execute` flag.
Deleted notes land in Recently Deleted and are recoverable for 30 days.

**Strict mode is additive, never destructive.** Enabling `forever_notes_mode: strict`
adds Hub notes, tags, and the ✱ Home note. It does not alter folder structure, rename
existing notes, or change how classification works. A user can switch between modes
without any risk to existing notes.

**The heavy asterisk (✱, U+2731) sorts system notes to the top.** In Apple Notes with
alphabetical sort, ✱ Hub notes and ✱ Home appear before all other notes in any folder.
Scripts must use the exact Unicode character U+2731, not a standard asterisk `*`.

**Hub notes are cross-category indices.** A "✱ Health" Hub aggregates notes from
`Permanent/Health`, `Literature/Health`, and `Areas/Health` into one view. They cut
across the nature/domain dimensions and provide a single entry point for a topic
regardless of note type. `sync_hubs.py` queries all categories for each theme.

**Internal links default to plain text.** Hub bodies contain plain note titles that the
user converts to `applenotes://` links using Apple Notes' `>>` shortcut — a few minutes
of one-time work that produces stable links. The experimental `internal_links: "html"`
option attempts programmatic link construction but carries risk of broken links after
iCloud sync events.

**Tags are appended, never removed.** Strict-mode tag application only adds tags not
already present. It never removes existing tags, even if a note is reclassified. This
preserves manually applied tags and avoids unexpected data loss.

**Top-level container is transparent to classification.** When `toplevel_folder.enabled`
is true, the export post-processor strips the container prefix from `folder_path` so all
downstream tools (classify, dedup, discover, audit, triage, sync-hubs) see clean paths
that match the taxonomy. Only the export (strip) and apply (prepend) scripts are
container-aware. Disabling the setting requires no changes to any other component.
