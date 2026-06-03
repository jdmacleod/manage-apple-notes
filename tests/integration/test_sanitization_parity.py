"""Sanitization parity tests.

Verifies that the Python strip_unsupported_chars() function produces content that
Apple Intelligence accepts without a locale error.  The goal is not to test that
Python and Swift produce byte-identical output (they don't — Swift preserves word
boundaries differently for CJK); it's to test the property that matters:
"Python pre-sanitization produces content Apple will accept."

Run with:  uv run pytest tests/integration/test_sanitization_parity.py --real-providers -v
"""

from __future__ import annotations

import pytest

from scripts.json_utils import is_locale_error, strip_unsupported_chars


def _call_apple(apple_provider: object, content: str) -> None:
    """Call Apple Intelligence with content; raise AssertionError if locale error fires."""
    try:
        apple_provider.classify_messages(  # type: ignore[attr-defined]
            "Summarize in five words.", content, max_tokens=20
        )
    except RuntimeError as exc:
        if is_locale_error(exc):
            snippet = repr(content[:80])
            raise AssertionError(f"Locale error on sanitized content: {snippet}") from exc


_CORPUS = [
    # (description, raw_input)
    ("ASCII only", "Hello world. This is a plain English note."),
    ("Curly quotes", "“Great idea” — let’s try it…"),
    ("Accented Latin", "café résumé naïve"),
    ("CJK mixed with English", "Meeting notes: 中文内容 — see agenda"),
    ("Arabic mixed", "Notes: مرحبا with follow-up tasks"),
    ("Emoji", "Project done! \U0001f389 Next step: review."),
    ("Control chars", "hello\x01world\x1b[0mtest\x00end"),
    ("All CJK", "日本語テストノート"),
    ("Mixed scripts", "Café Москва 中文"),
]


class TestSanitizedContentAcceptedByApple:
    @pytest.mark.parametrize("description,raw", _CORPUS)
    def test_sanitized_input_no_locale_error(
        self, apple_provider: object, description: str, raw: str
    ) -> None:
        sanitized = strip_unsupported_chars(raw)
        if not sanitized.strip():
            pytest.skip(f"Input {description!r} sanitizes to empty — nothing to test")
        _call_apple(apple_provider, sanitized)

    def test_all_cjk_sanitizes_to_empty(self) -> None:
        # Verify that pure CJK content sanitizes to empty string (no testable content).
        result = strip_unsupported_chars("日本語テスト")
        assert result.strip() == ""

    def test_curly_quotes_stripped(self) -> None:
        # Verify that typographic punctuation is stripped, not passed through.
        result = strip_unsupported_chars("“Hello”—world…")
        assert "“" not in result
        assert "—" not in result
        assert "…" not in result
        assert "Hello" in result
        assert "world" in result
