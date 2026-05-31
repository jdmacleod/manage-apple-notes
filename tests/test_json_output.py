"""Tests for scripts/json_output.py — emit_result() helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.json_output import emit_result


class TestEmitResult:
    def test_ok_with_summary(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("classify", summary={"moves": 5}, log_file="/data/logs/x.json")
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ok"
        assert out["command"] == "classify"
        assert out["dry_run"] is False
        assert out["summary"] == {"moves": 5}
        assert out["log_file"] == "/data/logs/x.json"
        assert out["output_file"] is None

    def test_error_status(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("move", status="error", error="File not found", dry_run=True)
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "error"
        assert out["error"] == "File not found"
        assert out["dry_run"] is True
        assert out["command"] == "move"

    def test_dry_run_flag(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("audit", dry_run=True, output_file="/data/reports/audit.md")
        out = json.loads(capsys.readouterr().out)
        assert out["dry_run"] is True
        assert out["output_file"] == "/data/reports/audit.md"

    def test_path_objects_serialized_as_strings(self, capsys: pytest.CaptureFixture) -> None:
        emit_result(
            "export",
            output_file=Path("/data/exports/notes.json"),
            log_file=Path("/data/logs/export.json"),
        )
        out = json.loads(capsys.readouterr().out)
        assert out["output_file"] == "/data/exports/notes.json"
        assert out["log_file"] == "/data/logs/export.json"

    def test_no_error_key_when_ok(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("discover", summary={"themes_found": 12})
        out = json.loads(capsys.readouterr().out)
        assert "error" not in out

    def test_no_summary_key_when_omitted(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("move", status="error", error="boom")
        out = json.loads(capsys.readouterr().out)
        assert "summary" not in out

    def test_output_is_single_line(self, capsys: pytest.CaptureFixture) -> None:
        emit_result("classify", summary={"moves": 1})
        stdout = capsys.readouterr().out
        assert stdout.count("\n") == 1  # exactly one trailing newline
        json.loads(stdout.strip())  # must be valid JSON
