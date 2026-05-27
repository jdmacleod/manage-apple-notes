"""Python wrapper for export-notes.applescript."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import find_latest_export

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run_export() -> None:
    script = REPO_ROOT / "scripts" / "export" / "export-notes.applescript"
    with console.status("Exporting notes from Apple Notes…"):
        result = subprocess.run(["osascript", str(script)], capture_output=True, text=True)
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "unknown error").strip()
        console.print(f"[red]Export failed:[/red]\n{error}")
        raise SystemExit(1)
    export_path = find_latest_export()
    notes = json.loads(export_path.read_text())
    console.print(f"[green]Exported[/green] {len(notes)} notes → {export_path}")
