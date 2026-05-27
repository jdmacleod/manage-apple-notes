"""Python wrapper for export-notes.applescript."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import find_latest_export, load_settings

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _strip_container_prefix(notes: list[dict], container_name: str) -> int:
    """Strip the toplevel container prefix from folder_path/parent_folder fields.

    Notes whose immediate parent is the container (e.g. 'Areas' inside 'All Notes')
    have parent_folder set to the container name. Strip it so downstream tools see
    clean paths that match the taxonomy (e.g. 'Areas', not 'All Notes/Areas').
    Notes in subfolders (e.g. 'Areas/Finance') are unaffected.
    Returns the count of notes modified.
    """
    patched = 0
    for note in notes:
        if note.get("parent_folder") == container_name:
            note["parent_folder"] = ""
            note["folder_path"] = note["folder"]
            patched += 1
    return patched


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

    settings = load_settings()
    cfg = settings.get("toplevel_folder", {})
    if cfg.get("enabled", False):
        container_name = cfg.get("name", "All Notes")
        patched = _strip_container_prefix(notes, container_name)
        export_path.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        if patched:
            console.print(f"  [dim]Stripped '{container_name}/' prefix from {patched} folder path(s)[/dim]")

    console.print(f"[green]Exported[/green] {len(notes)} notes → {export_path}")
