---
name: applescript-review
description: "Review AppleScript and JXA (JavaScript for Automation) code for correctness, error handling, and Apple Notes-specific failure modes. Use this skill whenever the user opens, writes, edits, or asks about any .applescript, .scpt, or .js file that references the Notes application — or any Python/shell code that invokes osascript. Also trigger when the user reports a script that hangs, silently fails, returns wrong results, or behaves differently across iCloud accounts or folder structures. AppleScript has almost no community review tooling; this skill encodes the Notes-specific patterns that are otherwise learned only through painful debugging."
---

# AppleScript Review

This skill reviews AppleScript and JXA code that interacts with Apple Notes.
The goal is to catch the failure modes that are unique to this environment:
Apple Notes' asynchronous folder operations, the iCloud account boundary,
nested folder path construction, and AppleScript error handling conventions.

General code quality review is secondary. The primary concern is: will this
script work correctly and reliably against a real Apple Notes library, or will
it fail silently, hang, or return results from the wrong account?

Read `references/applescript-patterns.md` for annotated code snippets. Use
this SKILL.md to understand which patterns to look for and why they matter.

---

## The Four Review Areas

### 0. Note iteration pattern (check first)

Never iterate `every note` at the application level. On macOS Sequoia,
`container of aNote` returns a generic `item` reference — not a `folder` —
so folder names are silently empty and no error is raised.

```applescript
-- BROKEN on Sequoia: container returns item, not folder
set allNotes to every note of application "Notes"
repeat with aNote in allNotes
    set folderName to name of container of aNote  -- silently wrong
end repeat
```

The correct pattern is `accounts → folders → notes` with the folder name
captured from the outer loop:

```applescript
tell application "Notes"
    repeat with acct in accounts
        repeat with aFolder in folders of acct
            set folderName to name of aFolder
            repeat with aNote in notes of aFolder
                -- folderName is always correct here
            end repeat
        end repeat
    end repeat
end tell
```

Flag any script using `every note` at application level or relying on
`container of aNote` to determine the folder context.

### 1. Error handling

AppleScript error handling exists on a spectrum from useless to correct.
The bare form swallows all diagnostic information:

```applescript
try
    -- risky operation
on error
    -- no errMsg, no errNum — completely opaque
end try
```

The correct form names the error message and number explicitly:

```applescript
try
    -- risky operation
on error errMsg number errNum
    -- errMsg and errNum are now available for logging or re-raise
end try
```

**Why this matters for Notes specifically:** Apple Notes returns undocumented
error codes for common operations — `-1728` (object not found), `-10004`
(permission denied by user), `-600` (Notes not running). Without the error
number, a script that fails against a specific folder structure or account
is essentially undebuggable. Flag every bare `on error` block.

For JXA, the equivalent concern is a bare `.catch(() => {})` or
`.catch(e => {})` where `e` is never logged or re-thrown.

Also flag any use of `url of note` without a guard — this property returns
`missing value`, not a string, and coercing it raises error -1700. Any access
must be wrapped in `try / on error`.

### 2. Folder path construction

Apple Notes allows folders with the same name in different accounts and
different parent folders. A flat name lookup is ambiguous:

```applescript
-- FRAGILE: returns the first folder named "Projects" regardless of account
folder "Projects" of application "Notes"
```

The correct form chains the full path:

```applescript
-- CORRECT: unambiguous path through account and parent
folder "Projects" of folder "Library" of account "iCloud"
```

**Why this matters:** When a user has both an iCloud account and an "On My
Mac" account, flat lookups consistently return results from whichever account
the OS happens to enumerate first — usually not the one the user intended.
Flag any folder reference that does not include an explicit account.

For nested folders (subfolder within a top-level folder), the chained form
is required:

```applescript
folder "Work" of folder "Areas" of account "iCloud"
```

Not:
```applescript
folder "Work" of application "Notes"  -- ambiguous
```

### 3. Iteration over large libraries

`every note` without a count guard is a common performance trap. On a
library with 2000+ notes, iterating the full set in a single AppleScript
call can hit the 60-second scripting timeout and return an empty result
with no error — the script appears to succeed while returning nothing.

```applescript
-- RISKY on large libraries: may silently timeout
set allNotes to every note of folder "Inbox" of account "iCloud"
```

The safer pattern fetches a bounded count first and processes in chunks,
or uses the Notes search API rather than full iteration. Flag unbounded
`every note` calls in scripts that may be run against libraries with
hundreds of notes.

**Async folder creation:** After creating a new folder in Notes, the folder
may not be immediately accessible to subsequent AppleScript statements. A
`delay 0.5` after folder creation prevents the next lookup from failing with
object-not-found:

