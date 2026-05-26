(*
  apply-proposal.applescript
  Reads an approved proposal JSON and moves notes in Apple Notes.

  Usage:
    osascript scripts/execute/apply-proposal.applescript [--dry-run] <proposal.json>

  Only the 'moves' array in the proposal is processed.
  'needs_review' and 'no_change' entries are ignored.
*)

on run argv
	-- ── Parse arguments ─────────────────────────────────────────────────────

	set dryRun to false
	set proposalFile to ""

	repeat with arg in argv
		set argStr to arg as string
		if argStr is "--dry-run" then
			set dryRun to true
		else if argStr is not "" then
			set proposalFile to argStr
		end if
	end repeat

	if proposalFile is "" then
		error "Usage: osascript apply-proposal.applescript [--dry-run] <proposal.json>"
	end if

	-- Resolve to absolute path
	set proposalFile to do shell script "cd " & quoted form of (do shell script "dirname " & quoted form of proposalFile) & " && pwd"  & "/" & do shell script "basename " & quoted form of proposalFile

	-- Verify file exists
	try
		do shell script "test -f " & quoted form of proposalFile
	on error
		error "Proposal file not found: " & proposalFile
	end try

	-- ── Parse JSON via Python ────────────────────────────────────────────────
	-- Emit one tab-separated line per move: id \t title \t current_folder \t proposed_folder

	set pyParse to "import json,sys
with open(sys.argv[1]) as f:
    p=json.load(f)
for m in p.get('moves',[]):
    row=[m.get('id',''),m.get('title',''),m.get('current_folder',''),m.get('proposed_folder','')]
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
				set targetFolder to item 4 of fields

				if dryRun then
					log "[DRY RUN] \"" & noteTitle & "\" → " & targetFolder
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
								-- Move within the same account as the note
								set noteAccount to container of (container of targetNote)

								if not (exists folder targetFolder of noteAccount) then
									make new folder with properties {name: targetFolder} at noteAccount
								end if

								move targetNote to folder targetFolder of noteAccount
								log "[MOVED] \"" & noteTitle & "\" → " & targetFolder
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
