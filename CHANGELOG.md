# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-06-10

### Added

- Export staleness safety checks across all pipeline commands, driven by new `safety:` config block in `settings.example.yaml` (`export_max_age_hours: 24`, `proposal_max_age_hours: 48`):
  - **Soft warning** on `discover`, `classify`, `triage`, `audit`, and `dedup` if the export is older than `export_max_age_hours`
  - **Hard guard** on `notes move`: aborts if a newer export exists since the proposal was generated, or if the proposal itself is older than `proposal_max_age_hours`; `--force` downgrades to a warning
  - **Hard guard** on `notes sync-hubs`: aborts if the export is older than `export_max_age_hours`; `--force` downgrades to a warning
  - `restore` intentionally excluded (designed to operate from historical data); `revert` and `arrange` don't use exports
- `export_age_hours(path)` helper in `scripts/config.py`

## [0.4.1] - 2026-06-08

### Documentation

- README quickstart: `notes export` moved before `notes setup` so the wizard can analyse the library for framework recommendation (matches the runbook and Commands section, which already had the correct order)
- README quickstart: added `notes review` (interactive proposal review) and `notes backup` before `notes move`
- README Commands section: added `notes review` after `notes classify`, `notes review --dedup` after `notes dedup`, and `notes review` after `notes triage` — replacing "# → HUMAN: review proposal JSON" comments that implied raw JSON editing
- README Commands section: added `notes revert` to the Recovery block (was documented in the runbook but absent from the README)
- README and runbook: `notes arrange` now appears before `notes sync-hubs` in all examples — the saved category order must be set before syncing so the Home note reflects the user's intent
- Runbook Step 1: added callout directing users who haven't set up yet to run export before `notes setup`
- README: added Apple Notes screenshot

## [0.4.0] - 2026-06-08

### Added

- `notes setup` wizard overhaul:
  - Defaults LLM provider to **Apple Intelligence** (Enter to accept)
  - Checks Apple Intelligence prerequisites when Apple provider is selected: Xcode ≥ 26 (`xcodebuild -version`), compiled Swift bridge binary, live inference probe; prints a disk-space warning if Xcode needs to be downloaded and fewer than 50 GB are free
  - Asks the container folder question before folder mapping so the taxonomy wizard has the correct folder context
  - **Existing-system path**: auto-generates `taxonomy.local.yaml` directly from the export folder hierarchy; strips the container prefix before role detection; correctly writes `toplevel_folder.enabled: true` when a container is detected (previously this was silently skipped, causing `notes draft` to treat the container as a taxonomy category)
  - Writes a **framework-appropriate `categories:` block** on first settings creation for all frameworks (PARA, Zettelkasten, GTD, existing) — only roles present in the chosen taxonomy are included, with built-in descriptions and behavioral flags
  - Forever Notes Hub setup: new **`internal_links` question** — choose between clickable `applenotes://` HTML links (requires Full Disk Access for Terminal) and plain text titles (default); **surfaces Hub and Home note placement** when a container is detected and offers a one-field override (writes both `home_note_folder` and `hub_note_folder`)
  - Mode-aware post-discover next steps printed based on `reorganization_mode`
  - Higher subfolder threshold default (15 notes) for the existing-system path
- `static` reorganization mode — folder structure is fixed; `notes discover` runs for audit/triage only; `notes draft` is a no-op; `notes classify` places notes into existing folders without proposing new subfolders
- `notes discover`: per-theme `status` field in theme-map output; stronger anchoring to existing paths in `conservative` mode
- `notes sync-hubs`: Home note now lists **notes directly in flat top-level categories** (categories with no subfolders) as `<li>` items under the h2 heading — mirrors Hub note behavior for libraries that haven't adopted subfolders
- `notes sync-hubs`: **Home note category order and Hub category section order now reflect the Apple Notes sidebar position**, read from `ZPARENTMODIFICATIONDATE` in NoteStore.sqlite; falls back to export first-appearance order (alphabetical) when Full Disk Access is unavailable
- `notes sync-hubs` dry-run output now shows the folder where each Hub note will be placed

