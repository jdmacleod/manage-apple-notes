"""LLM provider abstraction for the classification pipeline."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    def classify_messages(self, system_prompt: str, user_content: str, max_tokens: int = 4096) -> str: ...


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

    def classify_messages(self, system_prompt: str, user_content: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text


class OllamaProvider:
    def __init__(self, model: str) -> None:
        import openai
        raw = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        base_url = raw if raw.endswith("/v1") else f"{raw}/v1"
        self._client = openai.OpenAI(base_url=base_url, api_key="ollama")
        self._model = os.environ.get("OLLAMA_MODEL", model)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    def classify_messages(self, system_prompt: str, user_content: str, max_tokens: int = 4096) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        return response.choices[0].message.content


def get_provider(settings: dict) -> LLMProvider:
    llm_cfg = settings.get("llm") or settings.get("claude", {})
    provider_name = llm_cfg.get("provider", "anthropic")
    default_model = "claude-opus-4-6" if provider_name == "anthropic" else "llama3"
    model = llm_cfg.get("model", default_model)
    return OllamaProvider(model) if provider_name == "ollama" else AnthropicProvider(model)
