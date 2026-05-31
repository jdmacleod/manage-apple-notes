"""Tests for scripts/execute/run_apply.py"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.execute.run_apply import find_latest_proposal, run_apply


class TestFindLatestProposal:
    def test_returns_path_when_file_exists(self, tmp_path: Path, mocker: MagicMock) -> None:
        proposal = tmp_path / "proposal-2026-05-28.json"
        proposal.write_text("{}")
        mocker.patch("scripts.execute.run_apply.PROPOSALS_DIR", tmp_path)

        result = find_latest_proposal()
        assert result == proposal

    def test_raises_when_no_files(self, tmp_path: Path, mocker: MagicMock) -> None:
        mocker.patch("scripts.execute.run_apply.PROPOSALS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            find_latest_proposal()

    def test_returns_most_recent_by_mtime(self, tmp_path: Path, mocker: MagicMock) -> None:
        mocker.patch("scripts.execute.run_apply.PROPOSALS_DIR", tmp_path)
        older = tmp_path / "proposal-2026-05-01.json"
        newer = tmp_path / "proposal-2026-05-28.json"
        older.write_text("{}")
        time.sleep(0.01)
        newer.write_text("{}")

        result = find_latest_proposal()
        assert result == newer


class TestRunApply:
    def test_with_explicit_proposal_path(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[MOVED] Note 1\n", ""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        run_apply(proposal_file=str(proposal), dry_run=False)
        mock_popen.assert_called_once()

    def test_dry_run_passes_flag_to_osascript(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        run_apply(proposal_file=str(proposal), dry_run=True)

        cmd = mock_popen.call_args[0][0]
        assert "--dry-run" in cmd

    def test_missing_proposal_file_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_apply(proposal_file=str(tmp_path / "nonexistent.json"), dry_run=False)

    def test_no_proposal_specified_uses_latest(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-latest.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.PROPOSALS_DIR", tmp_path)
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        run_apply(proposal_file=None, dry_run=False)
        mock_popen.assert_called_once()

    def test_ambiguous_line_increments_skipped(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            '[AMBIGUOUS] "Meeting Notes": 2 notes match in folder "Inbox" — skipping to avoid wrong move\n',
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mock_logger = mocker.patch("scripts.execute.run_apply.RunLogger")
        instance = mock_logger.return_value
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        run_apply(proposal_file=str(proposal), dry_run=False)

        finish_call = instance.finish.call_args
        assert finish_call[1]["summary"]["skipped"] == 1

    def test_nonzero_exit_code_raises(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[ERROR] Something failed\n", ""]
        mock_proc.returncode = 1
        mock_proc.wait.return_value = 1
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_apply(proposal_file=str(proposal), dry_run=False)

    def test_json_output_emits_json_to_stdout(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[MOVED] Note 1\n", ""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        run_apply(proposal_file=str(proposal), dry_run=False, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert out["command"] == "move"
        assert out["dry_run"] is False
        assert out["summary"]["moved"] == 1

    def test_json_output_error_path_emits_json(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_apply(proposal_file=str(tmp_path / "missing.json"), dry_run=False, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["command"] == "move"

    def test_dry_run_output_line_printed(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        """Covers the [DRY RUN] branch in the output-reading loop."""
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            '[DRY RUN] "A Note" (Inbox) → Resources/Tech\n',
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)
        run_apply(proposal_file=str(proposal), dry_run=True)
        mock_popen.assert_called_once()

    def test_json_output_no_proposals_emits_error(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Covers the json_output branch when find_latest_proposal raises."""
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)
        mocker.patch(
            "scripts.execute.run_apply.find_latest_proposal",
            side_effect=FileNotFoundError("No proposals"),
        )

        with pytest.raises(SystemExit):
            run_apply(proposal_file=None, dry_run=True, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert "No proposals" in out["error"]
