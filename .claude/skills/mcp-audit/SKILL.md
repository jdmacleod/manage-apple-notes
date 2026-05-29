---
name: mcp-audit
description: "Security audit for MCP (Model Context Protocol) server source code. Use this skill whenever the user wants to review, evaluate, or accept an MCP server — whether examining a community server from GitHub, reviewing a diff between versions, auditing a fork before installation, or deciding whether a new MCP dependency is safe. Trigger even when the user doesn't say 'audit' — phrases like 'is this MCP safe to use', 'check this server before I install it', 'should I update the MCP version', 'review this MCP diff', or simply opening any file inside a directory named *-mcp/ or mcp-*/ all warrant this skill. The stakes are high: MCP servers run with the user's local permissions and process personal note content — a compromised server can silently exfiltrate data."
---

# MCP Audit

This skill guides a structured security audit of an MCP server's source code.
The goal is to determine whether the server is safe to run locally — specifically
whether it could exfiltrate note content, write unexpected files, or execute
arbitrary code.

The audit is not about finding bugs or reviewing code quality. It's about a
narrower question: **does this server do anything beyond what it claims to do?**

Read `references/audit-checklist.md` for the full itemised checklist. Use this
SKILL.md to understand the approach and report format.

---

## Context: Why This Matters

MCP servers run as local processes with the same filesystem and network
permissions as the user. This project processes personal Apple Notes content
through the MCP server — the server sees every note title, folder path, and
body text that passes through it.

A server that makes unexpected network calls, writes to unexpected files, or
executes dynamic code could silently send note content to a third party. The
user may never notice. This audit exists to catch that before it happens.

---

## Which Files to Examine

Start with the files most likely to contain risky behaviour, in this order:

1. **`package.json`** — check `scripts.postinstall`, `scripts.prepare`,
   `scripts.preinstall`. Any script that runs at install time is high-risk.
2. **Entry point** — typically `src/index.ts`, `src/server.ts`, or `index.js`.
   This is where the server initialises; network setup usually appears here.
3. **Tool handler files** — wherever the MCP tools are implemented. These
   handle the actual note data and are the most likely exfiltration point.
4. **Utility / helper files** — any file imported by the above.
5. **`package-lock.json` or `yarn.lock`** — spot-check for unexpected
   dependencies (network clients, telemetry libraries).

For a diff review, focus only on changed files. A diff that touches only
AppleScript bridge code and adds a new tool is lower risk than one that
modifies the initialisation logic or adds a new import.

---

## The Six Audit Categories

Work through each category. For each finding, note the file name and line
number. A clean result is "no findings" — not "looks OK".

### 1. Network calls
Any outbound connection that is not explicitly required by the server's stated
function is a red flag. Most Apple Notes MCP servers communicate only via
AppleScript locally — they have no legitimate reason to make HTTP requests.

Look for: `fetch(`, `axios`, `http.request`, `https.request`, `net.connect`,
`WebSocket`, `EventSource`, `XMLHttpRequest`. Flag any URL that is not
`localhost` or `127.0.0.1`. See the checklist for the full pattern list.

### 2. File system writes
The server should not write files outside its own working directory. Personal
note content written to disk — even as a cache or log — is a data exposure risk.

Look for: `fs.writeFile`, `fs.appendFile`, `fs.createWriteStream`, any write to
a path constructed from note content (a filename derived from a note title could
itself leak data). See the checklist for the full pattern list.

### 3. Dynamic code execution
Code that constructs and runs strings as code is a classic injection vector.

Look for: `eval(`, `new Function(`, `vm.runInNewContext(`, `child_process.exec`
or `spawn` where arguments include user-controlled input (tool parameters or
note content). See the checklist.

### 4. Install-time hooks
Scripts that run at `npm install` time execute before the user has reviewed
the server code. They can download payloads, phone home, or modify the
environment. `postinstall` hooks that make network requests are an automatic
rejection.

### 5. Dependency version pinning

For npm/Node projects, floating version specifiers allow upstream code changes
without any change to the repository. Flag:
- `@latest` in `package.json` dependencies
- `^` or `~` prefix on any dependency (allows minor/patch updates automatically)
- No `package-lock.json` or `yarn.lock` committed, or a lockfile that is not
  included in the pinned commit hash being reviewed

A pinned commit hash in your MCP config does not protect you if the server's
own dependencies float — `npm install` at that commit can still pull newer
package versions.

### 6. Scope creep and tool schema
Compare what the server *claims* to do (its declared MCP tool list and README)
against what the code *actually* accesses. A tool declared as read-only that
calls `fs.writeFile` is scope creep. A search tool that serialises all results
to a local file is scope creep.

Also review the tool schema itself — the operations the server advertises to
the AI assistant:
- List every tool name and its declared parameter schema
- Flag tools with overly broad scope: "read all notes", "search entire library",
  "list all folders" give the AI access to the full notes graph
- Flag write or delete tools that have no confirmation parameter — a tool that
  deletes a note on a single call with no undo step is high risk in an agentic context
- Flag misleading tool descriptions: a tool described as "read-only" that accepts
  a `content` write parameter is a red flag regardless of what the code does

---

## Verdict Criteria

**APPROVED** — All five categories are clean. No unexplained network calls,
file writes, dynamic execution, install hooks, or scope discrepancies.

**CONDITIONAL** — Minor findings that are explainable and low-risk (e.g., a
log file written to the server's own temp directory, documented and bounded).
Document the condition the user must accept to proceed.

**REJECTED** — Any unexplained outbound network call; any write of note content
to disk; any `eval()` with user-controlled input; any install hook that makes
a network request; any floating dependency version with no lockfile. Do not
rationalise these findings — flag them and let the user decide.

---

## Report Format

Produce the audit report in this structure. Be specific: name files and line
numbers for every finding. "No findings" is a valid and good result.

```
## MCP Audit Report
Server: <name and version>
Audited: <date>
Scope: <what was examined — full source / diff vX to vY / specific files>

### 1. Network calls: PASS / FAIL
<findings or "No findings">

### 2. File system writes: PASS / FAIL
<findings or "No findings">

### 3. Dynamic code execution: PASS / FAIL
<findings or "No findings">

### 4. Install-time hooks: PASS / FAIL
<findings or "No findings">

### 5. Dependency version pinning: PASS / FAIL
<findings or "No findings">

### 6. Scope creep and tool schema: PASS / FAIL
<findings or "No findings">

### Summary
<One paragraph: what was found, what it means, any caveats>

### Verdict: APPROVED / CONDITIONAL / REJECTED
<If CONDITIONAL: state the condition>
<If REJECTED: state which finding is disqualifying and why>
```

---

## Tips for Efficient Auditing

- Grep before reading. Run pattern searches across the full source before
  opening individual files — this surfaces findings fast and avoids missing
  occurrences in files you didn't think to open.
- A finding is a finding even if it looks benign. Document it and let the
  verdict section explain the risk level. The user can decide; your job is
  to surface everything.
- For diff reviews, also check whether the diff *removes* existing safety
  checks — a version that deletes rate limiting or removes a localhost-only
  check is as suspicious as one that adds a network call.
- If the server has TypeScript source, audit the `.ts` files, not the
  compiled `.js` output. Compiled output can obfuscate intent.
- Dependencies matter. A new dependency on `got`, `node-fetch`, `superagent`,
  or `pino` (logging) added in a version bump warrants scrutiny even if the
  main source files look clean.
