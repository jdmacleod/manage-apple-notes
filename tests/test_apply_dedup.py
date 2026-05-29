"""Tests for scripts/execute/apply_dedup.py"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.execute.apply_dedup import find_latest_dedup_proposal, run_apply_dedup


class TestFindLatestDedupProposal:
    def test_returns_path_when_file_exists(self, tmp_path: Path, mocker: MagicMock) -> None:
        proposal = tmp_path / "dedup-2026-05-28.json"
        proposal.write_text("{}")
        mocker.patch("scripts.execute.apply_dedup.DEDUP_PROPOSALS_DIR", tmp_path)

        result = find_latest_dedup_proposal()
        assert result == proposal

    def test_raises_when_no_files(self, tmp_path: Path, mocker: MagicMock) -> None:
        mocker.patch("scripts.execute.apply_dedup.DEDUP_PROPOSALS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            find_latest_dedup_proposal()

    def test_returns_most_recent_by_mtime(self, tmp_path: Path, mocker: MagicMock) -> None:
        mocker.patch("scripts.execute.apply_dedup.DEDUP_PROPOSALS_DIR", tmp_path)
        older = tmp_path / "dedup-2026-05-01.json"
        newer = tmp_path / "dedup-2026-05-28.json"
        older.write_text("{}")
        time.sleep(0.01)
        newer.write_text("{}")

        result = find_latest_dedup_proposal()
        assert result == newer


class TestRunApplyDedup:
    def test_with_explicit_proposal_path(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        proposal = tmp_path / "dedup-test.json"
        proposal.write_text(json.dumps({"groups": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[DRY RUN] Would delete Note\n", ""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        run_apply_dedup(proposal_file=str(proposal), execute=False)
        mock_popen.assert_called_once()

    def test_execute_flag_passed_to_osascript(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        proposal = tmp_path / "dedup-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        run_apply_dedup(proposal_file=str(proposal), execute=True)

        cmd = mock_popen.call_args[0][0]
        assert "--execute" in cmd

    def test_missing_proposal_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(SystemExit):
            run_apply_dedup(proposal_file=str(tmp_path / "nonexistent.json"), execute=False)

    def test_no_proposal_uses_latest(
        self,
        mocker: MagicMock,
        tmp_path: Path,
    ) -> None:
        proposal = tmp_path / "dedup-latest.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.apply_dedup.DEDUP_PROPOSALS_DIR", tmp_path)

        run_apply_dedup(proposal_file=None, execute=False)
        mock_popen.assert_called_once()
