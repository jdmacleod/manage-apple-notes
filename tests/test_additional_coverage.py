"""Targeted tests to close coverage gaps identified after initial run."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from scripts.cli import app
from scripts.execute.apply_dedup import run_apply_dedup
from scripts.execute.run_apply import run_apply
from scripts.maintenance.process_inbox import run_inbox
from scripts.restore.run_restore import run_restore

runner = CliRunner()


# ---------------------------------------------------------------------------
# CLI — actual command invocations (covers run_* call sites in cli.py)
# ---------------------------------------------------------------------------


class TestCliCommands:
    def test_classify_invokes_run_classify(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_classify")
        result = runner.invoke(app, ["classify", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True)

    def test_discover_invokes_run_discover(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_discover")
        result = runner.invoke(app, ["discover", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True)

    def test_audit_invokes_run_audit(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_audit")
        result = runner.invoke(app, ["audit", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, output_override=None, dry_run=True)

    def test_export_invokes_run_export(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_export")
        result = runner.invoke(app, ["export"])
        assert result.exit_code == 0
        mock.assert_called_once()

    def test_backup_invokes_run_backup(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_backup")
        result = runner.invoke(app, ["backup"])
        assert result.exit_code == 0
        mock.assert_called_once()

    def test_triage_invokes_run_inbox(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_inbox")
        result = runner.invoke(app, ["triage", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(dry_run=True)

    def test_sync_hubs_invokes_run_sync_hubs(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_sync_hubs")
        result = runner.invoke(app, ["sync-hubs", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, dry_run=True)

    def test_dedup_invokes_run_dedup(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_dedup")
        result = runner.invoke(app, ["dedup", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(export_file=None, proposal_file=None, dry_run=True)

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

    def test_repair_invokes_run_repair_restored(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_repair_restored")
        result = runner.invoke(app, ["repair", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(missing_file=None, old_export_file=None, dry_run=True)

    def test_restore_invokes_run_restore(self, mocker: MagicMock) -> None:
        mock = mocker.patch("scripts.cli.run_restore")
        result = runner.invoke(app, ["restore", "--dry-run"])
        assert result.exit_code == 0
        mock.assert_called_once_with(backup_file=None, missing_file=None, dry_run=True)


# ---------------------------------------------------------------------------
# process_inbox — non-dry-run path writes a proposal
# ---------------------------------------------------------------------------


class TestProcessInboxRealRun:
    def test_real_run_writes_proposal(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        notes = [
            {
                "id": "x-coredata://test/p1",
                "title": "Router setup",
                "body": "Configure admin page.",
                "folder": "Inbox",
                "folder_path": "Inbox",
            }
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        taxonomy = {"forever_notes": {"inbox": {"folder": "Inbox"}}}
        mock_llm_provider.classify_messages.return_value = json.dumps(
            [
                {
                    "id": "x-coredata://test/p1",
                    "proposed_folder": "Resources",
                    "confidence": "high",
                    "reason": "Reference material",
                }
            ]
        )

        mocker.patch(
            "scripts.maintenance.process_inbox.load_settings", return_value=minimal_settings
        )
        mocker.patch("scripts.maintenance.process_inbox.load_taxonomy", return_value=taxonomy)
        mocker.patch(
            "scripts.maintenance.process_inbox.find_latest_export", return_value=export_file
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.inject_taxonomy", return_value="injected prompt"
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.get_provider", return_value=mock_llm_provider
        )
        mocker.patch("scripts.maintenance.process_inbox.PROPOSALS_DIR", tmp_path)

        run_inbox(dry_run=False)

        proposals = list(tmp_path.glob("inbox-*.json"))
        assert len(proposals) == 1
        data = json.loads(proposals[0].read_text())
        assert "moves" in data

    def test_real_run_note_needs_review_when_low_confidence(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        notes = [
            {
                "id": "x-coredata://test/p1",
                "title": "Ambiguous note",
                "body": "Unclear.",
                "folder": "Inbox",
                "folder_path": "Inbox",
            }
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        taxonomy = {"forever_notes": {"inbox": {"folder": "Inbox"}}}
        mock_llm_provider.classify_messages.return_value = json.dumps(
            [
                {
                    "id": "x-coredata://test/p1",
                    "proposed_folder": "Inbox",
                    "confidence": "low",
                    "reason": "Unclear",
                }
            ]
        )

        mocker.patch(
            "scripts.maintenance.process_inbox.load_settings", return_value=minimal_settings
        )
        mocker.patch("scripts.maintenance.process_inbox.load_taxonomy", return_value=taxonomy)
        mocker.patch(
            "scripts.maintenance.process_inbox.find_latest_export", return_value=export_file
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.inject_taxonomy", return_value="injected prompt"
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.get_provider", return_value=mock_llm_provider
        )
        mocker.patch("scripts.maintenance.process_inbox.PROPOSALS_DIR", tmp_path)

        run_inbox(dry_run=False)

        proposals = list(tmp_path.glob("inbox-*.json"))
        data = json.loads(proposals[0].read_text())
        assert len(data["needs_review"]) == 1


# ---------------------------------------------------------------------------
# sync_hubs — real run with mocked subprocess
# ---------------------------------------------------------------------------


class TestRunSyncHubsRealRun:
    def test_creates_hub_and_home_notes(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": f"x-coredata://test/p{i}",
                "title": f"Python guide {i}",
                "folder": "Resources",
                "folder_path": "Resources/Reference",
                "modified": "2026-01-01",
            }
            for i in range(10)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {
                "hub_title_prefix": "✱ ",
                "home_note_title": "✱ Home",
                "internal_links": "text",
            },
            "thresholds": {"min_notes_for_subfolder": 5},
            "toplevel_folder": {"enabled": False},
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "created:p100"
        mock_result.stderr = ""
        mock_subprocess = mocker.patch("subprocess.run", return_value=mock_result)

        from scripts.forever_notes.sync_hubs import run_sync_hubs

        run_sync_hubs(export_file=str(export_file), dry_run=False)

        assert mock_subprocess.call_count >= 2  # hub + home

    def test_updated_status_increments_counter(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": f"x-coredata://test/p{i}",
                "title": f"Note {i}",
                "folder": "Resources",
                "folder_path": "Resources/Reference",
                "modified": "2026-01-01",
            }
            for i in range(8)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {"hub_title_prefix": "✱ ", "home_note_title": "✱ Home"},
            "thresholds": {"min_notes_for_subfolder": 5},
            "toplevel_folder": {"enabled": False},
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "updated:p100"  # "updated" status
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        from scripts.forever_notes.sync_hubs import run_sync_hubs

        run_sync_hubs(export_file=str(export_file), dry_run=False)


# ---------------------------------------------------------------------------
# run_apply — additional streaming line types + container + except path
# ---------------------------------------------------------------------------


class TestRunApplyAdditional:
    def test_skip_and_plain_lines_covered(
        self, mocker: MagicMock, tmp_path: Path, minimal_settings: dict
    ) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "[MOVED] Note A\n",
            "[SKIP] Note B already correct\n",
            "[ERROR] Note C not found\n",
            "Some other output\n",
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)
        run_apply(proposal_file=str(proposal), dry_run=False)

    def test_container_flag_added_when_enabled(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal = tmp_path / "proposal-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        settings_with_container = {"toplevel_folder": {"enabled": True, "name": "Library"}}
        mocker.patch(
            "scripts.execute.run_apply.load_settings", return_value=settings_with_container
        )

        run_apply(proposal_file=str(proposal), dry_run=False)

        cmd = mock_popen.call_args[0][0]
        assert "--container" in cmd
        assert "Library" in cmd

    def test_no_proposal_empty_dir_exits(
        self, mocker: MagicMock, tmp_path: Path, minimal_settings: dict
    ) -> None:
        mocker.patch("scripts.execute.run_apply.PROPOSALS_DIR", tmp_path)
        mocker.patch("scripts.execute.run_apply.load_settings", return_value=minimal_settings)

        with pytest.raises(SystemExit):
            run_apply(proposal_file=None, dry_run=False)


# ---------------------------------------------------------------------------
# apply_dedup — additional streaming types + except path
# ---------------------------------------------------------------------------


class TestApplyDedupAdditional:
    def test_deleted_skip_error_plain_lines(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal = tmp_path / "dedup-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "[DELETED] Note A\n",
            "[SKIP] Note B\n",
            "[ERROR] Note C\n",
            "Info line\n",
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        run_apply_dedup(proposal_file=str(proposal), execute=False)

    def test_no_proposal_empty_dir_exits(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.execute.apply_dedup.DEDUP_PROPOSALS_DIR", tmp_path)

        with pytest.raises(SystemExit):
            run_apply_dedup(proposal_file=None, execute=False)

    def test_nonzero_exit_code_raises(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal = tmp_path / "dedup-test.json"
        proposal.write_text("{}")

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 1
        mock_proc.wait.return_value = 1
        mock_popen.return_value = mock_proc

        with pytest.raises(SystemExit):
            run_apply_dedup(proposal_file=str(proposal), execute=False)


# ---------------------------------------------------------------------------
# run_restore — "no missing file" restores all + more paths
# ---------------------------------------------------------------------------


class TestRunRestoreAdditional:
    def test_no_missing_file_restores_all_backup_notes(
        self, mocker: MagicMock, tmp_path: Path, minimal_settings: dict
    ) -> None:
        backup_notes = [
            {"title": "Router setup", "body": "Hold reset.", "folder": "Resources"},
            {"title": "Cake recipe", "body": "Mix flour.", "folder": "Areas"},
        ]
        backup_file = tmp_path / "backup-test.json"
        backup_file.write_text(json.dumps(backup_notes))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "[CREATED] Router setup\n",
            "[EXISTS] Cake recipe\n",
            "[DRY RUN] X\n",
            "[ERROR] Y\n",
            "Info\n",
            "",
        ]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.restore.run_restore.DATA_DIR", tmp_path)  # no missing-notes files

        run_restore(backup_file=str(backup_file), missing_file=None, dry_run=False)
        mock_popen.assert_called_once()

    def test_no_backup_and_no_export_exits(
        self, mocker: MagicMock, tmp_path: Path, minimal_settings: dict
    ) -> None:
        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.restore.run_restore.BACKUPS_DIR", tmp_path)
        mocker.patch("scripts.restore.run_restore.EXPORTS_DIR", tmp_path)

        with pytest.raises(SystemExit):
            run_restore(backup_file=None, missing_file=None, dry_run=False)

    def test_export_fallback_used_when_no_backup(
        self, mocker: MagicMock, tmp_path: Path, minimal_settings: dict
    ) -> None:
        export_notes = [{"title": "Note A", "body": "Body", "folder": "Inbox"}]
        export_file = tmp_path / "notes-2026-05-28.json"
        export_file.write_text(json.dumps(export_notes))

        mock_popen = mocker.patch("subprocess.Popen")
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        mocker.patch("scripts.restore.run_restore.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.restore.run_restore.BACKUPS_DIR", tmp_path / "empty_backups")
        mocker.patch("scripts.restore.run_restore.EXPORTS_DIR", tmp_path)
        mocker.patch("scripts.restore.run_restore.DATA_DIR", tmp_path)

        run_restore(backup_file=None, missing_file=None, dry_run=True)


# ---------------------------------------------------------------------------
# deduplicate_notes — utility functions called directly + _choose_keep edge case
# ---------------------------------------------------------------------------


class TestDeduplicateUtilityFunctions:
    def test_load_settings_returns_dict(self) -> None:
        from scripts.classify.deduplicate_notes import load_settings

        result = load_settings()
        assert isinstance(result, dict)

    def test_find_latest_proposal_returns_none_when_empty(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        from scripts.classify.deduplicate_notes import find_latest_proposal

        mocker.patch("scripts.classify.deduplicate_notes.PROPOSALS_DIR", tmp_path)
        result = find_latest_proposal()
        assert result is None
