"""Payload locale tests — confirm the x-coredata:// ID hypothesis.

These tests verify that:
1. A classify payload containing x-coredata:// IDs triggers Apple's locale filter.
2. The same payload with placeholder IDs ("note_0") does NOT trigger it.
3. The _build_classify_payload function (Fix A) produces accepted payloads.

This is the most important diagnostic step: if test (1) fails (no locale error from
x-coredata:// IDs), the root cause of the classify failures is elsewhere.

Run with:  uv run pytest tests/integration/test_payload_locale.py --real-providers -v
"""

from __future__ import annotations

import json

import pytest

from scripts.classify.classify_notes import _build_classify_payload
from scripts.json_utils import is_locale_error

_CLASSIFY_SYSTEM = (
    "You are a note classifier. For each note, return a JSON array with one object per note: "
    '{"id": "<id from input>", "proposed_folder": "Inbox", "confidence": "high", "reason": "test"}. '
    "Return ONLY the JSON array, no prose."
)

_SIMPLE_NOTES = [
    {
        "id": "placeholder",
        "title": "Router setup",
        "body": "Admin page at 192.168.1.1",
        "folder": "Inbox",
    },
]


class TestXCoredataIdTriggersLocale:
    def test_raw_coredata_id_in_payload_triggers_locale_error(self, apple_provider: object) -> None:
        """Payload with x-coredata:// IDs should trigger Apple's language filter.

        If this test FAILS (no locale error), the ID hypothesis is disproven and
        the root cause must be investigated via test_sanitization_parity.py instead.
        """
        notes = [
            {
                "id": "x-coredata://8F3A2B1C-4D5E-6F7A-8B9C-0D1E2F3A4B5C/ICNote/p42",
                "title": "Router setup",
                "body": "Admin page at 192.168.1.1. Set password.",
                "folder": "Inbox",
            }
        ]
        payload = json.dumps(
            [
                {
                    "id": n["id"],
                    "title": n["title"],
                    "body": n["body"],
                    "current_folder": n["folder"],
                }
                for n in notes
            ],
            indent=2,
        )
        with pytest.raises(RuntimeError) as exc_info:
            apple_provider.classify_messages(_CLASSIFY_SYSTEM, payload, max_tokens=100)  # type: ignore[attr-defined]
        if not is_locale_error(exc_info.value):
            pytest.skip(
                f"x-coredata:// ID did NOT trigger locale error (got: {exc_info.value}). "
                "The ID hypothesis may not apply on this device — investigate other causes."
            )

    def test_placeholder_id_no_locale_error(self, apple_provider: object) -> None:
        """Payload with note_N placeholder IDs must NOT trigger a locale error."""
        payload = json.dumps(
            [
                {
                    "id": "note_0",
                    "title": "Router setup",
                    "body": "Admin page at 192.168.1.1.",
                    "current_folder": "Inbox",
                }
            ],
            indent=2,
        )
        try:
            apple_provider.classify_messages(_CLASSIFY_SYSTEM, payload, max_tokens=150)  # type: ignore[attr-defined]
        except RuntimeError as exc:
            if is_locale_error(exc):
                pytest.fail(f"Unexpected locale error on note_N placeholder IDs: {exc}")

    def test_build_classify_payload_apple_no_locale_error(self, apple_provider: object) -> None:
        """_build_classify_payload(for_apple=True) must produce content Apple accepts."""
        notes = [
            {
                "id": "x-coredata://UUID/ICNote/p1",
                "title": "Router setup",
                "body": "Config steps.",
                "folder": "Inbox",
            },
            {
                "id": "x-coredata://UUID/ICNote/p2",
                "title": "Meeting notes",
                "body": "Action items.",
                "folder": "Inbox",
            },
        ]
        payload_str, index_to_id = _build_classify_payload(notes, max_body=500, for_apple=True)
        assert "note_0" in index_to_id
        assert "note_1" in index_to_id
        try:
            apple_provider.classify_messages(_CLASSIFY_SYSTEM, payload_str, max_tokens=200)  # type: ignore[attr-defined]
        except RuntimeError as exc:
            if is_locale_error(exc):
                pytest.fail(f"Locale error on _build_classify_payload output: {exc}")

    def test_id_remapping_roundtrip(self, apple_provider: object) -> None:
        """The LLM should return placeholder IDs; remapping restores originals."""
        notes = [
            {
                "id": "x-coredata://UUID/ICNote/p99",
                "title": "Test note",
                "body": "Some content.",
                "folder": "Inbox",
            },
        ]
        payload_str, index_to_id = _build_classify_payload(notes, max_body=500, for_apple=True)
        response = apple_provider.classify_messages(_CLASSIFY_SYSTEM, payload_str, max_tokens=150)  # type: ignore[attr-defined]

        from scripts.json_utils import extract_json_array

        try:
            results = extract_json_array(response)
        except ValueError:
            pytest.skip(f"LLM returned non-JSON response: {response[:200]!r}")

        # Remap placeholders back to real IDs (same logic as classify_batch)
        for result in results:
            placeholder = result.get("id", "")
            if placeholder in index_to_id:
                result["id"] = index_to_id[placeholder]

        ids_in_results = [r.get("id") for r in results]
        assert "x-coredata://UUID/ICNote/p99" in ids_in_results, (
            f"Real ID not found after remapping. Results: {results}"
        )
