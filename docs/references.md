# References

Web references consulted during the development of this project, grouped by topic.

---

## Apple Notes Platform

| Reference | Notes |
|-----------|-------|
| [Apple Developer Forums — AppleScript notes URL schemes (thread 701574)](https://developer.apple.com/forums/thread/701574) | Community investigation of `applenotes://` URL format and the stable UUID required for note-to-note links; established that `applenotes://showNote?identifier=<UUID>` is the correct scheme |
| [Hookmark Community Forum — Using the built-in Notes URL scheme](https://discourse.hookproductivity.com/t/using-the-built-in-notes-url-scheme/6071) | Independent investigation of obtaining stable iCloud UUIDs from NoteStore.sqlite; corroborated the `ZICCLOUDSYNCINGOBJECT.ZIDENTIFIER` query approach |
| [Apple Dispatch — Comprehensive Guide for Backing Up Apple Notes](https://appledispatch.substack.com/p/comprehensive-guide-for-backing-up-apple-notes) | Survey of Apple Notes backup options (iCloud, SQLite, export); informed the documented scope limitation of `notes backup` (text-only) and the recommendation to use Time Machine or a filesystem clone for full media backup |
| [Apple — Privacy & Security, Full Disk Access (macOS)](https://support.apple.com/guide/mac-help/mh15217) | macOS system preference for granting shell access to protected directories including `~/Library/Group Containers/group.com.apple.notes/`; required for NoteStore.sqlite UUID lookup in `internal_links: "html"` mode |

### NoteStore.sqlite

Apple Notes stores all note content in `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite`. This schema is **undocumented and unsupported** by Apple; its structure has been reverse-engineered by the community. The project uses only a narrow, read-only query (`ZICCLOUDSYNCINGOBJECT.ZIDENTIFIER`) to resolve stable note UUIDs, and copies the database to a temp directory before opening it to avoid interfering with the live Notes process.

---

## Note Organisation Frameworks

| Reference | Notes |
|-----------|-------|
| [Forever Notes Framework](https://forevernotesframework.com) | Primary framework this project implements in strict mode; defines the Hub note / Home note / tag structural layer on top of the folder taxonomy |
| [myforevernotes.com — Framework Documentation](https://www.myforevernotes.com/docs/home) | Full specification of the Forever Notes taxonomy (Inbox, Fleeting, Literature, Permanent, Projects, Areas, Resources, Archive, Review) and the Zettelkasten-influenced design rationale |
| [The PARA Method — Tiago Forte (Forte Labs)](https://fortelabs.com/blog/para/) | Original article defining PARA (Projects, Areas, Resources, Archive); basis for `config/taxonomy.para.yaml` and `docs/para-method.md` |
| [The PARA Method — Book (Building a Second Brain)](https://www.buildingasecondbrain.com/para) | Book-length treatment of PARA; reference for the expanded taxonomy design (per-project subfolders, differentiated Resources lanes) |

---

## Security and Privacy

| Reference | Notes |
|-----------|-------|
| [Anthropic Privacy Policy](https://www.anthropic.com/legal/privacy) | Governs how note content transmitted to the Anthropic API is handled; reviewed before recommending cloud mode for personal use |
| [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) | Usage constraints for the Anthropic API; reviewed for compliance with processing personal note content |
| [Model Context Protocol — Specification](https://modelcontextprotocol.io/introduction) | Defines the MCP standard that `apple-notes-mcp` servers implement; relevant for understanding the permission model and attack surface of MCP server integrations |
| [OWASP Top Ten](https://owasp.org/www-project-top-ten/) | Checklist consulted when reviewing subprocess construction, external input handling, and credential management in the Python pipeline |

---

## LLM Providers and Tools

| Reference | Notes |
|-----------|-------|
| [Anthropic API (Claude)](https://console.anthropic.com) | Cloud LLM provider used for note classification and theme discovery; default provider in `settings.example.yaml` |
| [Ollama](https://ollama.com) | Local LLM inference server; supported as a privacy-preserving alternative to the cloud provider; configuration documented in `settings.example.yaml` and `docs/technical-notes.md` |
| [uv — Python Package and Project Manager](https://docs.astral.sh/uv/) | Dependency and virtualenv management tool used to run all project commands (`uv run notes <command>`) |

---

## Apple Notes MCP Servers on GitHub

Model Context Protocol servers allow an AI assistant to query and write Apple Notes directly, bypassing the export/apply pipeline. Several community implementations exist. This project documents a fork-and-audit workflow for integrating one; see `docs/security-considerations.md` for the audit checklist and safe integration pattern.

| Repository | Language | Approach | Notes |
|-----------|----------|----------|-------|
| [sweetrb/apple-notes-mcp](https://github.com/sweetrb/apple-notes-mcp) | TypeScript | AppleScript bridge | **Chosen reference implementation.** Requires forking, auditing, and pinning to a specific commit hash before use. See `docs/security-considerations.md` for the full rationale and audit checklist. |
| [RafalWilinski/mcp-apple-notes](https://github.com/RafalWilinski/mcp-apple-notes) | TypeScript | AppleScript bridge | Alternative community implementation; similar audit requirements apply before use |

### Why sweetrb/apple-notes-mcp

`sweetrb/apple-notes-mcp` is the most widely referenced Apple Notes MCP server in the Claude community and has the most visible maintenance history at the time of writing. Neither it nor any alternative has undergone a formal independent security review. The project's documented position is:

- **Do not use any Apple Notes MCP directly from `main`**
- Fork to your own account, audit the source at a specific commit (using the `/mcp-audit` skill), pin that commit hash in your MCP config, and re-audit before merging upstream changes
- The same requirements apply to any alternative implementation

Any community MCP that gains a credible independent audit and a transparent maintenance process could be substituted.
