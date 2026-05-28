# GitHub MCP / Tool Security Audit

Perform a security audit of the GitHub repository provided. This skill is designed
for auditing community-developed MCP servers (e.g. Apple Notes integrations) before
adding them to an AI assistant's tool configuration.

Reference checklist: `docs/security-considerations.md` → "Audit checklist"

## Audit steps

### 1. Network / exfiltration check
Search the full source for any outbound network calls:
- JavaScript/TypeScript: `fetch(`, `axios`, `http.`, `https.`, `net.`, `socket`, `XMLHttpRequest`
- Python: `requests.`, `httpx.`, `urllib`, `socket.`
Flag every hit. Determine whether each is necessary for the tool's stated purpose or
is unexplained. Unexplained outbound calls are a hard blocker.

### 2. SQLite / database access scope
If the tool reads any local database (e.g. NoteStore.sqlite for Apple Notes):
- Is the access read-only or does it write?
- Is it copying to a temp directory first (safe) or opening the live DB directly?
- Is it reading a narrow set of columns for a documented purpose, or bulk-extracting?
- Is this access disclosed in the README / documentation?
Undisclosed bulk reads or any write access are hard blockers.

### 3. Dependency audit
Review `package.json`, `pyproject.toml`, or `requirements.txt`:
- List all runtime dependencies and their stated purpose
- Flag any dependency that is network-capable but whose purpose is not obvious
  (e.g. a logging library that phones home, analytics packages)
- Note whether dependencies are pinned to exact versions or ranges

### 4. Credential and environment variable access
Search for reads of environment variables:
- `process.env.`, `os.environ`, `os.getenv`
- Flag any access to credentials beyond what the tool documents
  (e.g. reading `ANTHROPIC_API_KEY`, `AWS_*`, or other secrets unrelated to its function)

### 5. Scope of Apple Notes / filesystem access
If the tool reads or writes Apple Notes or the local filesystem:
- Does it limit access to what it documents, or does it traverse broadly?
- Does it write notes or files without explicit user instruction?
- Are there any patterns that could silently modify data during unrelated AI tasks?

### 6. Commit hygiene
- Note the most recent commit hash reviewed
- Flag if the tool uses a floating `main` branch reference with no pinning
- Recommend pinning to a specific commit hash in MCP config

## Output format

Produce a structured report:

```
## Summary
[Pass / Requires review / Hard blocker] — one sentence verdict

## Findings by category
[One section per audit step above; "No issues found" if clean]

## Recommended action
[Safe to pin at <hash> / Fix required before use / Do not use]
```

$ARGUMENTS
