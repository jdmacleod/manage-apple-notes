(*
  apply-proposal.applescript
  Reads an approved proposal JSON and moves notes in Apple Notes.
  Creates nested subfolders as needed.

  Usage:
    osascript scripts/execute/apply-proposal.applescript [--dry-run] [--container <name>] <proposal.json>

  Only the 'moves' array in the proposal is processed.
  'needs_review' and 'no_change' entries are ignored.

  When --container is given, all folders are created/found inside that
  top-level container folder (3-level nesting: container → folder → subfolder).
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
	--   id \t title \t current_folder \t proposed_folder \t proposed_subfolder

	set pyParse to "import json,sys
with open(sys.argv[1]) as f:
    p=json.load(f)
for m in p.get('moves',[]):
    row=[
        m.get('id',''),
        m.get('title',''),
        m.get('current_folder',''),
        m.get('proposed_folder',''),
        m.get('proposed_subfolder') or '',
    ]
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
				set targetFolderName to item 4 of fields
				set subfolderName to ""
				if (count fields) >= 5 then
					set subfolderName to item 5 of fields
				end if

				-- Build display path for logging
				set displayPath to targetFolderName
				if containerName is not "" then
					set displayPath to containerName & "/" & targetFolderName
				end if
				if subfolderName is not "" then
					set displayPath to displayPath & "/" & subfolderName
				end if

				if dryRun then
					log "[DRY RUN] \"" & noteTitle & "\" → " & displayPath
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
									set matches to (every note of folder currentFolder whose name is noteTitle)
									if (count matches) > 0 then set targetNote to item 1 of matches
								end try
							end if

							if targetNote is missing value then
								log "[SKIP]  Not found: \"" & noteTitle & "\""
								set skipCount to skipCount + 1
							else
								set noteAccount to container of (container of targetNote)

								if containerName is not "" then
									-- ── 3-level: container → folder → subfolder ──────────
									if not (exists folder containerName of noteAccount) then
										make new folder with properties {name: containerName} at noteAccount
									end if
									if not (exists folder targetFolderName of folder containerName of noteAccount) then
										make new folder at folder containerName of noteAccount with properties {name: targetFolderName}
									end if
									if subfolderName is not "" then
										if not (exists folder subfolderName of folder targetFolderName of folder containerName of noteAccount) then
											make new folder at folder targetFolderName of folder containerName of noteAccount with properties {name: subfolderName}
										end if
										move targetNote to folder subfolderName of folder targetFolderName of folder containerName of noteAccount
									else
										move targetNote to folder targetFolderName of folder containerName of noteAccount
									end if
								else
									-- ── 2-level: folder → subfolder (no container) ───────
									if not (exists folder targetFolderName of noteAccount) then
										make new folder with properties {name: targetFolderName} at noteAccount
									end if
									if subfolderName is not "" then
										if not (exists folder subfolderName of folder targetFolderName of noteAccount) then
											make new folder at folder targetFolderName of noteAccount with properties {name: subfolderName}
										end if
										move targetNote to folder subfolderName of folder targetFolderName of noteAccount
									else
										move targetNote to folder targetFolderName of noteAccount
									end if
								end if

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
