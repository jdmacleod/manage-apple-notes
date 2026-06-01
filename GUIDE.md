# manage-apple-notes — Full Guide

This document covers everything not in the [README quickstart](README.md): full prerequisites for all providers, provider-specific setup, privacy details, and contributing.

## Prerequisites

All providers require:

- macOS with Apple Notes
- [uv](https://docs.astral.sh/uv/) — `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Terminal Automation permission** — export, move, restore, and hub-sync commands run AppleScript via `osascript`. Grant it in **System Settings → Privacy & Security → Automation** — enable the Notes checkbox under your terminal app (Terminal, iTerm2, etc.). macOS will prompt on first run; if it doesn't, add it manually.
- **Full Disk Access (some commands)** — commands that read `NoteStore.sqlite` (note-to-note link insertion) require Full Disk Access for your terminal app. Grant it in **System Settings → Privacy & Security → Full Disk Access**, run the relevant command, then revoke it if you prefer a conservative security posture. See [Technical Notes: Full Disk Access](docs/technical-notes.md#full-disk-access-requirement) for step-by-step instructions.

## Setup

```bash
git clone https://github.com/jdmacleod/manage-apple-notes.git
cd manage-apple-notes
git config core.hooksPath .git-hooks   # blocks accidental data commits
uv sync

# Interactive wizard — pick a framework, name your folders (~2 min)
uv run notes setup
```

`notes setup` writes `config/taxonomy.local.yaml` for you. See [docs/setup.md](docs/setup.md) for the full wizard walkthrough, framework comparison, and manual editing reference.

Then follow the provider-specific steps below to configure your LLM provider in `config/settings.local.yaml`.

---

## Apple Intelligence provider

Run classification entirely on-device — no API key, no Ollama, no network traffic.

**Requirements:** macOS 26+, Apple Silicon Mac, Apple Intelligence enabled in System Settings → Apple Intelligence & Siri, Xcode 26.

**One-time build:**

```bash
# From the repo root — requires Xcode 26 command-line tools
make -C swift/apple-llm build
```

The binary is placed at `swift/apple-llm/.build/release/apple-llm` (gitignored). Run `make -C swift/apple-llm` with no target to see all targets (`build`, `debug`, `test`, `clean`, `smoke`).

**`settings.local.yaml`:**

```yaml
llm_provider: "apple"
```

That's it — `batch_size: 1` and `context_size: 4096` are already the defaults for the `apple` provider. The 4096-token context window accommodates the system prompt (~1200 tokens), the note being classified, and the response. See [Technical Notes: Apple Intelligence provider](docs/technical-notes.md#apple-intelligence-provider) for details.

---

## Anthropic API provider

Send notes to Anthropic's cloud API for classification. Note content is transmitted to Anthropic's servers and is subject to [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy).

**Requirements:** An [Anthropic API key](https://console.anthropic.com).

**`.env`:**

```
ANTHROPIC_API_KEY=sk-ant-...
```

**`settings.local.yaml`:**

```yaml
llm_provider: "anthropic"
```

---

## Ollama (local) provider

Run an open-weight model locally via [Ollama](https://ollama.com). Note content never leaves your machine.

**Requirements:** Ollama installed and running (`brew install ollama` or download from ollama.com), a model pulled (`ollama pull llama3`).

**`.env`** (optional — defaults to `http://localhost:11434`):

```
OLLAMA_BASE_URL=http://localhost:11434
```

**`settings.local.yaml`:**

```yaml
llm_provider: "ollama"
# llm_overrides:
#   model: "mistral"   # override the default llama3
```

---

## AWS-Ollama provider

Run classification on a cloud GPU — an AWS EC2 g5.xlarge instance running Ollama — accessible via an SSH tunnel. Note content never leaves your SSH tunnel; inference runs on the EC2 instance you control.

**Default model:** `gpt-oss:20b` — a 20B-parameter open-weight model that fits in the 24 GB VRAM of the A10G GPU on g5.xlarge. See [Technical Notes: AWS-Ollama](docs/technical-notes.md#aws-ollama-provider-g5xlarge-24-gb-vram) for VRAM and context window details.

**Requirements:** AWS account with EC2 g-instance quota (request an increase if needed — see [docs/aws-infrastructure.md](docs/aws-infrastructure.md)), AWS CLI configured, CDK CLI (`npm install -g aws-cdk`), an EC2 key pair in your target region.

**One-time CDK deploy:**

```bash
cd infra && pip install -r requirements.txt
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
cdk deploy
```

CDK outputs an `SshTunnelCommand`. Run it once per session to forward the Ollama endpoint to `localhost:11434`:

```bash
ssh -i ~/.ssh/my-aws-key.pem -N -L 11434:localhost:11434 ec2-user@<IP>
```

**`.env`:**

```
OLLAMA_BASE_URL=http://localhost:11434
```

**`settings.local.yaml`:**

```yaml
llm_provider: "aws-ollama"

aws:
  region: "us-east-1"
  instance_type: "g5.xlarge"
  key_pair_name: "my-aws-key"
  ssh_key_path: "~/.ssh/my-aws-key.pem"
  model: "gpt-oss:20b"
```

Run `cdk destroy` to decommission all infrastructure. See [docs/aws-infrastructure.md](docs/aws-infrastructure.md) for the full guide including model persistence, cost notes, and troubleshooting.

---

## Privacy and data flow

**LLM provider choice controls what leaves your device:**

| Provider | Where inference runs | Note content sent off-device? |
|---|---|---|
| Apple Intelligence | Your Apple Silicon chip | Never |
| Ollama (local) | Your machine | Never |
| AWS-Ollama | Your EC2 instance (SSH tunnel) | Never — traffic stays inside your tunnel |
| Anthropic API | Anthropic's servers | Yes — subject to Anthropic's privacy policy |

**Git hygiene — personal data never enters the repo:**

- `config/taxonomy.local.yaml` and `config/settings.local.yaml` — gitignored
- `.env` (API keys) — gitignored; only `.env.example` is committed
- `data/` (exports, proposals, reports) — entirely gitignored
- A pre-commit hook blocks accidental commits of private files (`git config core.hooksPath .git-hooks`)

See [`config/taxonomy.example.yaml`](config/taxonomy.example.yaml) (Forever Notes / Zettelkasten), [`config/taxonomy.para.yaml`](config/taxonomy.para.yaml) (PARA method), and [`config/settings.example.yaml`](config/settings.example.yaml) for the committed templates.

