-- list-accounts.applescript
-- Returns Apple Notes account names, one per line. Used by notes setup.
-- Does not read note content; only accesses account metadata.
tell application "Notes"
    set output to ""
    repeat with acct in accounts
        set output to output & (name of acct) & linefeed
    end repeat
    return output
end tell
