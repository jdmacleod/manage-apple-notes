"""Shared JSON extraction helpers for parsing LLM responses."""

from __future__ import annotations

import json
import re


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

    Keeps printable ASCII (U+0020-U+007E) and standard line-break whitespace
    (tab U+0009, newline U+000A, carriage-return U+000D). Everything else --
    non-printable control chars (U+0001-U+0008, U+000B-U+000C, U+000E-U+001F,
    U+007F) and all non-ASCII (U+0080 and above) -- is replaced with a space;
    consecutive spaces are then collapsed.

    This matches the Swift bridge's stripToASCII() threshold. Apple
    Intelligence's locale filter rejects any non-ASCII character, including the
    curly-quote and em-dash characters that Apple's own autocorrect inserts into
    normal English notes -- retaining Latin-1 or higher was causing the retry to
    fail with a second locale error.
    """
    if not text:
        return text
    chars = []
    for ch in text:
        cp = ord(ch)
        if (0x20 <= cp <= 0x7E) or ch in "\t\n\r":
            chars.append(ch)
        else:
            chars.append(" ")
    return re.sub(r" {2,}", " ", "".join(chars)).strip()
