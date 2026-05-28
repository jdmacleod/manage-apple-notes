# sync-hubs prompt (retired)

Hub note bodies are now generated directly by `scripts/forever_notes/sync_hubs.py`
(`_generate_hub_body`) without an LLM call. This file is kept for reference only.

## Previous behaviour

The LLM was given the Hub name and a JSON list of note titles grouped by category,
and asked to produce a plain-text body with category headings and note title lists.
The prompt constrained the model to list only provided titles, add no commentary,
and end with a `#hub #[theme] #ForeverNotes` tag block.

## Current behaviour

`_generate_hub_body` produces an HTML body directly from the theme index:
- `<h2>` for each category heading
- `<ul><li>` with `applenotes://showNote?identifier=pNNN` links for each note
- `<p>` for the closing tag block

The `applenotes://` local identifier is extracted from the note's `x-coredata://`
ID in the export (last path component). See `docs/technical-notes.md` for
stability caveats on these links.
