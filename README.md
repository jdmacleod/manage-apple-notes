# manage-apple-notes

[![CI](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml/badge.svg)](https://github.com/jdmacleod/manage-apple-notes/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jdmacleod/manage-apple-notes/graph/badge.svg)](https://codecov.io/gh/jdmacleod/manage-apple-notes)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Scripts and workflows for organizing Apple Notes using AI-powered classification into a user-defined folder taxonomy — PARA, Zettelkasten-influenced, or custom. Optional [Forever Notes](https://forevernotesframework.com) structural features (Hub notes, tags) are available in strict mode.

The pipeline is: **export → discover themes → AI classify → human review → apply**. Nothing touches your notes until you approve a proposal.

Set `reorganization_mode` in `settings.local.yaml` to control how aggressively the pipeline proposes changes — from `"conservative"` (only high-confidence moves for notes outside Inbox/Fleeting) through `"standard"` (default) to `"full"` (reclassify from scratch).

## Prerequisites

- macOS with Apple Notes
- **Terminal Automation permission** — export, move, restore, and hub-sync commands run AppleScript via `osascript`, which requires your terminal app to be allowed to control Notes. Grant it in **System Settings → Privacy & Security → Automation** — enable the Notes checkbox under your terminal app (Terminal, iTerm2, etc.). macOS will prompt the first time a script runs; if the prompt never appears, open System Settings and add it manually.
- **Full Disk Access (some commands)** — commands that read `NoteStore.sqlite` directly (such as note-to-note link insertion) require Full Disk Access for your terminal app. Grant it in **System Settings → Privacy & Security → Full Disk Access**, run the relevant commands, then revoke it when done if you prefer a conservative security posture. See [Technical Notes: Full Disk Access requirement](docs/technical-notes.md#full-disk-access-requirement) for step-by-step instructions.
- [uv](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- An LLM provider: an [Anthropic API key](https://console.anthropic.com) (cloud), [Ollama](https://ollama.com) running locally, [AWS EC2 GPU instance](#aws-ollama-provider) (cloud GPU via Ollama), **or** Apple Intelligence on-device (macOS 26+, see [Apple Intelligence provider](#apple-intelligence-provider))

## Setup

```bash
# 1. Clone
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes

# 2. Activate pre-commit hook (blocks accidental data commits)
git config core.hooksPath .git-hooks

# 3. Copy and fill in personal config (these files are gitignored)
# Use taxonomy.example.yaml (Forever Notes / Zettelkasten) or taxonomy.para.yaml (PARA method)
cp config/taxonomy.example.yaml config/taxonomy.local.yaml
cp config/settings.example.yaml config/settings.local.yaml
# Edit both files with your actual Apple Notes folder names.
# Taxonomy files use "taxonomy:" as the root key — if upgrading from an earlier version,
# rename "forever_notes:" to "taxonomy:" in your taxonomy.local.yaml.
# If all your taxonomy folders live inside a single container folder in Apple Notes
# (e.g. "Library"), set toplevel_folder.enabled: true and update toplevel_folder.name
# in settings.local.yaml to match.

# 4. Install Python dependencies and create virtual environment
uv sync

# 5. Set your API key / provider URL
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY for cloud, or set OLLAMA_BASE_URL for local
```

## Quick Reference

See [docs/runbooks/main-workflow.md](docs/runbooks/main-workflow.md) for the full walkthrough.

```bash
# Initial library setup (one-time)
uv run notes export              # export from Apple Notes
uv run notes backup              # safety backup before bulk changes → data/backups/
uv run notes discover            # map thematic clusters → data/theme-maps/
uv run notes draft               # generate editable taxonomy YAML → data/taxonomy-drafts/
# → HUMAN: review draft, copy to config/taxonomy.local.yaml
uv run notes classify            # classify notes → data/proposals/
# → HUMAN: review proposal JSON
uv run notes move --dry-run      # preview moves
uv run notes move                # move notes per approved proposal
uv run notes dedup               # detect duplicates → data/dedup-proposals/
# → HUMAN: review dedup proposal
uv run notes purge               # preview deletions (dry-run by default)
uv run notes purge --execute     # delete confirmed duplicates
uv run notes export              # refresh after deletions
uv run notes sync-hubs           # create ✱ Home and ✱ Hub notes (strict mode only)

# Ongoing
uv run notes backup              # timestamped backup to data/backups/
uv run notes triage              # triage Inbox captures → data/proposals/
# → HUMAN: review proposal JSON
uv run notes move                # move notes per approved proposal
uv run notes audit               # quality report (stale, stub, duplicate)
uv run notes export              # refresh before hub sync
uv run notes sync-hubs           # update ✱ Home and ✱ Hub notes (strict mode only)

# Recovery
uv run notes restore             # recreate notes lost during move
uv run notes repair              # fix formatting after an iCloud Recently Deleted restore
```

Most commands accept `--dry-run` to preview without making changes. `purge` is a dry-run by default; pass `--execute` to apply deletions.

> **Backup scope:** `notes backup` saves a text-only snapshot — note titles, plaintext body, and folder paths. Images, attachments, sketches, and formatting are not captured. For full media backup, use Time Machine or a clone utility (CCC, SuperDuper) to back up `~/Library/Group Containers/group.com.apple.notes/`.

Full documentation lives in the [`docs/`](docs/) directory.

## Privacy, Cost, and Speed

**LLM provider choice affects what leaves your device.** Pick the option that matches your comfort level:

| Provider | Note content sent off-device? | Setup complexity | Cost | Speed |
|----------|-------------------------------|------------------|------|-------|
| [Anthropic API](https://console.anthropic.com) | Yes — note text is sent to Anthropic's servers for inference and is subject to [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy) | Low — API key only | Pay per use with token credits | Fast |
| [Ollama](https://ollama.com) (local) | No — inference runs entirely on your machine | Medium — install Ollama, pull a model | No cost, model runs locally | Slower, but depends on your hardware |
| [AWS-Ollama](#aws-ollama-provider) (cloud GPU) | No — inference runs on your EC2 instance; traffic stays inside your SSH tunnel | Medium-High — AWS account, CDK CLI, EC2 key pair, GPU quota | ~$1.01/hr while instance is running | Fast — NVIDIA A10G GPU (24 GB VRAM) |
| Apple Intelligence (on-device) | No — inference runs on your Apple Silicon chip | Medium — macOS 26+, Apple Intelligence enabled, compile Swift tool | No cost | Fast on Apple Silicon |

Regardless of provider, this repo is public and personal data is kept out of git:

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` are gitignored
- `.env` (your API keys) is gitignored; only `.env.example` is committed
- The entire `data/` directory (exports, proposals, reports) is gitignored
- A pre-commit hook blocks accidental commits of private files

See [`config/taxonomy.example.yaml`](config/taxonomy.example.yaml) (Forever Notes / Zettelkasten), [`config/taxonomy.para.yaml`](config/taxonomy.para.yaml) (PARA method), and [`config/settings.example.yaml`](config/settings.example.yaml) for the committed templates.

## AWS-Ollama provider

Run classification on a cloud GPU — an AWS EC2 g5.xlarge instance running Ollama — accessible via an SSH tunnel. Note content never leaves your tunnel; inference runs on the EC2 instance you control.

**Default model:** `gpt-oss:20b` — a 20B-parameter open-weight model that fits comfortably in the 24 GB VRAM of the A10G GPU on g5.xlarge. See [Technical Notes: AWS-Ollama](docs/technical-notes.md#aws-ollama-provider-g5xlarge-24-gb-vram) for VRAM and context window details.

**One-time CDK deploy:**

```bash
# Install the CDK CLI (requires Node.js)
npm install -g aws-cdk

# Install Python CDK dependencies
cd infra && pip install -r requirements.txt

# Bootstrap CDK in your account/region (once per account)
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>

# Deploy the EC2 instance
cdk deploy
```

CDK outputs an `SshTunnelCommand`. Run it once per session to forward the Ollama endpoint to `localhost:11434`, then set `OLLAMA_BASE_URL` in your `.env`:

```
OLLAMA_BASE_URL=http://localhost:11434
```

**Configure `settings.local.yaml`:**

```yaml
aws:
  region: "us-east-1"
  instance_type: "g5.xlarge"
  key_pair_name: "my-aws-key"
  ssh_key_path: "~/.ssh/my-aws-key.pem"
  model: "gpt-oss:20b"

llm:
  provider: "ollama"
  model: "gpt-oss:20b"
  batch_size: 10
  context_size:
    ollama: 8192      # safe for gpt-oss:20b on 24 GB VRAM; see technical notes
```

The `OLLAMA_BASE_URL` env var activates the Ollama provider automatically once the SSH tunnel is running. Run `cdk destroy` to decommission all infrastructure. See [docs/aws-infrastructure.md](docs/aws-infrastructure.md) for the full guide including model persistence, cost notes, and troubleshooting.

## Apple Intelligence provider

Run classification entirely on-device using Apple's Foundation Models framework — no API key or Ollama required.

**Requirements:** macOS 26+, Apple Silicon Mac, Apple Intelligence enabled in System Settings → Apple Intelligence & Siri, Xcode 26.

**One-time build:**

```bash
# From the repo root — requires Xcode 26 command-line tools
make -C swift/apple-llm build
```

The binary is placed at `swift/apple-llm/.build/release/apple-llm` (gitignored). Run `make -C swift/apple-llm` with no target to list all available targets (`build`, `debug`, `test`, `clean`, `smoke`).

**Configure `settings.local.yaml`:**

```yaml
llm:
  provider: "apple"
  batch_size: 1          # required — context window is 4096 tokens total
```

The `batch_size: 1` constraint is important: the 4096-token context window must accommodate the system prompt (~1200 tokens), the note being classified, and the response. See [Technical Notes: Apple Intelligence provider](docs/technical-notes.md#apple-intelligence-provider) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code quality requirements, and how to submit a pull request.

## License

MIT
