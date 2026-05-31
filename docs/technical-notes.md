# Technical Notes

Research findings and platform-specific behavior discovered during the development and
use of this project.

---

## Tested Platforms

All behavior documented here has been observed on one or more of the following:

| Device | Chip | OS |
|---|---|---|
| MacBook Pro (M4, 2024) | Apple M4 | macOS Tahoe 26.5 |
| Mac mini (2018) | Intel Core i5 | macOS Sequoia 15.7.7 |
| iPhone 16e | Apple A16 Bionic | iOS 26.4.2 |

Platform-specific findings are noted where behavior differs between devices or OS versions.

---

## Apple Notes Platform Behavior

### `container of folder` is broken for path-building on macOS Sequoia

On macOS Sequoia, `container of folder` has two distinct problems that make it unusable
for building full hierarchical paths:

**1. `class of (container of aFolder)` cannot be coerced to a string**

The error message is `"Can't make class of container of … into type specifier."` This means
any approach that checks `class of parentContainer is folder` to decide whether to recurse
will fail silently — the comparison always evaluates to `false`, regardless of whether the
parent is actually a folder.

**2. `container of aNote` when iterating `every note`**

`every note` at the application level returns notes without folder context. `container of
aNote` returns a generic reference whose class cannot be determined. The reliable pattern is
to iterate `accounts → folders of acct → notes of aFolder` so the folder is always known
from the outer loop.

**The correct approach: walk DOWN using `folders of folder`**

`folders of aFolder` reliably returns direct children (subfolders) on all tested macOS
versions. Instead of walking UP the container chain, the export script now walks DOWN,
passing the accumulated path as a parameter:

```applescript
on processFolder(aFolder, folderPath)
    tell application "Notes"
        repeat with aNote in notes of aFolder
            -- record note with folderPath as folder_path
        end repeat
        try
            repeat with subFolder in folders of aFolder
                set subName to name of subFolder
                my processFolder(subFolder, folderPath & "/" & subName)
            end repeat
        end try
    end tell
end processFolder
```

**Top-level folder detection and the `contents of` pitfall**

`folders of acct` returns ALL folders flat (including nested ones). To walk only from
top-level folders (avoiding duplicating every note), the script builds a set of subfolder
names: for each folder, collect `name of` its direct children. Any folder whose name
appears in that set is NOT top-level. The remaining folders are walked from the top.

The critical subtlety: in AppleScript's `repeat with item in list`, the loop variable is a
**reference** to the list item, not a copy of its value. Comparing it with `is` always
returns `false`:

```applescript
-- WRONG: sn is a reference, not a value
if sn is fName then ...

-- CORRECT: dereference the list item before comparing
if (contents of sn) is fName then ...
```

This `is` comparison failure produces an empty top-level set (all folders treated as
top-level), causing every note to be exported once per level of nesting depth.

**Caveat:** `container of aFolder` raises error -1728 ("Can't get container of…") for
folders in secondary accounts (e.g. "On My Mac"). The walk-down approach avoids this
entirely since it never calls `container of`.

The diagnostic test at `scripts/export/test-getfullpath.applescript` documents these
findings and can be used to verify correct behavior after macOS upgrades.

### Why AppleScript, not SQLite

Apple Notes stores data in `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite`.
This database is:
- **Undocumented** — no official schema or migration guarantee
- **Schema-unstable** — it changes between macOS versions; queries that work on Sonoma
  may break on Sequoia
- **Locked while Notes is open** — direct reads require Notes to be closed

This project uses AppleScript exclusively. AppleScript calls go through the Notes app's own
APIs, which are stable across macOS upgrades and safe to use while Notes is running.

### Note IDs are not stable

Apple Notes identifies notes with `x-coredata://UUID/ICNote/pNNNN` URIs. These IDs:
- **Can change** after iCloud sync conflicts, device migrations, or restoring from backup
- **Are not portable** between accounts or iCloud containers

Scripts in this project match on ID first, then fall back to title + folder if the ID is
not found. When the title fallback finds more than one matching note, it logs `[AMBIGUOUS]`
and skips that note rather than moving the wrong one. Never treat a stored `x-coredata://`
ID as a permanent stable identifier.

### Note-to-note links: current status and limitations

Clickable note-to-note links in Hub and Home notes are technically difficult to create
programmatically. This section documents what has been investigated and what is required
to make them work.

#### How Apple Notes stores note links

