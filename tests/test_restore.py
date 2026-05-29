"""Tests for scripts/restore/run_restore.py"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.restore.run_restore import _build_restore_entries, _find_latest, run_restore


class TestFindLatest:
    def test_returns_newest_matching_file(self, tmp_path: Path) -> None:
        older = tmp_path / "notes-2026-05-01.json"
        newer = tmp_path / "notes-2026-05-28.json"
        older.write_text("{}")
        time.sleep(0.01)
        newer.write_text("{}")

        result = _find_latest(tmp_path, "notes-*.json")
        assert result == newer

    def test_raises_when_no_match(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _find_latest(tmp_path, "notes-*.json")


class TestBuildRestoreEntries:
    def test_basic_merge(self) -> None:
        backup_notes = [
            {"title": "Router setup", "body": "Hold reset button for 10s."},
            {"title": "Cake recipe", "body": "Mix flour, eggs, butter."},
        ]
        proposal_destinations = {
            "Router setup": {"proposed_folder": "Resources", "proposed_subfolder": "Reference"},
        }
        entries = _build_restore_entries(backup_notes, None, proposal_destinations)
        assert len(entries) == 1
        assert entries[0]["title"] == "Router setup"
        assert entries[0]["body"] == "Hold reset button for 10s."
        assert entries[0]["folder_path"] == "Resources/Reference"

    def test_missing_titles_filter(self) -> None:
        backup_notes = [
            {"title": "Router setup", "body": "Hold reset."},
            {"title": "Cake recipe", "body": "Mix flour."},
        ]
        proposal_destinations = {
            "Router setup": {"proposed_folder": "Resources", "proposed_subfolder": None},
            "Cake recipe": {"proposed_folder": "Areas", "proposed_subfolder": None},
        }
        missing_titles = {"Router setup"}
        entries = _build_restore_entries(backup_notes, missing_titles, proposal_destinations)
        assert len(entries) == 1
        assert entries[0]["title"] == "Router setup"

    def test_deduplicates_same_title_folder_combination(self) -> None:
        backup_notes = [{"title": "Note A", "body": "Body"}]
        proposal_destinations = {
            "Note A": {"proposed_folder": "Inbox", "proposed_subfolder": None},
        }
        entries = _build_restore_entries(backup_notes, None, proposal_destinations)
        assert len(entries) == 1

    def test_missing_body_defaults_to_empty(self) -> None:
        backup_notes = [{"title": "Empty Note"}]
        proposal_destinations = {
            "Empty Note": {"proposed_folder": "Inbox", "proposed_subfolder": None},
        }
        entries = _build_restore_entries(backup_notes, None, proposal_destinations)
        assert entries[0]["body"] == ""


class TestRunRestore:
    def test_dry_run_calls_popen_with_dry_run_flag(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        backup_file = tmp_path / "backup-2026-05-28.json"
        backup_notes = [{"title": "Router setup", "body": "Hold reset.", "folder": "Resources"}]
        backup_file.write_text(json.dumps(backup_notes))

        missing_data = {
            "notes": [
                {
                    "title": "Router setup",
                    "proposed_folder": "Resources",
                    "proposed_subfolder": None,
                }
            ]
        }
        missing_file = tmp_path / "missing-notes-test.json"
        missing_file.write_text(json.dumps(missing_data))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[DRY RUN] Router setup\n", ""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)

        run_restore(backup_file=str(backup_file), missing_file=str(missing_file), dry_run=True)

        cmd = mock_popen.call_args[0][0]
        assert "--dry-run" in cmd

    def test_nothing_to_restore_returns_early(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        backup_file = tmp_path / "backup-test.json"
        backup_file.write_text(json.dumps([]))

        missing_data = {"notes": []}
        missing_file = tmp_path / "missing-notes-test.json"
        missing_file.write_text(json.dumps(missing_data))

        mock_popen = mocker.patch("subprocess.Popen")

        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)

        run_restore(backup_file=str(backup_file), missing_file=str(missing_file), dry_run=True)
        mock_popen.assert_not_called()

    def test_missing_backup_file_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_restore(backup_file=str(tmp_path / "nonexistent.json"), dry_run=False)
