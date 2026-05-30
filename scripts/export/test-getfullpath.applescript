-- test-getfullpath.applescript
-- Diagnostic / regression test for folder path building in export-notes.applescript.
--
-- Creates a 3-level folder structure in the default Notes account:
--
--   _GFP_L1  (top-level)
--   _GFP_L1/_GFP_L2
--   _GFP_L1/_GFP_L2/_GFP_L3  <- test note lives here
--
-- macOS Sequoia 15.x findings (updated as tests reveal more):
--   - 'container of folder' works one level, and two levels, but the class of the
--     returned object is not recognized as 'folder', breaking class-based checks.
--   - 'folders of folder' returns direct children reliably with DIRECT refs.
--   - 'folders of (enumerated ref from folders of acct)' is tested here to see
--     whether it also works or silently fails.
--   - Walk-down V4 using direct refs passes all cases.
--
-- Sections:
--   1. Verify 'folders of folder' works with both direct AND enumerated refs
--   2. Name-based top-level detection — log subNames to see if detection works
--   3. Walk-down from a NAMED folder (like 'Library') via direct lookup
--   4. Walk-down V4 with DIRECT refs (known-good baseline)
--   5. Walk-down V4 from named container (production-style, for toplevel_folder users)
--
-- Cleans up all test folders and notes when done.
-- Usage: osascript scripts/export/test-getfullpath.applescript

-- ── Helper: PASS/FAIL line ────────────────────────────────────────────────────
on check(results, label, got, expected)
	if got is expected then
		set end of results to "  PASS  " & label & ": " & got
	else
		set end of results to "  FAIL  " & label
		set end of results to "         got:      " & got
		set end of results to "         expected: " & expected
	end if
	return results
end check

-- ── Main ─────────────────────────────────────────────────────────────────────
set out to {}
set end of out to "=== getFullPath diagnostic -- macOS " & (do shell script "sw_vers -productVersion") & " ==="
set end of out to ""

