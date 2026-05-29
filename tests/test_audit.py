"""Tests for scripts/maintenance/audit.py"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.maintenance.audit import (
    _find_subfolder_candidates,
    _md_table,
    _normalize_title,
    _parse_date,
    run_audit,
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
            {"folder": "Resources", "folder_path": "Resources/Programming", "title": f"Python guide {i}"}
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=8, max_depth=3)
        assert len(candidates) >= 1

    def test_depth_two_path_excluded_when_at_max_depth(self) -> None:
        notes = [
            {"folder": "Resources", "folder_path": "Resources/Programming", "title": f"Python guide {i}"}
            for i in range(10)
        ]
        candidates = _find_subfolder_candidates(notes, {"Resources"}, min_notes=3, max_depth=2)
        assert candidates == []


class TestRunAudit:
    def _make_notes(self, count: int = 5) -> list[dict]:
        old_date = (datetime.now() - timedelta(days=200)).isoformat()
        recent_date = datetime.now().isoformat()
        notes = []
        for i in range(count):
            notes.append(
                {
                    "id": f"x-coredata://test/p{i}",
                    "title": f"Note {i}",
                    "body": "Some content here for testing purposes.",
                    "folder": "Resources",
                    "folder_path": "Resources",
                    "modified": old_date if i < 2 else recent_date,
                }
            )
        return notes

    def test_dry_run_does_not_write_report(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = self._make_notes()
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=None, dry_run=True)

        assert not list(tmp_path.glob("audit-*.md"))

    def test_real_run_writes_report(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = self._make_notes()
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-test.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        assert report_path.exists()
        content = report_path.read_text()
        assert "Library Audit" in content
        assert "Duplicate Titles" in content

    def test_duplicate_titles_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
        sample_notes: list[dict],
    ) -> None:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(sample_notes))
        report_path = tmp_path / "audit-dup.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        assert "Python typing guide" in content

    def test_missing_export_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        with pytest.raises(SystemExit):
            run_audit(
                export_file=str(tmp_path / "nonexistent.json"),
                output_override=None,
                dry_run=True,
            )
