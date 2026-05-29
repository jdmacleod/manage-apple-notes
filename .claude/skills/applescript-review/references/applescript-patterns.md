# AppleScript Patterns Reference

---

## Note Iteration — Sequoia Trap

### Application-level `every note` — broken on Sequoia (flag this)

```applescript
-- BROKEN on macOS Sequoia: container returns generic item, not folder
set allNotes to every note of application "Notes"
repeat with aNote in allNotes
    set folderName to name of container of aNote  -- silently empty
end repeat
```

**Problem:** On Sequoia, `container of aNote` returns an `item` reference when
iterating at application level. `name of item` silently returns empty string — no
error is raised. Every note appears to have an empty folder.

### Correct pattern — accounts → folders → notes

```applescript
tell application "Notes"
    repeat with acct in accounts
        repeat with aFolder in folders of acct
            set folderName to name of aFolder
            set parentFolderName to ""
            try
                if class of container of aFolder is folder then
                    set parentFolderName to name of container of aFolder
                end if
            end try
            repeat with aNote in notes of aFolder
                -- folderName and parentFolderName are always correct here
            end repeat
        end repeat
    end repeat
end tell
```

The folder name comes from the outer loop variable, not from `container of aNote`.
This works correctly on all tested macOS versions (Sequoia 15.7.7, Tahoe 26.5).

---

## `set body` and `href` Attributes

### Links are stripped (document, don't fix)

```applescript
-- Setting HTML body with an <a href> tag:
set body of theNote to "<p><a href=\"applenotes://showNote?identifier=UUID\">Link text</a></p>"

-- Result in Notes: the text "Link text" appears underlined but NOT clickable.
-- The href attribute is silently removed. This affects ALL URL schemes:
--   applenotes://, https://, x-coredata://, notes://
```

**There is no programmatic workaround via `set body`.** Scripts that write
Hub or Home note content with `applenotes://` links should include a comment
explaining this. Creating a clickable link requires manual action in the Notes
app: select the text and use Insert → Add Link (⌘K).

---

Annotated code snippets for the `applescript-review` skill.
Each section shows the problematic pattern and the correct replacement.

---

## Error Handling

### Bare on error (flag this)

```applescript
try
    set theNote to note "My Note" of folder "Inbox" of account "iCloud"
on error
    -- silently continues — caller has no idea what went wrong
end try
```

**Problem:** No error message or number is captured. Apple Notes returns
specific, diagnosable error codes. Without them, failures are opaque.

### Named error form (correct)

```applescript
try
    set theNote to note "My Note" of folder "Inbox" of account "iCloud"
on error errMsg number errNum
    log "Notes error " & errNum & ": " & errMsg
    -- or re-raise: error errMsg number errNum
end try
```

### Key Notes error codes

| Code | Meaning | Common cause |
|------|---------|--------------|
| -1728 | Object not found | Folder or note name doesn't exist, wrong account |
| -10004 | Permission denied | User declined Automation permission for Notes |
| -600 | Application not running | Notes.app not open |
| -1700 | Type conversion error | Trying to use a list where a scalar is expected |
| -50 | Parameter error | Malformed `make new note` call |

### JXA equivalent (flag this)

```javascript
// BARE CATCH — swallows all errors
try {
    const note = Application('Notes').notes.whose({name: 'My Note'})[0];
} catch (e) {
    // silent
}
```

### JXA correct form

```javascript
try {
    const note = Application('Notes').notes.whose({name: 'My Note'})[0];
} catch (e) {
    console.log(`Notes error: ${e.message} (${e.number})`);
    throw e; // re-raise unless intentionally suppressing
}
```

---

## Folder Path Construction

### Flat lookup — ambiguous (flag this)

```applescript
-- Returns first "Projects" folder found, regardless of account
set myFolder to folder "Projects" of application "Notes"
```

```applescript
-- Also ambiguous: which account owns this folder?
tell application "Notes"
    set myFolder to folder "Work"
end tell
```

### Fully qualified — correct

```applescript
-- Explicit: iCloud account, top-level folder
set myFolder to folder "Library" of account "iCloud"

-- Nested: subfolder within top-level
set mySubfolder to folder "Work" of folder "Areas" of account "iCloud"

-- Two levels deep
set deepFolder to folder "Q3 Campaign" of folder "Projects" of account "iCloud"
```

