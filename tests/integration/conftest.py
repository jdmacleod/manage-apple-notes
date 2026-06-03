"""Fixtures for integration tests that call real LLM providers.

All tests here are skipped unless --real-providers is passed to pytest:

    uv run pytest tests/integration/ --real-providers -v
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_APPLE_BINARY = REPO_ROOT / "swift" / "apple-llm" / ".build" / "release" / "apple-llm"

# Load .env so OLLAMA_BASE_URL, OLLAMA_MODEL, and ANTHROPIC_API_KEY are available
# without requiring the CLI entry point (scripts/cli.py) to run first.
load_dotenv(REPO_ROOT / ".env")


# ---------------------------------------------------------------------------
# Skip gate — all tests in this directory skip unless --real-providers is set
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def require_real_providers(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--real-providers", default=False):
        pytest.skip("pass --real-providers to run integration tests")


# ---------------------------------------------------------------------------
# Session-level availability probes (one network/subprocess call per session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _apple_available() -> bool:
    """Return True if the apple-llm binary exists and Apple Intelligence responds."""
    from scripts.providers import AppleProvider

    if not _APPLE_BINARY.is_file():
        return False
    provider = AppleProvider(str(_APPLE_BINARY), dry_run=False)
    try:
        provider.classify_messages("Reply: OK", "ping", max_tokens=10)
        return True
    except SystemExit:
        return False  # Apple Intelligence not available on this device
    except RuntimeError:
        return True  # Any RuntimeError (locale/overflow) means AI is active


@pytest.fixture(scope="session")
def _ollama_available() -> bool:
    """Return True if Ollama is reachable and the configured model is loaded."""
    from scripts.providers import OllamaProvider

    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    try:
        OllamaProvider(model, dry_run=False)
        return True
    except SystemExit:
        return False


# ---------------------------------------------------------------------------
# Per-test provider fixtures — skip if the provider is unavailable
# ---------------------------------------------------------------------------


@pytest.fixture
def apple_provider(_apple_available: bool) -> Generator:
    """Live AppleProvider; skips the test if Apple Intelligence is not active."""
    from scripts.providers import AppleProvider

    if not _apple_available:
        pytest.skip(
            "Apple Intelligence not available — binary missing or AI not enabled. "
            "Build with: swift build -c release --package-path swift/apple-llm"
        )
    yield AppleProvider(str(_APPLE_BINARY), dry_run=False)


@pytest.fixture
def ollama_provider(_ollama_available: bool) -> Generator:
    """Live OllamaProvider; skips the test if Ollama is not reachable."""
    from scripts.providers import OllamaProvider

    if not _ollama_available:
        pytest.skip("Ollama not available — start with: ollama serve")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    yield OllamaProvider(model, dry_run=False)
