"""Shared JSON extraction helpers for parsing LLM responses."""

from __future__ import annotations

import json
import re
import unicodedata

# ── Slug title normalisation ─────────────────────────────────────────────────
# Apple Intelligence's language detector rejects titles of the form
# "YYYY-MM-DD-Word-Word" because the dense-hyphen, numeric-date pattern scores
# low on all known-language n-gram models.  Converting to natural English prose
# before sending the payload avoids the unsupportedLanguageOrLocale error.

_ISO_SLUG_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")

_MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

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


def extract_json_themes(text: str) -> list:
    """Extract a themes list from an LLM response, accepting two formats:

    - {"themes": [...]} — the canonical format the discover prompt requests
    - [...]             — a bare array, returned by some on-device models (e.g.
                          Apple Intelligence) that echo the input array format

    Tries the object format first so that a correctly-wrapped response is always
    preferred.  Falls back to bare-array parsing when the object form is absent or
    lacks a "themes" key.
    """
    fence = text.find("```") if "```" in text else 0
    obj_start = text.find("{", fence)
    arr_start = text.find("[", fence)

    # Try {"themes": [...]} first
    if obj_start != -1:
        try:
            result, _ = json.JSONDecoder().raw_decode(text, obj_start)
            if isinstance(result, dict):
                themes = result.get("themes")
                if isinstance(themes, list):
                    return themes
        except json.JSONDecodeError:
            pass

    # Fallback: bare [...] array
    if arr_start != -1:
        try:
            result, _ = json.JSONDecoder().raw_decode(text, arr_start)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No JSON themes found in response:\n{text[:300]}")


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


def normalize_for_apple(text: str) -> str:
    """Normalize text to the ASCII subset Apple Intelligence can process.

    Three-pass approach:

    1. Replace common typographic Unicode with ASCII equivalents (curly quotes
       → straight, em/en dash → hyphen, ellipsis → three dots).  Apple's
       autocorrect inserts these into virtually every English note, so without
       this step words like "it's" or phrases like "cost—benefit" are corrupted
       rather than preserved.

    2. NFD-decompose accented Latin characters, then drop the resulting
       combining marks (Unicode category Mn).  This maps "café" → "cafe",
       "naïve" → "naive", "résumé" → "resume" — the base word is kept intact.

    3. Replace any remaining non-ASCII and non-printable characters with spaces
       (keeps printable ASCII U+0020–U+007E plus tab/newline/CR); collapse runs
       of spaces.  CJK, Arabic, Cyrillic, and other non-Latin scripts become
       spaces (no transliteration in Python — the Swift bridge's
       sanitizeForAppleIntelligence does that via CFStringTransform).
    """
    if not text:
        return text
    # Pass 1: typographic substitution
    text = text.translate(_TYPOGRAPHIC_TABLE)
    # Pass 2: diacritic normalization via NFD decomposition
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


def normalize_slug_title(title: str) -> str:
    """Rewrite YYYY-MM-DD-slug titles to natural English for Apple's language detector.

    "2019-04-02-Legislative-Conference"  →  "Legislative Conference (April 2, 2019)"
    "2018-08-28-L839-AMPTP"              →  "L839 AMPTP (August 28, 2018)"

    Returns the title unchanged when it does not match the pattern or the month
    component is out of the 1–12 range.  Apply after normalize_for_apple so
    the regex always operates on clean ASCII input.
    """
    m = _ISO_SLUG_RE.match(title)
    if not m:
        return title
    year, month_str, day_str, slug = m.groups()
    month = int(month_str)
    if not 1 <= month <= 12:
        return title
    words = slug.replace("-", " ")
    return f"{words} ({_MONTH_NAMES[month - 1]} {int(day_str)}, {year})"
