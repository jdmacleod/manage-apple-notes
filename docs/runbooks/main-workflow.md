# Notes Workflow

All steps use the `notes` CLI (`uv run notes <command>`). Human review checkpoints are
marked explicitly — no notes are modified without your approval.

---

## Initial Library Setup (one-time)

Run this once to organize an existing library into the configured folder taxonomy.

**Time estimate:** 30–60 min (plus review time for large libraries).

**Prerequisites:** `uv run notes setup` complete (`uv sync` run, `taxonomy.local.yaml` written, LLM provider configured), Apple Notes open and synced. Terminal must have Automation permission to control Notes (System Settings → Privacy & Security → Automation).

### Step 1 — Export

```bash
uv run notes export
```

Writes `data/exports/notes-YYYY-MM-DD.json` and prints the note count.

### Step 2 — Discover themes and draft subfolders (optional)

> **Skip this step if you don't need subfolders.** `notes classify` works with a flat
> taxonomy (top-level folders only). Come back to discover/draft when a category grows
> large enough that you want to split it into subfolders.

```bash
uv run notes discover --dry-run   # preview batch count and API cost
uv run notes discover             # → data/theme-maps/themes-YYYY-MM-DD.json
```

Sends batches of note summaries to the LLM to map the thematic clusters in your library.
No notes are changed. At the end, `notes discover` prints mode-aware guidance based on
your `reorganization_mode` setting — follow that rather than the generic steps below.

**If `reorganization_mode` is `static`:** skip directly to Step 3 — discover is
informational only and `notes draft` is a no-op.

**If no themes reached the subfolder threshold:** `notes discover` will say so; skip
`notes draft` and go straight to Step 3.

**Otherwise:** run `notes draft` to turn the theme-map into an editable taxonomy YAML.
The draft YAML is the right place to review what will change — it's readable and shows
exactly which subfolders would be added. Edit it before applying; the raw theme-map JSON
in `data/theme-maps/` is an advanced option for renaming or merging themes.

```bash
uv run notes draft --dry-run   # preview proposed additions
uv run notes draft             # → data/taxonomy-drafts/taxonomy-draft-YYYY-MM-DD.yaml
                               # then prompts: "Apply to config/taxonomy.local.yaml? [Y/n]"
```

`notes draft` will ask whether to apply the draft directly to `config/taxonomy.local.yaml`
(default: yes). Accept to apply in one step. If you declined, or want to review first:

```bash
# Review the draft manually, then copy when satisfied:
cp data/taxonomy-drafts/taxonomy-draft-YYYY-MM-DD.yaml config/taxonomy.local.yaml
```

The header comment in the draft lists every new path added. Remove subfolders you don't
want and rename any that need adjusting before applying.

### Step 3 — Classify

```bash
uv run notes classify --dry-run   # preview batch count and API cost
uv run notes classify             # → data/proposals/proposal-YYYY-MM-DD.json
```

Classifies every note into a folder and subfolder based on your updated taxonomy.

**→ HUMAN REVIEW:** Use `notes review` to handle the proposal interactively — no JSON
editing required:

```bash
uv run notes review                       # review the latest proposal
uv run notes review --confidence medium   # first drop low-confidence moves, then review
```

`notes review` shows a summary of all moves by confidence level, then walks you through
each `needs_review` item so you can place it in a folder or skip it. When done, it writes
the updated proposal back and prints the `notes move` command to apply it.

Alternatively, open `data/proposals/proposal-YYYY-MM-DD.json` in a text editor. Delete
any entry in `moves` you disagree with. Move items from `needs_review` into `moves` with
`proposed_folder`, `proposed_subfolder`, and `proposed_folder_path` filled in. Folder
names must exactly match your `taxonomy.local.yaml`.

### Step 4 — Backup and Apply

**Always take a backup before applying moves.** The backup captures note titles,
plaintext body content, and folder paths — sufficient to recreate text content if
notes are accidentally moved or deleted. Images, attachments, and formatting are
not included; for full media backup use Time Machine or a filesystem clone of
`~/Library/Group Containers/group.com.apple.notes/`.

