# Notes Workflow

All steps use the `notes` CLI (`uv run notes <command>`). Human review checkpoints are
marked explicitly — no notes are modified without your approval.

---

## Initial Library Setup (one-time)

Run this once to organize an existing library into the configured folder taxonomy.

**Time estimate:** 30–60 min (plus review time for large libraries).

**Prerequisites:** Setup complete (`uv sync`, `.env` configured, `taxonomy.local.yaml` filled in), Apple Notes open and synced.

### Step 1 — Export

```bash
uv run notes export
```

Writes `data/exports/notes-YYYY-MM-DD.json` and prints the note count.

### Step 2 — Discover themes (Pass 1)

```bash
uv run notes discover --dry-run   # preview batch count and API cost
uv run notes discover             # → data/theme-maps/themes-YYYY-MM-DD.json
```

Sends batches of note summaries to the LLM to map the thematic clusters in your library.
No notes are changed.

**→ HUMAN REVIEW:** Open `data/theme-maps/themes-YYYY-MM-DD.json` and review the themes.
Merge, rename, or discard as needed. Then add the approved subfolder names to
`config/taxonomy.local.yaml` under the relevant categories:

```yaml
permanent:
  folder: "Resources"
  subfolders: ["Health", "Technology", "Writing"]
```

### Step 3 — Classify (Pass 2)

```bash
uv run notes classify --dry-run   # preview batch count and API cost
uv run notes classify             # → data/proposals/proposal-YYYY-MM-DD.json
```

Classifies every note into a folder and subfolder based on your updated taxonomy.

**→ HUMAN REVIEW:** Open `data/proposals/proposal-YYYY-MM-DD.json` and review the `moves`
array. Delete any entry you disagree with. Move items from `needs_review` into `moves` if
you know where they should go. Folder names in `proposed_folder` must exactly match your
`taxonomy.local.yaml`; `proposed_subfolder` must match a name in that category's
`subfolders` list.

### Step 4 — Apply

```bash
uv run notes apply --dry-run   # preview every move with colored output
uv run notes apply             # apply approved moves to Apple Notes
```

Each move is logged: `[MOVED]` (green), `[SKIP]` (yellow), `[ERROR]` (red).
To apply a specific proposal file: `uv run notes apply data/proposals/proposal-YYYY-MM-DD.json`.

### Step 5 — Deduplicate (Pass 3, optional)

Run after applying moves so that `proposed_folder_path` can be used as a similarity signal.

```bash
uv run notes dedup --dry-run   # preview exact + fuzzy candidate counts (no LLM)
uv run notes dedup             # → data/dedup-proposals/dedup-YYYY-MM-DD.json
```

Runs a three-pass funnel: exact content hash → fuzzy title/body similarity → LLM review.
Exact duplicates are recommended for deletion automatically; fuzzy pairs are reviewed by the LLM.

**→ HUMAN REVIEW:** Open `data/dedup-proposals/dedup-YYYY-MM-DD.json` and review each group.
For `resolution: "delete"` groups, verify `keep_id` is the right note to keep. Remove any
group you disagree with. Groups with `resolution: "review"` are flagged for manual triage in
Apple Notes and are not touched by the apply script.

```bash
uv run notes apply-dedup             # dry-run by default — shows [DRY RUN] for each deletion
uv run notes apply-dedup --execute   # actually delete; notes go to Recently Deleted (30-day recovery)
```

### After setup

- Run `uv run notes audit` to find remaining stale, stub, or duplicate notes
- Set a recurring inbox-processing habit (see below)

---

## Ongoing Inbox Processing (weekly)

Run whenever your Inbox accumulates ~10+ unprocessed notes.

**Time estimate:** 2–5 min (plus review time).

```bash
uv run notes export               # re-export if you've captured new notes
uv run notes inbox --dry-run      # preview cost
uv run notes inbox                # → data/proposals/inbox-YYYY-MM-DD.json
```

**→ HUMAN REVIEW:** Open `data/proposals/inbox-YYYY-MM-DD.json`. Check the `moves` array;
edit entries you disagree with. Move items from `needs_review` into `moves` if you know
where they should go. Notes in `no_change` are flagged as inbox-appropriate — leave or
delete them as you see fit.

```bash
uv run notes apply --dry-run data/proposals/inbox-YYYY-MM-DD.json
uv run notes apply data/proposals/inbox-YYYY-MM-DD.json
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
| **Stale Notes** | Not modified in >180 days, not in Archive | Move to Archive or delete |
| **Stub Notes** | Body <50 characters | Expand, merge with another note, or delete |
| **Duplicate Titles** | Same or similar title in multiple notes | Merge or rename to clarify |
| **Stale Inbox** | In Inbox >7 days | Process via `notes inbox` or delete |
| **Stale Fleeting** | In Fleeting >30 days | Promote to Permanent/Literature or delete |
| **Subfolder Candidates** | Flat folders large enough for subfolders | Run `notes discover`, add subfolders to taxonomy |

For bulk moves, create a proposal JSON manually (matching the `proposal-YYYY-MM-DD.json`
schema) and apply it with `uv run notes apply`. For individual notes, it's often faster to
act directly in Apple Notes.
