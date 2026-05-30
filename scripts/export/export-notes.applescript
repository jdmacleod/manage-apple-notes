(*
  export-notes.applescript
  Exports all Apple Notes to data/exports/notes-YYYY-MM-DD.json

  Usage:
    osascript scripts/export/export-notes.applescript

  Architecture: AppleScript collects note data and writes a delimited temp
  file; Python converts it to properly-encoded UTF-8 JSON. This avoids
  AppleScript's unreliable file encoding and manual JSON-escaping limitations.

  Folder path strategy: builds paths top-down via 'folders of folder'.
  'container of folder' is not used — on macOS Sequoia it only works one level
  deep and class-of-container comparisons are unreliable. Instead, processFolder
  is called recursively with the accumulated path so every nested note gets the
  correct full slash-delimited path (e.g. "Library/Areas/Finance").
  run_export.py strips any container prefix configured in settings.
*)

-- ── Utilities ───────────────────────────────────────────────────────────────

on pad2(n)
	set ns to n as string
	if (count ns) < 2 then return "0" & ns
	return ns
end pad2

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

-- ── Script-level state (shared with processFolder handler) ───────────────────

property gNoteRecords : {}
property gExportedCount : 0
property gSkippedCount : 0
property gFieldSep : ""
property gProgressFile : ""
property gTotalCount : 0
property gCurrentAccountName : ""

-- ── Recursive folder processor ───────────────────────────────────────────────
-- Called for each top-level folder and recurses into subfolders.
-- folderPath is the slash-delimited path built top-down, e.g. "Library/Areas/Finance".
on processFolder(aFolder, folderPath)
	tell application "Notes"
		-- Collect notes in this folder
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

			-- folderName = leaf component of folderPath
			set folderName to name of aFolder

			-- One record = 10 fields joined by gFieldSep
			set end of gNoteRecords to noteId & gFieldSep & noteTitle & gFieldSep & noteBody & gFieldSep & folderName & gFieldSep & folderPath & gFieldSep & createdStr & gFieldSep & modifiedStr & gFieldSep & wordCountStr & gFieldSep & attachmentCountStr & gFieldSep & gCurrentAccountName

			set gExportedCount to gExportedCount + 1

			-- Write progress every 25 notes so Python can update the counter
			if (gExportedCount mod 25) = 0 then
				tell current application
					do shell script "echo '" & gExportedCount & "/" & gTotalCount & "' > " & quoted form of gProgressFile
				end tell
			end if
		end repeat

		-- Recurse into subfolders, extending the path
		try
			repeat with subFolder in folders of aFolder
				set subName to name of subFolder
				my processFolder(subFolder, folderPath & "/" & subName)
			end repeat
		end try
	end tell
end processFolder

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

-- Read primary account filter written by run_export.py before launching this script.
-- Empty string means "export all accounts".
set primaryAccountFilter to do shell script "cat /tmp/notes_export_account.tmp 2>/dev/null || true"

-- ── Pass 1: count notes (fast — no body access) ──────────────────────────────

set totalCount to 0
tell application "Notes"
	repeat with acct in accounts
		if primaryAccountFilter is "" or name of acct is primaryAccountFilter then
			repeat with aFolder in folders of acct
				if name of aFolder is not "Recently Deleted" then
					set totalCount to totalCount + (count notes of aFolder)
				end if
			end repeat
		end if
	end repeat
end tell

-- Initialise progress file so Python can show "[000/NNN]" immediately
do shell script "echo '0/" & totalCount & "' > " & quoted form of progressFile

-- ── Pass 2: collect notes (walk down from top-level folders) ─────────────────
-- 'folders of acct' returns all folders flat (including nested ones).
-- We identify top-level folders using a name-based approach: build the set of
-- folder names that appear as direct children of any folder; those are NOT
-- top-level. The remaining folders are top-level and we walk down from each.

set gNoteRecords to {}
set gExportedCount to 0
set gSkippedCount to 0
set gFieldSep to fieldSep
set gProgressFile to progressFile
set gTotalCount to totalCount

tell application "Notes"
	repeat with acct in accounts
		if primaryAccountFilter is "" or name of acct is primaryAccountFilter then
			set allFolders to folders of acct

			-- Build the set of subfolder names: iterate all folders and collect
			-- the names of their direct children via 'folders of folder'.
			-- Any folder whose name appears here is NOT a top-level folder.
			set subNames to {}
			repeat with f in allFolders
				try
					repeat with sub in folders of f
						set end of subNames to name of sub
					end repeat
				end try
			end repeat

			-- Walk down from each top-level folder.
			-- Skip Recently Deleted entirely (count its notes as skipped).
			set gCurrentAccountName to name of acct
			repeat with f in allFolders
				set fName to name of f
				if fName is "Recently Deleted" then
					set gSkippedCount to gSkippedCount + (count notes of f)
				else
					-- Top-level if its name is not found in the subfolder name set
					set isChild to false
					repeat with sn in subNames
						if (contents of sn) is fName then
							set isChild to true
							exit repeat
						end if
					end repeat
					if not isChild then
						my processFolder(f, fName)
					end if
				end if
			end repeat
		end if
	end repeat
end tell

do shell script "echo 'DONE:" & gExportedCount & "/" & totalCount & "' > " & quoted form of progressFile

-- ── Write temp file ─────────────────────────────────────────────────────────

set AppleScript's text item delimiters to recordSep
set rawData to gNoteRecords as text
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
    an = f[9].strip() if len(f) > 9 else ''
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
        'account_name': an,
    })
with open(sys.argv[2], 'w', encoding='utf-8') as out:
    json.dump(notes, out, indent=2, ensure_ascii=False)
import os; os.unlink(sys.argv[1])"

do shell script "python3 -c " & quoted form of pyScript & " " & quoted form of tempFile & " " & quoted form of outputFile

-- ── Summary ─────────────────────────────────────────────────────────────────

log "Exported " & gExportedCount & " notes to " & outputFile
if gSkippedCount > 0 then
	log "Skipped " & gSkippedCount & " notes in Recently Deleted."
end if