Apple Notes stores note-to-note links internally as `NSTextAttachment` objects, not as
HTML `<a href>` elements. When read back via AppleScript's `body` property, real note
links appear as `<u><br></u>` — the href and display text are both invisible. In the
macOS Accessibility tree they appear as `UI element` nodes with an Object Replacement
Character (U+FFFC) prefix in their description (e.g. `￼ ✱ Finance`).

#### Why `set body` cannot create note links

AppleScript's `set body` strips **all** `href` attributes from every `<a>` tag,
regardless of URL scheme. This has been confirmed for `applenotes://showNote`,
`applenotes:note/UUID`, `x-coredata://`, `https://`, and `notes://showNote` — all are
silently stripped, leaving only the link text wrapped in `<u>` tags.

#### The correct URL format

The macOS URL scheme for opening a specific note is:

```
applenotes://showNote?identifier=<UUID>
```

where `<UUID>` is the note's stable iCloud identifier (e.g.
`5F8F2E2B-C506-4EEA-BB1B-93DC68BDD670`). This is **not** the numeric `pNNN` component
from the `x-coredata://` URI. The UUID must be obtained by querying NoteStore.sqlite:

```sql
-- Z_PK comes from stripping the leading 'p' off the x-coredata last path component
SELECT ZIDENTIFIER FROM ZICCLOUDSYNCINGOBJECT WHERE Z_PK = <primary_key>;
```

#### Full Disk Access requirement

NoteStore.sqlite lives in `~/Library/Group Containers/group.com.apple.notes/` and is
protected by macOS Privacy controls. Reading it requires **Full Disk Access** for
whichever shell or app runs the query. Scripts running as subprocesses of Claude Code
do not inherit this grant; they fail with `PermissionError`.

The recommended practice is:

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Grant access to Terminal (or iTerm2, etc.)
3. Run the note-link operations from that terminal
4. Revoke Full Disk Access when the session is complete

Scripts in this project that require Full Disk Access should detect the permission
failure and exit with a clear message explaining the above steps, rather than silently
producing incorrect output.

#### Note-to-note links as a user opt-in

Because note-to-note links require Full Disk Access and must be run from a user
terminal session (not as a background/automated task), this feature is treated as an
opt-in operation. The `sync-hubs` command generates Hub and Home notes with plain
text titles (no links) by default. A separate command will be provided to add links
once the workflow is functioning and Full Disk Access is confirmed available.

*This section will be updated once the complete link-insertion workflow is implemented
and tested.*

### Notes are stored as HTML internally

AppleScript exposes two body properties on each note:
- `body` — returns the raw HTML (formatted text, attachments, tables)
- `plaintext` — strips all formatting and returns plain text

This project uses `plaintext` for all LLM classification. As a consequence, merging note
content programmatically would silently lose formatting, attachments, and embedded links.
This is why the deduplication pass flags merge candidates as `resolution: "review"` rather
than automating merges — the user must merge manually inside the Notes app to preserve
content fidelity.

### AppleScript encoding for non-ASCII content

AppleScript file I/O has unreliable behavior with notes containing non-ASCII characters
(accented letters, CJK characters, emoji). Writing note content directly from AppleScript
to a file can produce double-encoded or truncated output.

The export script works around this by:
1. Using ASCII control characters (chr 30 = Record Separator, chr 31 = Unit Separator) as
   field/record delimiters — safe for all note content since these never appear in text
2. Passing the delimited data to Python via a temp file
3. Reading the temp file as `mac_roman` encoding with error replacement
4. Re-serializing to UTF-8 JSON with `json.dump`

This two-stage approach consistently handles multilingual content and special characters.

### Deleted notes are recoverable

AppleScript's `delete` command on a note moves it to the "Recently Deleted" folder, not
permanent deletion. Notes in Recently Deleted are recoverable for 30 days from within the
Notes app (select the folder, then right-click → "Recover").

`apply-dedup-proposal.applescript` uses `delete` for all removals specifically to preserve
this recovery window. The `--execute` confirmation output reminds users of this.

### Notes at account root have a shallow container chain

Apple Notes allows notes to exist directly inside an account (no enclosing folder).
When this is the case, `container of targetNote` in AppleScript returns the account
itself — so the common pattern `container of (container of targetNote)` to reach the
account fails with "Can't get container of container of note id …".

The fix is to check the class of the direct container before dereferencing:

```applescript
set noteDirectContainer to container of targetNote
if class of noteDirectContainer is account then
    set noteAccount to noteDirectContainer
else
    set noteAccount to container of noteDirectContainer
end if
```

This is relevant any time a script needs the account reference in order to create
folders or move notes. Unorganized libraries (notes never placed in a folder) will
trigger this path for every note on the first apply run.

### Bulk moves can send notes to Recently Deleted via iCloud conflict resolution

When a large number of notes (hundreds) are moved in rapid succession via
AppleScript, iCloud sync may treat some moves as write conflicts. The conflict
resolution can move the "losing" copy to Recently Deleted rather than merging.
This has been observed with notes stored in the iCloud default `Notes` folder,
particularly older notes (pre-2015) with longer sync histories across many devices.

**Symptoms:** Notes report `[MOVED]` in the apply log but are subsequently
unfindable — `every note whose name is <title>` returns 0 matches and the notes
are absent from all folders. Total visible note count equals exactly the number
of confirmed moves, with no notes unaccounted for elsewhere.

**Recovery:** Open the Notes app on Mac or iPhone, navigate to Recently Deleted
(bottom of the iCloud sidebar), and restore the affected notes. The apply script
can then be re-run against the same proposal to move them to their correct
destinations — note IDs will have changed, but the title-search fallback will
locate them.

**AppleScript cannot read Recently Deleted.** `folder "Recently Deleted" of
account` raises an error. There is no programmatic way to restore notes from
Recently Deleted; it must be done through the Notes app UI.

### Folder depth supports up to five levels

Apple Notes supports up to five levels of folder nesting (one top-level folder
plus four subfolder levels), confirmed on iPhone 16e running current iOS. The
same structure is accessible and navigable on macOS.

This project's taxonomy uses at most three levels when `toplevel_folder` is
enabled: the container (e.g. "Library") at level 1, PARA categories
(e.g. "Areas") at level 2, and theme subfolders (e.g. "Finance") at level 3.
Without a container, the taxonomy remains two levels deep.

---

## LLM Classification Findings

### Context window vs. batch size

Smaller quantized local models (7B–8B at Q4) commonly have effective context windows of
4096 tokens. A batch of 20 notes with 2000-char bodies can easily exceed this, producing
either a context overflow error or a truncated JSON response.

Both `notes classify` and `notes discover` use recursive batch splitting to handle this:
on a context overflow API error or a `ValueError`/`JSONDecodeError` from truncated output,
the batch halves and both halves retry independently. This continues down to a minimum
batch size of 1. If a single-note batch fails, it is skipped with a warning logged.

**Practical guidance:** For local models, start with `batch_size: 5–10` in
`settings.local.yaml`. Batch splitting adds latency but ensures completion.

### Token estimation

Approximate input token costs for the Anthropic provider:
- ~700 tokens per note (title + 2000-char body)
- ~1500 tokens per system prompt (shared across all notes in a batch)
- A 300-note library at `batch_size: 10` → ~220k input tokens
- Cost at `claude-opus-4-6` pricing (~$15/M input tokens, mid-2026): ~$3.30
- Cost at `claude-sonnet-4-6` pricing (~$3/M input tokens, mid-2026): ~$0.66 (see `settings.example.yaml`)

The `--dry-run` flag on `notes classify` and `notes discover` prints an estimate before
any API calls are made.

### Theme discovery synthesis pass

`notes discover` runs in two stages:
1. **Per-batch extraction**: each batch of notes is sent to the LLM to identify themes
   present in that batch
2. **Synthesis call**: all per-batch theme lists are merged in a single follow-up call
   that deduplicates and consolidates overlapping or fragmented theme names

The synthesis call is critical — without it, 15 batches produce 15 slightly-different names
for the same theme (e.g. "Health", "Health & Fitness", "Fitness & Nutrition"). If a first
run produces too many themes, increasing `theme_discovery_sample` or re-running often
produces a cleaner consolidated result.

### Anchored discovery — convergence across repeated runs

By default (`theme_discovery_mode: "anchored"` in settings), `notes discover` injects all
existing taxonomy subfolder paths into both the per-batch and synthesis prompts. The LLM is
instructed to map themes to established paths before proposing new ones. This means:

- Re-running discover on the same library after adding subfolders to `taxonomy.local.yaml`
  produces the same `suggested_path` values for unchanged note clusters — theme names stabilise
- The console output labels themes as "existing" or "new", and the theme map JSON includes
  `established_paths` and `new_paths` keys for at-a-glance review
