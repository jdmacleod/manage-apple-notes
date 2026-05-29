(*
  export-notes.applescript
  Exports all Apple Notes to data/exports/notes-YYYY-MM-DD.json

  Usage:
    osascript scripts/export/export-notes.applescript

  Architecture: AppleScript collects note data and writes a delimited temp
  file; Python converts it to properly-encoded UTF-8 JSON. This avoids
  AppleScript's unreliable file encoding and manual JSON-escaping limitations.
*)

-- ── Utilities ───────────────────────────────────────────────────────────────

on pad2(n)
	set ns to n as string
	if (count ns) < 2 then return "0" & ns
	return ns
end pad2

-- Walk the container chain upward to build the full slash-delimited folder path.
-- Stops when the container is an account (not a folder) or on any error.
on getFullPath(aFolder)
	set folderName to name of aFolder
	try
		set parentContainer to container of aFolder
		if class of parentContainer is folder then
			return (my getFullPath(parentContainer)) & "/" & folderName
		else
			return folderName
		end if
	on error
		return folderName
	end try
end getFullPath

-- Format an AppleScript date as ISO 8601 (local time, Z suffix)
on formatISO(d)
	set y to (year of d) as string
	set mo to my pad2(month of d as integer)
	set dy to my pad2(day of d)
	set hr to my pad2(hours of d)
	set mn to my pad2(minutes of d)
	set sc to my pad2(seconds of d)
	return y & "-" & mo & "-" & dy & "T" & hr & ":" & mn & ":" & sc & "Z"
end formatISO

-- ── Setup ───────────────────────────────────────────────────────────────────

-- Locate repo root: this script lives at scripts/export/export-notes.applescript
set scriptDir to do shell script "dirname " & quoted form of (POSIX path of (path to me))
set repoRoot to do shell script "cd " & quoted form of scriptDir & " && cd ../.. && pwd"
set exportsDir to repoRoot & "/data/exports"

do shell script "mkdir -p " & quoted form of exportsDir

set outputDate to do shell script "date +%Y-%m-%d"
set outputFile to exportsDir & "/notes-" & outputDate & ".json"
set tempFile to "/tmp/notes_export_" & outputDate & ".tmp"
set progressFile to "/tmp/notes_export_progress.tmp"

-- Field/record separators: ASCII 31 (Unit Sep) and 30 (Record Sep).
-- These are non-printable control characters that will not appear in note text.
set fieldSep to character id 31
set recordSep to character id 30

-- ── Pass 1: count notes (fast — no body access) ──────────────────────────────

set totalCount to 0
tell application "Notes"
	repeat with acct in accounts
		repeat with aFolder in folders of acct
			if name of aFolder is not "Recently Deleted" then
				set totalCount to totalCount + (count notes of aFolder)
			end if
		end repeat
	end repeat
end tell

-- Initialise progress file so Python can show "[000/NNN]" immediately
do shell script "echo '0/" & totalCount & "' > " & quoted form of progressFile

-- ── Pass 2: collect notes ────────────────────────────────────────────────────
-- Iterate accounts → folders → notes so that folder context is always known
-- from the outer loop. Accessing 'container of aNote' via 'every note' returns
-- a generic 'item' reference on macOS Sequoia; iterating by folder avoids this.

set noteRecords to {}
set exportedCount to 0
set skippedCount to 0

tell application "Notes"
	repeat with acct in accounts
		repeat with aFolder in folders of acct
			set folderName to name of aFolder

			-- Skip Recently Deleted / Trash folder entirely
			if folderName is "Recently Deleted" then
				set skippedCount to skippedCount + (count notes of aFolder)
			else
				-- Build the full slash-delimited path for this folder by walking up the
				-- container chain. Wrapped in getFullPath which handles -1728 errors.
				set fullFolderPath to my getFullPath(aFolder)

				repeat with aNote in notes of aFolder
					set noteId to id of aNote

					set noteTitle to ""
					try
						set noteTitle to name of aNote
					end try

					set noteBody to ""
					try
						set noteBody to plaintext of aNote
					end try

					set createdStr to my formatISO(creation date of aNote)
					set modifiedStr to my formatISO(modification date of aNote)
					set wordCountStr to (count words of noteBody) as string

					set attachmentCountStr to "0"
					try
						set attachmentCountStr to (count attachments of aNote) as string
					end try

					-- One record = fields joined by fieldSep (9 fields)
					set end of noteRecords to noteId & fieldSep & noteTitle & fieldSep & noteBody & fieldSep & folderName & fieldSep & fullFolderPath & fieldSep & createdStr & fieldSep & modifiedStr & fieldSep & wordCountStr & fieldSep & attachmentCountStr

					set exportedCount to exportedCount + 1

					-- Write progress every 25 notes so Python can update the counter
					if (exportedCount mod 25) = 0 then
						do shell script "echo '" & exportedCount & "/" & totalCount & "' > " & quoted form of progressFile
					end if
				end repeat
			end if
		end repeat
	end repeat
end tell

do shell script "echo 'DONE:" & exportedCount & "/" & totalCount & "' > " & quoted form of progressFile

-- ── Write temp file ─────────────────────────────────────────────────────────

set AppleScript's text item delimiters to recordSep
set rawData to noteRecords as text
set AppleScript's text item delimiters to ""

set tempRef to open for access (POSIX file tempFile) with write permission
set eof of tempRef to 0
write rawData to tempRef
close access tempRef

-- ── Convert to UTF-8 JSON via Python ────────────────────────────────────────
-- Python handles all Unicode, control-character escaping, and file encoding.

set pyScript to "import sys, json
data = open(sys.argv[1], encoding='mac_roman', errors='replace').read()
notes = []
for rec in data.split(chr(30)):
    f = rec.split(chr(31))
    if len(f) < 8:
        continue
    nid, title, body, folder, folder_path = f[0], f[1], f[2], f[3], f[4]
    created, modified, wc = f[5], f[6], f[7]
    ac = f[8].strip() if len(f) > 8 else '0'
    notes.append({
        'id': nid,
        'title': title,
        'body': body,
        'folder': folder,
        'folder_path': folder_path,
        'created': created,
        'modified': modified,
        'word_count': int(wc) if wc.isdigit() else 0,
        'attachment_count': int(ac) if ac.isdigit() else 0,
    })
with open(sys.argv[2], 'w', encoding='utf-8') as out:
    json.dump(notes, out, indent=2, ensure_ascii=False)
import os; os.unlink(sys.argv[1])"

do shell script "python3 -c " & quoted form of pyScript & " " & quoted form of tempFile & " " & quoted form of outputFile

-- ── Summary ─────────────────────────────────────────────────────────────────

log "Exported " & exportedCount & " notes to " & outputFile
if skippedCount > 0 then
	log "Skipped " & skippedCount & " notes in Recently Deleted."
end if
