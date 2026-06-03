"""Shared JSON extraction helpers for parsing LLM responses."""

from __future__ import annotations

import json
import re
import unicodedata

# Common typographic Unicode chars that Apple's autocorrect inserts into ordinary
# English notes.  Mapped to their plain-ASCII equivalents before sanitization so
# words like "it's" are preserved rather than split at the apostrophe.
_TYPOGRAPHIC_TABLE = str.maketrans(
    {
        "‘": "'",  # ' LEFT SINGLE QUOTATION MARK
        "’": "'",  # ' RIGHT SINGLE QUOTATION MARK
        "“": '"',  # " LEFT DOUBLE QUOTATION MARK
        "”": '"',  # " RIGHT DOUBLE QUOTATION MARK
        "–": "-",  # – EN DASH
        "—": "-",  # — EM DASH
        "…": "...",  # … HORIZONTAL ELLIPSIS
    }
)


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
    """Normalize and strip characters Apple Intelligence cannot process.

    Three-pass approach:

    1. Replace common typographic Unicode with ASCII equivalents (curly quotes
       → straight, em/en dash → hyphen, ellipsis → three dots).  Apple's
       autocorrect inserts these into virtually every English note, so without
       this step words like "it's" or phrases like "cost—benefit" are split at
       the typographic char rather than preserved.

    2. NFD-decompose accented Latin characters, then drop the resulting
       combining marks (Unicode category Mn).  This maps "café" → "cafe",
       "naïve" → "naive", "résumé" → "resume" rather than corrupting the words
       into "caf", "na ve", "r sum".

    3. Replace any remaining non-ASCII and non-printable characters with spaces
       (keeps printable ASCII U+0020-U+007E plus tab/newline/CR); collapse runs
       of spaces; strip leading/trailing whitespace.  CJK, Arabic, Cyrillic,
       and other non-Latin scripts become spaces (no transliteration in Python —
       the Swift bridge's sanitizeForAppleIntelligence does that via
       CFStringTransform on its own retry path).
    """
    if not text:
        return text
    # Pass 1: typographic normalisation
    text = text.translate(_TYPOGRAPHIC_TABLE)
    # Pass 2: diacritic stripping via NFD decomposition
    nfd = unicodedata.normalize("NFD", text)
    chars: list[str] = []
    for ch in nfd:
        if unicodedata.category(ch) == "Mn":
            continue  # combining mark — the accent half of a decomposed char
        cp = ord(ch)
        if (0x20 <= cp <= 0x7E) or ch in "\t\n\r":
            chars.append(ch)
        else:
            chars.append(" ")
    return re.sub(r" {2,}", " ", "".join(chars)).strip()
