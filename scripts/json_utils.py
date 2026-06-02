"""Shared JSON extraction helpers for parsing LLM responses."""

from __future__ import annotations

import json
import re

# Common Unicode punctuation used in English prose that Apple Intelligence can handle.
_LOCALE_SAFE_EXTRA: frozenset[str] = frozenset("‘’“”–—…")


def extract_json_array(text: str) -> list:
    """Extract a JSON array from an LLM response that may include prose or fences."""
    if "```" in text:
        start = text.find("[", text.find("```"))
    else:
        start = text.find("[")
    if start == -1:
        raise ValueError(f"No JSON array found in response:\n{text[:300]}")
    try:
        result, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"No JSON array found in response:\n{text[:300]}") from exc
    if not isinstance(result, list):
        raise ValueError(f"Expected JSON array, got {type(result).__name__}")
    return result


def extract_json_object(text: str) -> dict:
    """Extract a JSON object from an LLM response that may include prose or fences."""
    if "```" in text:
        start = text.find("{", text.find("```"))
    else:
        start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response:\n{text[:300]}")
    try:
        result, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as exc:
        raise ValueError(f"No JSON object found in response:\n{text[:300]}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object, got {type(result).__name__}")
    return result


def is_context_overflow(exc: Exception) -> bool:
    """Return True if the exception indicates an LLM context-length overflow."""
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "exceed_context",
            "context_length",
            "context size",
            "context window",
            "maximum context",
        )
    )


def is_locale_error(exc: Exception) -> bool:
    """Return True if the exception indicates an Apple Intelligence unsupported-locale error."""
    return "apple_unsupported_locale" in str(exc)


def strip_unsupported_chars(text: str) -> str:
    """Replace characters Apple Intelligence cannot process with spaces.

    Keeps ASCII (U+0000–U+007F), Latin-1 Supplement (U+0080–U+00FF), Latin Extended-A/B
    (U+0100–U+024F), and common English prose punctuation (curly quotes, em/en dash,
    ellipsis). CJK, Arabic, Hebrew, Devanagari, and other non-Latin scripts are replaced
    with a space; consecutive spaces are collapsed.
    """
    if not text:
        return text
    chars = []
    for ch in text:
        if ord(ch) <= 0x024F or ch in _LOCALE_SAFE_EXTRA:
            chars.append(ch)
        else:
            chars.append(" ")
    return re.sub(r" {2,}", " ", "".join(chars)).strip()
