# manage-apple-notes — Plan Archive

> Archived content from `PLAN.md`. Contains detailed specifications for completed
> implementation phases, embedded config examples, and the original scripts specification.
> The active plan lives in `PLAN.md`.

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

### config/taxonomy.example.yaml  *(Forever Notes / Zettelkasten)*

The taxonomy supports nested subfolders. The `subfolders` list under each
category is populated after the theme discovery pass and lives in
`taxonomy.local.yaml` only. Categories without a `subfolders` key remain flat.

This template uses the full Zettelkasten-influenced set: Inbox, Fleeting,
Literature, Permanent, Projects, Areas, Resources, Archive, Review. See
`config/taxonomy.para.yaml` for the PARA alternative.

```yaml
# Forever Notes folder taxonomy — generic template.
# Copy to taxonomy.local.yaml and fill in your actual folder names and subfolders.
#
# Subfolders are discovered during the theme discovery pass (notes discover).
# Add them to taxonomy.local.yaml before running notes classify.
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

### config/taxonomy.para.yaml  *(PARA method)*

An alternative template using PARA's four actionability-based top-level
categories. Omits Fleeting, Literature, Permanent, and Review — those
note types are absorbed into Projects, Areas, and Resources via subfolders.
See `docs/para-method.md` for guidance on minimalist vs. expanded PARA designs
and how PARA maps to the default Forever Notes taxonomy.

To use PARA: copy `taxonomy.para.yaml` to `taxonomy.local.yaml` and fill in
your folder names. Forever Notes strict mode is compatible with PARA — Hub notes
will be generated for any subfolders defined.

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

deduplication:
  fuzzy_title_threshold: 85         # thefuzz token_sort_ratio threshold (0–100)
  jaccard_content_threshold: 80     # thefuzz token_set_ratio threshold (0–100)
  content_preview_chars: 300        # characters of each note shown in the dedup proposal
  semantic_sweep: false             # full LLM pass over theme clusters (expensive; off by default)
  default_resolution: "review"      # conservative default: flag for human, don't auto-delete

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
  "folder_path": "Areas/Travel/Atlanta",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-03-20T14:22:00Z",
  "word_count": 142
}
```

**Implementation notes:**
- Use ASCII 31/30 as field/record separators (safe for all note content)
- `folder_path` is built recursively via `getFullPath` (walks `container of aFolder` until hitting an account)
- Python converts the delimited temp file to UTF-8 JSON via `json.dump`
- Skip notes in the "Recently Deleted" folder

---

### scripts/export/run_export.py

**Purpose:** Python wrapper that invokes `export-notes.applescript` and writes the result to `data/exports/`. Also implements the `backup` command, which runs export then copies the output to `data/backups/backup-YYYY-MM-DD-HHmmss.json`.

**CLI:**
- `uv run notes export` — export to `data/exports/notes-YYYY-MM-DD.json`
- `uv run notes backup` — export + timestamped copy to `data/backups/`

---

### scripts/classify/discover_themes.py

**Purpose:** Analyze the exported library and discover the natural thematic
clusters. Writes a theme map to `data/theme-maps/themes-YYYY-MM-DD.json`
for human review before any classification begins.

**CLI:** `uv run notes discover [export_file] [--dry-run]`

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
    }
  ]
}
```

**Human review step:** Run `notes draft` to generate an editable taxonomy YAML,
review the proposed subfolders, then copy to `config/taxonomy.local.yaml` before
running `notes classify`.

---

### scripts/classify/draft_taxonomy.py

**Purpose:** Read the latest theme map, merge above-threshold suggested paths not
already in the taxonomy into a deep copy of `taxonomy.local.yaml`, and write a
complete, ready-to-review YAML to `data/taxonomy-drafts/taxonomy-draft-YYYY-MM-DD.yaml`.

**CLI:** `uv run notes draft [theme_map_file] [--dry-run]`

---

### scripts/classify/classify_notes.py

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
    }
  ],
  "needs_review": [...],
  "no_change": [...]
}
```

---

### scripts/classify/deduplicate_notes.py

