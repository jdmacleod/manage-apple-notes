# notes setup — interactive onboarding

`notes setup` walks you through picking a note organization framework, names your Apple Notes folders, and writes `config/taxonomy.local.yaml` and (on first run) `config/settings.local.yaml`.

## Usage

```bash
uv run notes setup           # full wizard — corpus analysis + 3 questions
uv run notes setup --dry-run # preview what would be written without touching files
uv run notes setup --no-corpus  # skip corpus analysis; rely on questions only
```

Run `notes setup` again any time you want to switch frameworks or rename folders. It backs up your existing `taxonomy.local.yaml` before overwriting.

---

## What it does

1. **Account detection** — setup queries Apple Notes via AppleScript to list your accounts (e.g. iCloud, Gmail). If a single account is found, it's noted and setup continues. If multiple accounts are found, setup explains the implications and asks which one you want to organize; the selection is written to `settings.local.yaml` as `primary_account` so all subsequent exports and moves stay within that account. If detection fails (Automation permission not yet granted), setup prints a reminder and continues — you can set `primary_account` manually later.

2. **Corpus analysis** — if a recent export exists in `data/exports/`, setup analyzes it silently and uses those signals to weight the framework recommendation. If no export exists, setup relies on your answers alone.

3. **3 questions** — goal, maintenance appetite, working style. Your answers are scored against three framework profiles.

4. **Recommendation** — setup shows the recommended framework with a rationale, a folder structure preview, and confidence level. You can accept or override.

5. **Folder naming** — for each category in the chosen framework, setup prompts for a folder name (defaulting to the canonical name). Press Enter to accept. For the "use existing system" path, setup reads your export to show your current folders and auto-generate the taxonomy, then offers to add any standard folders that are missing.

6. **Write config files** — `config/taxonomy.local.yaml` is written (existing file is backed up as `.bak`). If `config/settings.local.yaml` doesn't exist, it's copied from the example.

7. **Organization style** — if `settings.local.yaml` was just created, setup asks: how aggressively the AI should reorganize (standard / conservative / static), how many notes trigger a new subfolder, and whether Archive notes should be excluded from classification. Writes `reorganization_mode`, `folder_nesting`, `thresholds.min_notes_for_subfolder`, and `classify.exclude_archive`. Skipped on re-runs.

8. **Forever Notes Hub structure** — asks whether to enable Hub and Home notes (the `sync-hubs` layer). If yes, collects the home note title and hub note prefix. Writes `forever_notes_mode` and related `strict_mode` keys. Skipped on re-runs.

9. **LLM provider selection** — asks which LLM provider to use and writes `llm_provider` to `settings.local.yaml`. For Anthropic, optionally collects your API key and writes it to `.env` (never echoed). For Ollama, collects the base URL and model name. Skipped on re-runs.

10. **Container folder structure** — asks whether to nest all taxonomy folders inside a single container folder (e.g. `Library/`) or place them at the account root. Writes `toplevel_folder.enabled` and `toplevel_folder.name`. Skipped on re-runs.

11. **Primary account** — if multiple accounts were detected in step 1 and `settings.local.yaml` was just created, writes the selected account as `primary_account` in `settings.local.yaml`.

---

## Framework comparison

| Framework | Folders | Best for | Maintenance |
|-----------|---------|----------|-------------|
| **PARA** | Inbox / Projects / Areas / Resources / Archive | Digital generalists; low-friction organization | Low |
| **GTD** | Inbox / Next Actions / Waiting For / Projects / Someday-Maybe / Reference / Archive | People overwhelmed by tasks and commitments | Medium — weekly review required |
| **Zettelkasten** | Inbox / Fleeting / Literature / Permanent / Projects / Areas / Resources / Archive / Review | Writers, researchers building compounding knowledge | High — every note must be processed and linked |

Not sure which fits? PARA is the recommended default — it's the easiest to start with and works well for most people. You can always re-run `notes setup` to switch frameworks later.

---

## Corpus signals

When a `notes-*.json` export is available, setup extracts these signals:

| Signal | How it's measured | Effect |
|--------|-------------------|--------|
| Note count | Total notes in export | Large libraries (>1000) favor Zettelkasten |
| Folder count | Unique top-level folders | Many folders (>6) favor PARA |
| Avg note length | Mean word count per body | Long notes (>300 words) favor Zettelkasten; short (<80) favor GTD |
| Task keywords | Notes with TODO / `- [ ]` / @ / next: / waiting | High density (>10%) favors GTD |
| Cross-references | Notes with `[[...]]` patterns | Any presence (>5%) strongly favors Zettelkasten |
| Oldest note | Days since the oldest modified note | Old libraries (>3 years) slightly favor Zettelkasten |

---

## After setup

You're ready to run the pipeline. If you chose "Skip" for provider selection (or are
re-running setup to change your taxonomy), set `llm_provider` manually first:

```yaml
llm_provider: "apple"   # apple | anthropic | ollama | aws-ollama
```

See [GUIDE.md](../GUIDE.md) for provider-specific prerequisites (Apple Intelligence Swift
build, Ollama install and model pull, Anthropic API key).

Then run the pipeline:

```bash
uv run notes export    # pull notes from Apple Notes (skip if setup already analyzed an export)
uv run notes discover  # map thematic clusters → data/theme-maps/ (optional — only needed for subfolders)
uv run notes classify  # AI classification → proposal
uv run notes review    # interactively place needs-review items; optionally drop low-confidence moves
uv run notes move      # apply the approved proposal
```

---

## GTD: additional settings step

GTD uses category keys (`next_actions`, `waiting_for`, `someday_maybe`, `reference`) that are not in the built-in defaults. When GTD is chosen, `notes setup` prints a YAML snippet to add to the `categories:` block of `config/settings.local.yaml` so the classifier and audit use the correct descriptions.

See [`docs/gtd-method.md`](gtd-method.md) for a full explanation of the GTD categories, two ready-to-use taxonomy designs, and guidance on adapting the system for Apple Notes.

Example snippet:

```yaml
categories:
  next_actions:
    active_days: 14
    description: concrete next actions — single tasks to do ASAP
  waiting_for:
    description: items delegated or blocked on someone else
    stale_days: 14
  someday_maybe:
    description: deferred ideas and projects
  reference:
    description: reference material — not actionable
    exclude_from_classify: true
```

---

## Manual config editing

If you prefer to edit config files directly rather than using the wizard:

- **`config/taxonomy.local.yaml`** — map category keys to Apple Notes folder names. See `config/taxonomy.zettelkasten.yaml` (Zettelkasten), `config/taxonomy.para.yaml` (PARA), or `config/taxonomy.gtd.yaml` (GTD) as templates.
- **`config/settings.local.yaml`** — provider, model, batch size, thresholds. See `config/settings.example.yaml`.

Category keys defined in `taxonomy.local.yaml` automatically inherit built-in defaults from `scripts/config.py`. Override per-category metadata (descriptions, flags) in the `categories:` block of `settings.local.yaml`.
