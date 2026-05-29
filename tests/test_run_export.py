"""Tests for scripts/export/run_export.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.export.run_export import _strip_container_prefix, run_backup, run_export


class TestStripContainerPrefix:
    def test_strips_matching_notes(self) -> None:
        notes = [
            {"folder": "Areas", "folder_path": "Library/Areas", "parent_folder": "Library"},
            {"folder": "Resources", "folder_path": "Library/Resources", "parent_folder": "Library"},
        ]
        patched = _strip_container_prefix(notes, "Library")
        assert patched == 2
        assert notes[0]["folder_path"] == "Areas"
        assert notes[0]["parent_folder"] == ""

    def test_does_not_strip_non_matching(self) -> None:
        notes = [
            {"folder": "Work", "folder_path": "Areas/Work", "parent_folder": "Areas"},
        ]
        patched = _strip_container_prefix(notes, "Library")
        assert patched == 0
        assert notes[0]["folder_path"] == "Areas/Work"

    def test_empty_list_returns_zero(self) -> None:
        assert _strip_container_prefix([], "Library") == 0


class TestRunExport:
    def test_success_returns_export_path(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps([{"id": "1", "title": "Note", "folder": "Inbox"}]))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)
        mocker.patch("scripts.export.run_export.find_latest_export", return_value=export_file)
        mocker.patch("scripts.export.run_export.load_settings", return_value=minimal_settings)

        result = run_export()
        assert result == export_file

    def test_subprocess_failure_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "AppleScript error"
        mocker.patch("subprocess.run", return_value=mock_result)

        with pytest.raises(SystemExit):
            run_export()

    def test_container_prefix_stripped_when_enabled(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        notes = [
            {
                "id": "1",
                "title": "Note",
                "folder": "Areas",
                "folder_path": "Library/Areas",
                "parent_folder": "Library",
            },
        ]
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps(notes))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)
        mocker.patch("scripts.export.run_export.find_latest_export", return_value=export_file)

        settings_with_container = {"toplevel_folder": {"enabled": True, "name": "Library"}}
        mocker.patch(
            "scripts.export.run_export.load_settings", return_value=settings_with_container
        )

        run_export()

        patched_notes = json.loads(export_file.read_text())
        assert patched_notes[0]["folder_path"] == "Areas"


class TestRunBackup:
    def test_creates_backup_file(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps([]))

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)
        mocker.patch("scripts.export.run_export.find_latest_export", return_value=export_file)
        mocker.patch("scripts.export.run_export.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.export.run_export.REPO_ROOT", tmp_path)

        run_backup()

        backups = list((tmp_path / "data" / "backups").glob("backup-*.json"))
        assert len(backups) == 1