```bash
uv run notes backup            # export + save timestamped copy to data/backups/
uv run notes move --dry-run    # preview every move with colored output
uv run notes move              # move notes per approved proposal
```

If you want to reverse the move (return notes to their original folders):

```bash
uv run notes revert --dry-run    # preview what would move back
uv run notes revert              # move notes back per the same proposal
```

`revert` reads the proposal's `current_folder` values and moves everything back.
It is all-or-nothing by default; to reverse a subset, edit the proposal file and
remove the entries you want to keep in their new location, then run `notes revert`.

If notes went missing (not just moved to the wrong place):

```bash
uv run notes restore --dry-run   # preview what would be recreated
uv run notes restore             # recreate missing notes from the backup
```

`restore` compares the backup against the current library (matched by title within
each folder) and recreates every note that is absent. No manual list is needed.

For targeted restoration of a specific subset of notes, create a
`data/missing-notes-YYYY-MM-DD.json` file manually and pass it with
`uv run notes restore --missing data/missing-notes-YYYY-MM-DD.json`.

Each move is logged: `[MOVED]` (green), `[SKIP]` / `[AMBIGUOUS]` (yellow), `[ERROR]` (red).
`[AMBIGUOUS]` means the ID fallback found multiple notes with the same title — those notes are
skipped to avoid moving the wrong one. Rename the duplicates in Apple Notes and re-run.
To move from a specific proposal file: `uv run notes move data/proposals/proposal-YYYY-MM-DD.json`.

### Step 5 — Deduplicate (optional)

Run after applying moves so that `proposed_folder_path` can be used as a similarity signal.

```bash
uv run notes dedup --dry-run   # preview exact + fuzzy candidate counts (no LLM)
uv run notes dedup             # → data/dedup-proposals/dedup-YYYY-MM-DD.json
```

Runs a three-pass funnel: exact content hash → fuzzy title/body similarity → LLM review.
Exact duplicates are recommended for deletion automatically; fuzzy pairs are reviewed by the LLM.

If you have already run `notes classify`, pass the proposal to improve placement-based duplicate detection:

```bash
uv run notes dedup --proposal data/proposals/proposal-YYYY-MM-DD.json
```

Two notes heading to the same `proposed_folder_path` are a stronger duplicate signal than two notes in different categories. Omitting `--proposal` still works — the pass simply uses current folder paths instead.

**→ HUMAN REVIEW:** Use `notes review --dedup` to walk through deletion groups interactively:

```bash
uv run notes review --dedup
```

For each `resolution: "delete"` group, it shows which note will be kept and which deleted
(with a content preview) and asks you to confirm. Groups you decline are removed from the
proposal — both notes survive. `resolution: "review"` groups (borderline cases) are noted
but not touched.

Alternatively, open `data/dedup-proposals/dedup-YYYY-MM-DD.json` directly. For
`resolution: "delete"` groups, verify `keep_id` is the right note to keep and remove any
group you disagree with.

```bash
uv run notes purge             # dry-run by default — shows [DRY RUN] for each deletion
uv run notes purge --execute   # actually delete; notes go to Recently Deleted (30-day recovery)
```

### After setup

- Run `uv run notes audit` to find remaining stale, stub, or duplicate notes
- Set a recurring inbox-processing habit (see below)
- If running in strict mode (`forever_notes_mode: strict`), export first then sync hubs
  to create the ✱ Home and ✱ Hub notes:
  ```bash
  uv run notes export
  uv run notes sync-hubs
  ```
  `sync-hubs` builds hub content from the latest export, so the export must reflect the
  current state of Apple Notes — including any manual moves made after `notes move`.

---

## Ongoing Inbox Processing (weekly)

Run whenever your Inbox accumulates ~10+ unprocessed notes.

**Time estimate:** 2–5 min (plus review time).

```bash
uv run notes export                # re-export if you've captured new notes
uv run notes triage --dry-run      # preview cost
uv run notes triage                # → data/proposals/inbox-YYYY-MM-DD.json
```

