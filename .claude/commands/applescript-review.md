# AppleScript Review — Apple Notes Scripts

Review the AppleScript file(s) provided. Focus on correctness with the Apple Notes
API and the known platform limitations documented in `docs/technical-notes.md`.

## What to check

**Error handling**
- Every `tell application "Notes"` block has an outer `try / on error errMsg number errNum`
- Error -1728 (container object access for secondary-account folders) is caught and handled,
  not assumed impossible — see `docs/technical-notes.md`
- `url of note` returns `missing value`, not a string — any use must be guarded with
  `try / on error` before coercion

**`missing value` safety**
- Properties that can return `missing value` (url, container, body) are checked before use
- Coercions like `someVal as string` are never applied to a potentially-missing value without a guard

**String construction**
- Newlines inside strings use `linefeed` or `return` variables, not `& return` at end of
  a statement (which is parsed as a return statement, not a newline character)
- Intermediate variables are used before concatenation when operator precedence with
  `as string` could cause a syntax error (e.g., assign `set x to class of el as string`
  before using `x` in a concatenation)

**Note identity and matching**
- Scripts that locate notes by ID fall back to title + folder matching when the ID is
  not found, and log the ambiguity
- x-coredata:// IDs are treated as potentially stale (they can change after iCloud sync
  conflicts or device migrations)

**`set body` limitations**
- Scripts that write HTML body content must not assume `href` attributes will survive —
  `set body` strips all `href` values from `<a>` tags regardless of URL scheme
- If the intent is clickable links, add a comment noting this is not achievable via
  `set body` and must be done manually via Insert > Add Link (⌘K)

**Account and folder access**
- Folder lookups specify the account explicitly where multiple accounts may be present
- Container-level access for secondary accounts is wrapped in error handling for -1728

**AppleScript syntax traps**
- No `is settable of attribute` inline — must use `try / on error` to test settability
- Handler parameter names do not shadow AppleScript keywords

## Output format

For each issue: file, approximate line or handler name, severity (error / warning /
suggestion), and a one-sentence explanation. If no issues, say so explicitly.

$ARGUMENTS