**Purpose:** Detect duplicate notes using a three-pass funnel and write a dedup
proposal to `data/dedup-proposals/` for human review before any deletions occur.

**CLI:** `uv run notes dedup [export_file] [--proposal <file>] [--dry-run]`

**Algorithm — three-pass funnel:**

*Pass 1 — exact hash (free, instant):*
- Normalize body: lowercase, collapse whitespace, strip punctuation
- MD5 hash normalized content; group notes with identical hash
- Auto-resolved as `delete` — no LLM review needed

*Pass 2 — fuzzy candidates (free, fast):*
- Group notes by `proposed_folder_path`
- Flag pairs exceeding both `fuzzy_title_threshold` (85) and `jaccard_content_threshold` (80)

*Pass 3 — LLM review of fuzzy candidates:*
- Send each candidate pair to the LLM via `provider.classify_messages()`
- LLM returns: `is_duplicate`, `resolution` (`delete` or `review`), `keep_id`, `reason`
- No `merge` resolution — pairs with unique content on both sides → `review`

---

### scripts/execute/apply-proposal.applescript

**Purpose:** Read an approved proposal JSON and execute the moves in Apple Notes,
creating nested folder structure as needed.

---

### scripts/execute/apply-dedup-proposal.applescript

**Purpose:** Read an approved dedup proposal JSON and delete confirmed duplicate
notes (moves to Recently Deleted — recoverable for 30 days).

- Default is dry-run; requires `--execute` flag to make actual changes
- Processes only groups with `resolution: "delete"`; skips `review`

---

### scripts/restore/run_restore.py, scripts/maintenance/repair_restored_notes.py

See `docs/runbooks/main-workflow.md` for usage.

---

## Prompt Templates

Active prompts (`prompts/classify-notes.md`, `prompts/discover-themes.md`,
`prompts/deduplicate-notes.md`) contain the LLM instructions plus JSON schema
and placeholder markers that are replaced at runtime by `inject_taxonomy()` and
`inject_discover_taxonomy()`.

An earlier LLM-based hub generation approach used `prompts/sync-hubs.md` as
a template. This was replaced by direct HTML generation in `sync_hubs.py`
(`_generate_hub_body()`, `_build_home_body()`). The prompt file has been removed.

---

## Completed Implementation Phases

### Phase 1 — Scaffold and Safety ✅

Directory structure, git, `.gitignore`, pre-commit hook, config examples, README.

### Phase 2 — Export ✅

`export-notes.applescript` with ASCII-delimited temp file → Python UTF-8 JSON conversion.
`run_export.py` Python wrapper; `notes export` and `notes backup` commands.

### Phase 2a — Theme Discovery ✅

1. `discover_themes.py` with `notes discover` CLI command
2. `prompts/discover-themes.md`
3. `draft_taxonomy.py` with `notes draft` CLI command
4. `docs/runbooks/main-workflow.md`

### Phase 2b — Classify and Execute ✅

1. `classify_notes.py`: nested taxonomy reads, subfolder in proposals
2. `apply-proposal.applescript`: subfolder creation and 5-field move logic
3. `prompts/classify-notes.md`: subfolder placeholders
4. `process_inbox.py`: nested taxonomy reads

### Phase 3 — Maintenance Scripts ✅

1. `audit.py`: nested taxonomy reads + subfolder candidate detection
2. `repair_restored_notes.py`: fix formatting after iCloud Recently Deleted restore
3. `run_restore.py`: recreate notes from backup
4. Consolidated `docs/runbooks/main-workflow.md`

### Phase 3b — Deduplicate ✅

1. `deduplicate_notes.py` with three-pass funnel
2. `apply-dedup-proposal.applescript` with `--execute` flag requirement
3. `apply_dedup.py` Python wrapper with streaming colored output
4. `prompts/deduplicate-notes.md` LLM review prompt
5. `notes dedup` and `notes purge` commands

### Phase 3c — Hub Setup ✅ *(strict mode only)*

1. `sync_hubs.py` + `sync-hubs.applescript`
2. `notes sync-hubs` command
3. NoteStore.sqlite UUID lookup for stable `applenotes://` links (opt-in via `internal_links: "html"`)
