(*
  apply-dedup-proposal.applescript
  Reads an approved dedup proposal JSON and deletes duplicate notes in Apple Notes.

  Usage:
    osascript scripts/execute/apply-dedup-proposal.applescript [--execute] <dedup-proposal.json>

  Default is dry-run. Pass --execute to actually delete notes.
  Only processes groups with resolution: "delete". Groups marked "review" are skipped.
  Deleted notes are moved to Recently Deleted (recoverable for 30 days).
*)

on run argv
	-- ── Parse arguments ─────────────────────────────────────────────────────

	set executeMode to false
	set proposalFile to ""

	repeat with arg in argv
		set argStr to arg as string
		if argStr is "--execute" then
			set executeMode to true
		else if argStr is not "" then
			set proposalFile to argStr
		end if
	end repeat

	if proposalFile is "" then
		error "Usage: osascript apply-dedup-proposal.applescript [--execute] <dedup-proposal.json>"
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
	-- Emit one tab-separated line per deletion:
	--   group_id \t keep_id \t keep_title \t delete_id \t delete_title

	set pyParse to "import json,sys
with open(sys.argv[1]) as f:
    p=json.load(f)
for g in p.get('groups',[]):
    if g.get('resolution') != 'delete':
        continue
    keep_id = g.get('keep_id','')
    keep_title = next((n['title'] for n in g.get('notes',[]) if n['id']==keep_id),'')
    for del_id in g.get('delete_ids',[]):
        del_title = next((n['title'] for n in g.get('notes',[]) if n['id']==del_id),'')
        row = [str(g.get('group_id','')), keep_id, keep_title, del_id, del_title]
        print('\t'.join(str(v).replace('\t',' ') for v in row))"

	set deleteData to do shell script "python3 -c " & quoted form of pyParse & " " & quoted form of proposalFile

	-- Count deletions for the summary header
	set totalDeletions to 0
	repeat with deleteLine in paragraphs of deleteData
		if (deleteLine as string) is not "" then
			set totalDeletions to totalDeletions + 1
		end if
	end repeat

	if not executeMode then
		log "Dry run — no changes will be made to Apple Notes."
		log totalDeletions & " deletion(s) would be made. Pass --execute to apply."
		log ""
	else
		log "Executing: " & totalDeletions & " note(s) will be deleted."
		log "Deleted notes are moved to Recently Deleted (recoverable for 30 days)."
		log ""
	end if

	-- ── Process deletions ────────────────────────────────────────────────────

	set deleteCount to 0
	set skipCount to 0
	set errorCount to 0

	repeat with deleteLine in paragraphs of deleteData
		set lineStr to deleteLine as string
		if lineStr is "" then
			-- skip blank lines
		else
			set AppleScript's text item delimiters to tab
			set fields to text items of lineStr
			set AppleScript's text item delimiters to ""

			if (count fields) < 5 then
				set skipCount to skipCount + 1
			else
				set keepId to item 2 of fields
				set keepTitle to item 3 of fields
				set deleteId to item 4 of fields
				set deleteTitle to item 5 of fields

				if not executeMode then
					log "[DRY RUN] Delete \"" & deleteTitle & "\" (duplicate of \"" & keepTitle & "\")"
					set deleteCount to deleteCount + 1
				else
					try
						tell application "Notes"
							-- Verify the keep note exists before deleting anything
							set keepNote to missing value
							try
								set keepMatches to (every note whose id is keepId)
								if (count keepMatches) > 0 then set keepNote to item 1 of keepMatches
							end try

							if keepNote is missing value then
								log "[SKIP]  Keep note not found: \"" & keepTitle & "\" — skipping deletion of \"" & deleteTitle & "\""
								set skipCount to skipCount + 1
							else
								set deleteNote to missing value
								try
									set deleteMatches to (every note whose id is deleteId)
									if (count deleteMatches) > 0 then set deleteNote to item 1 of deleteMatches
								end try

								if deleteNote is missing value then
									log "[SKIP]  Not found: \"" & deleteTitle & "\""
									set skipCount to skipCount + 1
								else
									delete deleteNote
									log "[DELETED] \"" & deleteTitle & "\" (duplicate of \"" & keepTitle & "\")"
									set deleteCount to deleteCount + 1
								end if
							end if
						end tell
					on error errMsg
						log "[ERROR] \"" & deleteTitle & "\": " & errMsg
						set errorCount to errorCount + 1
					end try
				end if
			end if
		end if
	end repeat

	-- ── Summary ──────────────────────────────────────────────────────────────

	log ""
	if not executeMode then
		log "Dry run complete: " & deleteCount & " deletion(s) previewed."
	else
		log "Done: " & deleteCount & " deleted, " & skipCount & " skipped, " & errorCount & " errors."
		if deleteCount > 0 then
			log "Deleted notes are in Recently Deleted — recoverable for 30 days."
		end if
	end if
end run
