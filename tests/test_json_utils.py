"""Tests for scripts/json_utils.py."""

from __future__ import annotations

import pytest

from scripts.json_utils import (
    extract_json_array,
    extract_json_object,
    is_context_overflow,
    is_locale_error,
    strip_unsupported_chars,
)


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


class TestIsLocaleError:
    def test_detects_apple_unsupported_locale(self) -> None:
        assert is_locale_error(RuntimeError("apple_unsupported_locale")) is True

    def test_unrelated_error_is_false(self) -> None:
        assert is_locale_error(Exception("context_length exceeded")) is False

    def test_empty_message_is_false(self) -> None:
        assert is_locale_error(Exception("")) is False


class TestStripUnsupportedChars:
    def test_ascii_text_unchanged(self) -> None:
        assert strip_unsupported_chars("Hello world!") == "Hello world!"

    def test_diacritics_normalized_to_ascii_base(self) -> None:
        # NFD decomposition strips the combining mark, keeping the base letter.
        # Words are preserved intact rather than corrupted by spaces at each accent.
        result = strip_unsupported_chars("café résumé naïve")
        assert result == "cafe resume naive"

    def test_accented_word_preserved_intact(self) -> None:
        # Before: "café" → "caf" (accent became a space, word corrupted).
        # After:  "café" → "cafe" (combining accent dropped, base letter kept).
        assert strip_unsupported_chars("café") == "cafe"

    def test_typographic_chars_converted_to_ascii(self) -> None:
        # Curly quotes, em dash, and ellipsis inserted by Apple autocorrect.
        # Before: "it’s" → "it s" (word split at the typographic apostrophe).
        # After:  "it’s" → "it's" (U+2019 mapped to straight apostrophe first).
        text = "it’s “great”—really…"
        assert strip_unsupported_chars(text) == 'it\'s "great"-really...'

    def test_curly_apostrophe_preserves_contraction(self) -> None:
        assert strip_unsupported_chars("it’s") == "it's"
        assert strip_unsupported_chars("don’t") == "don't"

    def test_curly_quotes_converted(self) -> None:
        assert strip_unsupported_chars("“hello”") == '"hello"'

    def test_em_dash_converted_to_hyphen(self) -> None:
        assert strip_unsupported_chars("cost—benefit") == "cost-benefit"

    def test_ellipsis_converted(self) -> None:
        assert strip_unsupported_chars("really…") == "really..."

    def test_cjk_replaced_and_spaces_collapsed(self) -> None:
        result = strip_unsupported_chars("Hello 日本語 world")
        assert result == "Hello world"

    def test_arabic_stripped(self) -> None:
        result = strip_unsupported_chars("test مرحبا end")
        assert result == "test end"

    def test_empty_string_returns_empty(self) -> None:
        assert strip_unsupported_chars("") == ""

    def test_mixed_script_collapses_to_single_spaces(self) -> None:
        result = strip_unsupported_chars("Title 日本語 and 中文 content")
        assert result == "Title and content"

    def test_all_unsupported_returns_empty(self) -> None:
        result = strip_unsupported_chars("日本語")
        assert result == ""

    def test_non_printable_ascii_control_chars_stripped(self) -> None:
        assert strip_unsupported_chars("hello\x01world") == "hello world"
        assert strip_unsupported_chars("hello\x1b[0mworld") == "hello [0mworld"

    def test_tab_and_newline_preserved(self) -> None:
        result = strip_unsupported_chars("line1\n\tindented\r\nline2")
        assert result == "line1\n\tindented\r\nline2"

    def test_del_char_stripped(self) -> None:
        result = strip_unsupported_chars("before\x7fafter")
        assert result == "before after"
