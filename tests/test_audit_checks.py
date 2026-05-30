"""Unit tests for pure-function helpers in scripts/maintenance/audit.py."""

from __future__ import annotations

from datetime import datetime

from scripts.maintenance.audit import (
    _find_subfolder_candidates,
    _md_table,
    _normalize_title,
    _parse_date,
)


class TestParseDate:
    def test_valid_iso_date(self) -> None:
        result = _parse_date("2026-05-01T10:00:00")
        assert isinstance(result, datetime)
        assert result.year == 2026

    def test_iso_date_with_z_suffix(self) -> None:
        result = _parse_date("2026-05-01T10:00:00Z")
        assert isinstance(result, datetime)

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_date("not-a-date") is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_date("") is None

    def test_none_returns_none(self) -> None:
        assert _parse_date(None) is None  # type: ignore[arg-type]


class TestNormalizeTitle:
    def test_lowercases(self) -> None:
        assert _normalize_title("HELLO WORLD") == "hello world"

    def test_strips_punctuation(self) -> None:
        assert _normalize_title("Hello, World!") == "hello world"

    def test_collapses_whitespace(self) -> None:
        assert _normalize_title("  too   many   spaces  ") == "too many spaces"

    def test_unicode_normalization(self) -> None:
        result = _normalize_title("Café Notes")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_duplicate_detection_equivalence(self) -> None:
        assert _normalize_title("Python Guide") == _normalize_title("Python Guide")
        assert _normalize_title("Python Guide!") == _normalize_title("Python Guide")


class TestMdTable:
    def test_empty_list_returns_none_line(self) -> None:
        result = _md_table([], [("Title", "title")])
        assert "_None._" in result[0]

    def test_generates_header_and_rows(self) -> None:
        items = [{"title": "Test Note", "folder": "Inbox"}]
        cols = [("Title", "title"), ("Folder", "folder")]
        result = _md_table(items, cols)
        assert any("Title" in line and "Folder" in line for line in result)
        assert any("Test Note" in line for line in result)

    def test_escapes_pipe_in_content(self) -> None:
        items = [{"title": "A|B", "folder": "Inbox"}]
        result = _md_table(items, [("Title", "title")])
        assert any("A\\|B" in line for line in result)


class TestFindSubfolderCandidates:
    def test_finds_candidate_above_threshold(self) -> None:
        notes = [
            {"folder": "Resources", "folder_path": "Resources", "title": f"Python guide {i}"}
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=8)
        assert len(candidates) >= 1
        assert candidates[0]["folder"] == "Resources"

    def test_below_threshold_not_included(self) -> None:
        notes = [
            {"folder": "Resources", "folder_path": "Resources", "title": "Python guide 1"},
            {"folder": "Resources", "folder_path": "Resources", "title": "Python guide 2"},
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=8)
        assert candidates == []

    def test_ignores_notes_with_subfolder_path(self) -> None:
        notes = [
            {"folder": "Reference", "folder_path": "Resources/Reference", "title": f"Note {i}"}
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=3)
        assert candidates == []

    def test_unknown_folder_not_candidate(self) -> None:
        notes = [
            {"folder": "UnknownFolder", "folder_path": "UnknownFolder", "title": f"Note {i}"}
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Inbox"}, min_notes=3)
        assert candidates == []

    def test_depth_two_path_candidate_when_max_depth_three(self) -> None:
        notes = [
            {
                "folder": "Resources",
                "folder_path": "Resources/Programming",
                "title": f"Python guide {i}",
            }
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=8, max_depth=3)
        assert len(candidates) >= 1

    def test_depth_two_path_excluded_when_at_max_depth(self) -> None:
        notes = [
            {
                "folder": "Resources",
                "folder_path": "Resources/Programming",
                "title": f"Python guide {i}",
            }
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=3, max_depth=2)
        assert candidates == []
