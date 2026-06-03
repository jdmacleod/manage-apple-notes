"""Tests for scripts/cli.py (Typer app wiring and command routing)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

from typer.testing import CliRunner

from scripts.cli import app

runner = CliRunner()


# ── Help / usage smoke tests ───────────────────────────────────────────────


def test_help_returns_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Apple Notes" in result.output


def test_classify_help() -> None:
    result = runner.invoke(app, ["classify", "--help"])
    assert result.exit_code == 0
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "dry-run" in plain


def test_audit_help() -> None:
    result = runner.invoke(app, ["audit", "--help"])
    assert result.exit_code == 0


def test_sync_hubs_help() -> None:
    result = runner.invoke(app, ["sync-hubs", "--help"])
    assert result.exit_code == 0


def test_dedup_help() -> None:
    result = runner.invoke(app, ["dedup", "--help"])
    assert result.exit_code == 0


# ── Command routing — each CLI verb invokes the correct run_* function ────


class TestCliCommands:
    def test_classify_invokes_run_classify(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_classify")
        result = runner.invoke(app, ["classify", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True, json_output=False)

    def test_discover_invokes_run_discover(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_discover")
        result = runner.invoke(app, ["discover", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True, json_output=False, debug=False)

    def test_audit_invokes_run_audit(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_audit")
        result = runner.invoke(app, ["audit", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(
            export_file=None, output_override=None, dry_run=True, json_output=False
        )

    def test_export_invokes_run_export(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_export")
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0
        mock.assert_called_once_with(json_output=False)

    def test_backup_invokes_run_backup(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_backup")
        result = runner.invoke(app, ["backup"])
        assert result.exit_code == 0
        mock.assert_called_once_with(json_output=False)

    def test_triage_invokes_run_inbox(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_inbox")
        result = runner.invoke(app, ["triage", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(dry_run=True, json_output=False)

    def test_sync_hubs_invokes_run_sync_hubs(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_sync_hubs")
        result = runner.invoke(app, ["sync-hubs", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True, json_output=False)

    def test_dedup_invokes_run_dedup(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_dedup")
        result = runner.invoke(app, ["dedup", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(
            export_file=None, proposal_file=None, dry_run=True, json_output=False
        )

    def test_move_invokes_run_apply(self, mocker: MagicMock, tmp_path: Path) -> None:
        mock = mocker.patch("scripts.cli.run_apply")
        proposal = tmp_path / "proposal.json"
        proposal.write_text("{}")
        result = runner.invoke(app, ["move", str(proposal)])
        assert result.exit_code == 0
        mock.assert_called_once()

    def test_purge_invokes_run_apply_dedup(self, mocker: MagicMock, tmp_path: Path) -> None:
        mock = mocker.patch("scripts.cli.run_apply_dedup")
        proposal = tmp_path / "dedup.json"
        proposal.write_text("{}")
        result = runner.invoke(app, ["purge", str(proposal)])
        assert result.exit_code == 0
        mock.assert_called_once()

    def test_restore_invokes_run_restore(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_restore")
        result = runner.invoke(app, ["restore", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(
            backup_file=None, missing_file=None, dry_run=True, json_output=False
        )

    def test_setup_invokes_run_setup(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_setup")
        result = runner.invoke(app, ["setup", "--dry-run", "--no-corpus"])
        assert result.exit_code == 0
        mock.assert_called_once_with(dry_run=True, no_corpus=True)
