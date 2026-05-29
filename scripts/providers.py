"""LLM provider abstraction for the classification pipeline."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable


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
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text


class OllamaProvider:
    def __init__(self, model: str, timeout: float = 1200.0, dry_run: bool = False) -> None:
        import openai

        raw = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        base_url = raw if raw.endswith("/v1") else f"{raw}/v1"
        self._client = openai.OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
        self._model = os.environ.get("OLLAMA_MODEL", model)
        if not dry_run:
            self._probe(raw)

    def _probe(self, raw: str) -> None:
        root = raw[:-3].rstrip("/") if raw.endswith("/v1") else raw
        try:
            urllib.request.urlopen(f"{root}/api/tags", timeout=3)
        except urllib.error.HTTPError:
            pass  # server responded — Ollama is up
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
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content


def get_provider(settings: dict, dry_run: bool = False) -> LLMProvider:
    llm_cfg = settings.get("llm") or settings.get("claude", {})
    # OLLAMA_BASE_URL in the environment takes precedence over settings.local.yaml
    if os.environ.get("OLLAMA_BASE_URL"):
        model = llm_cfg.get("model", "llama3")
        timeout = float(llm_cfg.get("request_timeout", 1200))
        return OllamaProvider(model, timeout=timeout, dry_run=dry_run)
    provider_name = llm_cfg.get("provider", "anthropic")
    default_model = "claude-opus-4-6" if provider_name == "anthropic" else "llama3"
    model = llm_cfg.get("model", default_model)
    if provider_name == "ollama":
        timeout = float(llm_cfg.get("request_timeout", 1200))
        return OllamaProvider(model, timeout=timeout, dry_run=dry_run)
    return AnthropicProvider(model)