### Changed

- `notes repair` command removed

### Fixed

- `notes setup`: taxonomy generation now preserves full folder hierarchy from export and excludes the container folder from the generated taxonomy
- `notes discover` / `notes classify` / `notes sync-hubs`: Apple Intelligence locale errors resolved — strips control characters, drops the `id` field, adds a language anchor; handles bare-array LLM responses; sanitizes system prompts before locale-error retry
- `notes draft`: strips container prefix from suggested paths so drafts don't include the container as a taxonomy category
- `notes sync-hubs`: strips container prefix before building the theme index
- YAML config templates and generated files: non-ASCII punctuation (curly quotes, em-dashes, ellipsis) replaced with ASCII equivalents to prevent YAML parse errors

## [0.3.0] - 2026-05-31

### Added

- `--json` flag on all 14 commands — routes human-readable output to stderr and emits a compact JSON summary to stdout; designed for LLM agents and shell scripts that need structured results without parsing Rich-formatted text. Shape: `{"status": "ok"|"error", "command": "...", "dry_run": bool, "output_file": "...|null", "log_file": "...|null", "summary": {...}}`. Composable with `--dry-run`.

## [0.2.0] - 2026-05-31

### Added

- `notes draft` now directly promotes all subfolders present in the export into the taxonomy draft, regardless of whether the LLM named them in a theme — previously, structural subfolders like `Archive/Animation Guild` were silently dropped when the LLM routed those notes to a flat parent path (`Archive`) rather than using the folder name as the `suggested_path`
- `notes draft` threshold bypass: existing Apple Notes folders are now always included in the taxonomy draft regardless of `min_notes_for_subfolder` — the threshold was designed to prevent creating thin *new* folders, not to filter folders the user already made; a folder with 1 note is honoured if it exists in the library
- `notes revert [proposal]` — new command that reverses a previous `notes move` run; reads `current_folder` from the proposal and moves notes back to their original folders; supports `--dry-run`; defaults to the most recent proposal in `data/proposals/`
- `notes move` dry-run output now includes the source folder for each note — `[DRY RUN] "title" (Inbox) → Resources/Technical` — making it easier to identify which note will move when titles are not unique
- `notes draft` now bootstraps the initial taxonomy from your actual Apple Notes folder structure when no `taxonomy.local.yaml` exists — one LLM call maps your top-level folders (e.g. `Archive`, `Areas`, `Resources`) to the standard taxonomy roles, so the draft reflects your real library instead of the generic example template
- `notes discover` now injects the complete Apple Notes folder tree (all unique `folder_path` values from the export) into the batch and synthesis prompts as the primary anchor for `suggested_path` values — previously the LLM only saw folder paths scattered in individual note summaries per batch, with no holistic view of existing structure
- `reorganization_mode` setting in `settings.local.yaml` — controls how aggressively `notes discover` and `notes classify` propose changes:
  - `"conservative"`: most notes are already organized; only propose moves with high confidence for notes outside Inbox/Fleeting; discovery requires strong evidence before suggesting new paths
  - `"standard"`: default — classify all notes, anchoring to existing taxonomy paths
  - `"full"`: treat the library as raw material; reclassify from scratch without anchoring to current locations
- `notes export` now includes `account_name` in each note record
- `primary_account` filter in `settings.local.yaml` — limits export to a single named iCloud account (useful for multi-account setups)
- Ollama startup check now verifies the configured model is available; exits with an actionable message listing available models and the `ollama pull` command if the model is missing (llama.cpp is unaffected — the check is skipped when the server does not return an Ollama-format model list)
- Warning printed to stderr when `settings.local.yaml` is absent — includes the copy command to create one
- Per-command warnings when `taxonomy.local.yaml` is absent: `notes classify`, `notes audit`, and `notes sync-hubs` warn that folder names are placeholders; `notes draft` prints a neutral info message (discovery is expected to run before a local taxonomy exists)

### Changed

