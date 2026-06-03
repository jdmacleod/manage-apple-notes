"""System prompt safety tests.

Verifies that the system prompt built from inject_taxonomy():
1. Stays within Apple's 4096-token context budget (leaving room for notes + response).
2. Is accepted by Apple Intelligence without a locale error.
3. Does not lose its essential structure after normalize_for_apple().

Run with:  uv run pytest tests/integration/test_system_prompt.py --real-providers -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.classify.classify_notes import inject_taxonomy, load_prompt_template
from scripts.config import load_settings, load_taxonomy
from scripts.json_utils import is_locale_error, normalize_for_apple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Conservative token estimate: 1 character ≈ 0.25 tokens (4 chars/token).
# System prompt should leave at least 2500 tokens for notes + response.
_MAX_SYSTEM_PROMPT_TOKENS = 1500


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@pytest.fixture(scope="module")
def real_system_prompt() -> str:
    """Build the actual system prompt used in classify runs."""
    settings = load_settings()
    taxonomy = load_taxonomy()
    template = load_prompt_template()
    return inject_taxonomy(template, taxonomy, settings)


class TestSystemPromptBudget:
    def test_system_prompt_fits_token_budget(self, real_system_prompt: str) -> None:
        sanitized = normalize_for_apple(real_system_prompt)
        estimated = _estimate_tokens(sanitized)
        assert estimated <= _MAX_SYSTEM_PROMPT_TOKENS, (
            f"System prompt is ~{estimated} tokens after sanitization "
            f"(limit: {_MAX_SYSTEM_PROMPT_TOKENS}). "
            "Reduce taxonomy description lengths or category count."
        )

    def test_sanitization_preserves_structure(self, real_system_prompt: str) -> None:
        sanitized = normalize_for_apple(real_system_prompt)
        # System prompt should retain substantial content after normalization
        assert len(sanitized) >= len(real_system_prompt) * 0.85, (
            f"Normalization removed more than 15% of the system prompt "
            f"({len(real_system_prompt)} → {len(sanitized)} chars). "
            "Taxonomy folder names may contain significant non-ASCII content."
        )
        # Key structural phrases must survive
        assert "proposed_folder" in sanitized
        assert "confidence" in sanitized


class TestSystemPromptApple:
    def test_normalized_system_prompt_accepted(
        self, apple_provider: object, real_system_prompt: str
    ) -> None:
        sanitized = normalize_for_apple(real_system_prompt)
        try:
            apple_provider.classify_messages(  # type: ignore[attr-defined]
                sanitized,
                "Test note. Please classify it.",
                max_tokens=100,
            )
        except RuntimeError as exc:
            if is_locale_error(exc):
                pytest.fail(
                    f"Locale error on sanitized system prompt. "
                    f"Prompt length: {len(sanitized)} chars. Error: {exc}"
                )

    def test_raw_system_prompt_may_cause_locale_error(
        self, apple_provider: object, real_system_prompt: str
    ) -> None:
        """Informational test: records whether the raw system prompt triggers locale errors.

        This test does not fail — it marks as xfail if the raw prompt succeeds (meaning
        the taxonomy has no non-ASCII in folder names).  It's a diagnostic, not a gate.
        """
        has_non_ascii = any(ord(c) > 0x7F for c in real_system_prompt)
        if not has_non_ascii:
            pytest.skip("System prompt is already pure ASCII — no locale risk")
        try:
            apple_provider.classify_messages(  # type: ignore[attr-defined]
                real_system_prompt,
                "Test note. Please classify it.",
                max_tokens=100,
            )
            # If we reach here, raw prompt didn't cause an error
            pytest.xfail(
                "Raw system prompt (with non-ASCII) did not trigger a locale error on this device. "
                "Pre-sanitization is still recommended for portability."
            )
        except RuntimeError as exc:
            if is_locale_error(exc):
                pass  # Expected: non-ASCII system prompt triggered locale filter
            else:
                raise
