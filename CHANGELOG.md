# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- Taxonomy YAML files use `taxonomy:` as the root key instead of `forever_notes:` — rename the key in `config/taxonomy.local.yaml` if upgrading from an earlier version
- `notes audit` report now separates **Untracked Folders** (subfolders nested under known taxonomy categories but not yet in `taxonomy.local.yaml`) from **Uncategorized Notes** (notes in folders with no taxonomy ancestor at all) — previously both appeared under a single "Uncategorized" section
- Ollama mid-run connection loss now exits with a clear "Lost connection to Ollama" message and `ollama serve` guidance instead of a raw API error
- `notes discover` post-run next steps now directs users to `notes draft` before editing the taxonomy, matching the recommended workflow

### Fixed

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

[Unreleased]: https://github.com/jdmacleod/manage-apple-notes/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jdmacleod/manage-apple-notes/releases/tag/v0.1.0
