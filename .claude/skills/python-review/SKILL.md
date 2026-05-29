---
name: python-review
description: "Review Python code in the manage-apple-notes toolkit for correctness, safety, and project conventions. Use this skill whenever the user opens, writes, edits, or asks about any .py file in the project — especially scripts that call the Anthropic API, invoke subprocess/osascript, load YAML config, read or write JSON proposal files, or apply changes to Apple Notes. Also trigger when the user asks 'does this handle errors correctly', 'is this safe to run', or 'will this work with dry-run'. This project processes personal note data with destructive write potential — silent failures and missing dry-run guards are the most dangerous defects."
---

# Python Review

This skill reviews Python code in the manage-apple-notes toolkit. The project
has three external dependencies that require specific handling patterns, and
one cross-cutting concern that applies to every script that modifies data.

Read `references/python-conventions.md` for annotated code snippets.
Use this SKILL.md to understand which patterns matter and why.

---

## Before Manual Review

Run the automated checks first — they catch mechanical issues that don't need human
attention:

```bash
uv run ruff check scripts/     # must pass clean before review
uv run mypy scripts/           # address errors in files touched by the change
```

Fix any ruff errors before proceeding. Mypy is configured with
`disallow_untyped_defs = true`, so type hints are required on **all** functions —
public and private. Mypy errors in untouched files are pre-existing and out of scope.

---

## The Four Review Areas

### 1. Anthropic API calls

Every call to `anthropic.messages.create()` must handle three distinct
failure modes explicitly. The pattern to look for:

```python
# Minimum required error handling
try:
    response = client.messages.create(...)
except anthropic.RateLimitError:
    # retry with backoff — never just re-raise immediately
except anthropic.APIStatusError as e:
    # log e.status_code and e.message, then decide to retry or abort
except anthropic.APIConnectionError:
    # network unreachable — log and abort gracefully
```

**Why these three specifically:** `RateLimitError` is recoverable with
backoff; `APIStatusError` covers server errors (5xx) and bad requests
(4xx); `APIConnectionError` covers the case where the user is offline or
the API is unreachable. A bare `except Exception` that treats all three
the same way will silently swallow rate limit signals and retry too
aggressively, or abort too early on a transient network blip.

Beyond error handling, watch for response parsing. The LLM may return
malformed JSON or a response that doesn't match the expected schema.
Response parsing must be separated from the API call itself — a function
that both calls the API and parses the result cannot be independently
tested. Flag any function where `client.messages.create()` and
`json.loads()` appear in the same function body.

### 2. subprocess / osascript calls

Scripts that invoke AppleScript via `subprocess` have two concerns:
shell injection and silent failure.

**Silent failure** is the more common defect. `subprocess.run()` does not
raise on non-zero exit by default. Flag any call missing `check=True` or
an explicit `returncode` check:

```python
# SILENT FAILURE: non-zero exit is ignored
result = subprocess.run(["osascript", "-e", script], capture_output=True)
output = result.stdout.decode()  # may be empty string on failure

# CORRECT: raises CalledProcessError on non-zero exit
result = subprocess.run(
    ["osascript", "-e", script],
    capture_output=True,
    text=True,
    check=True,
)
```

**Shell injection** occurs when note content or user input is interpolated
into a shell command string. Flag any `subprocess.run(shell=True, ...)` where
the command string includes a variable, and any `os.system()` call.
The fix is always `shell=False` with an argument list.

### 3. YAML config loading and proposal file I/O

**Config loading** must validate required keys before use. A script that
accesses `config['notes_root_folder']` without first checking the key exists
will raise `KeyError` in a way that looks identical to a code bug rather
than a user configuration error. The convention is to validate at load time
and produce a clear error message pointing to the relevant settings key.

**Proposal file writes** are the most dangerous I/O in this project — they
feed the step that deletes or merges notes. The atomic write pattern is
required for any file that will be read back and acted upon:

