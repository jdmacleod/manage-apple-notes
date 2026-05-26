# Runbook: Library Audit

Scan your full Notes library for quality issues: stale notes, stub notes,
duplicate titles, and notes that have lingered too long in Inbox or Fleeting.

No notes are changed — the audit only writes a Markdown report for human review.

**Time estimate:** Under 1 minute. Run monthly or after a major reorganization.

---

## Prerequisites

- A recent full export exists in `data/exports/`
- `taxonomy.local.yaml` is configured (folder names needed for inbox/fleeting/archive checks)

---

## Step 1: Refresh the Export

```bash
osascript scripts/export/export-notes.applescript
```

---

## Step 2: Dry-Run (optional)

```bash
uv run notes audit --dry-run
```

Shows which checks will run and where the report will be written.

---

## Step 3: Run the Audit

```bash
uv run notes audit
```

Writes `data/reports/audit-YYYY-MM-DD.md`. To specify a custom output path:

```bash
uv run notes audit --output /path/to/my-report.md
```

---

## Understanding the Report

| Section | What it means | Suggested action |
|---|---|---|
| **Stale Notes** | Not modified in >180 days, not in Archive | Move to Archive or delete |
| **Stub Notes** | Body <50 characters | Expand, merge with another note, or delete |
| **Duplicate Titles** | Same or similar title in multiple notes | Merge or rename to clarify |
| **Stale Inbox** | In Inbox >7 days | Process via `notes inbox` or delete |
| **Stale Fleeting** | In Fleeting >30 days | Promote to Permanent/Literature or delete |

---

## Acting on the Report

The report lists titles and folders — use it as a checklist. For bulk moves,
create a proposal JSON manually (matching the `proposal-YYYY-MM-DD.json` schema)
and apply it with `apply-proposal.applescript`.

For individual notes, it's often faster to handle them directly in Apple Notes.