- `notes discover` now prints the active `reorganization_mode` before processing starts (both in dry-run and live runs), so users can exit early to adjust the setting before a long discovery run
- Taxonomy YAML files use `taxonomy:` as the root key instead of `forever_notes:` — rename the key in `config/taxonomy.local.yaml` if upgrading from an earlier version
- `notes audit` report now separates **Untracked Folders** (subfolders nested under known taxonomy categories but not yet in `taxonomy.local.yaml`) from **Uncategorized Notes** (notes in folders with no taxonomy ancestor at all) — previously both appeared under a single "Uncategorized" section
- Ollama mid-run connection loss now exits with a clear "Lost connection to Ollama" message and `ollama serve` guidance instead of a raw API error
- `notes discover` post-run next steps now directs users to `notes draft` before editing the taxonomy, matching the recommended workflow

### Fixed

- `notes audit` no longer flags subfolder candidates when `reorganization_mode: conservative` — in conservative mode the user's folder structure is intentional, and suggestions to add subfolders are noise; the report now shows a one-line note explaining the section is skipped
- `notes move` no longer silently moves the wrong note when the ID fallback finds multiple notes with the same title — the ambiguous entries are now skipped with an `[AMBIGUOUS]` warning; fulfilled the CLAUDE.md promise of "logging any ambiguities"
- `notes discover` synthesis step no longer silently falls back to the raw theme list — the JSON extractor was using `rfind("}")` to find the end of the LLM response, so trailing prose like "I merged {15} themes" caused a parse error every run; replaced with `JSONDecoder.raw_decode()` which stops at the correct boundary
- Output filenames (`themes-YYYY-MM-DD.json`, `proposal-YYYY-MM-DD.json`, etc.) now use local time to match the export filename, which also uses local time — previously UTC was used, producing a next-day date for users in negative-UTC timezones (e.g. North America evenings)
- `notes export` now correctly builds full folder paths for notes nested more than one subfolder level deep on macOS Sequoia (`container of folder` is broken on Sequoia; the export script now walks down using `folders of folder` instead)
- `notes export` now correctly reports `folder_path` for all nesting depths on macOS Sequoia (previously truncated after the first subfolder level)

## [0.1.0] - 2026-05-29

### Added

- `notes export` — export all notes from Apple Notes as structured JSON
- `notes backup` — timestamped text-only snapshot of all notes to `data/backups/`
- `notes discover` — AI-powered theme discovery; outputs theme maps for taxonomy review
- `notes draft` — generate an editable taxonomy YAML from discovery results; merges new paths into a copy of the current taxonomy for human review before classifying
- `notes classify` — AI classification of notes into the user-defined folder taxonomy
- `notes move` — move notes in Apple Notes per a human-reviewed classification proposal
- `notes triage` — focused classification of Inbox notes only
- `notes dedup` — three-pass duplicate detection (exact hash, fuzzy similarity, LLM-assisted)
- `notes purge` — delete confirmed duplicates from a human-reviewed dedup proposal (dry-run by default; `--execute` to apply)
- `notes audit` — quality report: stale, stub, and duplicate notes; subfolder candidates
- `notes sync-hubs` — generate/update ✱ Hub and ✱ Home navigation notes (Forever Notes strict mode)
- `notes restore` — recreate notes lost during a bulk move from backup + proposal
- `notes repair` — fix plain-text formatting on notes restored from iCloud Recently Deleted
- Anthropic Claude (cloud) and Ollama (local) LLM provider support
- PARA method taxonomy template (`config/taxonomy.para.yaml`)
- Forever Notes / Zettelkasten taxonomy template (`config/taxonomy.example.yaml`)
- Forever Notes loose and strict modes (strict adds Hub notes, ✱ Home, and tags)
- `--dry-run` flag on all commands
- Pre-commit hook blocking accidental commits of personal config and note data
- Pytest test suite with ≥90% line coverage

[Unreleased]: https://github.com/jdmacleod/manage-apple-notes/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/jdmacleod/manage-apple-notes/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/jdmacleod/manage-apple-notes/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jdmacleod/manage-apple-notes/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/jdmacleod/manage-apple-notes/releases/tag/v0.1.0
