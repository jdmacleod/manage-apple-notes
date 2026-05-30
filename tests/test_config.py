"""Tests for scripts/config.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.config import find_latest_export, load_settings, load_taxonomy


class TestLoadSettings:
    def test_returns_dict(self) -> None:
        result = load_settings()
        assert isinstance(result, dict)

    def test_returns_empty_dict_when_no_files(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_settings()
        assert result == {}


class TestLoadTaxonomy:
    def test_returns_dict(self) -> None:
        result = load_taxonomy()
        assert isinstance(result, dict)

    def test_returns_empty_dict_when_no_files(self, tmp_path: Path, mocker) -> None:
        mocker.patch("scripts.config.CONFIG_DIR", tmp_path)
        result = load_taxonomy()
        assert result == {}


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
