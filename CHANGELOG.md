# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
