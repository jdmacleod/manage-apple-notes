(*
  sync-hubs.applescript
  Create or update a single note in Apple Notes by title.
  Called by sync_hubs.py for each Hub note and for ✱ Home.

  Usage (called by Python):
    osascript scripts/forever_notes/sync-hubs.applescript <title> <body> <folder> [<container>]

  Arguments:
    title      — Note title to find or create
    body       — Full body HTML to set
    folder     — Subfolder name to create the note in (empty string = use container root)
    container  — Optional top-level container folder name (empty string = disabled)

  Folder resolution rules:
    - container set, folder empty or folder == container  → place in container itself
    - container set, folder is a different name           → place in named subfolder of container
    - container empty, folder set                         → place in named folder at account root
    - both empty                                          → place at iCloud account root

  Output (stdout):
    "created:<localId>" if a new note was made
    "updated:<localId>" if an existing note was found and updated
    where <localId> is the last path component of the note's x-coredata:// URI
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
		set targetNote to missing value
		set targetFolder to missing value

		-- Resolve the target folder
		if containerName is not "" and (folderName is "" or folderName is containerName) then
			-- Place directly in the container folder itself
			repeat with acct in accounts
				if exists folder containerName of acct then
					set targetFolder to folder containerName of acct
					exit repeat
				end if
			end repeat
		else if folderName is not "" then
			-- Place in a named folder, optionally inside a container
			repeat with acct in accounts
				if containerName is not "" then
					if exists folder containerName of acct then
						repeat with f in folders of folder containerName of acct
							if name of f is folderName then
								set targetFolder to f
								exit repeat
							end if
						end repeat
					end if
				else
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

		-- Search for an existing note with this title in the target folder
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

		-- Record whether the note already existed before we write
		set wasExisting to (targetNote is not missing value)

		-- Always use `set body` (not creation properties) so HTML is rendered correctly
		if wasExisting then
			set body of targetNote to noteBody
		else
			if targetFolder is not missing value then
				set targetNote to make new note at targetFolder with properties {name: noteTitle}
			else
				set targetNote to make new note with properties {name: noteTitle}
			end if
			set body of targetNote to noteBody
		end if

		-- Extract local identifier from x-coredata:// URI (last path component)
		set noteFullId to id of targetNote
		set AppleScript's text item delimiters to "/"
		set localId to item -1 of (every text item of noteFullId)
		set AppleScript's text item delimiters to ""

		if wasExisting then
			return "updated:" & localId
		else
			return "created:" & localId
		end if
	end tell
end run