**→ HUMAN REVIEW:** Use `notes review` to handle the inbox proposal interactively:

```bash
uv run notes review
```

Or open `data/proposals/inbox-YYYY-MM-DD.json` directly. Check the `moves` array; delete
entries you disagree with. Move items from `needs_review` into `moves` if you know where
they should go. Notes in `no_change` are flagged as inbox-appropriate — leave or delete
them as you see fit.

```bash
uv run notes backup
uv run notes move --dry-run data/proposals/inbox-YYYY-MM-DD.json
uv run notes move data/proposals/inbox-YYYY-MM-DD.json
```

If using strict mode, re-export then sync Hub notes after applying moves. This is also
the correct sequence after any manual reorganization in Apple Notes:

```bash
uv run notes export
uv run notes sync-hubs
```

---

## Periodic Audit (monthly)

Scan the library for quality issues. No notes are changed — the audit writes a report only.

**Time estimate:** Under 1 minute.

```bash
uv run notes export
uv run notes audit                # → data/reports/audit-YYYY-MM-DD.md
```

To specify a custom output path: `uv run notes audit --output /path/to/report.md`

**→ HUMAN REVIEW:** Open `data/reports/audit-YYYY-MM-DD.md` and work through each section.

### Understanding the report

| Section | What it means | Suggested action |
|---|---|---|
| **Library Statistics** | Note count by PARA category and age distribution | Orientation only — no action required |
| **Inactive Projects** | In Projects, not modified in >90 days | Archive completed projects; reactivate stalled ones |
| **Untitled Notes** | No meaningful title | Add a title so the note is findable |
| **Stub Notes** | ≤5 combined title+body words, no attachments, not in Archive | Expand, merge with another note, or delete |
| **Duplicate Titles** | Same or similar title in multiple notes | Merge or rename to clarify |
| **Stale Inbox** | In Inbox >7 days | Process via `notes triage` or delete |
| **Stale Fleeting** | In Fleeting >30 days (Forever Notes taxonomy only) | Promote to Permanent/Literature or delete |
| **Untracked Folders** | Folders under taxonomy categories, not yet in taxonomy | Add to `taxonomy.local.yaml`, or run `notes discover` to incorporate |
| **Uncategorized Notes** | No connection to the taxonomy (container root, foreign folder) | Run `notes classify` to get move proposals |
| **Subfolder Candidates** | Flat folders large enough for subfolders | Run `notes discover`, add subfolders to taxonomy |

For bulk moves, create a proposal JSON manually (matching the `proposal-YYYY-MM-DD.json`
schema) and run `uv run notes move`. For individual notes, it's often faster to act
directly in Apple Notes.

---

## Agentic Use

Every command accepts `--json` to emit a compact JSON summary to stdout while routing human-readable output to stderr. This makes the CLI easy to drive from LLM agents or shell scripts.

```bash
# Run a command and capture the result as JSON
result=$(uv run notes classify --dry-run --json)
echo "$result" | python3 -m json.tool

# Extract the output file path
output_file=$(uv run notes classify --json | python3 -c "import sys,json; print(json.load(sys.stdin)['output_file'])")

# Chain: classify → move, checking for errors
if uv run notes classify --json | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d['status']=='ok' else 1)"; then
  uv run notes move --json
fi
```

### JSON output shape

```json
{
  "status": "ok",
  "command": "classify",
  "dry_run": false,
  "output_file": "data/proposals/proposal-2026-05-31.json",
  "log_file": "data/logs/classify-2026-05-31-143022.json",
  "summary": {"notes_processed": 312, "moves": 45, "needs_review": 12, "no_change": 255}
}
```

On failure: `"status": "error"` with an `"error"` field explaining what went wrong. `output_file` and `log_file` are `null` when not applicable (e.g. `notes move` produces no output file).

`--json` and `--dry-run` are composable: `notes classify --dry-run --json` returns `"dry_run": true` with the preview summary and no API calls made.
