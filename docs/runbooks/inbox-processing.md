# Runbook: Inbox Processing

Process notes in your Inbox folder and get a proposal for where each should live.
Run this whenever your Inbox accumulates ~10+ unprocessed notes.

**Time estimate:** 2–5 minutes (plus review time).

---

## Prerequisites

- A recent full export exists in `data/exports/` (run after any major capture session)
- `taxonomy.local.yaml` is configured with your inbox folder name
- `ANTHROPIC_API_KEY` is set

---

## Step 1: Refresh the Export (if needed)

If you've captured new notes since the last export, re-run it:

```bash
osascript scripts/export/export-notes.applescript
```

Skip this if the latest export in `data/exports/` is recent enough.

---

## Step 2: Dry-Run (optional)

```bash
uv run notes inbox --dry-run
```

Shows how many inbox notes will be classified and the estimated API cost.

---

## Step 3: Classify

```bash
uv run notes inbox
```

Writes `data/proposals/inbox-YYYY-MM-DD.json`. Output includes:
- **Moves** — inbox notes Claude wants to move to a permanent folder
- **Needs review** — low-confidence or ambiguous notes
- **No change** — notes Claude thinks should stay in Inbox

---

## Step 4: Review

Open `data/proposals/inbox-YYYY-MM-DD.json` and check the `moves` array.
Edit any entry you disagree with. Move items from `needs_review` into `moves`
if you know where they should go.

---

## Step 5: Apply

```bash
# Dry-run first
osascript scripts/execute/apply-proposal.applescript --dry-run data/proposals/inbox-YYYY-MM-DD.json

# Apply when satisfied
osascript scripts/execute/apply-proposal.applescript data/proposals/inbox-YYYY-MM-DD.json
```

---

## Tips

- Notes landing in Review or Needs Review after several passes may just need to
  be deleted or expanded — add them to your next audit pass.
- Archive processed proposals to `data/archive/` to keep `data/proposals/` tidy.
