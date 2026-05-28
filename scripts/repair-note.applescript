(*
  repair-note.applescript
  Update the body of every note matching a given title.
  Used by repair_restored_notes.py to fix notes whose HTML body was corrupted
  during an iCloud Recently Deleted restore.

  Usage:
    osascript scripts/repair-note.applescript <title> <body>

  Returns:
    "ok:<count>"   — number of notes updated (≥1; >1 when duplicates exist)
    "error:not found" — no note with that title exists
*)

on run argv
	if (count of argv) < 2 then
		error "Usage: repair-note.applescript <title> <body>"
	end if

	set noteTitle to item 1 of argv as string
	set noteBody to item 2 of argv as string

	tell application "Notes"
		set updatedCount to 0

		repeat with acct in accounts
			repeat with f in folders of acct
				repeat with n in notes of f
					if name of n is noteTitle then
						set body of n to noteBody
						set updatedCount to updatedCount + 1
					end if
				end repeat
			end repeat
		end repeat

		if updatedCount is 0 then
			return "error:not found"
		end if
		return "ok:" & updatedCount
	end tell
end run
