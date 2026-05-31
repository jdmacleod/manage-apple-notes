"""Tests for scripts/config.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.config import (
    find_latest_export,
    load_settings,
    load_taxonomy,
    local_taxonomy_exists,
    reorganization_mode,
)


class TestLoadSettings:
    def test_returns_dict_when_local_present(self, tmp_path: Path, mocker) -> None:
        local = tmp_path / "settings.local.yaml"
        local.write_text("llm:\n  provider: anthropic\n")
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_settings()
        assert isinstance(result, dict)
        assert result.get("llm", {}).get("provider") == "anthropic"

    def test_returns_empty_dict_when_no_files(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_settings()
        assert result == {}

    def test_warns_to_stderr_when_no_local_file(
        self, tmp_path: Path, mocker, capsys
    ) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        load_settings()
        captured = capsys.readouterr()
        assert "settings.local.yaml" in captured.err
        assert "cp config/settings.example.yaml" in captured.err


class TestLoadTaxonomy:
    def test_returns_dict_when_local_present(self, tmp_path: Path, mocker) -> None:
        local = tmp_path / "taxonomy.local.yaml"
        local.write_text("taxonomy:\n  inbox:\n    folder: Inbox\n")
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_taxonomy()
        assert isinstance(result, dict)
        assert result["taxonomy"]["inbox"]["folder"] == "Inbox"

    def test_returns_empty_dict_when_no_files(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_taxonomy()
        assert result == {}


class TestLocalTaxonomyExists:
    def test_returns_true_when_local_file_present(self, tmp_path: Path, mocker) -> None:
        (tmp_path / "taxonomy.local.yaml").write_text("taxonomy: {}\n")
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        assert local_taxonomy_exists() is True

    def test_returns_false_when_local_file_absent(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        assert local_taxonomy_exists() is False


class TestReorganizationMode:
    def test_defaults_to_standard(self) -> None:
        assert reorganization_mode(None) == "standard"
        assert reorganization_mode({}) == "standard"

    def test_reads_explicit_values(self) -> None:
        assert reorganization_mode({"reorganization_mode": "conservative"}) == "conservative"
        assert reorganization_mode({"reorganization_mode": "standard"}) == "standard"
        assert reorganization_mode({"reorganization_mode": "full"}) == "full"

    def test_empty_string_falls_back_to_standard(self) -> None:
        assert reorganization_mode({"reorganization_mode": ""}) == "standard"


class TestFindLatestExport:
    def test_raises_when_no_files(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.EXPORTS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError, match="uv run notes export"):
            find_latest_export()

    def test_returns_latest_file(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.EXPORTS_DIR", tmp_path)
        older = tmp_path / "notes-2025-01-01.json"
        newer = tmp_path / "notes-2025-06-01.json"
        older.write_text(json.dumps([]))
        newer.write_text(json.dumps([]))
        result = find_latest_export()
        assert result == newer

    def test_returns_single_file(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.EXPORTS_DIR", tmp_path)
        f = tmp_path / "notes-2025-01-01.json"
        f.write_text(json.dumps([]))
        result = find_latest_export()
        assert result == f
