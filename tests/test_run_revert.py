"""Tests for scripts/execute/run_revert.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.execute.run_revert import _build_reverse_moves, run_revert


class TestBuildReverseMoves:
    def test_swaps_origin_and_destination(self) -> None:
        proposal = {
            "moves": [
                {
                    "id": "x-coredata://abc/ICNote/p1",
                    "title": "My Note",
                    "current_folder": "Inbox",
                    "proposed_folder_path": "Resources/Technical",
                }
            ]
        }
        result = _build_reverse_moves(proposal)
        assert len(result) == 1
        assert result[0]["current_folder"] == "Resources/Technical"
        assert result[0]["proposed_folder_path"] == "Inbox"
        assert result[0]["id"] == "x-coredata://abc/ICNote/p1"
        assert result[0]["title"] == "My Note"

    def test_falls_back_to_proposed_folder_plus_subfolder(self) -> None:
        proposal = {
            "moves": [
                {
                    "id": "id1",
                    "title": "Note",
                    "current_folder": "Inbox",
                    "proposed_folder": "Resources",
                    "proposed_subfolder": "Technical",
                }
            ]
        }
        result = _build_reverse_moves(proposal)
        assert result[0]["current_folder"] == "Resources/Technical"
        assert result[0]["proposed_folder_path"] == "Inbox"

    def test_skips_entries_missing_origin(self) -> None:
        proposal = {
            "moves": [
                {
                    "id": "id1",
                    "title": "Note",
                    "current_folder": "",
                    "proposed_folder_path": "Resources/Technical",
                }
            ]
        }
        result = _build_reverse_moves(proposal)
        assert result == []

    def test_skips_entries_missing_destination(self) -> None:
        proposal = {
            "moves": [
                {
                    "id": "id1",
                    "title": "Note",
                    "current_folder": "Inbox",
                    "proposed_folder_path": "",
                    "proposed_folder": "",
                }
            ]
        }
        result = _build_reverse_moves(proposal)
        assert result == []

    def test_empty_moves_returns_empty(self) -> None:
        assert _build_reverse_moves({"moves": []}) == []

    def test_multiple_moves(self) -> None:
        proposal = {
            "moves": [
                {
                    "id": "id1",
                    "title": "A",
                    "current_folder": "Inbox",
                    "proposed_folder_path": "Areas/Finance",
                },
                {
                    "id": "id2",
                    "title": "B",
                    "current_folder": "Fleeting",
                    "proposed_folder_path": "Resources/Tools",
                },
            ]
        }
        result = _build_reverse_moves(proposal)
        assert len(result) == 2
        assert result[0]["proposed_folder_path"] == "Inbox"
        assert result[1]["proposed_folder_path"] == "Fleeting"


class TestRunRevert:
    def test_dry_run_passes_flag_to_osascript(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(
            json.dumps(
                {
                    "moves": [
                        {
                            "id": "id1",
                            "title": "Note",
                            "current_folder": "Inbox",
                            "proposed_folder_path": "Resources/Tech",
                        }
                    ]
                }
            )
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=True)

        cmd = mock_popen.call_args[0][0]
        assert "--dry-run" in cmd

    def test_reversed_proposal_passed_to_applescript(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(
            json.dumps(
                {
                    "moves": [
                        {
                            "id": "id1",
                            "title": "Note",
                            "current_folder": "Inbox",
                            "proposed_folder_path": "Resources/Tech",
                        }
                    ]
                }
            )
        )

        captured_tmp: list[str] = []

        def fake_popen(cmd: list, **kwargs: object) -> MagicMock:
            captured_tmp.append(cmd[-1])  # last arg is the temp proposal path
            mock_proc = MagicMock()
            mock_proc.stdout.readline.side_effect = ["[MOVED] Note\n", ""]
            mock_proc.returncode = 0
            mock_proc.wait.return_value = 0
            return mock_proc

        mocker.patch("subprocess.Popen", side_effect=fake_popen)
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=False)

        assert captured_tmp, "Popen was never called"
        tmp_file = Path(captured_tmp[0])
        assert not tmp_file.exists(), "Temp file should be cleaned up"

    def test_missing_proposal_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)
        with pytest.raises(SystemExit):
            run_revert(proposal_file=str(tmp_path / "nonexistent.json"), dry_run=False)

    def test_empty_moves_returns_early(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mock_popen = mocker.patch("subprocess.Popen")
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=False)

        mock_popen.assert_not_called()

    def test_no_proposal_specified_uses_latest(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        proposal = tmp_path / "proposal-latest.json"
        proposal.write_text(
            json.dumps(
                {
                    "moves": [
                        {
                            "id": "id1",
                            "title": "Note",
                            "current_folder": "Inbox",
                            "proposed_folder_path": "Resources/Tech",
                        }
                    ]
                }
            )
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_revert.find_latest_proposal", return_value=proposal)
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=None, dry_run=False)
        mock_popen.assert_called_once()

    def test_json_output_emits_json_to_stdout(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(
            json.dumps(
                {
                    "moves": [
                        {
                            "id": "id1",
                            "title": "Note",
                            "current_folder": "Inbox",
                            "proposed_folder_path": "Resources/Tech",
                        }
                    ]
                }
            )
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["[MOVED] Note\n", ""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=False, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert out["command"] == "revert"
        assert out["summary"]["moved"] == 1

    def test_json_output_error_emits_json(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_revert(
                proposal_file=str(tmp_path / "missing.json"), dry_run=False, json_output=True
            )

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["command"] == "revert"

    def test_no_proposals_found_raises(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Covers the except FileNotFoundError branch when json_output=True."""
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)
        mocker.patch(
            "scripts.execute.run_revert.find_latest_proposal",
            side_effect=FileNotFoundError("No proposals found"),
        )

        with pytest.raises(SystemExit):
            run_revert(proposal_file=None, dry_run=True, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert "No proposals" in out["error"]

    def test_skip_line_increments_skipped(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        """Covers the [SKIP] branch in the output-reading loop."""
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(
            json.dumps(
                {
                    "moves": [
                        {
                            "id": "id1",
                            "title": "Note",
                            "current_folder": "Inbox",
                            "proposed_folder_path": "Resources/Tech",
                        }
                    ]
                }
            )
        )

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "[SKIP] Note: already in Inbox\n",
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=False)
        mock_popen.assert_called_once()

    def test_json_output_empty_moves_emits_json(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text(json.dumps({"moves": []}))

        mocker.patch("subprocess.Popen")
        mocker.patch("scripts.execute.run_revert.load_settings", return_value=minimal_settings)

        run_revert(proposal_file=str(proposal), dry_run=False, json_output=True)

        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert out["command"] == "revert"
        assert out["summary"]["moved"] == 0
