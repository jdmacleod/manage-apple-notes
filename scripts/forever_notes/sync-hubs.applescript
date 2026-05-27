(*
  sync-hubs.applescript
  Create or update a single note in Apple Notes by title.
  Called by sync_hubs.py for each Hub note and for ✱ Home.

  Usage (called by Python):
    osascript scripts/forever_notes/sync-hubs.applescript <title> <body> <folder> [<container>]

  Arguments:
    title      — Note title to find or create
    body       — Full body text to set
    folder     — Folder name to create the note in (empty string = iCloud root)
    container  — Optional top-level container folder name (empty string = disabled)

  When container is provided, the folder is looked up inside the container
  rather than at the account root.

  Output (stdout):
    "created" if a new note was made
    "updated" if an existing note was found and updated
*)

on run argv
	if (count of argv) < 3 then
		error "Usage: sync-hubs.applescript <title> <body> <folder> [<container>]"
	end if

	set noteTitle to item 1 of argv as string
	set noteBody to item 2 of argv as string
	set folderName to item 3 of argv as string
	set containerName to ""
	if (count of argv) >= 4 then
		set containerName to item 4 of argv as string
	end if

	tell application "Notes"
		-- Locate or create the target note
		set targetNote to missing value
		set targetFolder to missing value

		-- Find the folder, optionally inside a container
		if folderName is not "" then
			repeat with acct in accounts
				if containerName is not "" then
					-- Look for folder inside the container
					if exists folder containerName of acct then
						repeat with f in folders of folder containerName of acct
							if name of f is folderName then
								set targetFolder to f
								exit repeat
							end if
						end repeat
					end if
				else
					-- Look for folder at account root
					repeat with f in folders of acct
						if name of f is folderName then
							set targetFolder to f
							exit repeat
						end if
					end repeat
				end if
				if targetFolder is not missing value then exit repeat
			end repeat
		end if

		-- Search for an existing note with this title
		if targetFolder is not missing value then
			set allNotes to notes of targetFolder
		else
			set allNotes to every note
		end if

		repeat with n in allNotes
			if name of n is noteTitle then
				set targetNote to n
				exit repeat
			end if
		end repeat

		if targetNote is not missing value then
			-- Update existing note
			set body of targetNote to noteBody
			return "updated"
		else
			-- Create new note
			if targetFolder is not missing value then
				make new note at targetFolder with properties {name: noteTitle, body: noteBody}
			else
				make new note with properties {name: noteTitle, body: noteBody}
			end if
			return "created"
		end if
	end tell
end run
