"""Smoke tests for scripts/cli.py (Typer app wiring)."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from scripts.cli import app

runner = CliRunner()


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
