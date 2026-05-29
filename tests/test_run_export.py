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
            {"folder": "Areas", "folder_path": "Library/Areas"},
            {"folder": "Resources", "folder_path": "Library/Resources"},
        ]
        patched = _strip_container_prefix(notes, "Library")
        assert patched == 2
        assert notes[0]["folder_path"] == "Areas"
        assert notes[1]["folder_path"] == "Resources"

    def test_strips_deep_paths(self) -> None:
        notes = [
            {"folder": "Atlanta", "folder_path": "Library/Areas/Travel/Atlanta"},
        ]
        patched = _strip_container_prefix(notes, "Library")
        assert patched == 1
        assert notes[0]["folder_path"] == "Areas/Travel/Atlanta"

    def test_does_not_strip_non_matching(self) -> None:
        notes = [
            {"folder": "Work", "folder_path": "Areas/Work"},
        ]
        patched = _strip_container_prefix(notes, "Library")
        assert patched == 0
        assert notes[0]["folder_path"] == "Areas/Work"

    def test_empty_list_returns_zero(self) -> None:
        assert _strip_container_prefix([], "Library") == 0


def _mock_popen(mocker: MagicMock, returncode: int = 0, stderr: str = "") -> MagicMock:
    """Return a Popen mock that immediately reports completion."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = returncode
    mock_proc.returncode = returncode
    mock_proc.communicate.return_value = ("", stderr)
    mocker.patch("subprocess.Popen", return_value=mock_proc)
    return mock_proc


class TestRunExport:
    def test_success_returns_export_path(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps([{"id": "1", "title": "Note", "folder": "Inbox"}]))

        _mock_popen(mocker)
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
        _mock_popen(mocker, returncode=1, stderr="AppleScript error")

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
            },
        ]
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps(notes))

        _mock_popen(mocker)
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

        _mock_popen(mocker)
        mocker.patch("scripts.export.run_export.find_latest_export", return_value=export_file)
        mocker.patch("scripts.export.run_export.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.export.run_export.REPO_ROOT", tmp_path)

        run_backup()

        backups = list((tmp_path / "data" / "backups").glob("backup-*.json"))
        assert len(backups) == 1
