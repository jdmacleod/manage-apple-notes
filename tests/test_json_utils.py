"""Tests for scripts/json_utils.py."""

from __future__ import annotations

import pytest

from scripts.json_utils import extract_json_array, extract_json_object, is_context_overflow


class TestExtractJsonArray:
    def test_plain_array(self) -> None:
        result = extract_json_array('[{"id": "1"}]')
        assert result == [{"id": "1"}]

    def test_array_in_fences(self) -> None:
        text = '```json\n[{"id": "2"}]\n```'
        result = extract_json_array(text)
        assert result == [{"id": "2"}]

    def test_array_with_prose(self) -> None:
        text = 'Here is the result:\n[{"id": "3"}]\nDone.'
        result = extract_json_array(text)
        assert result == [{"id": "3"}]

    def test_empty_array(self) -> None:
        assert extract_json_array("[]") == []

    def test_raises_when_no_array(self) -> None:
        with pytest.raises(ValueError, match="No JSON array found"):
            extract_json_array("This is just prose.")

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(ValueError):
            extract_json_array("[not valid json")


class TestExtractJsonObject:
    def test_plain_object(self) -> None:
        result = extract_json_object('{"themes": []}')
        assert result == {"themes": []}

    def test_object_in_fences(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_object(text)
        assert result == {"key": "value"}

    def test_object_with_prose(self) -> None:
        text = 'Analysis:\n{"count": 5}\nEnd.'
        result = extract_json_object(text)
        assert result == {"count": 5}

    def test_raises_when_no_object(self) -> None:
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json_object("No JSON here at all.")

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(ValueError):
            extract_json_object("{not valid}")


class TestIsContextOverflow:
    def test_context_window_message(self) -> None:
        assert is_context_overflow(Exception("context window exceeded")) is True

    def test_context_length_message(self) -> None:
        assert is_context_overflow(Exception("context_length limit")) is True

    def test_exceed_context_message(self) -> None:
        assert is_context_overflow(Exception("exceed_context")) is True

    def test_maximum_context_message(self) -> None:
        assert is_context_overflow(Exception("maximum context size")) is True

    def test_context_size_message(self) -> None:
        assert is_context_overflow(Exception("context size too large")) is True

    def test_unrelated_error(self) -> None:
        assert is_context_overflow(Exception("network error")) is False

    def test_empty_message(self) -> None:
        assert is_context_overflow(Exception("")) is False
