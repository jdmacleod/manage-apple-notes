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

### Tags and mentions require iOS 14.5 / iPadOS 14.5 / macOS 11.3 or later

Notes containing tags (e.g. `#project`) or `@mentions` are only viewable on
**iOS 14.5, iPadOS 14.5, and macOS 11.3 (Big Sur) or later**. Devices running
older OS versions display these notes without the tag or mention formatting, and
the tags do not appear in the Tags browser.

This is relevant to the `tag_all_notes`, `tag_theme_notes`, and `tag_hub_notes`
settings (currently unreleased — see `settings.example.yaml`): enabling any of
these on a library accessed from older devices will silently strip the tags on
those devices. Confirm all devices accessing the iCloud account meet the minimum
OS requirement before enabling tag features.

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
  produces the same `suggested_path` values for unchanged note clusters — theme names stabilize
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
- `OLLAMA_BASE_URL` in `.env` sets the connection URL; `OLLAMA_MODEL` overrides the model
  name — both apply when `provider: "ollama"` is set in `settings.local.yaml`

### Pulling and configuring a model

```bash
ollama pull llama3.1:8b

# Add to .env (gitignored) — connection URL and optional model override:
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Set `provider: "ollama"` and `batch_size: 10` in `settings.local.yaml`. The
`llm.provider` setting is the authoritative selector — `OLLAMA_BASE_URL` configures
where to connect, but does not change which provider runs.

---

## AWS-Ollama Provider (g5.xlarge, 24 GB VRAM)

### Hardware

The default CDK stack deploys an **EC2 g5.xlarge** instance:

| Spec | Value |
|------|-------|
| GPU | NVIDIA A10G |
| VRAM | 24 GB GDDR6 |
| vCPUs | 4 |
| System RAM | 16 GB |

### Default model: `gpt-oss:20b`

`gpt-oss:20b` is the recommended default for this instance class. At Q4_K_M quantization:

| Component | VRAM |
|-----------|------|
| Model weights | ~12 GB |
| CUDA + framework overhead | ~1 GB |
| **Available for KV cache** | **~11 GB** |

With ~11 GB for the KV cache, an **8,192-token (8K) context window** fits comfortably. Values up to 16K may work depending on the model's exact attention head configuration, but 8K is the tested and recommended default. Set `context_size.ollama: 8192` in `settings.local.yaml` (see `settings.example.yaml` for the full snippet).

### Comparison with local macOS models

| Scenario | Model | Context window | Relative quality |
|----------|-------|---------------|-----------------|
| Local Mac, 24 GB unified RAM | `mistral-nemo:12b` or `qwen2.5:14b` | 4K–8K | Good |
| AWS g5.xlarge, 24 GB VRAM | `gpt-oss:20b` | **8K** | Better — 20B params, dedicated GPU |
| Anthropic cloud | `claude-opus-4-6` | 8K (configured) | Best — largest model |

The A10G's 24 GB of dedicated GDDR6 is a significant advantage over unified-memory Macs: the model runs entirely in VRAM with no CPU offload, producing faster and more consistent inference than even a 24 GB M-series Mac.

### Recommended settings

```yaml
# config/settings.local.yaml
aws:
  region: "us-east-1"
  instance_type: "g5.xlarge"
  key_pair_name: "my-aws-key"
  ssh_key_path: "~/.ssh/my-aws-key.pem"
  model: "gpt-oss:20b"

llm:
  provider: "ollama"
  model: "gpt-oss:20b"
  batch_size: 10
  context_size:
    ollama: 8192