### In a tell block

```applescript
tell application "Notes"
    -- Still needs account qualification inside tell blocks
    set myFolder to folder "Library" of account "iCloud"
    set notes in folder to every note of myFolder
end tell
```

### JXA equivalent

```javascript
const app = Application('Notes');
// Flat — ambiguous (flag this)
const folder = app.folders.whose({name: 'Projects'})[0];

// Qualified — correct
const account = app.accounts.whose({name: 'iCloud'})[0];
const folder = account.folders.whose({name: 'Library'})[0];
const subfolder = folder.folders.whose({name: 'Work'})[0];
```

---

## Iteration and Timing

### Unbounded iteration — risky on large libraries (flag if library may be large)

```applescript
-- May silently timeout on 1000+ notes; returns empty list with no error
set allNotes to every note of folder "Library" of account "iCloud"
repeat with theNote in allNotes
    -- process
end repeat
```

### Count guard before iteration

```applescript
set noteCount to count of notes of myFolder
if noteCount > 500 then
    -- use search API or chunked approach instead
    set results to notes of myFolder whose name contains searchTerm
else
    set allNotes to every note of myFolder
    repeat with theNote in allNotes
        -- process
    end repeat
end if
```

### Chunked iteration pattern (for large libraries)

```applescript
set chunkSize to 100
set totalNotes to count of notes of myFolder
set offset to 1

repeat while offset ≤ totalNotes
    set endIdx to offset + chunkSize - 1
    if endIdx > totalNotes then set endIdx to totalNotes
    set chunk to notes offset through endIdx of myFolder
    repeat with theNote in chunk
        -- process theNote
    end repeat
    set offset to offset + chunkSize
end repeat
```

### Folder creation timing — delay required (flag missing delay)

```applescript
-- BROKEN: folder may not be accessible immediately after creation
make new folder with properties {name:"New Hub"} at account "iCloud"
set newFolder to folder "New Hub" of account "iCloud"  -- may throw -1728

-- CORRECT: brief delay allows Notes to register the folder
make new folder with properties {name:"New Hub"} at account "iCloud"
delay 0.5
set newFolder to folder "New Hub" of account "iCloud"
```

---

## JXA-Specific Patterns

### Quitting Notes (almost always unintentional — flag this)

```javascript
// This closes Notes.app for the user — almost never intended
Application('Notes').quit();
```

### Property extraction before serialisation (flag direct JSON.stringify of Notes objects)

```javascript
// BROKEN: JXA proxy objects are not plain JS — this throws
const note = app.notes[0];
const json = JSON.stringify(note); // TypeError

// CORRECT: extract properties explicitly
const note = app.notes[0];
const data = {
    title: note.name(),
    body: note.body(),
    id: note.id(),
    modificationDate: note.modificationDate().toISOString()
};
const json = JSON.stringify(data);
```

### Method vs property access

```javascript
// notes() — calling as method returns a snapshot array
const notesArray = app.notes(); // array of current notes

// notes — accessing as property returns a live reference
const notesRef = app.notes; // live, re-evaluated on each access

// Both work, but behave differently in loops — use the method form
// inside loops to avoid re-evaluation overhead:
const notes = app.notes(); // snapshot once
for (const note of notes) {
    console.log(note.name());
}
```

---

## Account Name Portability

Hardcoded account names make scripts non-portable (flag in shared/public code):

```applescript
-- Fragile: only works if the user's iCloud account is named exactly "iCloud"
set myAccount to account "iCloud"
```

The portable pattern enumerates accounts and selects by type, or accepts
the account name as a parameter:

```applescript
-- Portable: find the first iCloud-type account
set targetAccount to missing value
tell application "Notes"
    repeat with acc in accounts
        if class of acc is iCloud account then
            set targetAccount to acc
            exit repeat
        end if
    end repeat
end tell

if targetAccount is missing value then
    error "No iCloud account found in Notes" number -1728
end if
```

Or, for the manage-apple-notes toolkit specifically, read the account name
from `settings.local.yaml` and inject it at runtime rather than hardcoding.