```applescript
make new folder with properties {name:"New Folder"} at account "iCloud"
delay 0.5  -- allow Notes to register the new folder
set myFolder to folder "New Folder" of account "iCloud"
```

Flag any script that creates a folder and immediately uses it without a
delay.

### 4. String construction traps

Two AppleScript-specific syntax traps cause silent bugs:

**`& return` at end of statement:** In AppleScript, `return` at the end of
a concatenation expression is parsed as a `return` statement, not the newline
character. This means the handler exits early with a partial value instead of
appending a newline.

```applescript
-- BROKEN: parsed as "return theString", not string & newline
set theString to "Hello" & return

-- CORRECT: assign return/linefeed to a variable first
set nl to return  -- or: set nl to linefeed
set theString to "Hello" & nl & "World"
```

**`as string` operator precedence in concatenation:** When coercing a value
inside a concatenation, operator precedence causes a syntax error unless an
intermediate variable is used:

```applescript
-- BROKEN: syntax error — "as" binds to the concatenation
set result to "Class: " & (class of el as string) & " end"

-- CORRECT: coerce first, then concatenate
set elClass to class of el as string
set result to "Class: " & elClass & " end"
```

Flag any `& return` at the end of a statement, and any `as string` coercion
inside a `&` chain without an intermediate variable.

### 5. `set body` limitations

Scripts that write HTML to note bodies via `set body` must not assume `href`
attributes will survive. Apple Notes strips **all** `href` values from `<a>`
tags regardless of URL scheme — `applenotes://`, `https://`, `x-coredata://`
are all stripped. Links appear as underlined text but are not clickable.

Flag any script that writes `<a href=...>` links via `set body` and does not
have a comment explaining this limitation. Creating real note-to-note links
requires manual intervention: select the text in the Notes app and use
**Insert → Add Link (⌘K)**.

### 6. JXA-specific gotchas

JXA (JavaScript for Automation) has several behaviours that surprise
developers coming from Node.js:

- **`Application('Notes').quit()`** closes the Notes UI for the user. This
  is almost never intended in a background automation script. Flag it.
- **`app.notes()` vs `app.notes`** — calling notes as a method vs accessing
  it as a property behaves differently depending on context. If a script
  works intermittently, this is a common cause.
- **Serialisation:** JXA objects are not plain JS objects. Attempting to
  `JSON.stringify()` a Notes object directly throws. The correct pattern is
  to extract properties explicitly:
  ```javascript
  const note = app.notes[0];
  const title = note.name(); // call as method to get value
  ```
  Flag any `JSON.stringify(notesObject)` without explicit property extraction.

---

## Review Output Format

Produce a structured review with one section per area. For each finding,
cite the approximate line number and explain the risk. Close with a
**verdict** and a prioritised fix list.

```
## AppleScript Review

Script: <filename or description>
Reviewed: <date>

### 0. Note iteration pattern
<findings — or N/A if script does not iterate notes>

### 1. Error handling
<findings — cite line numbers>
— or —
No issues. All try/on error blocks use the named form.

### 2. Folder path construction
<findings>
— or —
No issues. All folder references include explicit account.

### 3. Iteration and timing
<findings>
— or —
No issues.

### 4. String construction traps
<findings — or N/A if no string concatenation>

### 5. set body limitations
<findings — or N/A if script does not write note bodies>

### 6. JXA-specific issues
<findings — or N/A if script is classic AppleScript>

### Verdict
<one of: LOOKS GOOD / NEEDS FIXES / SIGNIFICANT ISSUES>

### Fix priority
1. <highest priority fix>
2. <next fix>
...
```

Use **LOOKS GOOD** when all areas are clean or findings are cosmetic.
Use **NEEDS FIXES** when there are correctness issues that will cause
failures in real conditions (wrong account, large library, nested folders,
Sequoia iteration pattern, string traps).
Use **SIGNIFICANT ISSUES** when error handling is absent across the whole
script, or when the script would destroy or corrupt data under failure.

---

## Tips

- Read the whole script before flagging anything — sometimes a bare
  `on error` wraps a section intentionally, with a comment explaining why.
  Give benefit of the doubt when intent is clear.
- The command injection risk (interpolating user input into `osascript`
  shell calls) is a **security issue**, not an AppleScript correctness
  issue. Mention it if present, but it belongs in the mcp-audit or
  python-review lens, not this one.
- Notes AppleScript is case-insensitive for keywords but the object model
  is case-sensitive for names. `folder "inbox"` and `folder "Inbox"` are
  different if the folder is named "Inbox".
- If the script targets a specific account name, note that account names
  are user-configurable — a script hardcoded to `account "iCloud"` will
  fail for a user whose account is named "jason@icloud.com". Flag hardcoded
  account names if the project intends to be portable.