```

`batch_size: 10` works reliably within the 8K context window. If you see context overflow errors (malformed or truncated JSON), reduce `batch_size` to 5 before lowering `context_size`.

### Verifying GPU utilization

After connecting via SSH tunnel and running a classification pass, confirm the model is running on the GPU (not CPU-offloaded):

```bash
ssh -i ~/.ssh/my-aws-key.pem ec2-user@<ip> nvidia-smi
```

The `GPU-Util` column should show non-zero utilization during inference and `ollama` should appear in the process list. A model that partially offloads to system RAM will show lower VRAM utilization and slower throughput.

---

## Apple Intelligence Provider

### Why a Swift CLI bridge is required

Apple's `FoundationModels` framework is Swift-only — it cannot be called directly from
Python. The solution is a thin Swift CLI tool at `swift/apple-llm/` that:

1. Checks `SystemLanguageModel.default.availability` and exits with code 2 if unavailable
2. Reads a JSON object from stdin (`{"system": "...", "user": "...", "max_tokens": N}`)
3. Creates a `LanguageModelSession` with the system prompt as instructions
4. Calls `session.respond(to:)` asynchronously
5. Writes the plain-text response to stdout

The Python `AppleProvider.classify_messages()` calls this binary via `subprocess.run()`,
which blocks until the process exits — bridging Swift's async API to the synchronous
Python interface naturally.

### Requirements

- **macOS 26 or later** — `FoundationModels` is only available on macOS 26+
- **Apple Silicon Mac** — Apple Intelligence requires an M-series chip
- **Apple Intelligence enabled** — enable in System Settings → Apple Intelligence & Siri
- **Xcode 26** — required to compile the Swift package (`swift build`)

### Building the CLI tool

The Swift package includes a self-documenting `Makefile`. Run with no target to list
all available targets:

```bash
# From the repo root
make -C swift/apple-llm          # list available targets (help)
make -C swift/apple-llm build    # compile the release binary
make -C swift/apple-llm smoke    # build and run a quick end-to-end smoke test
```

Available targets:

| Target | Description |
|--------|-------------|
| `build` | Compile the release binary → `.build/release/apple-llm` |
| `debug` | Compile a debug binary with symbols → `.build/debug/apple-llm` |
| `test` | Run the Swift test suite |
| `clean` | Remove all build artefacts (`.build/`) |
| `smoke` | Build then pipe a minimal JSON request through the binary |

The `.build/` directory is gitignored. The binary must be compiled on the machine where
it will run — it cannot be committed to or distributed from the repo.

### Context window constraint and batch_size

Apple's on-device model has a **4096-token total context window** shared by:
- System prompt (~1000–1500 tokens for the classification prompt)
- User content (the batch of notes to classify)
- Generated response

At ~3–4 characters per token, a single note with a 2000-character body uses roughly
500–700 tokens. With the system prompt occupying ~1200 tokens, there is room for roughly
one note and a compact response within the 4096-token ceiling.

**Always set `batch_size: 1`** in `settings.local.yaml` when using the Apple provider:

```yaml
llm:
  provider: "apple"
  batch_size: 1
```

If the context window is exceeded, the Swift tool exits with code 3 and the Python
provider raises `RuntimeError("apple_context_overflow")`. The pipeline logs this as a
batch error and continues.

### Exit codes

| Code | Meaning | Python behavior |
|------|---------|-----------------|
| 0 | Success | Returns stdout as response text |
| 1 | General error | Raises `RuntimeError` with stderr message |
| 2 | Apple Intelligence unavailable | Calls `sys.exit()` — halts the pipeline |
| 3 | Context window exceeded | Raises `RuntimeError("apple_context_overflow")` |
| 4 | Unsupported language/locale | Raises `RuntimeError("apple_unsupported_locale")` — note is skipped |

### Language and locale support

Apple Intelligence supports **23 locales** across Dutch, Swedish, Turkish, Spanish, Danish,
Chinese, Italian, Japanese, Norwegian, French, Portuguese, English, German, Korean, and
Vietnamese. **Always check at runtime** rather than hardcoding this list, as support expands
with OS updates:

```swift
let supported = SystemLanguageModel.default.supportedLanguages  // [Locale.Language]
```

#### What triggers `unsupportedLanguageOrLocale`

The error fires when the Foundation Models framework detects that the prompt is asking it
to respond in a language it does not support. Because the classification *system* prompt is
entirely in English, the trigger in practice is **note body content** in an unsupported
language — a recipe in French, a quote in Japanese, pasted foreign-language text, etc.
Purely structural content (URLs, code snippets, numbers) generally does not trigger it.

This is a content-language filter, not a device-locale check. A Mac set to English US can
still hit this error if a note contains enough non-English text.

#### What the locale filter actually checks

The filter has two distinct triggers:

**Character encoding** — rejects any non-printable or non-ASCII character:
- Latin-1 accented letters (`é`, `ü`, `ñ`) — common in names and loanwords
- Curly quotes and em dash — inserted by Apple autocorrect into virtually every note
- Non-printable ASCII control chars (U+0001–U+001F, U+007F) — from pasted terminal output

Standard ASCII punctuation (`.`, `,`, `!`, `?`, `-`, `(`, `)`, `[`, `]`) is **not** a problem.

**Language detection** — even with content normalized to ASCII, the model runs a
language classifier on the user content. Triggers that look non-English to the classifier:
- `x-coredata://UUID/ICNote/pN` Apple Notes IDs sent as part of the batch
- Batches where many notes have empty content after CJK normalization (the classifier sees
  mostly JSON structure and empty fields, which are ambiguous)
