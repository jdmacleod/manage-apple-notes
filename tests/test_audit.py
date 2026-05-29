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


class TestRunAudit:
    def _make_notes(self, count: int = 5) -> list[dict]:
        recent_date = datetime.now().isoformat()
        return [
            {
                "id": f"x-coredata://test/p{i}",
                "title": f"Note {i}",
                "body": "Some content here for testing purposes.",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": recent_date,
            }
            for i in range(count)
        ]

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
        assert "Library Statistics" in content
        assert "Duplicate Titles" in content

    def test_report_contains_all_sections(
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

        content = report_path.read_text()
        for section in [
            "Library Statistics",
            "Inactive Projects",
            "Untitled Notes",
            "Stub Notes",
            "Duplicate Titles",
            "Stale Inbox",
            "Stale Fleeting",
            "Orphaned Notes",
            "Subfolder Candidates",
        ]:
            assert section in content, f"Missing section: {section}"

    def test_stub_notes_few_words_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {  # 1 title word + 1 body word = 2 total → stub
                "id": "s1",
                "title": "Buy",
                "body": "milk",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "word_count": 1,
                "attachment_count": 0,
                "modified": datetime.now().isoformat(),
            },
            {  # 4 title words + 3 body words = 7 total → not a stub
                "id": "s2",
                "title": "Complete project overview document",
                "body": "meeting notes here",
                "folder": "Resources",
                "folder_path": "Resources",
                "word_count": 3,
                "attachment_count": 0,
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-stub.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        stub_section = content.split("## Stub Notes")[1].split("\n---\n")[0]
        assert "Buy" in stub_section
        assert "Complete project overview" not in stub_section

    def test_stub_notes_with_attachment_excluded(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {  # 1 body word, 1 attachment → not a stub (receipt/scan)
                "id": "r1",
                "title": "Receipt",
                "body": "$42.50",
                "folder": "Resources",
                "folder_path": "Resources",
                "word_count": 1,
                "attachment_count": 1,
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-receipt.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        stub_section = content.split("## Stub Notes")[1].split("\n---\n")[0]
        assert "Receipt" not in stub_section

    def test_stub_notes_in_archive_excluded(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {  # 2 total words but in Archive → excluded
                "id": "a1",
                "title": "Done",
                "body": "ok",
                "folder": "Archive",
                "folder_path": "Archive",
                "word_count": 1,
                "attachment_count": 0,
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-archive-stub.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        stub_section = content.split("## Stub Notes")[1].split("\n---\n")[0]
        assert "Done" not in stub_section

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

    def test_inactive_projects_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        old_date = (datetime.now() - timedelta(days=120)).isoformat()
        recent_date = datetime.now().isoformat()
        notes = [
            {
                "id": "p1",
                "title": "Old project note",
                "body": "work in progress",
                "folder": "Projects",
                "folder_path": "Projects",
                "modified": old_date,
            },
            {
                "id": "p2",
                "title": "Active project note",
                "body": "just updated",
                "folder": "Projects",
                "folder_path": "Projects",
                "modified": recent_date,
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-proj.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        assert "Old project note" in content
        assert "Active project note" not in content.split("## Inactive Projects")[1].split("\n---\n")[0]

    def test_untitled_notes_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "u1",
                "title": "",
                "body": "body without a title",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "modified": datetime.now().isoformat(),
            },
            {
                "id": "u2",
                "title": "Has a title",
                "body": "normal note",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-untitled.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        untitled_section = content.split("Untitled Notes")[1].split("---")[0]
        assert "Found 1" in untitled_section

    def test_orphaned_notes_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "o1",
                "title": "Orphan note",
                "body": "in a random folder",
                "folder": "RandomFolder",
                "folder_path": "RandomFolder",
                "modified": datetime.now().isoformat(),
            },
            {
                "id": "o2",
                "title": "Normal note",
                "body": "in taxonomy folder",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-orphan.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        orphan_section = content.split("## Orphaned Notes")[1].split("\n---\n")[0]
        assert "Orphan note" in orphan_section
        assert "Normal note" not in orphan_section

    def test_taxonomy_subfolder_notes_not_orphaned(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "s1",
                "title": "Subfolder note",
                "body": "in taxonomy subfolder",
                "folder": "Reference",
                "folder_path": "Resources/Reference",
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-sub.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        orphan_section = content.split("Orphaned Notes")[1].split("---")[0]
        assert "Subfolder note" not in orphan_section

    def test_statistics_section_contains_category_counts(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": f"r{i}",
                "title": f"Resource {i}",
                "body": "reference material",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            }
            for i in range(3)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-stats.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        stats_section = content.split("## Library Statistics")[1].split("\n---\n")[0]
        assert "Resources" in stats_section
        assert "Age Distribution" in stats_section

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
