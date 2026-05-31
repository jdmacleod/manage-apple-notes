"""Tests for note-content detection logic in run_audit (stubs, duplicates, uncategorized, etc.)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.maintenance.audit import run_audit


class TestRunAuditStubNotes:
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


class TestRunAuditOtherChecks:
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
        assert (
            "Active project note"
            not in content.split("## Inactive Projects")[1].split("\n---\n")[0]
        )

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

    def test_uncategorized_notes_detected(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # RandomFolder has no taxonomy ancestor → uncategorized, not untracked
        notes = [
            {
                "id": "o1",
                "title": "Uncategorized note",
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
        report_path = tmp_path / "audit-uncategorized.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        uncategorized_section = content.split("## Uncategorized Notes")[1].split("\n---\n")[0]
        assert "Uncategorized note" in uncategorized_section
        assert "Normal note" not in uncategorized_section


class TestRunAuditUntrackedFolders:
    def test_untracked_folder_appears_as_folder_row(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # Resources is in minimal_taxonomy; Resources/Photography is not → untracked folder
        notes = [
            {
                "id": "u1",
                "title": "Photo note",
                "body": "landscape shot",
                "folder": "Photography",
                "folder_path": "Resources/Photography",
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-untracked.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        untracked_section = content.split("## Untracked Folders")[1].split("\n---\n")[0]
        assert "Resources/Photography" in untracked_section
        # Should appear as a folder row, not in uncategorized
        uncategorized_section = content.split("## Uncategorized Notes")[1].split("\n---\n")[0]
        assert "Photo note" not in uncategorized_section

    def test_untracked_folder_groups_by_folder(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # Two notes in the same untracked folder → one table row with count 2
        notes = [
            {
                "id": f"u{i}",
                "title": f"Photo note {i}",
                "body": "content",
                "folder": "Photography",
                "folder_path": "Resources/Photography",
                "modified": datetime.now().isoformat(),
            }
            for i in range(2)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-grouped.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        untracked_section = content.split("## Untracked Folders")[1].split("\n---\n")[0]
        assert "Resources/Photography" in untracked_section
        assert untracked_section.count("Resources/Photography") == 1
        assert "2" in untracked_section

    def test_fully_foreign_folder_is_uncategorized(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # Random/Stuff — parent "Random" is not in taxonomy → uncategorized
        notes = [
            {
                "id": "f1",
                "title": "Foreign note",
                "body": "content",
                "folder": "Stuff",
                "folder_path": "Random/Stuff",
                "modified": datetime.now().isoformat(),
            },
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-foreign.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        uncategorized_section = content.split("## Uncategorized Notes")[1].split("\n---\n")[0]
        assert "Foreign note" in uncategorized_section

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
        assert "Subfolder note" not in content.split("## Untracked Folders")[1].split("\n---\n")[0]
        assert (
            "Subfolder note" not in content.split("## Uncategorized Notes")[1].split("\n---\n")[0]
        )


class TestRunAuditConservativeMode:
    def test_subfolder_candidates_suppressed_in_conservative_mode(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # 10 notes in Resources all sharing a theme — would normally trigger subfolder candidates
        notes = [
            {
                "id": f"r{i}",
                "title": f"Recipe note {i}",
                "body": "recipe cooking food ingredient",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            }
            for i in range(10)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-conservative.md"

        conservative_settings = {**minimal_settings, "reorganization_mode": "conservative"}
        mocker.patch("scripts.maintenance.audit.load_settings", return_value=conservative_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        subfolder_section = content.split("## Subfolder Candidates")[1]
        assert "conservative" in subfolder_section.lower()
        assert "Recipe note" not in subfolder_section

    def test_subfolder_candidates_shown_in_standard_mode(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        # Same 10 notes, but standard mode → subfolder candidates appear
        notes = [
            {
                "id": f"r{i}",
                "title": f"Recipe note {i}",
                "body": "recipe cooking food ingredient",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            }
            for i in range(10)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-standard.md"

        standard_settings = {**minimal_settings, "reorganization_mode": "standard"}
        mocker.patch("scripts.maintenance.audit.load_settings", return_value=standard_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        subfolder_section = content.split("## Subfolder Candidates")[1]
        # The section header should show the threshold and candidate count
        assert "flat folders" in subfolder_section


class TestRunAuditJsonOutput:
    def test_json_output_emits_summary_to_stdout(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        notes = [
            {
                "id": "n1",
                "title": "My Note",
                "body": "content",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "modified": datetime.now().isoformat(),
            }
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-test.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(
            export_file=str(export_file),
            output_override=str(report_path),
            dry_run=False,
            json_output=True,
        )

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert out["command"] == "audit"
        assert out["summary"]["notes_scanned"] == 1
        assert "output_file" in out
