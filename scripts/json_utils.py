"""Shared JSON extraction helpers for parsing LLM responses."""

from __future__ import annotations

import json


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