- Dense technical content (URLs, code, hex strings)

**Discover action** — `id` field excluded entirely (discover never references IDs in
its output), and `"Notes sample:\n\n"` preamble prepended so the classifier sees
English prose first.

**Classify action** — `id` field cannot be removed because the LLM response must echo
it back for note matching. Instead, `x-coredata://UUID/ICNote/pN` IDs are replaced with
short placeholders (`note_0`, `note_1`, …) before sending, and remapped back to real IDs
after parsing the response. A `"Classify these notes:\n\n"` preamble is also prepended.

**Two-level retry:** `apple-llm` (Swift) retries automatically, and the Python pipeline
retries if the Swift-level retry also fails. Both normalize to printable ASCII + standard
whitespace (tab, newline, CR). Non-printable control chars (U+0001–U+001F excluding
whitespace, and U+007F) are also removed.

Swift-level (`apple-llm`):
1. First attempt: full content → `unsupportedLanguageOrLocale`
2. Normalize **both** system prompt and user content to ASCII; collapse whitespace
3. If ≥ 5 ASCII words remain in user content: retry
4. Retry succeeds → exit 0; fails or too short → exit 4

Python-level (`discover` and `classify` actions, on receiving exit 4):

**Pre-normalization (Apple provider only):** Before the first API call, both the batch
payload and system prompt are normalized for locale compatibility. This prevents the
fail/retry cycle for character-encoding issues (accented letters, autocorrect curly
quotes) on every batch.

**Batch retry and split strategy (for batches > 1 note):**
1. On locale error: sanitize batch + system prompt to ASCII; retry the full batch.
2. If sanitized retry also fails with locale error: the aggregate language of the batch
   is triggering the detector even on ASCII-only content (common when CJK/Arabic notes
   dominate a batch). Split the batch in half and process each independently.
3. Recurse until each note is processed individually or succeeds in a sub-batch.
4. Notes that fail at batch size 1 are logged by title and skipped.

This mirrors the context-overflow split strategy and ensures that English notes in a
mixed-language batch are not discarded because non-English notes tipped the detector.

**Single-note path (batch == 1):**
1. Sanitize and retry once.
2. If still locale error: skip with a per-note warning showing the note title.

#### Residual limitations

- Notes composed entirely in an unsupported language cannot be classified by the Apple
  provider. Switch to Anthropic or Ollama for multilingual libraries.
- The language detector can be triggered by ASCII content whose pattern looks non-English
  (romanized text, dense code snippets). These notes are isolated to batch size 1 and
  skipped individually rather than causing whole-batch failures.
- Notes composed entirely in an unsupported language cannot be classified by the Apple
  provider. Switch to Anthropic or Ollama for multilingual libraries.

### Response token ceiling

