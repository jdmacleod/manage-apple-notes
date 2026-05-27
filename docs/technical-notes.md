# Technical Notes

Research findings and platform-specific behavior discovered during the development and
use of this project.

---

## Apple Notes Platform Behavior

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
not found, logging any ambiguities. Never treat a stored `x-coredata://` ID as a permanent
stable identifier.

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

### Folder depth is limited to two levels

The Apple Notes UI supports at most two levels of folder nesting:
- Top-level folder (e.g. "Permanent")
- Subfolder inside a top-level folder (e.g. "Health")

Deeper nesting is not supported in the UI, though it may be technically writable. This
project's `Category/Theme` taxonomy is designed around this two-level constraint.

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
- Cost at `claude-sonnet-4-6` pricing (~$3/M input tokens, mid-2026): ~$0.66

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

### Why deduplication runs after classification

Running `notes dedup` after `notes classify` gives the dedup algorithm access to
`proposed_folder_path` from the classification proposal. Two notes both heading to
`Permanent/Health` are far more likely to be true duplicates than two notes in different
categories that happen to share a theme.

Running dedup before classification loses this placement signal entirely and produces more
false positives (near-duplicate pairs that are actually intentionally distinct notes on a
related theme but destined for different categories).

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

### Recommended models

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
