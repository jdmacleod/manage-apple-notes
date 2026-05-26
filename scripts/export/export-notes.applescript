(*
  export-notes.applescript
  Exports all Apple Notes to data/exports/notes-YYYY-MM-DD.json

  Usage:
    osascript scripts/export/export-notes.applescript
*)

-- ── Utilities ───────────────────────────────────────────────────────────────

on replaceText(theString, findStr, replaceStr)
	set AppleScript's text item delimiters to findStr
	set theItems to text items of theString
	set AppleScript's text item delimiters to replaceStr
	set theResult to theItems as text
	set AppleScript's text item delimiters to ""
	return theResult
end replaceText

-- Escape a value for embedding in a JSON string (does not add surrounding quotes)
on escapeJSON(val)
	set val to my replaceText(val, "\\", "\\\\")
	set val to my replaceText(val, "\"", "\\\"")
	set val to my replaceText(val, return, "\\n")
	set val to my replaceText(val, linefeed, "\\n")
	set val to my replaceText(val, tab, "\\t")
	return val
end escapeJSON

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

-- ── Setup ───────────────────────────────────────────────────────────────────

-- Locate repo root: this script lives at scripts/export/export-notes.applescript
set scriptDir to do shell script "dirname " & quoted form of (POSIX path of (path to me))
set repoRoot to do shell script "cd " & quoted form of scriptDir & " && cd ../.. && pwd"
set exportsDir to repoRoot & "/data/exports"

do shell script "mkdir -p " & quoted form of exportsDir

set outputDate to do shell script "date +%Y-%m-%d"
set outputFile to exportsDir & "/notes-" & outputDate & ".json"

-- ── Collect notes ───────────────────────────────────────────────────────────

set jsonObjects to {}
set exportedCount to 0
set skippedCount to 0

tell application "Notes"
	set allNotes to every note

	repeat with aNote in allNotes
		set folderName to ""
		try
			set folderName to name of container of aNote
		end try

		-- Skip Recently Deleted / Trash
		if folderName is "Recently Deleted" then
			set skippedCount to skippedCount + 1
		else
			set noteId to id of aNote
			set noteTitle to ""
			try
				set noteTitle to name of aNote
			end try

			set noteBody to ""
			try
				set noteBody to plaintext of aNote
			end try

			set noteCreated to my formatISO(creation date of aNote)
			set noteModified to my formatISO(modification date of aNote)
			set wordCount to count words of noteBody

			set jsonObj to "{" & ¬
				"\"id\": \"" & my escapeJSON(noteId) & "\", " & ¬
				"\"title\": \"" & my escapeJSON(noteTitle) & "\", " & ¬
				"\"body\": \"" & my escapeJSON(noteBody) & "\", " & ¬
				"\"folder\": \"" & my escapeJSON(folderName) & "\", " & ¬
				"\"created\": \"" & noteCreated & "\", " & ¬
				"\"modified\": \"" & noteModified & "\", " & ¬
				"\"word_count\": " & wordCount & ¬
				"}"

			set end of jsonObjects to jsonObj
			set exportedCount to exportedCount + 1
		end if
	end repeat
end tell

-- ── Write output ────────────────────────────────────────────────────────────

set AppleScript's text item delimiters to "," & linefeed
set jsonBody to jsonObjects as text
set AppleScript's text item delimiters to ""

set jsonContent to "[" & linefeed & jsonBody & linefeed & "]"

-- Write via file I/O
set outputPosix to POSIX file outputFile
set fh to open for access outputPosix with write permission
set eof of fh to 0
write jsonContent to fh
close access fh

-- ── Summary ─────────────────────────────────────────────────────────────────

log "Exported " & exportedCount & " notes to " & outputFile
if skippedCount > 0 then
	log "Skipped " & skippedCount & " notes in Recently Deleted."
end if
