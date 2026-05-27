# Forever Notes Framework Reference

The [Forever Notes framework](https://forevernotesframework.com) (fully documented at
[myforevernotes.com](https://www.myforevernotes.com/docs/home)) is a note organization
system built around two orthogonal dimensions: the **nature** of a note (Permanent,
Literature, Projects, etc.) and its **subject domain** (Health, Technology, etc.). This
project implements that taxonomy and optionally adds the framework's structural navigation
layer.

---

## Operating Modes

Set `forever_notes_mode` in `settings.local.yaml`:

### `loose` (default)

Folder taxonomy, theme discovery, classification, and deduplication — the full pipeline
described in `docs/runbooks/main-workflow.md`. No structural notes required. A clean,
well-organised library without any additional maintenance overhead.

Good for users who want the organizational benefits of the framework without committing to
the full navigational layer.

### `strict`

Everything in loose mode, plus:

- **✱ Hub notes** — one per theme (e.g. "✱ Health"), listing all notes on that topic
  across every category they appear in
- **✱ Home** — a root note indexing all Hub notes; the single entry point for the library
- **Tags** — `#[theme]` and `#ForeverNotes` appended to classified notes

Strict mode is additive. It does not rename notes, change folder structure, or alter how
classification works. Switching to `loose` after using `strict` leaves the Hub and Home
notes in place but stops updating them — they simply become inert notes.

---

## Structural Layer (strict mode)

### ✱ Home

A single root note that indexes all Hub notes, grouped by category. Serves as the entry
point for the entire library. The `✱` prefix (Unicode U+2731, not a standard asterisk)
sorts it above all other notes in alphabetical order in any folder.

Created and maintained by `uv run notes sync-hubs`.

### ✱ Hub Notes

One Hub note per theme (e.g. "✱ Health", "✱ Technology"). Each Hub is a **cross-category
index**: it lists notes from every category that has a subfolder for that theme —
`Permanent/Health`, `Literature/Health`, `Areas/Health` — in one place.

This is the key insight: Hubs cut across the nature/domain dimensions and provide a single
entry point for a topic regardless of note type. You don't need to navigate into
`Permanent` and then `Health` separately — the Hub shows everything.

Hub notes are created and updated by `uv run notes sync-hubs`.

### Tags

When `tag_all_notes: true` (default in strict mode), every classified note gets
`#ForeverNotes` appended if not already present. When `tag_theme_notes: true`, notes also
get a `#[theme]` tag (e.g. `#health`). Tags are appended only — never removed, even if a
note is reclassified.

---

## Internal Links

Hub note bodies reference other notes by title. Two formats are available:

**`internal_links: "text"` (default, safe)**

Hub bodies contain plain note titles as a list. You can convert any title to an internal
link at your own pace using Apple Notes' `>>` shortcut — type `>>` followed by the note
title to create a live link. This produces stable `applenotes://` links that survive iCloud
sync reliably. A few minutes of manual work after setup; never needs repeating unless you
add notes.

**`internal_links: "html"` (experimental)**

The sync script attempts to construct `applenotes://` URLs from note IDs and write them as
HTML anchor links directly. This is experimental: the URL-to-ID mapping may be unreliable
after iCloud sync events, device migrations, or Notes app updates. Only enable if you
understand the risk of broken links and have verified stability in your environment.

---

## sync-hubs.py Usage

```bash
uv run notes sync-hubs              # update all hubs (reads latest export)
uv run notes sync-hubs --dry-run    # preview what would be created/updated
uv run notes sync-hubs <export.json>  # use a specific export file
```

The script reads the most recent export file (or the one you specify) plus your taxonomy,
generates Hub note content via the LLM, and writes to Apple Notes via AppleScript. It is
idempotent — safe to run repeatedly.

Exits with a clear message if `forever_notes_mode` is not `strict`.

---

## When to Use Strict Mode

Strict mode adds a maintenance step: after any pass that files new notes (inbox processing,
classification), Hub note contents go stale until you run `sync-hubs`. The overhead is
small for a weekly workflow but grows if you add notes daily.

Consider strict mode if:
- You have a large, well-organized library with stable themes
- You find yourself navigating between multiple subfolders to find notes on a topic
- You want a dashboard-style ✱ Home as a daily starting point

Loose mode is a complete organizational system on its own — there is no pressure to use
strict mode.

---

## Further Reading

- [myforevernotes.com](https://www.myforevernotes.com/docs/home) — full framework documentation
- `docs/technical-notes.md` — Apple Notes platform behavior, encoding quirks, ID instability
- `docs/security-considerations.md` — data flow, MCP audit guidance