- As the taxonomy matures, the "new proposals" count approaches zero — discover becomes a
  validation pass rather than a re-invention pass

Set `theme_discovery_mode: "full"` to ignore existing paths and get a fresh proposal (useful
after a major library restructure or to reset the taxonomy entirely).

### Why deduplication runs after classification

Running `notes dedup` after `notes classify` gives the dedup algorithm access to
`proposed_folder_path` from the classification proposal. Two notes both heading to
`Permanent/Health` are far more likely to be true duplicates than two notes in different
categories that happen to share a theme.

Running dedup before classification loses this placement signal entirely and produces more
false positives (near-duplicate pairs that are actually intentionally distinct notes on a
related theme but destined for different categories).

### Hub note generation: LLM approach replaced by direct HTML

An early implementation of `sync-hubs` used an LLM call to generate Hub note bodies from
a `prompts/sync-hubs.md` template. This was retired when it became clear that Hub structure
is deterministic (group notes by subfolder, render HTML list) and requires no inference.
Hub and Home note bodies are now built directly by `_generate_hub_body()` and
`_build_home_body()` in `scripts/forever_notes/sync_hubs.py`.

### Prompt caching (Anthropic)

The system prompt for each classification call is sent with `cache_control: "ephemeral"`,
which caches it in Anthropic's infrastructure for 5 minutes. On a 30-batch run with the
same system prompt, this cache hit reduces both latency and input token cost significantly.
The cache is keyed on the exact prompt text — updating `taxonomy.local.yaml` between runs
invalidates it.

---

## Local LLM Model Recommendations (macOS, ≤24 GB unified memory)

### Task requirements

The classification task requires a model that can:
- Output a valid JSON array of 10–20 structured objects per call
- Adhere to a taxonomy schema (exact folder names, null vs. string subfolder)
- Write a concise one-sentence rationale per note
- Handle system + user messages totaling 3000–8000 tokens

Instruction-tuned models consistently outperform base models on all four requirements.
Models fine-tuned for structured output (function calling, JSON mode) work best.

### Memory guidance

On Apple Silicon Macs, RAM is unified memory shared between CPU and GPU. macOS reserves
approximately 4–6 GB for the OS and running apps, leaving the rest available to Ollama.

| Available unified RAM | Usable for models | Notes |
|---|---|---|
| 8 GB total | ~3–4 GB | Only small quantized models |
| 16 GB total | ~10–12 GB | 8B models fit comfortably |
| 24 GB total | ~18 GB | 12B–14B models fit well |

### Recommended models (May 2026, changes quickly)

| Device RAM | Model | Ollama tag | Size on disk |
|---|---|---|---|
| 8 GB | Phi-3.5 Mini Instruct | `phi3.5` | ~2.5 GB |
| 8 GB | Llama 3.2 3B Instruct | `llama3.2:3b` | ~2 GB |
| 16 GB | Llama 3.1 8B Instruct | `llama3.1:8b` | ~5 GB |
| 16 GB | Gemma 2 9B Instruct | `gemma2:9b` | ~6 GB |
| 24 GB | Mistral Nemo 12B Instruct | `mistral-nemo:12b` | ~7 GB |
| 24 GB | Qwen 2.5 14B Instruct | `qwen2.5:14b` | ~9 GB |

**First-choice recommendations by device:**
- **8 GB**: `phi3.5` — best JSON reliability in its size class
- **16 GB**: `llama3.1:8b` — strong instruction following, consistent JSON output
- **24 GB**: `mistral-nemo:12b` — significantly better than 8B models; reliable structured output

### Practical setup notes

- Set `batch_size: 5` for 8 GB devices; `batch_size: 10` for 16 GB+
- Run `ollama ps` to confirm the model is loaded into GPU memory rather than paged to disk —
  a model running on CPU is 5–10× slower
- If you see malformed or truncated JSON, reduce `batch_size` before switching models;
  context overflow is the most common cause
- `OLLAMA_BASE_URL` in `.env` takes precedence over `settings.local.yaml` — set it there
  to switch between cloud and local without editing config files

### Pulling and configuring a model

```bash
ollama pull llama3.1:8b

# Add to .env (gitignored):
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Then in `settings.local.yaml` set `batch_size: 10` under the `llm:` key. The
`OLLAMA_BASE_URL` env var activates the Ollama provider automatically — no need to change
`llm.provider` in settings.
