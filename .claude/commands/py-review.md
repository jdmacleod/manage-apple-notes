# Python Code Review

Review the Python file(s) or diff provided. Apply the project's conventions from
`CLAUDE.md` alongside general Python quality criteria.

## What to check

**Correctness and error handling**
- Exceptions are specific (never bare `except:`); errors surface with enough context to act on
- AppleScript subprocess calls check `returncode` and capture both stdout and stderr
- File I/O uses explicit `encoding="utf-8"` and handles missing files gracefully

**Security**
- No f-string or string-join construction of shell commands — use argument lists
- No accidental inclusion of `data/`, `config/*.local.*`, or `.env` content in output
- External input (note titles, folder names) is treated as untrusted data

**Project patterns**
- Config loaded via `_load_yaml(local_path, example_path)` fallback pattern
- Console output via `rich.console.Console`, not `print()`
- `data/` paths derived from `REPO_ROOT`, not hardcoded
- Batch sizes and thresholds come from settings, not magic numbers

**Style (from CLAUDE.md)**
- No comments that restate what the code does — only comments explaining non-obvious WHY
- No multi-line docstrings; one short line max where needed
- No unused backwards-compatibility shims or `_renamed` variables
- Type hints on all public function signatures

**Data integrity**
- Export functions must not silently truncate note content (truncation is only for LLM batches)
- Proposal JSON schema matches the expected `moves` / `needs_review` structure
- Any note ID used for matching logs a warning when falling back to title + folder

## Output format

For each issue found: file, line number, severity (error / warning / suggestion), and a
one-sentence explanation. Group by severity. If no issues are found, say so explicitly.

$ARGUMENTS
