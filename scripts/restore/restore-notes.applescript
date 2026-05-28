(*
  restore-notes.applescript
  Creates notes from a restore JSON file. Used to recover notes that were
  lost during apply operations (e.g. iCloud conflict resolution deletions).

  Usage:
    osascript scripts/restore/restore-notes.applescript [--dry-run] [--container <name>] <restore.json>

  The restore JSON is an array of objects:
    [{"title": "...", "body": "...", "folder": "...", "subfolder": "..."}, ...]

  folder    — top-level category (e.g. "Areas"); empty string = account root
  subfolder — optional subfolder within folder (e.g. "Travel"); empty = folder only

  When --container is given, folders are created inside that container folder.

  Each note is only created if no note with the same title already exists in the
  target folder — existing notes are never overwritten.

  Output (stderr/log):
    [CREATED] "<title>" → <path>
    [EXISTS]  "<title>" → <path>  (skipped, note already present)
    [DRY RUN] "<title>" → <path>
  Final line: summary counts.
*)

on run argv
	-- ── Parse arguments ─────────────────────────────────────────────────────

	set dryRun to false
	set containerName to ""
	set restoreFile to ""
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
				set restoreFile to argStr
			end if
		end if
	end repeat

	if restoreFile is "" then
		error "Usage: restore-notes.applescript [--dry-run] [--container <name>] <restore.json>"
	end if

	-- ── Parse restore JSON via Python ────────────────────────────────────────
	-- Use ASCII 30 (record sep) and 31 (field sep) so multi-line bodies are safe.

	set pyParse to "import json,sys
FS=chr(31)
RS=chr(30)
with open(sys.argv[1]) as f:
    entries=json.load(f)
records=[]
for e in entries:
    fields=[e.get('title',''),e.get('body',''),e.get('folder',''),e.get('subfolder') or '']
    records.append(FS.join(str(v) for v in fields))
sys.stdout.write(RS.join(records))"

	set restoreData to do shell script "python3 -c " & quoted form of pyParse & " " & quoted form of restoreFile

	-- Split into records on ASCII 30, then fields on ASCII 31
	set AppleScript's text item delimiters to character id 30
	set restoreRecords to text items of restoreData
	set AppleScript's text item delimiters to ""

	-- ── Process entries ──────────────────────────────────────────────────────

	set createdCount to 0
	set existsCount to 0
	set errorCount to 0

	repeat with oneRecord in restoreRecords
		set recStr to oneRecord as string
		if recStr is not "" then
			set AppleScript's text item delimiters to character id 31
			set fields to text items of recStr
			set AppleScript's text item delimiters to ""

			if (count fields) >= 3 then
				set noteTitle to item 1 of fields
				set noteBody to item 2 of fields
				set folderName to item 3 of fields
				set subfolderName to ""
				if (count fields) >= 4 then set subfolderName to item 4 of fields

				-- Build display path for logging
				set displayPath to folderName
				if containerName is not "" then
					set displayPath to containerName & "/" & displayPath
				end if
				if subfolderName is not "" then
					set displayPath to displayPath & "/" & subfolderName
				end if

				if dryRun then
					log "[DRY RUN] \"" & noteTitle & "\" → " & displayPath
					set createdCount to createdCount + 1
				else
					try
						tell application "Notes"
							-- Locate iCloud account
							set targetAcct to missing value
							repeat with a in accounts
								if name of a is "iCloud" then
									set targetAcct to a
									exit repeat
								end if
							end repeat
							if targetAcct is missing value then set targetAcct to item 1 of accounts

							-- Resolve (or create) target folder
							set targetFolder to missing value

							if folderName is not "" then
								if containerName is not "" then
									if not (exists folder containerName of targetAcct) then
										make new folder with properties {name: containerName} at targetAcct
									end if
									if not (exists folder folderName of folder containerName of targetAcct) then
										make new folder at folder containerName of targetAcct with properties {name: folderName}
									end if
									if subfolderName is not "" then
										if not (exists folder subfolderName of folder folderName of folder containerName of targetAcct) then
											make new folder at folder folderName of folder containerName of targetAcct with properties {name: subfolderName}
										end if
										set targetFolder to folder subfolderName of folder folderName of folder containerName of targetAcct
									else
										set targetFolder to folder folderName of folder containerName of targetAcct
									end if
								else
									if not (exists folder folderName of targetAcct) then
										make new folder with properties {name: folderName} at targetAcct
									end if
									if subfolderName is not "" then
										if not (exists folder subfolderName of folder folderName of targetAcct) then
											make new folder at folder folderName of targetAcct with properties {name: subfolderName}
										end if
										set targetFolder to folder subfolderName of folder folderName of targetAcct
									else
										set targetFolder to folder folderName of targetAcct
									end if
								end if
							end if

							-- Skip if a note with the same title already exists in the target
							set alreadyExists to false
							if targetFolder is not missing value then
								repeat with n in notes of targetFolder
									if name of n is noteTitle then
										set alreadyExists to true
										exit repeat
									end if
								end repeat
							end if

							if alreadyExists then
								log "[EXISTS]  \"" & noteTitle & "\" → " & displayPath
								set existsCount to existsCount + 1
							else
								if targetFolder is not missing value then
									make new note at targetFolder with properties {name: noteTitle, body: noteBody}
								else
									make new note at targetAcct with properties {name: noteTitle, body: noteBody}
								end if
								log "[CREATED] \"" & noteTitle & "\" → " & displayPath
								set createdCount to createdCount + 1
							end if
						end tell
					on error errMsg
						log "[ERROR]   \"" & noteTitle & "\": " & errMsg
						set errorCount to errorCount + 1
					end try
				end if
			end if
		end if
	end repeat

	-- ── Summary ──────────────────────────────────────────────────────────────

	log ""
	if dryRun then
		log "Dry run complete: " & createdCount & " notes would be created."
	else
		log "Done: " & createdCount & " created, " & existsCount & " already existed, " & errorCount & " errors."
	end if
end run