```python
# RISKY: a crash mid-write leaves a corrupt file
with open(output_path, "w") as f:
    json.dump(proposals, f, indent=2)

# CORRECT: atomic write via temp file + os.replace()
import tempfile, os
with tempfile.NamedTemporaryFile(
    mode="w", dir=output_path.parent, delete=False, suffix=".tmp"
) as tmp:
    json.dump(proposals, tmp, indent=2)
    tmp_path = tmp.name
os.replace(tmp_path, output_path)
```

Flag any `open(..., "w")` on a file under `data/` that is not using the
atomic pattern.

Also flag `os.path` usage anywhere — the project convention is `pathlib.Path`
throughout. `os.path.join`, `os.path.exists`, `os.path.dirname` should all
be replaced with their `pathlib` equivalents.

### 4. Project conventions

These patterns are specific to this codebase. Flag deviations:

- **Console output** — use `rich.console.Console`, never `print()`.
- **Paths** — derive from `REPO_ROOT`, never hardcode absolute paths.
- **Thresholds and batch sizes** — read from `settings` dict, never use
  magic numbers inline.
- **Comments** — only when the WHY is non-obvious. Never restate what the
  code does; never reference the PR, task, or caller.
- **Data integrity** — export functions must not silently truncate note
  content. Truncation is only for LLM batches (`max_body_chars` setting).
- **Proposal schema** — the `moves` and `needs_review` arrays must match
  the documented schema; any script writing proposals must validate keys
  before writing.

### 5. Dry-run guard

Every script that writes to Apple Notes or modifies files under `data/`
must have a `--dry-run` CLI flag that suppresses all writes. This is the
last line of defence before data loss during development and testing.

The guard pattern:

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true",
                    help="Preview changes without applying them")
args = parser.parse_args()

# Later, before any write:
if not args.dry_run:
    apply_changes(proposals)
else:
    print("[dry-run] would apply", len(proposals), "changes")
```

Flag any script that:
- Has a function named `apply_*`, `delete_*`, `move_*`, `create_*`, or `merge_*`
- Does not have `--dry-run` in its argument parser
- OR has `--dry-run` in the parser but does not gate all write operations
  behind the flag

Also flag any type annotations missing from public functions — functions
with parameters and return values that have no type hints make the codebase
harder to review and test.

---

## Review Output Format

```
## Python Review

Script: <filename>
Reviewed: <date>

### 1. Anthropic API calls
<findings — cite line numbers>
— or —
No issues.

### 2. subprocess / osascript calls
<findings>
— or —
No issues. / Not applicable.

### 3. Config loading and file I/O
<findings>
— or —
No issues.

### 4. Project conventions
<findings>
— or —
No issues.

### 5. Dry-run guard
<findings>
— or —
No issues. / Not applicable (read-only script).

### Verdict
<one of: LOOKS GOOD / NEEDS FIXES / SIGNIFICANT ISSUES>

### Fix priority
1. <most critical>
2. ...
```

Use **SIGNIFICANT ISSUES** if there is any missing dry-run guard on a
destructive script, any `shell=True` with user-controlled input, or any
API call with no error handling whatsoever. Use **NEEDS FIXES** for
missing type annotations, `os.path` usage, non-atomic file writes, or
project convention violations. Use **LOOKS GOOD** when all five areas
are clean or findings are minor style issues.

---

## Tips

- Read-only scripts (export, theme discovery, report generation) do not
  need a dry-run guard. Only flag its absence on scripts whose name or
  function set suggests writes: `apply_*`, `classify_*` (moves notes),
  `deduplicate_*`, `sync_hubs_*`.
- Type annotation completeness is required on all functions — mypy's
  `disallow_untyped_defs = true` enforces this for public and private alike.
  Private helpers (`_load_config`, `_parse_response`) are not exempt.
- The `thefuzz` and `python-Levenshtein` packages are intentional
  dependencies for the deduplication pipeline — do not flag them as
  unexpected.
- If a script imports `anthropic` but never calls `messages.create()`
  directly (it delegates to a helper), check the helper — the error
  handling requirement applies wherever the actual API call lives.
