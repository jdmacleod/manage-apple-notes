"""Python wrapper for export-notes.applescript."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.live import Live

from scripts.classify.classify_notes import find_latest_export, load_settings
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

_PROGRESS_FILE = Path("/tmp/notes_export_progress.tmp")
_ACCOUNT_FILE = Path("/tmp/notes_export_account.tmp")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _filter_primary_account(notes: list[dict], account_name: str) -> tuple[list[dict], int]:
    """Keep only notes from the named account. Returns (filtered_list, excluded_count)."""
    kept = [n for n in notes if n.get("account_name", "") == account_name]
    return kept, len(notes) - len(kept)


def _strip_container_prefix(notes: list[dict], container_name: str) -> int:
    """Strip the toplevel container prefix from folder_path fields.

    The AppleScript exports full paths from the account root (e.g. 'Library/Areas/Travel').
    Strip the container prefix so downstream tools see taxonomy-relative paths
    (e.g. 'Areas/Travel'). Works at any depth.
    Returns the count of notes modified.
    """
    prefix = container_name + "/"
    patched = 0
    for note in notes:
        fp = note.get("folder_path", "")
        if fp.startswith(prefix):
            note["folder_path"] = fp[len(prefix):]
            patched += 1
    return patched


def _read_export_progress() -> str:
    """Return an inline counter string like '[025/500]', or '' if not yet available."""
    try:
        text = _PROGRESS_FILE.read_text().strip()
        prefix = "DONE:" if text.startswith("DONE:") else ""
        parts = (text[5:] if prefix else text).split("/")
        current, total = int(parts[0]), int(parts[1])
        width = len(str(total))
        return f"[{current:0{width}d}/{total}]"
    except Exception:
        return ""


def run_export() -> Path:
    script = REPO_ROOT / "scripts" / "export" / "export-notes.applescript"
    settings = load_settings()

    # Write account filter to temp file so the AppleScript can apply it in both
    # the count pass (Pass 1) and the export pass (Pass 2), keeping the progress
    # denominator consistent with the final note count.
    primary_account = settings.get("export", {}).get("primary_account", "")
    if primary_account:
        _ACCOUNT_FILE.write_text(primary_account)
    else:
        _ACCOUNT_FILE.unlink(missing_ok=True)

    _PROGRESS_FILE.unlink(missing_ok=True)

    proc = subprocess.Popen(
        ["osascript", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    account_label = f" [dim]({primary_account})[/dim]" if primary_account else ""
    with Live(console=console, refresh_per_second=5, transient=True) as live:
        while proc.poll() is None:
            counter = _read_export_progress()
            live.update(f"Exporting notes from Apple Notes…{account_label} {counter}")
            time.sleep(0.2)

    _stdout, stderr = proc.communicate()
    _PROGRESS_FILE.unlink(missing_ok=True)
    _ACCOUNT_FILE.unlink(missing_ok=True)

    if proc.returncode != 0:
        error = (stderr or "unknown error").strip()
        console.print(f"[red]Export failed:[/red]\n{error}")
        raise SystemExit(1)
    export_path = find_latest_export()
    notes = json.loads(export_path.read_text())

    needs_write = False

    cfg = settings.get("toplevel_folder", {})
    if cfg.get("enabled", False):
        container_name = cfg.get("name", "Library")
        patched = _strip_container_prefix(notes, container_name)
        needs_write = True
        if patched:
            console.print(
                f"  [dim]Stripped '{container_name}/' prefix from {patched} folder path(s)[/dim]"
            )

    # Fallback filter: catches any notes from other accounts that slipped through
    # (e.g. if account_name is missing from older export data).
    if primary_account:
        notes, excluded = _filter_primary_account(notes, primary_account)
        if excluded:
            needs_write = True
            console.print(
                f"  [dim]Excluded {excluded} note(s) from other accounts "
                f"(primary_account: '{primary_account}')[/dim]"
            )

    if needs_write:
        export_path.write_text(json.dumps(notes, indent=2, ensure_ascii=False))

    console.print(f"[green]Exported[/green] {len(notes)} notes → {export_path}")
    RunLogger("export", logs_dir_path(settings)).finish(
        summary={"notes_exported": len(notes)},
        params={"export_file": str(export_path)},
    )
    return export_path


def run_backup() -> None:
    """Export notes and copy to data/backups/ with a timestamped filename."""
    export_path = run_export()
    backup_dir = REPO_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup_path = backup_dir / f"backup-{timestamp}.json"
    shutil.copy2(export_path, backup_path)
    console.print(f"[green]Backup saved[/green] → {backup_path}")
    console.print(
        "[dim]Note: this backup captures text content only — images, attachments, "
        "and formatting are not included. For full media backup use Time Machine or "
        "a clone of ~/Library/Group Containers/group.com.apple.notes/[/dim]"
    )
    settings = load_settings()
    notes = json.loads(backup_path.read_text())
    RunLogger("backup", logs_dir_path(settings)).finish(
        summary={"notes_exported": len(notes), "backup_path": str(backup_path)},
        params={"export_file": str(export_path)},
    )
