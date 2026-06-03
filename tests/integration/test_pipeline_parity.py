"""Full pipeline parity tests — Apple vs Ollama side-by-side.

Runs classify_batch_resilient() with the same small note batch against both
providers and compares results for validity (not identity — the two models will
choose different folders).

Run with:  uv run pytest tests/integration/test_pipeline_parity.py --real-providers -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.classify.classify_notes import (
    classify_batch_resilient,
    inject_taxonomy,
    load_prompt_template,
)
from scripts.config import load_settings, load_taxonomy

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SYNTHETIC_NOTES: list[dict[str, Any]] = [
    {
        "id": "x-coredata://TEST-UUID/ICNote/p1",
        "title": "Python async patterns",
        "body": "Notes on asyncio event loop, tasks, and gather().",
        "folder": "Inbox",
        "folder_path": "Inbox",
    },
    {
        "id": "x-coredata://TEST-UUID/ICNote/p2",
        "title": "Quarterly budget review",
        "body": "Q3 expenses: travel $2,400, software $800, misc $320.",
        "folder": "Inbox",
        "folder_path": "Inbox",
    },
    {
        "id": "x-coredata://TEST-UUID/ICNote/p3",
        "title": "Sourdough bread recipe",
        "body": "150g starter, 400g flour, 300g water, 10g salt. Autolyse 1hr.",
        "folder": "Inbox",
        "folder_path": "Inbox",
    },
]


@pytest.fixture(scope="module")
def classify_system_prompt() -> str:
    settings = load_settings()
    taxonomy = load_taxonomy()
    return inject_taxonomy(load_prompt_template(), taxonomy, settings)


def _validate_classify_results(results: list[dict], note_count: int) -> None:
    assert isinstance(results, list), f"Results must be a list, got {type(results)}"
    assert len(results) == note_count, (
        f"Expected {note_count} classification results, got {len(results)}"
    )
    for r in results:
        assert r.get("id"), f"Result missing 'id': {r}"
        assert r.get("proposed_folder"), f"Result missing 'proposed_folder': {r}"
        assert r.get("confidence") in ("high", "medium", "low"), (
            f"Invalid confidence in result: {r}"
        )


class TestClassifyBatchApple:
    def test_classifies_ascii_notes_without_locale_error(
        self, apple_provider: object, classify_system_prompt: str
    ) -> None:
        results = classify_batch_resilient(
            apple_provider,  # type: ignore[arg-type]
            _SYNTHETIC_NOTES,
            classify_system_prompt,
            settings={},
        )
        _validate_classify_results(results, len(_SYNTHETIC_NOTES))

    def test_classifies_mixed_ascii_unicode_notes(
        self, apple_provider: object, classify_system_prompt: str
    ) -> None:
        # Notes with curly quotes and em-dashes (Apple autocorrect artifacts)
        notes_with_unicode = [
            {
                **_SYNTHETIC_NOTES[0],
                "title": "Python “async” patterns — deep dive",
                "body": "It’s about asyncio… see docs.",
            }
        ]
        results = classify_batch_resilient(
            apple_provider,  # type: ignore[arg-type]
            notes_with_unicode,
            classify_system_prompt,
            settings={},
        )
        _validate_classify_results(results, 1)

    def test_response_ids_match_input_ids(
        self, apple_provider: object, classify_system_prompt: str
    ) -> None:
        notes = [_SYNTHETIC_NOTES[0]]
        results = classify_batch_resilient(
            apple_provider,  # type: ignore[arg-type]
            notes,
            classify_system_prompt,
            settings={},
        )
        if results:
            assert results[0]["id"] == notes[0]["id"], (
                f"ID mismatch: expected {notes[0]['id']!r}, got {results[0]['id']!r}. "
                "ID remapping may be broken."
            )


class TestClassifyBatchOllama:
    def test_classifies_ascii_notes(
        self, ollama_provider: object, classify_system_prompt: str
    ) -> None:
        results = classify_batch_resilient(
            ollama_provider,  # type: ignore[arg-type]
            _SYNTHETIC_NOTES,
            classify_system_prompt,
            settings={},
        )
        _validate_classify_results(results, len(_SYNTHETIC_NOTES))

    def test_response_ids_match_input_ids(
        self, ollama_provider: object, classify_system_prompt: str
    ) -> None:
        notes = [_SYNTHETIC_NOTES[0]]
        results = classify_batch_resilient(
            ollama_provider,  # type: ignore[arg-type]
            notes,
            classify_system_prompt,
            settings={},
        )
        if results:
            assert results[0]["id"] == notes[0]["id"]


class TestMalformedResponseHandling:
    def test_apple_context_overflow_splits_batch(self, apple_provider: object) -> None:
        # Exceed the 4096-token context by sending a batch with very long body text.
        # The resilient wrapper should split rather than silently drop.
        long_notes = [
            {
                "id": f"x-coredata://UUID/ICNote/p{i}",
                "title": f"Note {i}",
                "body": "The quick brown fox jumps over the lazy dog. " * 200,
                "folder": "Inbox",
                "folder_path": "Inbox",
            }
            for i in range(4)
        ]
        system = (
            "Classify each note. Return a JSON array: "
            '[{"id":"<id>","proposed_folder":"Inbox","confidence":"high","reason":"test"}]'
        )
        # Should not raise — overflow triggers splitting, not a crash
        results = classify_batch_resilient(
            apple_provider,  # type: ignore[arg-type]
            long_notes,
            system,
            settings={"export": {"max_body_chars": 2000}},
        )
        assert isinstance(results, list)
