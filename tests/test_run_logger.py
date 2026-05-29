"""Tests for scripts/run_logger.py"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path


class TestLogsDirPath:
    def test_reads_from_settings(self) -> None:
        settings = {"paths": {"logs_dir": "data/custom-logs"}}
        result = logs_dir_path(settings)
        assert result.name == "custom-logs"
        assert result.parent.name == "data"

    def test_default_when_missing(self) -> None:
        result = logs_dir_path({})
        assert result.name == "logs"
        assert result.parent.name == "data"

    def test_default_when_none(self) -> None:
        result = logs_dir_path(None)
        assert result.name == "logs"


class TestRunLogger:
    def test_finish_writes_json_file(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logger = RunLogger("classify", logs_dir)
        path = logger.finish(summary={"notes_processed": 10, "moves": 5})
        assert path is not None
        assert path.exists()
        assert path.suffix == ".json"
        assert path.name.startswith("classify-")

    def test_log_contains_required_fields(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        path = logger.finish(summary={"notes_processed": 10})
        assert path is not None
        data = json.loads(path.read_text())
        for field in (
            "command",
            "started_at",
            "finished_at",
            "duration_seconds",
            "dry_run",
            "params",
            "summary",
            "events",
            "errors",
        ):
            assert field in data

    def test_command_field_matches(self, tmp_path: Path) -> None:
        logger = RunLogger("apply", tmp_path / "logs")
        path = logger.finish(summary={})
        assert path is not None
        assert json.loads(path.read_text())["command"] == "apply"

    def test_duration_is_positive(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        time.sleep(0.01)
        path = logger.finish(summary={})
        assert path is not None
        assert json.loads(path.read_text())["duration_seconds"] > 0

    def test_dry_run_flag_persisted(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        path = logger.finish(summary={}, dry_run=True)
        assert path is not None
        assert json.loads(path.read_text())["dry_run"] is True

    def test_dry_run_false_by_default(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        path = logger.finish(summary={})
        assert path is not None
        assert json.loads(path.read_text())["dry_run"] is False

    def test_params_stored(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        path = logger.finish(summary={}, params={"model": "gpt-4", "batch_size": 20})
        assert path is not None
        data = json.loads(path.read_text())
        assert data["params"]["model"] == "gpt-4"

    def test_events_recorded(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        logger.event("batch", batch=1, count=20, status="ok")
        logger.event("batch", batch=2, count=20, status="ok")
        path = logger.finish(summary={})
        assert path is not None
        data = json.loads(path.read_text())
        events = [e for e in data["events"] if e["kind"] == "batch"]
        assert len(events) == 2
        assert events[0]["batch"] == 1

    def test_errors_recorded(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        logger.error("batch 3 failed: timeout")
        path = logger.finish(summary={})
        assert path is not None
        data = json.loads(path.read_text())
        assert "batch 3 failed: timeout" in data["errors"]

    def test_error_also_appears_in_events(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        logger.error("something went wrong")
        path = logger.finish(summary={})
        assert path is not None
        data = json.loads(path.read_text())
        error_events = [e for e in data["events"] if e["kind"] == "error"]
        assert len(error_events) == 1
        assert error_events[0]["msg"] == "something went wrong"

    def test_write_failure_returns_none(self, tmp_path: Path) -> None:
        # Point logs_dir at an existing file (not a directory) to trigger failure
        bad_path = tmp_path / "not-a-dir"
        bad_path.write_text("I am a file")
        logger = RunLogger("classify", bad_path)
        result = logger.finish(summary={})
        assert result is None

    def test_summary_stored(self, tmp_path: Path) -> None:
        logger = RunLogger("classify", tmp_path / "logs")
        path = logger.finish(summary={"notes_processed": 42, "moves": 10})
        assert path is not None
        data = json.loads(path.read_text())
        assert data["summary"]["notes_processed"] == 42

    def test_multiple_runs_produce_separate_files(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logger1 = RunLogger("classify", logs_dir)
        time.sleep(0.01)
        logger2 = RunLogger("classify", logs_dir)
        p1 = logger1.finish(summary={})
        p2 = logger2.finish(summary={})
        assert p1 != p2 or p1 is None  # different timestamps or both failed gracefully


class TestEstimateDuration:
    def _write_log(
        self, logs_dir: Path, command: str, notes: int, duration: float, dry_run: bool = False
    ) -> None:
        from datetime import UTC, datetime

        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        record = {
            "command": command,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_seconds": duration,
            "dry_run": dry_run,
            "params": {},
            "summary": {"notes_processed": notes},
            "events": [],
            "errors": [],
        }
        (logs_dir / f"{command}-{ts}.json").write_text(json.dumps(record))

    def test_no_logs_returns_none(self, tmp_path: Path) -> None:
        result = estimate_duration("classify", 100, tmp_path / "logs")
        assert result is None

    def test_empty_logs_dir_returns_none(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        result = estimate_duration("classify", 100, logs_dir)
        assert result is None

    def test_returns_estimate_string(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=1000, duration=300.0)
        result = estimate_duration("classify", 500, logs_dir)
        assert result is not None
        assert "~" in result
        assert "based on last run" in result

    def test_dry_run_only_logs_ignored(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=1000, duration=300.0, dry_run=True)
        result = estimate_duration("classify", 500, logs_dir)
        assert result is None

    def test_zero_notes_log_skipped(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=0, duration=10.0)
        result = estimate_duration("classify", 100, logs_dir)
        assert result is None

    def test_zero_duration_log_skipped(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=100, duration=0.0)
        result = estimate_duration("classify", 50, logs_dir)
        assert result is None

    def test_different_command_not_used(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "discover", notes=1000, duration=300.0)
        result = estimate_duration("classify", 500, logs_dir)
        assert result is None

    def test_zero_n_items_returns_none(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=1000, duration=300.0)
        result = estimate_duration("classify", 0, logs_dir)
        assert result is None

    def test_minutes_format(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=100, duration=120.0)
        result = estimate_duration("classify", 100, logs_dir)
        assert result is not None
        assert "m" in result

    def test_seconds_only_format(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        self._write_log(logs_dir, "classify", notes=100, duration=45.0)
        result = estimate_duration("classify", 50, logs_dir)
        assert result is not None
        assert "s" in result

    def test_nonexistent_logs_dir_returns_none(self, tmp_path: Path) -> None:
        result = estimate_duration("classify", 100, tmp_path / "no-such-dir")
        assert result is None

    def test_corrupt_log_skipped(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "classify-2026-01-01-000000.json").write_text("not json {{{")
        result = estimate_duration("classify", 100, logs_dir)
        assert result is None
