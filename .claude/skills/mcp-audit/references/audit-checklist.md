# MCP Audit Checklist

Reference for the `mcp-audit` skill. Use this file when conducting a full
audit — it contains the complete pattern lists and the audit report template.

---

## Category 1: Network Calls

Search the entire source tree for these patterns. Flag any match that is not
clearly scoped to localhost or a documented, user-initiated connection.

### Patterns to grep for

```
fetch(
axios
http.request(
http.get(
https.request(
https.get(
net.connect(
net.createConnection(
WebSocket
EventSource
XMLHttpRequest
superagent
got(
node-fetch
request(          # older npm package
needle(
```

### What to look for beyond pattern matches

- Any string literal containing `http://` or `https://` that is not
  `http://localhost` or `http://127.0.0.1`
- Environment variables used to construct URLs (the URL may be injected
  at runtime even if no hardcoded URL appears in source)
- Dynamic URL construction from tool input or note content
  — e.g., `` `https://api.example.com/log?note=${noteTitle}` ``

### Verdict guidance

Clean = zero matches, or matches clearly scoped to localhost only.
Flag = any external URL, any dynamic URL construction, any HTTP client
import that is not used for a documented purpose.

---

## Category 2: File System Writes

### Patterns to grep for

```
fs.writeFile
fs.writeFileSync
fs.appendFile
fs.appendFileSync
fs.createWriteStream
fs.open(.*'w'
fs.open(.*'a'
writeFile
appendFile
```

### What to look for beyond pattern matches

- Writes to paths constructed from note content (title, body excerpt,
  folder name). Even if the file stays local, the path itself leaks data.
- Writes to `~/Library/`, `/tmp/`, `/var/`, or any path outside the
  server's own working directory.
- Log rotation or cache files that accumulate note content over time.
- SQLite or other database writes (`better-sqlite3`, `sqlite3`) — these
  can persist note content indefinitely.

### Verdict guidance

Clean = no writes, or writes strictly to the server's own temp/log
directory with content that contains no note data.
Flag = any write of note content to disk, any write outside the server
directory, any database write.

---

## Category 3: Dynamic Code Execution

### Patterns to grep for

```
eval(
new Function(
vm.runInNewContext(
vm.runInThisContext(
vm.Script(
child_process.exec(
child_process.execSync(
child_process.spawn(
child_process.spawnSync(
Function(
```

### What to look for beyond pattern matches

- `child_process.exec` or `spawn` where the command string includes tool
  input parameters or note content (command injection risk).
- `eval()` called on any string that is not a hardcoded literal.
- Template literals passed to any of the above.

### Verdict guidance

Clean = no matches, or `child_process` used only for AppleScript
(`osascript`) with hardcoded script paths (not content-derived).
Flag = `eval()` on non-literal input; `child_process.exec` with
user-controlled arguments; any use of `vm` module.

---

## Category 4: Install-time Hooks

### What to check in `package.json`

Open `package.json` and examine the `scripts` block:

```json
{
  "scripts": {
    "postinstall": "...",   ← HIGH RISK
    "prepare": "...",       ← MEDIUM RISK (runs on npm install in some cases)
    "preinstall": "...",    ← HIGH RISK
    "install": "..."        ← HIGH RISK
  }
}
```

A `postinstall` that only runs a TypeScript compile (`tsc`) is acceptable.
A `postinstall` that runs a shell script, calls `node` on a separate file,
or makes any network request is a rejection.

### Also check

- Any `.npmrc` or `.yarnrc` that configures a non-standard registry
- Any `binding.gyp` or native addon build that runs C++ compilation at
  install time (low risk for data exfiltration but worth noting)

### Verdict guidance

Clean = no install hooks, or hooks that only perform compilation.
Flag = any hook that runs a script file, makes network requests, or
executes anything other than a standard build step.

---

## Category 5: Scope Creep

This category requires reading the server's declared tool list and README,
then verifying that the implementation matches the declaration.

### How to check

1. List all declared MCP tools (usually in the entry point or a tools
   definition file).
