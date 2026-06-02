-- list-folders.applescript
-- Returns Apple Notes top-level folder names, one per line. Used by notes setup.
-- Optionally filtered to a specific account via /tmp/notes_setup_account.tmp
-- Does not read note content; only accesses folder metadata.
tell application "Notes"
    set accountFilter to do shell script "cat /tmp/notes_setup_account.tmp 2>/dev/null || true"
    set output to ""
    repeat with acct in accounts
        if accountFilter is "" or name of acct is accountFilter then
            set allFolders to folders of acct

            -- Build the set of subfolder names: any folder whose name appears here is NOT top-level.
            set subNames to {}
            repeat with f in allFolders
                try
                    repeat with sub in folders of f
                        set end of subNames to name of sub
                    end repeat
                end try
            end repeat

            -- Include only top-level folders, skipping Recently Deleted.
            repeat with f in allFolders
                set fName to name of f
                if fName is not "Recently Deleted" then
                    set isChild to false
                    repeat with sn in subNames
                        if (contents of sn) is fName then
                            set isChild to true
                            exit repeat
                        end if
                    end repeat
                    if not isChild then
                        set output to output & fName & linefeed
                    end if
                end if
            end repeat
        end if
    end repeat
    return output
end tell
