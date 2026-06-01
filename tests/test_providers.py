"""Tests for scripts/providers.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.providers import (
    AnthropicProvider,
    AppleProvider,
    OllamaProvider,
    get_max_tokens,
    get_provider,
)

# ── Settings helper ────────────────────────────────────────────────────────────

_PROVIDER_BLOCKS: dict[str, dict] = {
    "anthropic": {"model": "claude-opus-4-6", "context_size": 8192, "batch_size": 20},
    "ollama": {
        "model": "llama3",
        "context_size": 4096,
        "batch_size": 10,
        "request_timeout": 1200,
    },
    "aws-ollama": {
        "model": "gpt-oss:20b",
        "context_size": 8192,
        "batch_size": 10,
        "request_timeout": 1200,
    },
    "apple": {
        "context_size": 4096,
        "batch_size": 1,
        "apple_llm_binary": "apple-llm",
    },
}


def _llm_settings(provider: str, overrides: dict | None = None) -> dict:
    """Build a minimal settings dict for a given provider, with optional llm_overrides."""
    base: dict = {"llm_provider": provider, "llm_providers": _PROVIDER_BLOCKS}
    if overrides:
        base["llm_overrides"] = overrides
    return base


class TestAnthropicProvider:
    def test_classify_messages_returns_text(self, mock_anthropic_success: MagicMock) -> None:
        provider = AnthropicProvider(model="claude-sonnet-4-6")
        result = provider.classify_messages("system", "user content")
        assert isinstance(result, str)
        assert "Resources" in result or len(result) > 0

    def test_rate_limit_error_propagates(self, mock_anthropic_rate_limit: MagicMock) -> None:
        import anthropic

        provider = AnthropicProvider(model="claude-sonnet-4-6")
        with pytest.raises(anthropic.RateLimitError):
            provider.classify_messages("system", "user")

    def test_connection_error_propagates(self, mock_anthropic_connection_error: MagicMock) -> None:
        import anthropic

        provider = AnthropicProvider(model="claude-sonnet-4-6")
        with pytest.raises(anthropic.APIConnectionError):
            provider.classify_messages("system", "user")

    def test_name_and_model_properties(self, mock_anthropic_success: MagicMock) -> None:
        provider = AnthropicProvider(model="claude-sonnet-4-6")
        assert provider.name == "anthropic"
        assert provider.model == "claude-sonnet-4-6"


class TestOllamaProvider:
    def test_classify_messages_returns_content(self, mocker: MagicMock) -> None:
        mock_openai = mocker.patch("openai.OpenAI")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[
            0
        ].message.content = "test response"
        mock_openai.return_value = mock_client

        provider = OllamaProvider(model="llama3", dry_run=True)
        result = provider.classify_messages("system", "user")
        assert result == "test response"

    def test_name_and_model_properties(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        mocker.patch("openai.OpenAI")
        provider = OllamaProvider(model="llama3", dry_run=True)
        assert provider.name == "ollama"
        assert provider.model == "llama3"

    def test_probe_url_error_exits(self, mocker: MagicMock) -> None:
        import urllib.error

        mocker.patch("openai.OpenAI")
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        )
        with pytest.raises(SystemExit):
            OllamaProvider(model="llama3", dry_run=False)

    def test_probe_http_error_passes(self, mocker: MagicMock) -> None:
        import urllib.error

        mocker.patch("openai.OpenAI")
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://localhost/api/tags", code=404, msg="Not Found", hdrs=None, fp=None
            ),
        )
        provider = OllamaProvider(model="llama3", dry_run=False)
        assert provider.name == "ollama"

    def test_probe_model_found_passes(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        mocker.patch("openai.OpenAI")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]}
        ).encode()
        mocker.patch("urllib.request.urlopen").return_value.__enter__.return_value = mock_resp
        provider = OllamaProvider(model="llama3", dry_run=False)
        assert provider.model == "llama3"

    def test_probe_model_not_found_exits(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        mocker.patch("openai.OpenAI")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"models": [{"name": "mistral:latest"}]}).encode()
        mocker.patch("urllib.request.urlopen").return_value.__enter__.return_value = mock_resp
        with pytest.raises(SystemExit, match="not found in Ollama"):
            OllamaProvider(model="llama3", dry_run=False)

    def test_probe_no_models_pulled_exits(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        mocker.patch("openai.OpenAI")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"models": []}).encode()
        mocker.patch("urllib.request.urlopen").return_value.__enter__.return_value = mock_resp
        with pytest.raises(SystemExit, match="not found in Ollama"):
            OllamaProvider(model="llama3", dry_run=False)

    def test_classify_messages_connection_error_exits(self, mocker: MagicMock) -> None:
        import openai

        mock_openai = mocker.patch("openai.OpenAI")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
            request=MagicMock()
        )
        mock_openai.return_value = mock_client

        provider = OllamaProvider(model="llama3", dry_run=True)
        with pytest.raises(SystemExit, match="Lost connection to Ollama"):
            provider.classify_messages("system", "user")

    def test_classify_messages_timeout_exits(self, mocker: MagicMock) -> None:
        import openai

        mock_openai = mocker.patch("openai.OpenAI")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APITimeoutError(
            request=MagicMock()
        )
        mock_openai.return_value = mock_client

        provider = OllamaProvider(model="llama3", dry_run=True)
        with pytest.raises(SystemExit, match="Lost connection to Ollama"):
            provider.classify_messages("system", "user")

    def test_ollama_aws_name_property(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        mocker.patch("openai.OpenAI")
        provider = OllamaProvider(model="gpt-oss:20b", dry_run=True, provider_name="aws-ollama")
        assert provider.name == "aws-ollama"
        assert provider.model == "gpt-oss:20b"

    def test_ollama_aws_probe_url_error_mentions_tunnel(self, mocker: MagicMock) -> None:
        import urllib.error

        mocker.patch("openai.OpenAI")
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        )
        with pytest.raises(SystemExit, match="SSH tunnel"):
            OllamaProvider(model="gpt-oss:20b", dry_run=False, provider_name="aws-ollama")

    def test_ollama_aws_classify_connection_error_mentions_tunnel(self, mocker: MagicMock) -> None:
        import openai

        mock_openai = mocker.patch("openai.OpenAI")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
            request=MagicMock()
        )
        mock_openai.return_value = mock_client

        provider = OllamaProvider(model="gpt-oss:20b", dry_run=True, provider_name="aws-ollama")
        with pytest.raises(SystemExit, match="SSH tunnel"):
            provider.classify_messages("system", "user")


class TestAppleProvider:
    def test_probe_missing_binary_exits(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "apple-llm")
        with pytest.raises(SystemExit):
            AppleProvider(binary_path=missing, dry_run=False)

    def test_probe_skipped_in_dry_run(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "apple-llm")
        provider = AppleProvider(binary_path=missing, dry_run=True)
        assert provider.name == "apple"

    def test_name_and_model_properties(self, tmp_path: Path) -> None:
        provider = AppleProvider(binary_path=str(tmp_path / "apple-llm"), dry_run=True)
        assert provider.name == "apple"
        assert provider.model == "on-device"

    def test_classify_messages_success(self, mocker: MagicMock, tmp_path: Path) -> None:
        mock_run = mocker.patch("scripts.providers.subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stdout="classified output", stderr="")
        provider = AppleProvider(binary_path=str(tmp_path / "apple-llm"), dry_run=True)
        result = provider.classify_messages("system prompt", "user content")
        assert result == "classified output"

    def test_classify_messages_context_overflow(self, mocker: MagicMock, tmp_path: Path) -> None:
        mock_run = mocker.patch("scripts.providers.subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=3, stdout="", stderr="error: context window exceeded"
        )
        provider = AppleProvider(binary_path=str(tmp_path / "apple-llm"), dry_run=True)
        with pytest.raises(RuntimeError, match="apple_context_overflow"):
            provider.classify_messages("system", "user")

    def test_classify_messages_unavailable_exits(self, mocker: MagicMock, tmp_path: Path) -> None:
        mock_run = mocker.patch("scripts.providers.subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=2, stdout="", stderr="error: Apple Intelligence is not enabled"
        )
        provider = AppleProvider(binary_path=str(tmp_path / "apple-llm"), dry_run=True)
        with pytest.raises(SystemExit):
            provider.classify_messages("system", "user")

    def test_classify_messages_general_error_raises(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        mock_run = mocker.patch("scripts.providers.subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: generation failed"
        )
        provider = AppleProvider(binary_path=str(tmp_path / "apple-llm"), dry_run=True)
        with pytest.raises(RuntimeError, match="apple-llm exited 1"):
            provider.classify_messages("system", "user")


class TestGetProvider:
    def test_anthropic_key_returns_anthropic_provider(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mocker.patch("anthropic.Anthropic")

        provider = get_provider(_llm_settings("anthropic"), dry_run=True)
        assert provider.name == "anthropic"

    def test_ollama_base_url_env_does_not_override_provider(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # OLLAMA_BASE_URL is a connection URL for Ollama, not a provider selector.
        # Explicit llm_provider in settings always wins.
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        mocker.patch("anthropic.Anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        provider = get_provider(_llm_settings("anthropic"), dry_run=True)
        assert provider.name == "anthropic"

    def test_ollama_base_url_env_used_as_connection_url(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # OLLAMA_BASE_URL is still read by OllamaProvider when llm_provider: ollama is set.
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-host:11434")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        mock_openai = mocker.patch("openai.OpenAI")

        get_provider(_llm_settings("ollama"), dry_run=True)

        call_kwargs = mock_openai.call_args.kwargs
        assert "custom-host" in call_kwargs.get("base_url", "")

    def test_ollama_provider_setting(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        mocker.patch("openai.OpenAI")

        provider = get_provider(_llm_settings("ollama"), dry_run=True)
        assert provider.name == "ollama"

    def test_default_anthropic_when_no_settings(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        mocker.patch("anthropic.Anthropic")

        # Empty settings: llm_provider defaults to "anthropic", reads from example.yaml
        provider = get_provider({}, dry_run=True)
        assert provider.name == "anthropic"

    def test_ollama_aws_provider_setting(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        mocker.patch("openai.OpenAI")

        provider = get_provider(_llm_settings("aws-ollama"), dry_run=True)
        assert provider.name == "aws-ollama"
        assert provider.model == "gpt-oss:20b"

    def test_apple_provider_setting(
        self, mocker: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        binary = str(tmp_path / "apple-llm")
        provider = get_provider(
            _llm_settings("apple", overrides={"apple_llm_binary": binary}), dry_run=True
        )
        assert provider.name == "apple"


class TestGetMaxTokens:
    def _make_provider(self, name: str) -> MagicMock:
        p = MagicMock()
        p.name = name
        return p

    def test_returns_provider_context_size(self) -> None:
        assert get_max_tokens(_llm_settings("anthropic"), self._make_provider("anthropic")) == 8192
        assert get_max_tokens(_llm_settings("ollama"), self._make_provider("ollama")) == 4096
        assert (
            get_max_tokens(_llm_settings("aws-ollama"), self._make_provider("aws-ollama")) == 8192
        )

    def test_unknown_provider_uses_default(self) -> None:
        settings = {"llm_provider": "unknown", "llm_providers": {}}
        assert get_max_tokens(settings, self._make_provider("unknown")) == 4096

    def test_override_context_size(self) -> None:
        settings = _llm_settings("anthropic", overrides={"context_size": 2048})
        assert get_max_tokens(settings, self._make_provider("anthropic")) == 2048

    def test_empty_settings_uses_example_yaml_default(self) -> None:
        # Empty settings → defaults to "anthropic" provider from example.yaml
        assert get_max_tokens({}, self._make_provider("anthropic")) == 8192
