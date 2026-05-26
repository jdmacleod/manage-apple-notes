# Runbook: One-Time Library Cleanup

This runbook walks through the full classification and reorganization of an
existing Apple Notes library. Run through it once to bring your library in line
with the Forever Notes taxonomy.

**Time estimate:** 30–60 min (plus review time for large libraries).

---

## Prerequisites

- Setup complete: `uv sync`, API key set, `taxonomy.local.yaml` configured
- Apple Notes is open and synced
- Pre-commit hook is active: `git config core.hooksPath .git-hooks`

---

## Step 1: Export

```bash
osascript scripts/export/export-notes.applescript
```

This writes `data/exports/notes-YYYY-MM-DD.json`. Verify it looks sane:

```bash
# Check note count
python3 -c "import json; notes=json.load(open('data/exports/notes-$(date +%Y-%m-%d).json')); print(f'{len(notes)} notes exported')"
```

If your library is large (1,000+ notes), consider a dry-run first to estimate
API cost before classifying.

---

## Step 2: Dry-Run (recommended)

```bash
uv run notes classify --dry-run
```

Review the estimated batch count and API cost. If the cost is higher than
expected, consider increasing `batch_size` in `settings.local.yaml` (fewer API
calls, more tokens per call) or switching to `claude-sonnet-4-6`.

---

## Step 3: Classify

```bash
uv run notes classify
```

This sends your notes to Claude in batches and writes a proposal to
`data/proposals/proposal-YYYY-MM-DD.json`. Progress is shown in the terminal.

Summary printed at the end:
- **Moves** — notes Claude wants to move to a different folder
- **Needs review** — notes with low confidence or genuinely ambiguous
- **No change** — notes already in the right folder

---

## Step 4: Review the Proposal

Open `data/proposals/proposal-YYYY-MM-DD.json` and review the `moves` array.

Things to look for:
- Any move that seems wrong — delete it from the array
- Any note in `needs_review` you want to manually place — move it to `moves`
  with a `proposed_folder` value
- Folder names in `proposed_folder` must exactly match your `taxonomy.local.yaml`

The `needs_review` and `no_change` arrays are ignored by the apply script.

---

## Step 5: Dry-Run the Apply

```bash
osascript scripts/execute/apply-proposal.applescript --dry-run data/proposals/proposal-YYYY-MM-DD.json
```

Prints every move that would happen. Review before proceeding.

---

## Step 6: Apply

```bash
osascript scripts/execute/apply-proposal.applescript data/proposals/proposal-YYYY-MM-DD.json
```

Each move is logged:
```
[MOVED] "Note Title" → Target Folder
[SKIP]  "Missing Note" — not found
[ERROR] "Problem Note": <error message>
```

A summary is printed at the end.

---

## After the Cleanup

- Run `uv run notes audit` to find any remaining stale, stub, or duplicate notes
- Set up a recurring inbox-processing habit: `uv run notes inbox` whenever your
  Inbox accumulates more than ~10 notes
- Archive proposals you've applied: move files from `data/proposals/` to `data/archive/`
