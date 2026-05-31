(*
  apply-proposal.applescript
  Reads an approved proposal JSON and moves notes in Apple Notes.
  Creates nested folders as needed, up to Apple Notes' maximum depth.

  Usage:
    osascript scripts/execute/apply-proposal.applescript [--dry-run] [--container <name>] <proposal.json>

  Only the 'moves' array in the proposal is processed.
  'needs_review' and 'no_change' entries are ignored.

  When --container is given, all folders are created/found inside that
  top-level container folder (container + proposed path components).
*)

on run argv
	-- ── Parse arguments ─────────────────────────────────────────────────────

	set dryRun to false
	set containerName to ""
	set proposalFile to ""
	set skipNext to false

	repeat with i from 1 to count of argv
		if skipNext then
			set skipNext to false
		else
			set argStr to item i of argv as string
			if argStr is "--dry-run" then
				set dryRun to true
			else if argStr is "--container" then
				if i < count of argv then
					set containerName to item (i + 1) of argv as string
					set skipNext to true
				end if
			else if argStr is not "" then
				set proposalFile to argStr
			end if
		end if
	end repeat

	if proposalFile is "" then
		error "Usage: osascript apply-proposal.applescript [--dry-run] <proposal.json>"
	end if

	-- Resolve to absolute path (skip if already absolute)
	if proposalFile does not start with "/" then
		set proposalFile to do shell script "cd " & quoted form of (do shell script "dirname " & quoted form of proposalFile) & " && pwd" & "/" & do shell script "basename " & quoted form of proposalFile
	end if

	-- Verify file exists
	try
		do shell script "test -f " & quoted form of proposalFile
	on error
		error "Proposal file not found: " & proposalFile
	end try

	-- ── Parse JSON via Python ────────────────────────────────────────────────
	-- Emit one tab-separated line per move:
	--   id \t title \t current_folder \t proposed_folder_path

	set pyParse to "import json,sys
with open(sys.argv[1]) as f:
    p=json.load(f)
for m in p.get('moves',[]):
    fp=m.get('proposed_folder_path','')
    if not fp:
        pf=m.get('proposed_folder','')
        ps=m.get('proposed_subfolder') or ''
        fp=pf+'/'+ps if ps else pf
    row=[m.get('id',''),m.get('title',''),m.get('current_folder',''),fp]
    print('\t'.join(str(v).replace('\t',' ') for v in row))"

	set moveData to do shell script "python3 -c " & quoted form of pyParse & " " & quoted form of proposalFile

	if dryRun then
		log "Dry run — no changes will be made to Apple Notes."
		log ""
	end if

	-- ── Process moves ────────────────────────────────────────────────────────

	set moveCount to 0
	set skipCount to 0
	set errorCount to 0

	repeat with moveLine in paragraphs of moveData
		set lineStr to moveLine as string
		if lineStr is "" then
			-- skip blank lines
		else
			set AppleScript's text item delimiters to tab
			set fields to text items of lineStr
			set AppleScript's text item delimiters to ""

			if (count fields) < 4 then
				set skipCount to skipCount + 1
			else
				set noteId to item 1 of fields
				set noteTitle to item 2 of fields
				set currentFolder to item 3 of fields
				set proposedPath to item 4 of fields

				-- Build display path for logging
				set displayPath to proposedPath
				if containerName is not "" then
					set displayPath to containerName & "/" & proposedPath
				end if

				if dryRun then
					log "[DRY RUN] \"" & noteTitle & "\" (" & currentFolder & ") → " & displayPath
					set moveCount to moveCount + 1
				else
					try
						tell application "Notes"
							-- Find note by ID; fall back to title in current folder
							set targetNote to missing value

							try
								set matches to (every note whose id is noteId)
								if (count matches) > 0 then set targetNote to item 1 of matches
							end try

							if targetNote is missing value then
								try
									if currentFolder is not "" then
										set matches to (every note of folder currentFolder whose name is noteTitle)
										if (count matches) = 1 then
											set targetNote to item 1 of matches
										else if (count matches) > 1 then
											log "[AMBIGUOUS] \"" & noteTitle & "\": " & (count matches) & " notes match in folder \"" & currentFolder & "\" — skipping to avoid wrong move"
											set skipCount to skipCount + 1
										end if
									end if
								end try
							end if

							-- Broadest fallback: search all notes by title.
							-- Needed when current_folder is empty (note was at account root)
							-- or when the folder no longer exists after a previous move run.
							if targetNote is missing value then
								try
									set matches to (every note whose name is noteTitle)
									if (count matches) = 1 then
										set targetNote to item 1 of matches
									else if (count matches) > 1 then
										log "[AMBIGUOUS] \"" & noteTitle & "\": " & (count matches) & " notes with this title exist — skipping to avoid wrong move"
										set skipCount to skipCount + 1
									end if
								end try
							end if

							if targetNote is missing value then
								log "[SKIP]  Not found: \"" & noteTitle & "\""
								set skipCount to skipCount + 1
							else
								-- Walk up the container chain to find the account.
								-- Handles notes at any depth (root, 1 folder, or already in a subfolder).
								set noteAccount to container of targetNote
								repeat while class of noteAccount is not account
									set noteAccount to container of noteAccount
								end repeat

								-- Split proposed path into components and find/create the folder hierarchy
								set AppleScript's text item delimiters to "/"
								set pathParts to text items of proposedPath
								set AppleScript's text item delimiters to ""

								set targetFolder to my findOrCreateFolder(noteAccount, containerName, pathParts)
								move targetNote to targetFolder

								log "[MOVED] \"" & noteTitle & "\" → " & displayPath
								set moveCount to moveCount + 1
							end if
						end tell
					on error errMsg
						log "[ERROR] \"" & noteTitle & "\": " & errMsg
						set errorCount to errorCount + 1
					end try
				end if
			end if
		end if
	end repeat

	-- ── Summary ──────────────────────────────────────────────────────────────

	log ""
	if dryRun then
		log "Dry run complete: " & moveCount & " moves previewed."
	else
		log "Done: " & moveCount & " moved, " & skipCount & " skipped, " & errorCount & " errors."
	end if
end run


-- ── findOrCreateFolder ───────────────────────────────────────────────────────
-- Recursively find or create each folder component under the account (and
-- optional container). Supports paths of 1–5 components (Apple Notes maximum).

on findOrCreateFolder(noteAccount, containerName, pathComponents)
	if containerName is not "" then
		tell application "Notes"
			if not (exists folder containerName of noteAccount) then
				make new folder with properties {name: containerName} at noteAccount
			end if
		end tell
		set currentParent to folder containerName of noteAccount
	else
		set currentParent to noteAccount
	end if

	tell application "Notes"
		repeat with componentName in pathComponents
			set cStr to componentName as string
			if cStr is not "" then
				if not (exists folder cStr of currentParent) then
					make new folder at currentParent with properties {name: cStr}
				end if
				set currentParent to folder cStr of currentParent
			end if
		end repeat
	end tell

	return currentParent
end findOrCreateFolder
