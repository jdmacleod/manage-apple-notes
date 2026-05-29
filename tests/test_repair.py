"""Tests for scripts/maintenance/repair_restored_notes.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.maintenance.repair_restored_notes import (
    _find_missing_notes_file,
    _find_old_export,
    _plaintext_to_html,
    _repair_note,
    run_repair_restored,
)


class TestPlaintextToHtml:
    def test_single_line(self) -> None:
        result = _plaintext_to_html("Hello World")
        assert result == "<div>Hello World</div>"

    def test_multiline_becomes_divs(self) -> None:
        result = _plaintext_to_html("Line 1\nLine 2\nLine 3")
        assert "<div>Line 1</div>" in result
        assert "<div>Line 2</div>" in result
        assert "<div>Line 3</div>" in result

    def test_empty_lines_become_br(self) -> None:
        result = _plaintext_to_html("Line 1\n\nLine 3")
        assert "<div><br></div>" in result

    def test_escapes_html_special_chars(self) -> None:
        result = _plaintext_to_html("a < b & c > d")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_nbsp_replaced_with_space(self) -> None:
        result = _plaintext_to_html("word\xa0word")
        assert "\xa0" not in result
        assert "word word" in result


class TestFindMissingNotesFile:
    def test_returns_most_recent_file(self, mocker: MagicMock, tmp_path: Path) -> None:
        f1 = tmp_path / "missing-notes-2026-05-01.json"
        f2 = tmp_path / "missing-notes-2026-05-28.json"
        f1.write_text("{}")
        f2.write_text("{}")
        mocker.patch("scripts.maintenance.repair_restored_notes.DATA_DIR", tmp_path)

        result = _find_missing_notes_file()
        assert result is not None
        assert result.name == "missing-notes-2026-05-28.json"

    def test_returns_none_when_no_files(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.maintenance.repair_restored_notes.DATA_DIR", tmp_path)
        assert _find_missing_notes_file() is None


class TestFindOldExport:
    def test_returns_file_that_is_not_current(self, mocker: MagicMock, tmp_path: Path) -> None:
        current = tmp_path / "notes-2026-05-28.json"
        older = tmp_path / "notes-2026-05-01.json"
        current.write_text("{}")
        older.write_text("{}")
        mocker.patch("scripts.maintenance.repair_restored_notes.EXPORTS_DIR", tmp_path)

        result = _find_old_export(current)
        assert result == older

    def test_returns_none_when_only_current(self, mocker: MagicMock, tmp_path: Path) -> None:
        current = tmp_path / "notes-2026-05-28.json"
        current.write_text("{}")
        mocker.patch("scripts.maintenance.repair_restored_notes.EXPORTS_DIR", tmp_path)

        result = _find_old_export(current)
        assert result is None


class TestRepairNote:
    def test_dry_run_returns_dry_run_status(self) -> None:
        status = _repair_note("Test Note", "<div>body</div>", dry_run=True)
        assert status == "[DRY RUN]"

    def test_success_returns_updated_status(self, mocker: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok:1"
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        status = _repair_note("Test Note", "<div>body</div>", dry_run=False)
        assert "updated" in status

    def test_nonzero_exit_returns_error(self, mocker: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Note not found"
        mocker.patch("subprocess.run", return_value=mock_result)

        status = _repair_note("Test Note", "<div>body</div>", dry_run=False)
        assert "error" in status.lower()


class TestRunRepairRestored:
    def test_dry_run_reports_titles(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        missing_data = {"notes": [{"title": "Router setup"}, {"title": "Cake recipe"}]}
        missing_file = tmp_path / "missing-notes-test.json"
        missing_file.write_text(json.dumps(missing_data))

        old_notes = [
            {"title": "Router setup", "body": "Hold reset button.\nDefault: admin/admin."},
            {"title": "Cake recipe", "body": "Mix flour, eggs, butter."},
        ]
        old_export = tmp_path / "notes-2026-05-01.json"
        old_export.write_text(json.dumps(old_notes))

        mock_run = mocker.patch("subprocess.run")

        run_repair_restored(
            missing_file=str(missing_file),
            old_export_file=str(old_export),
            dry_run=True,
        )

        mock_run.assert_not_called()

    def test_no_missing_file_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        mocker.patch("scripts.maintenance.repair_restored_notes.DATA_DIR", tmp_path)
        with pytest.raises(SystemExit):
            run_repair_restored(missing_file=None, old_export_file=None, dry_run=False)

    def test_title_not_in_old_export_is_skipped(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        missing_data = {"notes": [{"title": "Unknown Note"}]}
        missing_file = tmp_path / "missing-notes-test.json"
        missing_file.write_text(json.dumps(missing_data))

        old_notes: list[dict] = []
        old_export = tmp_path / "notes-old.json"
        old_export.write_text(json.dumps(old_notes))

        mock_run = mocker.patch("subprocess.run")

        run_repair_restored(
            missing_file=str(missing_file),
            old_export_file=str(old_export),
            dry_run=False,
        )

        mock_run.assert_not_called()
