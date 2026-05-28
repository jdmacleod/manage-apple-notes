# Security Considerations

This tool processes personal note content from Apple Notes. Before running it, understand
how data flows through the pipeline and choose the workflow that matches your situation.

---

## Data Flow Summary

| Step | What happens | Data leaves the machine? |
|------|-------------|--------------------------|
| `notes export` / `notes backup` | AppleScript extracts plaintext from Notes app → local JSON in `data/exports/` or `data/backups/` | No |
| `notes discover` / `notes classify` (cloud) | Note title + body excerpt sent to Anthropic API per batch | Yes — see below |
| `notes discover` / `notes classify` (local) | Same content sent to Ollama process on `localhost` | No |
| `notes apply` / `notes apply-dedup` | AppleScript moves or deletes notes inside the Notes app | No |
| `notes restore` / `notes repair-restored` | AppleScript creates or rewrites notes from local backup JSON | No |
| `notes sync-hubs` | Reads `NoteStore.sqlite` locally (read-only, requires Full Disk Access) to resolve stable note UUIDs; writes Hub and Home notes via AppleScript | No |

In cloud mode, each batch contains the note title and up to `max_body_chars` of body text
(default: 2000 characters). Notes are truncated before transmission; raw exports stay local.

`notes sync-hubs` reads `NoteStore.sqlite` directly as a read-only copy in a temp
directory. This requires Full Disk Access for Terminal (grant in System Settings →
Privacy & Security → Full Disk Access). Without it, the command falls back to numeric
identifiers and prints a warning — no data is transmitted either way.

---

## Choosing a Workflow

### Cloud — Anthropic (recommended default)

- Produces the highest classification quality across the full pipeline
- Note excerpts are transmitted to Anthropic's API and processed in their infrastructure
- Governed by [Anthropic's Privacy Policy](https://www.anthropic.com/legal/privacy) and
  [Usage Policy](https://www.anthropic.com/legal/aup)
- Your API key is stored in `.env`, which is gitignored and never committed
- For most personal use, this is the right choice

**Consider using the local workflow instead if your notes contain:**
- Attorney-client privileged communications
- Medical or financial records
- Trade secrets or unreleased product information
- Content subject to regulatory restrictions (HIPAA, GDPR, etc.)

Anthropic enterprise agreements provide stronger data handling and retention commitments
for organizations with elevated requirements.

### Local — Ollama

- Note content never leaves your machine at any point
- No account, API key, or internet connection required for classification
- Trade-offs compared to cloud:
  - Smaller batch sizes needed (5–10 notes; cloud handles 20+)
  - Classification quality varies by model; smaller models produce more `needs_review` results
  - Slower throughput, especially on models larger than 8B parameters

Suitable for any sensitivity level. See
[docs/technical-notes.md](technical-notes.md#local-llm-model-recommendations-macos-24gb-unified-memory)
for model recommendations.

---

## Git Safety

The repo is public. Personal data is kept out of version control by three layers:

**`.gitignore`** — excludes:
- `data/` entirely — exports, proposals, dedup proposals, reports
- `config/*.local.*` — your actual folder names and settings
- `.env` — your API keys and provider URLs

**Pre-commit hook** (`.git-hooks/pre-commit`) — blocks commits containing:
- Any file inside `data/`
- Any `*.local.*` config file
- `.env` files (`.env.example` is explicitly allowed)
- JSON files larger than 10 KB (likely an export)

Activate the hook after cloning:
```bash
git config core.hooksPath .git-hooks
```

**Verify before any commit:**
```bash
git diff --cached --name-only
```
Nothing from `data/`, `config/*.local.*`, or `.env` should appear.

---

## Apple Notes MCP Integration

`sweetrb/apple-notes-mcp` is a community-developed Model Context Protocol server that
allows Claude Code to query and write to Apple Notes directly, without the export/apply
cycle. It is an optional integration not included in this project.

### Why a forked and audited version is required

MCPs run as processes with your macOS user's full permissions — the same access as your
terminal session. An unaudited MCP can:
- Read note content silently during unrelated tasks
- Exfiltrate API keys or other credentials from your environment
- Write or modify notes without your knowledge

`sweetrb/apple-notes-mcp` is a community project with no formal security review. Its code
must be audited before adding it to any AI assistant's MCP configuration.

### Audit checklist

Before enabling any Apple Notes MCP:

1. **Read the full source** — look for any `fetch()`, `axios`, `http`, `net`, `requests`,
   or socket calls that could transmit data externally
2. **Verify the scope of any SQLite access** — this project itself uses a read-only
   `NoteStore.sqlite` query (copying the DB to a temp file first) solely to resolve
   stable note UUIDs for Hub links. That is a disclosed, scoped, read-only use. What
   to reject in an MCP: undisclosed database reads, write access, full-schema queries
   that bulk-extract note content, or any access that bypasses the Notes app for reads
   or writes beyond a narrow documented purpose
3. **Check dependencies** for unexpected network-capable packages
   (`package.json` / `pyproject.toml` / `requirements.txt`)
4. **Confirm env var access** — the MCP should not read `ANTHROPIC_API_KEY`, `AWS_*`,
   or other credentials beyond what it documents
5. **Pin a commit hash** in your fork after audit; never use a floating `main` branch reference

### Safe integration pattern

```
1. Fork sweetrb/apple-notes-mcp to your own GitHub account
2. Review the code at a specific commit; note the commit hash
3. Pin your fork to that hash in your Claude Code MCP config
4. Re-audit before merging any upstream changes
```

**MCP config locations:**
- Claude desktop app: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Claude Code project settings: `.claude/settings.json` in the project root

A pinned MCP config entry looks like:
```json
{
  "mcpServers": {
    "apple-notes": {
      "command": "npx",
      "args": ["-y", "github:YOUR_FORK/apple-notes-mcp#COMMIT_HASH"]
    }
  }
}
```
