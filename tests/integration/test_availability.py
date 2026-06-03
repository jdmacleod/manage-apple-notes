"""Provider availability smoke tests.

Each test passes if the provider is ready, fails with a actionable message if not.
Run these first to understand which providers are active before running the full suite:

    uv run pytest tests/integration/test_availability.py --real-providers -v

Unlike the other integration tests, these do NOT skip on unavailability — they fail
with a clear message so the cause is immediately visible in the output.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APPLE_BINARY = REPO_ROOT / "swift" / "apple-llm" / ".build" / "release" / "apple-llm"


# ---------------------------------------------------------------------------
# Apple Intelligence
# ---------------------------------------------------------------------------


class TestAppleIntelligenceAvailability:
    def test_binary_exists(self) -> None:
        assert _APPLE_BINARY.is_file(), (
            f"apple-llm binary not found at:\n  {_APPLE_BINARY}\n\n"
            "Build it with:\n"
            "  swift build -c release --package-path swift/apple-llm"
        )

    def test_apple_intelligence_responds(self) -> None:
        from scripts.providers import AppleProvider

        if not _APPLE_BINARY.is_file():
            pytest.fail(
                "apple-llm binary missing — run test_binary_exists first.\n"
                "Build: swift build -c release --package-path swift/apple-llm"
            )
        provider = AppleProvider(str(_APPLE_BINARY), dry_run=False)
        try:
            response = provider.classify_messages("Reply: OK", "ping", max_tokens=10)
        except SystemExit as exc:
            pytest.fail(
                f"Apple Intelligence is not available on this device: {exc}\n\n"
                "Check that:\n"
                "  1. You are on macOS 26+ with an Apple Silicon Mac\n"
                "  2. Apple Intelligence is enabled in System Settings → Apple Intelligence\n"
                "  3. The on-device model has finished downloading"
            )
        except RuntimeError:
            # Any RuntimeError (locale error, context overflow) means AI IS active —
            # the binary reached FoundationModels and got a real error back.
            return
        assert isinstance(response, str), f"Expected string response, got: {type(response)}"


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class TestOllamaAvailability:
    def _base_url(self) -> str:
        raw = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        return raw[:-3].rstrip("/") if raw.endswith("/v1") else raw

    def _model(self) -> str:
        return os.environ.get("OLLAMA_MODEL", "llama3.2")

    def test_server_reachable(self) -> None:
        # Use the OpenAI-compatible /v1/models endpoint — supported by both Ollama
        # and llama.cpp.  Ollama's /api/tags works too, but llama.cpp returns 404 for it.
        base = self._base_url()
        try:
            with urllib.request.urlopen(f"{base}/v1/models", timeout=5):
                pass
        except (urllib.error.URLError, OSError) as exc:
            pytest.fail(
                f"Server is not reachable at {base}: {exc}\n\n"
                "For Ollama: ollama serve\n"
                "For llama.cpp: check that the server is running and OLLAMA_BASE_URL in .env is correct."
            )

    def test_model_loaded(self) -> None:
        # /v1/models returns an OpenAI-compatible model list on both Ollama and llama.cpp.
        base = self._base_url()
        model = self._model()
        try:
            with urllib.request.urlopen(f"{base}/v1/models", timeout=5) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError) as exc:
            pytest.fail(f"Cannot reach server at {base}: {exc}")

        # OpenAI format: {"data": [{"id": "model-name", ...}]}
        available = [m.get("id", "") or m.get("name", "") for m in data.get("data", [])]
        if not available:
            # Fallback: some Ollama versions use {"models": [...]}
            available = [m.get("name", "") for m in data.get("models", [])]

        loaded = any(m == model or m.startswith(f"{model}:") for m in available)
        available_str = ", ".join(available) if available else "(none loaded)"
        assert loaded, (
            f"Model {model!r} is not loaded.\n\n"
            f"Available models: {available_str}\n\n"
            "For Ollama:    ollama pull {model}\n"
            "For llama.cpp: restart the server with the correct --model path.\n\n"
            f"Or set OLLAMA_MODEL in .env to one of the available models."
        )

    def test_model_responds(self) -> None:
        from scripts.providers import OllamaProvider

        model = self._model()
        try:
            provider = OllamaProvider(model, dry_run=False)
        except SystemExit as exc:
            pytest.fail(str(exc))

        # Use a generous token budget: thinking/reasoning models (e.g. gemma-4 via
        # llama.cpp) output to reasoning_content first and only populate content after
        # completing their reasoning chain.  20 tokens is not enough; 500 is.
        response = provider.classify_messages("Reply: OK", "ping", max_tokens=500)
        assert isinstance(response, str) and response.strip(), (
            f"Model {model!r} returned an empty response.\n\n"
            "If this is a thinking/reasoning model, check that max_tokens in settings "
            "is high enough for the model to finish its reasoning chain before producing output."
        )
