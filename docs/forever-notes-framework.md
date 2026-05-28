# Forever Notes Framework Reference

The [Forever Notes framework](https://forevernotesframework.com) (fully documented at
[myforevernotes.com](https://www.myforevernotes.com/docs/home)) is a note organization
system built around two orthogonal dimensions: the **nature** of a note (Permanent,
Literature, Projects, etc.) and its **subject domain** (Health, Technology, etc.). This
project implements that taxonomy and optionally adds the framework's structural navigation
layer.

---

## Default Taxonomy

The Forever Notes framework uses a Zettelkasten-influenced taxonomy as its default starting point.
This project ships with a template (`config/taxonomy.example.yaml`) based on that structure:

| Category | Purpose |
|----------|---------|
| **Inbox** | Temporary capture, not yet processed — keep flat |
| **Fleeting** | Quick thoughts to process or discard — keep flat |
| **Literature** | Notes tied to a specific source (book, article, talk) |
| **Permanent** | Atomic, evergreen concepts in your own words |
| **Projects** | Notes for a specific active project |
| **Areas** | Ongoing responsibilities and reference |
| **Resources** | Reference material, how-tos, collections |
| **Archive** | Inactive, completed, or outdated notes |
| **Review** | Needs human triage; use when classification is unclear — keep flat |

This is a starting framework. Copy `taxonomy.example.yaml` to `taxonomy.local.yaml`, rename each
folder to match your actual Apple Notes folders, add subfolders after a discovery pass, and the
system will honor exactly what you define. Category order in the file determines the order
categories appear in your ✱ Home note.

Users who prefer the PARA method (Projects, Areas, Resources, Archive) can start from
`config/taxonomy.para.yaml` instead. See [`docs/para-method.md`](para-method.md) for PARA
guidance and both minimalist and expanded designs.

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

`settings.local.yaml` exposes `tag_all_notes` and `tag_theme_notes` flags under
`strict_mode`, but **tag application to classified notes is not yet implemented** —
the classification pipeline does not currently append tags. Hub notes themselves do
receive `#hub`, `#[theme]`, and `#ForeverNotes` tags in their body as part of
`sync-hubs`. This section will be updated when tag application is implemented.

---

## Note-to-Note Links in Hub Notes

The `internal_links` setting in `settings.local.yaml` (under `strict_mode`) controls
how note titles appear in Hub and Home note bodies:

- **`"text"` (default):** Note titles are written as plain text. Safe and reliable across
  all setups; no special permissions or UUID resolution needed.
- **`"html"` (experimental):** Note titles are written as `applenotes://showNote?identifier=UUID`
  HTML links. UUIDs are resolved from `NoteStore.sqlite`, which requires Full Disk Access for
  Terminal (see `docs/technical-notes.md`). Falls back to numeric identifiers when FDA is not
  granted.

**Current limitation with `"html"` mode:** Apple Notes' AppleScript `set body` API strips all
`href` attributes from `<a>` tags regardless of URL scheme. Links therefore appear as
underlined text in Hub notes but are **not clickable**. This is a platform constraint
with no programmatic workaround via `set body`.

Creating clickable note-to-note links requires manual intervention: select the note
title text in a Hub note, then use **Insert > Add Link** (⌘K) to replace it with a
real note link. This must be done inside the Apple Notes app; it cannot be automated
via the current AppleScript API.

See `docs/technical-notes.md` → "Note-to-note links: current status and limitations"
for the full investigation.

---

## sync-hubs Usage

```bash
uv run notes sync-hubs              # update all hubs (reads latest export)
uv run notes sync-hubs --dry-run    # preview what would be created/updated
uv run notes sync-hubs <export.json>  # use a specific export file
```

The script reads the most recent export file (or the one you specify) plus your
taxonomy, builds Hub and Home note content directly from the data (no LLM call),
and writes to Apple Notes via AppleScript. It is idempotent — safe to run
repeatedly.

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
