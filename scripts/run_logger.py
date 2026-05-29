"""Persistent run logging for all CLI commands.

Each command invocation writes one JSON file to data/logs/, capturing timing,
parameters, per-item events, and a summary.  The logs answer "what happened?"
and provide time estimates for future LLM-heavy runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent

_console = Console()


def logs_dir_path(settings: dict | None = None) -> Path:
    """Return the resolved logs directory path from settings, defaulting to data/logs."""
    raw: str = (settings or {}).get("paths", {}).get("logs_dir", "data/logs")
    return REPO_ROOT / raw


class RunLogger:
    """Records events and writes a JSON log file on finish()."""

    def __init__(self, command: str, logs_dir: Path) -> None:
        self.command = command
        self.logs_dir = logs_dir
        self.started_at = datetime.now(UTC)
        self._events: list[dict[str, object]] = []
        self._errors: list[str] = []

    def event(self, kind: str, **kwargs: object) -> None:
        """Append a timestamped event to the log."""
        entry: dict[str, object] = {"t": datetime.now(UTC).isoformat(), "kind": kind}
        entry.update(kwargs)
        self._events.append(entry)

    def error(self, msg: str) -> None:
        """Record an error — also appended to the events list for queryability."""
        self._errors.append(msg)
        self.event("error", msg=msg)

    def finish(
        self,
        summary: dict[str, object],
        dry_run: bool = False,
        params: dict[str, object] | None = None,
    ) -> Path | None:
        """Write the log file and return its path.  Returns None if writing fails."""
        finished_at = datetime.now(UTC)
        duration = (finished_at - self.started_at).total_seconds()
        record: dict[str, object] = {
            "command": self.command,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round(duration, 2),
            "dry_run": dry_run,
            "params": params or {},
            "summary": summary,
            "events": self._events,
            "errors": self._errors,
        }
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            ts = self.started_at.strftime("%Y-%m-%d-%H%M%S")
            log_path = self.logs_dir / f"{self.command}-{ts}.json"
            counter = 0
            while log_path.exists():
                counter += 1
                log_path = self.logs_dir / f"{self.command}-{ts}-{counter}.json"
            log_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
            return log_path
        except Exception as exc:
            _console.print(f"[dim yellow]Warning: could not write run log: {exc}[/dim yellow]")
            return None


def estimate_duration(command: str, n_items: int, logs_dir: Path) -> str | None:
    """Return a human-readable time estimate from the most recent successful log, or None.

    Reads the most recent non-dry-run log for `command` that recorded
    `summary.notes_processed > 0` and computes a projected duration for `n_items`.
    """
    if n_items <= 0:
        return None
    try:
        candidates = sorted(logs_dir.glob(f"{command}-*.json"), reverse=True)
    except OSError:
        return None

    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("dry_run"):
            continue
        notes_processed = int(data.get("summary", {}).get("notes_processed", 0))
        duration = float(data.get("duration_seconds", 0))
        if notes_processed <= 0 or duration <= 0:
            continue
        rate = duration / notes_processed
        est_seconds = rate * n_items
        last_m, last_s = divmod(int(duration), 60)
        est_m, est_s = divmod(int(est_seconds), 60)
        last_str = f"{last_m}m {last_s:02d}s" if last_m else f"{last_s}s"
        est_str = f"{est_m}m {est_s:02d}s" if est_m else f"{est_s}s"
        return f"~{est_str} (based on last run: {last_str} for {notes_processed:,} notes)"
    return None
