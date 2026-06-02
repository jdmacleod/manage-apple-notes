-- list-subfolders.applescript
-- Returns subfolder names inside a named container folder, one per line.
-- Used by notes setup when the user's taxonomy lives inside a container.
-- Reads /tmp/notes_setup_account.tmp for account filter (optional)
-- Reads /tmp/notes_setup_container.tmp for the container folder name (required)
-- Does not read note content; only accesses folder metadata.
tell application "Notes"
    set accountFilter to do shell script "cat /tmp/notes_setup_account.tmp 2>/dev/null || true"
    set containerName to do shell script "cat /tmp/notes_setup_container.tmp 2>/dev/null || true"
    if containerName is "" then return ""
    set output to ""
    repeat with acct in accounts
        if accountFilter is "" or name of acct is accountFilter then
            repeat with f in folders of acct
                if name of f is containerName then
                    repeat with sub in folders of f
                        set output to output & name of sub & linefeed
                    end repeat
                    exit repeat
                end if
            end repeat
        end if
    end repeat
    return output
end tell