2. For each tool marked as read-only or search-only, confirm the handler
   does not call any write API (`fs.write*`, Notes create/update/delete).
3. For each tool that operates on a specific scope (e.g., "search notes
   in folder X"), confirm the implementation does not access folders or
   accounts outside that scope.
4. Confirm the server does not register more tools than it declares —
   some servers register dynamic tools at startup.

### Common scope creep patterns

- A `search_notes` tool that writes a cache of all note titles to disk
- A `get_note` tool that logs accessed note IDs to a persistent file
- A `list_folders` tool that also reads note body content
- Any tool that triggers a Notes sync or iCloud operation as a side effect

### Verdict guidance

Clean = implementation matches declaration for all tools.
Flag = any tool that does more than it declares, or any undeclared tool
registered at runtime.

---

## Dependency Version Pinning

### What to check in `package.json`

```json
{
  "dependencies": {
    "some-package": "^1.2.3",   ← FLOATING: allows 1.x.x updates automatically
    "other-package": "~2.0.0",  ← FLOATING: allows 2.0.x patch updates
    "pinned-package": "3.1.4",  ← SAFE: exact version
    "@org/tool": "latest"       ← DANGEROUS: pulls whatever is current at install time
  }
}
```

**Why this matters even with a pinned commit hash:** Pinning a commit in your
MCP config freezes the server's source code, but `npm install` at that commit
still resolves floating `^` or `~` ranges to the newest matching version at
install time. A compromised upstream package can reach your machine this way
without any change to the MCP's own source.

### Verdict guidance

Clean = all runtime dependencies pinned to exact versions AND a committed
`package-lock.json` or `yarn.lock`.
Flag = any `^`, `~`, or `latest`; no lockfile committed; lockfile excluded
from the commit being audited.

---

## Dependency Spot-Check

Check `package.json` dependencies (both `dependencies` and
`devDependencies`) for packages that suggest unexpected capabilities:

| Package | Why it's a flag |
|---------|-----------------|
| `axios`, `got`, `node-fetch`, `superagent`, `needle` | HTTP client — why does a local MCP need this? |
| `pino`, `winston`, `bunyan`, `log4js` | Logging framework — will it log note content? |
| `better-sqlite3`, `sqlite3`, `lowdb` | Persistent local database — could accumulate note data |
| `sentry`, `@sentry/node`, `bugsnag` | Error telemetry — may send stack traces containing note data |
| `mixpanel`, `segment`, `amplitude` | Analytics — designed to phone home |
| `nodemailer` | Email — no legitimate use in a Notes MCP |
| `ws` | WebSocket client — check if it connects outbound |

A package appearing in `devDependencies` only is lower risk (not included
in production bundle) but should still be noted.

---

## Audit Report Template

```
## MCP Audit Report
Server: <name> v<version>
Source: <GitHub URL or "local fork">
Audited: <YYYY-MM-DD>
Scope: <"full source" / "diff v1.x to v1.y" / "files: src/index.ts, src/tools.ts">

### 1. Network calls: PASS / FAIL
<File: line — description of finding>
— or —
No findings.

### 2. File system writes: PASS / FAIL
<File: line — description of finding>
— or —
No findings.

### 3. Dynamic code execution: PASS / FAIL
<File: line — description of finding>
— or —
No findings.

### 4. Install-time hooks: PASS / FAIL
<package.json scripts block content and assessment>
— or —
No install hooks present.

### 5. Dependency version pinning: PASS / FAIL
<findings or "No findings">

### 6. Scope creep and tool schema: PASS / FAIL
<Tool name — declared scope vs. actual behaviour; any overly broad or misleading tools>
— or —
No scope discrepancies found.

### Dependency flags
<Package name — reason for flagging>
— or —
No flagged dependencies.

### Summary
<One paragraph. What was examined, what was found, overall risk assessment.>

### Verdict: APPROVED / CONDITIONAL / REJECTED
<CONDITIONAL: state the condition explicitly>
<REJECTED: name the disqualifying finding and category>
```