tell application "Notes"
	set acct to default account

	-- ── Create test hierarchy ─────────────────────────────────────────────
	set f1 to make new folder at acct with properties {name: "_GFP_L1"}
	set f2 to make new folder at f1 with properties {name: "_GFP_L2"}
	set f3 to make new folder at f2 with properties {name: "_GFP_L3"}
	set testNote to make new note at f3 with properties {name: "_GFP_Note", body: "test"}
	set end of out to "Created: _GFP_L1/_GFP_L2/_GFP_L3 + note"
	set end of out to ""

	-- ── 1. Does 'folders of folder' work with enumerated refs? ───────────
	-- We know it works with direct refs (f1, f2, f3).
	-- Here we get an enumerated ref from 'folders of acct' and test 'folders of' on it.
	set end of out to "--- 1. 'folders of folder' with ENUMERATED refs ---"
	set allFolderRefs to folders of acct

	-- Find the enumerated ref for _GFP_L1
	set enumL1 to missing value
	repeat with aF in allFolderRefs
		if name of aF is "_GFP_L1" then
			set enumL1 to aF
			exit repeat
		end if
	end repeat

	if enumL1 is missing value then
		set end of out to "  ERROR: could not find _GFP_L1 in folders of acct"
	else
		-- Test 'folders of enumL1'
		try
			set subList to folders of enumL1
			set subCount to count of subList
			set subNameList to {}
			repeat with s in subList
				set end of subNameList to name of s
			end repeat
			set AppleScript's text item delimiters to ", "
			set end of out to "  folders of enumL1: " & subCount & " items {" & (subNameList as string) & "} (expected: 1 item {_GFP_L2})"
			set AppleScript's text item delimiters to ""
		on error errMsg
			set end of out to "  folders of enumL1: ERROR -- " & errMsg
		end try

		-- Now test iteration (repeat with sub in folders of enumL1)
		set iterNames to {}
		set iterErrors to {}
		try
			repeat with sub in folders of enumL1
				try
					set end of iterNames to name of sub
				on error e2
					set end of iterErrors to "name error: " & e2
				end try
			end repeat
		on error errMsg
			set end of iterErrors to "iteration error: " & errMsg
		end try
		set AppleScript's text item delimiters to ", "
		set end of out to "  iterate folders of enumL1: names={" & (iterNames as string) & "} errors={" & (iterErrors as string) & "}"
		set AppleScript's text item delimiters to ""
	end if
	set end of out to ""

	-- ── 2. Name-based top-level detection — explicit subNames logging ─────
	set end of out to "--- 2. Name-based top-level detection (explicit logging) ---"

	-- Pass 1a: using stored allFolderRefs (might have reference issues)
	set subNamesStored to {}
	set subErrorsStored to {}
	repeat with aF in allFolderRefs
		try
			set subs to folders of aF
			repeat with sub in subs
				set end of subNamesStored to name of sub
			end repeat
		on error e
			set end of subErrorsStored to (name of aF) & ": " & e
		end try
	end repeat
	set AppleScript's text item delimiters to ", "
	set end of out to "  subNames (stored allFolderRefs): {" & (subNamesStored as string) & "}"
	set end of out to "  errors: {" & (subErrorsStored as string) & "}"
	set AppleScript's text item delimiters to ""

	-- Pass 1b: using 'folders of acct' directly in-loop (avoids stored ref issues)
	set subNamesDirect to {}
	set subErrorsDirect to {}
	repeat with aF in folders of acct
		try
			set subs to folders of aF
			repeat with sub in subs
				set end of subNamesDirect to name of sub
			end repeat
		on error e
			set end of subErrorsDirect to (name of aF) & ": " & e
		end try
	end repeat
	set AppleScript's text item delimiters to ", "
	set end of out to "  subNames (direct loop):         {" & (subNamesDirect as string) & "}"
	set end of out to "  errors: {" & (subErrorsDirect as string) & "}"
	set end of out to "  (both should show: {_GFP_L2, _GFP_L3})"
	set AppleScript's text item delimiters to ""
	set end of out to ""

	-- ── 3. Walk-down from named container (production-style) ──────────────
	-- For users with 'toplevel_folder.enabled: true', the container name is known.
	-- Find it by name in the flat list, then walk down from it.
	-- This avoids all top-level detection logic.
	set end of out to "--- 3. Walk-down from named container '_GFP_L1' ---"
	set containerRef to missing value
	repeat with aF in folders of acct
		if name of aF is "_GFP_L1" then
			set containerRef to aF
			exit repeat
		end if
	end repeat

	if containerRef is missing value then
		set end of out to "  ERROR: could not find _GFP_L1"
	else
		set containerResults to {}
		set cPath to name of containerRef
		set end of containerResults to {nm: "_GFP_L1", pth: cPath}
		repeat with sub1 in folders of containerRef
			set s1Path to cPath & "/" & name of sub1
			set end of containerResults to {nm: name of sub1, pth: s1Path}
			repeat with sub2 in folders of sub1
				set s2Path to s1Path & "/" & name of sub2
				set end of containerResults to {nm: name of sub2, pth: s2Path}
			end repeat
		end repeat
		repeat with r in containerResults
			set rNm to nm of r
			set rPth to pth of r
			if rNm is "_GFP_L1" then
				set out to my check(out, "L1", rPth, "_GFP_L1")
			else if rNm is "_GFP_L2" then
				set out to my check(out, "L2", rPth, "_GFP_L1/_GFP_L2")
			else if rNm is "_GFP_L3" then
				set out to my check(out, "L3", rPth, "_GFP_L1/_GFP_L2/_GFP_L3")
			end if
		end repeat
	end if
	set end of out to ""

	-- ── 4. Walk-down V4 — DIRECT refs (known-good baseline) ──────────────
	set end of out to "--- 4. Walk-down V4 DIRECT refs (baseline) ---"
	set p1 to name of f1
	set out to my check(out, "L1", p1, "_GFP_L1")
	repeat with sub1 in folders of f1
		set p2 to p1 & "/" & name of sub1
		set out to my check(out, "L2", p2, "_GFP_L1/_GFP_L2")
		repeat with sub2 in folders of sub1
			set p3 to p2 & "/" & name of sub2
			set out to my check(out, "L3", p3, "_GFP_L1/_GFP_L2/_GFP_L3")
		end repeat
	end repeat
	set end of out to ""

	-- ── Cleanup ───────────────────────────────────────────────────────────
	set end of out to "Cleaning up..."
	delete testNote
	delete f3
	delete f2
	delete f1
	set end of out to "Done."
end tell

set AppleScript's text item delimiters to linefeed
return out as string