The Swift bridge caps `maximumResponseTokens` at **1600** via `cappedResponseTokens()` in
`Bridge.swift`. This value was raised from an earlier 800-token ceiling after discovery runs
exhibited systematic "no JSON object found" parse failures: a batch of 20 notes can produce
10–15 theme objects each with 6 fields (~150–200 tokens each), requiring 1,500–3,000
response tokens — far beyond the old 800-token cap.

The 1600-token ceiling is safe given the 4096-token total context budget:
- System prompt: ~1,200–1,500 tokens
- User content for a 5-note discover batch: ~250 tokens
- Remaining budget: ~2,300 tokens — well above 1600

For classify (always `batch_size: 1`), a single-note response is ~100 tokens; the ceiling
is not a factor.

Individual-note probes within the locale-isolation loop (see below) use a tighter cap of
400 tokens, since a single-note discover probe needs at most 2–3 themes and a full 1600-token
budget encourages the model to write verbose reasoning that overflows the context.

### ISO-8601 slug title normalisation

Notes with titles of the form `YYYY-MM-DD-Word-Word` (e.g. meeting notes exported from
note-taking apps as `2019-04-02-Legislative-Conference`) trigger Apple's language detector
even when all characters are pure ASCII. The dense-hyphen, numeric-date pattern creates
n-gram sequences that score low on all known-language models — the classifier sees a
technical identifier, not English prose.

`normalize_slug_title()` in `scripts/json_utils.py` detects the pattern and rewrites it
before the payload is sent to the on-device model:

```
2019-04-02-Legislative-Conference  →  Legislative Conference (April 2, 2019)
2018-08-28-L839-AMPTP              →  L839 AMPTP (August 28, 2018)
```

Applied after `normalize_for_apple` (so the regex always operates on clean ASCII)
in `_sanitize_batch_for_locale` (discover) and `_sanitize_notes_for_locale` (classify).
The original title is never modified in Apple Notes or in the proposal output.

### Locale isolation — linear probe

When a discover batch fails Apple's locale filter after slug normalisation, the pipeline
probes each note individually (O(n) API calls) to identify and skip only the problematic
notes, then collects themes from the passing notes. This replaces an earlier O(n log n)
binary-split cascade.

### Synthesis for Apple — two-step approach

The synthesis step merges per-batch theme lists into a single deduplicated list. The naive
approach — sending the full synthesis prompt (~1000 tokens) + all raw themes (~90 tokens
each) + 1600-token response ceiling to Apple's 4096-token context — overflows. The
pipeline uses a two-step approach to fit synthesis within the budget:

**Step 1 — Python exact dedup (no API call):** Themes with identical `suggested_path` are
merged in Python, summing `estimated_count` and keeping the first occurrence's metadata.
With `theme_discovery_sample: 5` and a 338-note library, ~200 raw themes from 68 batches
collapse to ~30–50 distinct-path themes.

**Step 2 — LLM semantic dedup (1 API call):** Themes are stripped to 3 fields (`name`,
`estimated_count`, `suggested_path`, ~25 tokens each) before sending. A minimal synthesis
prompt (~80 tokens) replaces the full prompt (~1000 tokens). Token budget:
- System: ~80 tokens
- User (50 stripped themes × 25): ~1,250 tokens
- Total input: ~1,330 tokens — leaves 2,766 tokens for response, capped at 1,600 ✓

After synthesis the full fields (`description`, `reasoning`, `appears_in_categories`) are
re-attached from the original raw themes by matching on `suggested_path`.

**Fallback:** If synthesis overflows (>95 distinct-path themes — very large libraries), the
Python-deduped list is used directly. Exact duplicates are still merged; only the semantic
near-duplicate consolidation is skipped.

### macOS 26.4+ context size API

Apple added `SystemLanguageModel.contextSize` (the available token capacity) and
`tokenCount(for:)` (precise token counting for a given input) in macOS 26.4, both
back-deployed to all macOS 26.x versions. A future improvement to the Swift tool could
use these to compute the exact available response budget dynamically, rather than using the
static 1600-token ceiling.
