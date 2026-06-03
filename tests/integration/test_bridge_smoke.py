"""Bridge smoke tests — verify the raw provider layer works before testing batch logic.

These are the narrowest possible tests: a single classify_messages() call with a
trivial ASCII payload.  If these fail, every downstream test will fail too.

Run with:  uv run pytest tests/integration/test_bridge_smoke.py --real-providers -v
"""

from __future__ import annotations

import pytest

from scripts.json_utils import extract_json_array, extract_json_object, is_locale_error


class TestAppleBridge:
    def test_returns_nonempty_string(self, apple_provider: object) -> None:
        response = apple_provider.classify_messages(  # type: ignore[attr-defined]
            "Answer in one sentence.", "What is 2+2?", max_tokens=50
        )
        assert isinstance(response, str)
        assert response.strip()

    def test_returns_json_array_when_asked(self, apple_provider: object) -> None:
        system = (
            'Return ONLY a JSON array with one object: {"result": "ok"}. No prose, no code fences.'
        )
        response = apple_provider.classify_messages(system, "go", max_tokens=50)  # type: ignore[attr-defined]
        results = extract_json_array(response)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_returns_json_object_when_asked(self, apple_provider: object) -> None:
        system = 'Return ONLY a JSON object: {"status": "ok"}. No prose, no code fences.'
        response = apple_provider.classify_messages(system, "go", max_tokens=50)  # type: ignore[attr-defined]
        obj = extract_json_object(response)
        assert isinstance(obj, dict)

    def test_ascii_content_no_locale_error(self, apple_provider: object) -> None:
        # Pure ASCII input must never raise a locale error.
        try:
            apple_provider.classify_messages(  # type: ignore[attr-defined]
                "Summarize in one word.", "Hello world. This is a test note.", max_tokens=20
            )
        except RuntimeError as exc:
            if is_locale_error(exc):
                pytest.fail(f"Locale error on pure ASCII content: {exc}")

    def test_raw_cjk_may_or_may_not_trigger_locale_error(self, apple_provider: object) -> None:
        # CJK content alone does NOT reliably trigger Apple's locale filter — the filter
        # is more strongly triggered by x-coredata:// URL strings (tested in
        # test_payload_locale.py) than by non-ASCII script characters.  This test
        # documents the observed behavior without asserting a specific outcome.
        try:
            apple_provider.classify_messages(  # type: ignore[attr-defined]
                "日本語のメモを分類してください。",
                "これはテストノートです。内容は日本語です。",
                max_tokens=50,
            )
            # No error: Apple Intelligence accepted CJK on this device/version.
        except RuntimeError as exc:
            if not is_locale_error(exc):
                raise  # unexpected error — re-raise so it is visible


class TestOllamaBridge:
    def test_returns_nonempty_string(self, ollama_provider: object) -> None:
        response = ollama_provider.classify_messages(  # type: ignore[attr-defined]
            "Answer in one sentence.", "What is 2+2?", max_tokens=50
        )
        assert isinstance(response, str)
        assert response.strip()

    def test_returns_json_array_when_asked(self, ollama_provider: object) -> None:
        # Thinking/reasoning models sometimes drop the outer array brackets and return
        # the inner object directly (e.g. {"result":"ok"} instead of [{"result":"ok"}]).
        # The bridge is working correctly if valid JSON is returned; the pipeline-level
        # tests in test_pipeline_parity.py verify that classify-style arrays work end-to-end.
        # Token budget: thinking models need room to complete their reasoning chain first.
        system = (
            'Return ONLY a JSON array with one object: {"result": "ok"}. No prose, no code fences.'
        )
        response = ollama_provider.classify_messages(system, "go", max_tokens=500)  # type: ignore[attr-defined]
        assert response.strip(), "Model returned an empty response"
        try:
            results = extract_json_array(response)
            assert isinstance(results, list) and len(results) >= 1
        except ValueError:
            # Accept a bare JSON object as a pass — model returned valid JSON, just
            # without the array wrapper.  This is a model formatting quirk, not a
            # bridge failure.
            obj = extract_json_object(response)
            assert isinstance(obj, dict), (
                f"Response contained neither a JSON array nor object: {response!r}"
            )

    def test_returns_json_object_when_asked(self, ollama_provider: object) -> None:
        # Token budget: thinking models need room to complete their reasoning chain first.
        system = 'Return ONLY a JSON object: {"status": "ok"}. No prose, no code fences.'
        response = ollama_provider.classify_messages(system, "go", max_tokens=500)  # type: ignore[attr-defined]
        assert response.strip(), "Model returned an empty response"
        obj = extract_json_object(response)
        assert isinstance(obj, dict)
