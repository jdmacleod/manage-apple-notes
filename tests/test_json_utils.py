"""Tests for scripts/json_utils.py."""

from __future__ import annotations

import pytest

from scripts.json_utils import (
    extract_json_array,
    extract_json_object,
    is_context_overflow,
    is_locale_error,
    normalize_slug_title,
    normalize_for_apple,
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


class TestNormalizeForApple:
    def test_ascii_text_unchanged(self) -> None:
        assert normalize_for_apple("Hello world!") == "Hello world!"

    def test_diacritics_normalized_to_ascii_base(self) -> None:
        # NFD decomposition strips the combining mark, keeping the base letter.
        # Words are preserved intact rather than corrupted by spaces at each accent.
        result = normalize_for_apple("café résumé naïve")
        assert result == "cafe resume naive"

    def test_accented_word_preserved_intact(self) -> None:
        # Before: "café" → "caf" (accent became a space, word corrupted).
        # After:  "café" → "cafe" (combining accent dropped, base letter kept).
        assert normalize_for_apple("café") == "cafe"

    def test_typographic_chars_converted_to_ascii(self) -> None:
        # Curly quotes, em dash, and ellipsis inserted by Apple autocorrect.
        # Before: "it’s" → "it s" (word split at the typographic apostrophe).
        # After:  "it’s" → "it's" (U+2019 mapped to straight apostrophe first).
        text = "it’s “great”—really…"
        assert normalize_for_apple(text) == 'it\'s "great"-really...'

    def test_curly_apostrophe_preserves_contraction(self) -> None:
        assert normalize_for_apple("it’s") == "it's"
        assert normalize_for_apple("don’t") == "don't"

    def test_curly_quotes_converted(self) -> None:
        assert normalize_for_apple("“hello”") == '"hello"'

    def test_em_dash_converted_to_hyphen(self) -> None:
        assert normalize_for_apple("cost—benefit") == "cost-benefit"

    def test_ellipsis_converted(self) -> None:
        assert normalize_for_apple("really…") == "really..."

    def test_cjk_replaced_and_spaces_collapsed(self) -> None:
        result = normalize_for_apple("Hello 日本語 world")
        assert result == "Hello world"

    def test_arabic_stripped(self) -> None:
        result = normalize_for_apple("test مرحبا end")
        assert result == "test end"

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_for_apple("") == ""

    def test_mixed_script_collapses_to_single_spaces(self) -> None:
        result = normalize_for_apple("Title 日本語 and 中文 content")
        assert result == "Title and content"

    def test_all_unsupported_returns_empty(self) -> None:
        result = normalize_for_apple("日本語")
        assert result == ""

    def test_non_printable_ascii_control_chars_stripped(self) -> None:
        assert normalize_for_apple("hello\x01world") == "hello world"
        assert normalize_for_apple("hello\x1b[0mworld") == "hello [0mworld"

    def test_tab_and_newline_preserved(self) -> None:
        result = normalize_for_apple("line1\n\tindented\r\nline2")
        assert result == "line1\n\tindented\r\nline2"

    def test_del_char_stripped(self) -> None:
        result = normalize_for_apple("before\x7fafter")
        assert result == "before after"


class TestNormalizeSlugTitle:
    def test_converts_full_date_slug(self) -> None:
        assert normalize_slug_title("2019-04-02-Legislative-Conference") == (
            "Legislative Conference (April 2, 2019)"
        )

    def test_converts_acronym_slug(self) -> None:
        assert normalize_slug_title("2018-08-28-L839-AMPTP") == "L839 AMPTP (August 28, 2018)"

    def test_converts_multi_word_slug(self) -> None:
        assert normalize_slug_title("2019-02-06-IATSE-GEB-Austin") == (
            "IATSE GEB Austin (February 6, 2019)"
        )

    def test_single_word_after_date(self) -> None:
        assert normalize_slug_title("2023-01-15-Work") == "Work (January 15, 2023)"

    def test_january_maps_correctly(self) -> None:
        result = normalize_slug_title("2023-01-01-Note")
        assert "January" in result

    def test_december_maps_correctly(self) -> None:
        result = normalize_slug_title("2023-12-25-Note")
        assert "December" in result

    def test_passthrough_no_date_prefix(self) -> None:
        title = "My-Project-Notes"
        assert normalize_slug_title(title) == title

    def test_passthrough_plain_title(self) -> None:
        title = "Budget review 2024"
        assert normalize_slug_title(title) == title

    def test_passthrough_invalid_month_13(self) -> None:
        title = "2019-13-02-Something"
        assert normalize_slug_title(title) == title

    def test_passthrough_month_zero(self) -> None:
        title = "2019-00-15-Something"
        assert normalize_slug_title(title) == title

    def test_passthrough_empty_string(self) -> None:
        assert normalize_slug_title("") == ""

    def test_day_integer_strips_leading_zero(self) -> None:
        # Day 02 should appear as "2" not "02" in the output
        result = normalize_slug_title("2019-04-02-Note")
        assert "April 2, 2019" in result
        assert "April 02" not in result
