"""Structured JSON output for agent-friendly CLI use.

When --json is passed to any command, this module emits a single compact JSON
line to stdout summarising the result.  Human-readable output goes to stderr.
"""

from __future__ import annotations

import json
from pathlib import Path


def emit_result(
    command: str,
    *,
    status: str = "ok",
    dry_run: bool = False,
    output_file: str | Path | None = None,
    log_file: str | Path | None = None,
    summary: dict | None = None,
    error: str | None = None,
) -> None:
    """Print a compact JSON result to stdout for agent consumption."""
    result: dict[str, object] = {
        "status": status,
        "command": command,
        "dry_run": dry_run,
        "output_file": str(output_file) if output_file else None,
        "log_file": str(log_file) if log_file else None,
    }
    if summary is not None:
        result["summary"] = summary
    if error is not None:
        result["error"] = error
    print(json.dumps(result))
