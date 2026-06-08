from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from scripts.forever_notes.arrange_folders import run_arrange

_SETTINGS_STRICT = """\
forever_notes_mode: "strict"
strict_mode:
  heavy_asterisk: "✱"
  home_note_title: "✱ Home"
  home_note_folder: null
  hub_title_prefix: "✱ "
  hub_note_folder: null
  internal_links: "text"
  folder_order: []
"""

_TAXONOMY = {
    "taxonomy": {
        "inbox": {"folder": "Inbox"},
        "projects": {"folder": "Projects"},
        "areas": {"folder": "Areas"},
        "resources": {"folder": "Resources"},
        "archive": {"folder": "Archive"},
    }
}

_SETTINGS_LOOSE = """\
forever_notes_mode: "loose"
strict_mode:
  folder_order: []
"""


def _mock_env(mocker, settings_text: str = _SETTINGS_STRICT, taxonomy: dict = _TAXONOMY):
    mocker.patch(
        "scripts.forever_notes.arrange_folders.load_settings", return_value=_parse(settings_text)
    )
    mocker.patch("scripts.forever_notes.arrange_folders.load_taxonomy", return_value=taxonomy)


def _parse(text: str) -> dict:
    import yaml

    return yaml.safe_load(text)


class TestArrangeStrictModeGuard:
    def test_exits_when_loose_mode(self, mocker):
        mocker.patch(
            "scripts.forever_notes.arrange_folders.load_settings",
            return_value=_parse(_SETTINGS_LOOSE),
        )
        mocker.patch("scripts.forever_notes.arrange_folders.load_taxonomy", return_value=_TAXONOMY)
        with pytest.raises(typer.Exit):
            run_arrange()


class TestArrangeReset:
    def test_reset_writes_empty_list(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        run_arrange(reset=True)
        written = settings_file.read_text(encoding="utf-8")
        assert "folder_order: []" in written

    def test_reset_dry_run_no_write(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        run_arrange(reset=True, dry_run=True)
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT


class TestArrangeInteractive:
    def test_empty_input_keeps_order_no_write(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        mocker.patch("typer.prompt", return_value="")
        run_arrange()
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_saves_new_order(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        # Reorder: 3 1 2 4 5 → Areas, Inbox, Projects, Resources, Archive
        mocker.patch("typer.prompt", return_value="3 1 2 4 5")
        mocker.patch("typer.confirm", return_value=True)
        run_arrange()
        written = settings_file.read_text(encoding="utf-8")
        saved = json.loads(written.split("folder_order:")[1].split("\n")[0].strip())
        assert saved == ["Areas", "Inbox", "Projects", "Resources", "Archive"]

    def test_dry_run_no_write(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        mocker.patch("typer.prompt", return_value="2 1 3 4 5")
        mocker.patch("typer.confirm", return_value=True)
        run_arrange(dry_run=True)
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_rejects_wrong_count(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        # First two inputs bad, third is empty (keep)
        mocker.patch("typer.prompt", side_effect=["1 2 3", "1 2 3 4 5 6", ""])
        run_arrange()
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_rejects_duplicates(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        mocker.patch("typer.prompt", side_effect=["1 1 2 3 4", ""])
        run_arrange()
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_rejects_out_of_range(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        mocker.patch("typer.prompt", side_effect=["1 2 3 4 9", ""])
        run_arrange()
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_cancel_confirm_no_write(self, mocker, tmp_path: Path):
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(_SETTINGS_STRICT, encoding="utf-8")
        _mock_env(mocker)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        mocker.patch("typer.prompt", return_value="2 1 3 4 5")
        mocker.patch("typer.confirm", return_value=False)
        run_arrange()
        assert settings_file.read_text(encoding="utf-8") == _SETTINGS_STRICT

    def test_drops_stale_saved_entries(self, mocker, tmp_path: Path):
        stale_settings = _SETTINGS_STRICT.replace(
            "folder_order: []",
            'folder_order: ["Inbox", "OldFolder", "Projects", "Areas", "Resources", "Archive"]',
        )
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(stale_settings, encoding="utf-8")
        _mock_env(mocker, settings_text=stale_settings)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        # "OldFolder" is gone; current order should be taxonomy dict order
        mocker.patch("typer.prompt", return_value="")
        run_arrange()
        # no write — just kept current (taxonomy order)
        assert settings_file.read_text(encoding="utf-8") == stale_settings

    def test_uses_saved_order_as_starting_point(self, mocker, tmp_path: Path):
        saved_settings = _SETTINGS_STRICT.replace(
            "folder_order: []",
            'folder_order: ["Archive", "Resources", "Areas", "Projects", "Inbox"]',
        )
        settings_file = tmp_path / "settings.local.yaml"
        settings_file.write_text(saved_settings, encoding="utf-8")
        _mock_env(mocker, settings_text=saved_settings)
        mocker.patch("scripts.forever_notes.arrange_folders.CONFIG_DIR", tmp_path)
        # Reverse back to 1 2 3 4 5 based on the saved order (which starts with Archive)
        mocker.patch("typer.prompt", return_value="5 4 3 2 1")
        mocker.patch("typer.confirm", return_value=True)
        run_arrange()
        written = settings_file.read_text(encoding="utf-8")
        saved = json.loads(written.split("folder_order:")[1].split("\n")[0].strip())
        # Saved order was Archive(1) Resources(2) Areas(3) Projects(4) Inbox(5)
        # 5 4 3 2 1 → Inbox, Projects, Areas, Resources, Archive
        assert saved == ["Inbox", "Projects", "Areas", "Resources", "Archive"]
