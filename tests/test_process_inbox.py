"""Tests for scripts/maintenance/process_inbox.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.maintenance.process_inbox import run_inbox


class TestRunInbox:
    def test_no_inbox_folder_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        taxonomy_no_inbox = {"forever_notes": {}}
        mocker.patch(
            "scripts.maintenance.process_inbox.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.load_taxonomy", return_value=taxonomy_no_inbox
        )

        with pytest.raises(SystemExit):
            run_inbox(dry_run=True)

    def test_placeholder_inbox_folder_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        taxonomy_placeholder = {"forever_notes": {"inbox": {"folder": "[Your Inbox Folder]"}}}
        mocker.patch(
            "scripts.maintenance.process_inbox.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.load_taxonomy", return_value=taxonomy_placeholder
        )

        with pytest.raises(SystemExit):
            run_inbox(dry_run=True)

    def test_no_notes_in_inbox_returns_early(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        notes = [
            {
                "id": "p1",
                "title": "Note",
                "body": "Body",
                "folder": "Resources",
                "folder_path": "Resources",
            }
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        taxonomy = {"forever_notes": {"inbox": {"folder": "Inbox"}}}
        mocker.patch(
            "scripts.maintenance.process_inbox.load_settings", return_value=minimal_settings
        )
        mocker.patch("scripts.maintenance.process_inbox.load_taxonomy", return_value=taxonomy)
        mocker.patch(
            "scripts.maintenance.process_inbox.find_latest_export", return_value=export_file
        )
        mocker.patch(
            "scripts.maintenance.process_inbox.get_provider", return_value=mock_llm_provider
        )

        run_inbox(dry_run=True)

        mock_llm_provider.classify_messages.assert_not_called()

    def test_dry_run_makes_no_api_calls(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        notes = [
            {
                "id": "p1",
                "title": "Router setup",
                "body": "Config guide.",
                "folder": "Inbox",
                "folder_path": "Inbox",
            }
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        taxonomy = {"forever_notes": {"inbox": {"folder": "Inbox"}}}
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

        run_inbox(dry_run=True)

        mock_llm_provider.classify_messages.assert_not_called()
