"""LLM provider abstraction for the classification pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

_REPO_ROOT = Path(__file__).resolve().parent.parent


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    def classify_messages(
        self, system_prompt: str, user_content: str, max_tokens: int = 4096
    ) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def classify_messages(
        self, system_prompt: str, user_content: str, max_tokens: int = 4096
    ) -> str:
        import anthropic

        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        block = response.content[0]
        assert isinstance(block, anthropic.types.TextBlock)
        return block.text


class OllamaProvider:
    def __init__(self, model: str, timeout: float = 1200.0, dry_run: bool = False) -> None:
        import openai

        raw = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        base_url = raw if raw.endswith("/v1") else f"{raw}/v1"
        self._client = openai.OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
        self._model = os.environ.get("OLLAMA_MODEL", model)
        self._raw_url = raw
        if not dry_run:
            self._probe(raw)

    def _probe(self, raw: str) -> None:
        root = raw[:-3].rstrip("/") if raw.endswith("/v1") else raw
        try:
            with urllib.request.urlopen(f"{root}/api/tags", timeout=3) as resp:
                # Ollama returns 200 with a JSON model list — check the model is available.
                # llama.cpp returns a non-200 (caught below as HTTPError) — no check possible.
                try:
                    data = json.loads(resp.read().decode())
                    available = [m.get("name", "") for m in data.get("models", [])]
                    if not any(
                        m == self._model or m.startswith(f"{self._model}:") for m in available
                    ):
                        available_str = ", ".join(available) if available else "(none pulled)"
                        sys.exit(
                            f"Model {self._model!r} not found in Ollama.\n"
                            f"  Available: {available_str}\n"
                            f"  Pull it with: ollama pull {self._model}"
                        )
                except (ValueError, KeyError):
                    pass  # unexpected response format — assume server is ok
        except urllib.error.HTTPError:
            pass  # server responded with an error — Ollama is up, or llama.cpp
        except (urllib.error.URLError, OSError):
            sys.exit(f"Ollama is not responding at {raw}\nIs Ollama running?  Try: ollama serve")

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    def classify_messages(
        self, system_prompt: str, user_content: str, max_tokens: int = 4096
    ) -> str:
        import openai

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            return response.choices[0].message.content or ""
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            sys.exit(
                f"Lost connection to Ollama at {self._raw_url}\n"
                f"  Is Ollama still running?  Try: ollama serve\n"
                f"  ({type(exc).__name__})"
            )


class AppleProvider:
    """On-device Apple Intelligence via a compiled Swift CLI bridge (macOS 26+)."""

    def __init__(self, binary_path: str, dry_run: bool = False) -> None:
        self._binary = binary_path
        self._model = "on-device"
        if not dry_run:
            self._probe()

    def _probe(self) -> None:
        if not Path(self._binary).is_file():
            sys.exit(
                f"Apple LLM binary not found: {self._binary}\n"
                "  Build it with:\n"
                "    swift build -c release --package-path swift/apple-llm\n"
                "  Then set llm.provider: apple in config/settings.local.yaml"
            )

    @property
    def name(self) -> str:
        return "apple"

    @property
    def model(self) -> str:
        return self._model

    def classify_messages(
        self, system_prompt: str, user_content: str, max_tokens: int = 4096
    ) -> str:
        payload = json.dumps(
            {"system": system_prompt, "user": user_content, "max_tokens": max_tokens}
        )
        result = subprocess.run(
            [self._binary],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 2:
            sys.exit(f"Apple Intelligence not available: {result.stderr.strip()}")
        if result.returncode == 3:
            raise RuntimeError("apple_context_overflow")
        if result.returncode == 4:
            raise RuntimeError("apple_unsupported_locale")
        if result.returncode != 0:
            raise RuntimeError(f"apple-llm exited {result.returncode}: {result.stderr.strip()}")
        return result.stdout


def get_provider(settings: dict, dry_run: bool = False) -> LLMProvider:
    llm_cfg = settings.get("llm") or settings.get("claude", {})
    provider_name = llm_cfg.get("provider", "anthropic")
    default_model = "claude-opus-4-6" if provider_name == "anthropic" else "llama3"
    model = llm_cfg.get("model", default_model)
    if provider_name == "ollama":
        timeout = float(llm_cfg.get("request_timeout", 1200))
        return OllamaProvider(model, timeout=timeout, dry_run=dry_run)
    if provider_name == "apple":
        default_binary = str(
            _REPO_ROOT / "swift" / "apple-llm" / ".build" / "release" / "apple-llm"
        )
        binary = llm_cfg.get("apple_llm_binary", default_binary)
        return AppleProvider(binary, dry_run=dry_run)
    return AnthropicProvider(model)


def get_max_tokens(settings: dict, provider: LLMProvider) -> int:
    """Return the configured max_tokens for the given provider, defaulting to 4096."""
    llm_cfg = settings.get("llm") or settings.get("claude", {})
    context_size = llm_cfg.get("context_size", {})
    if isinstance(context_size, dict):
        return int(context_size.get(provider.name, 4096))
    return int(context_size or 4096)
