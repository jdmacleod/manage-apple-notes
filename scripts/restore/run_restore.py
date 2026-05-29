"""Restore notes from a backup/export JSON.

Typical use: recover notes lost during apply operations by recreating them
from the most recent export in their correct destination folders.

Without --missing, restores ALL notes in the backup that are not currently
present in Apple Notes (matched by title within the target folder).
With --missing, only restores the notes listed in the given missing-notes JSON.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import load_settings
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUPS_DIR = REPO_ROOT / "data" / "backups"
EXPORTS_DIR = REPO_ROOT / "data" / "exports"
DATA_DIR = REPO_ROOT / "data"


def _find_latest(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No files matching '{pattern}' found in {directory}")
    return files[0]


def _build_restore_entries(
    backup_notes: list[dict],
    missing_titles: set[str] | None,
    proposal_destinations: dict[str, dict],
) -> list[dict]:
    """Join backup body content with destination info from the proposal."""
    body_by_title: dict[str, str] = {}
    for n in backup_notes:
        title = n.get("title", "")
        if title and title not in body_by_title:
            body_by_title[title] = n.get("body", "")

    entries = []
    seen: set[tuple[str, str]] = set()
    for title, dest in proposal_destinations.items():
        if missing_titles is not None and title not in missing_titles:
            continue
        body = body_by_title.get(title, "")
        # Prefer proposed_folder_path; fall back to folder + subfolder for old entries
        folder_path = dest.get("proposed_folder_path") or dest.get("folder_path") or ""
        if not folder_path:
            folder = dest.get("proposed_folder", "")
            subfolder = dest.get("proposed_subfolder") or ""
            folder_path = f"{folder}/{subfolder}" if subfolder else folder
        key = (title, folder_path)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"title": title, "body": body, "folder_path": folder_path})
    return entries


def run_restore(
    backup_file: str | None = None,
    missing_file: str | None = None,
    dry_run: bool = False,
) -> None:
    settings = load_settings()
    logger = RunLogger("restore", logs_dir_path(settings))
    tl_cfg = settings.get("toplevel_folder", {})
    container = tl_cfg.get("name", "") if tl_cfg.get("enabled", False) else ""

    # ── Locate backup ────────────────────────────────────────────────────────
    if backup_file:
        backup_path = Path(backup_file)
    else:
        # Prefer explicit backups; fall back to latest export
        try:
            backup_path = _find_latest(BACKUPS_DIR, "backup-*.json")
        except FileNotFoundError:
            try:
                backup_path = _find_latest(EXPORTS_DIR, "notes-*.json")
                console.print("[yellow]No backup found; using latest export as source.[/yellow]")
            except FileNotFoundError:
                console.print(
                    "[red]No backup or export file found. Run 'notes backup' first.[/red]"
                )
                raise SystemExit(1) from None

    if not backup_path.exists():
        console.print(f"[red]Backup not found:[/red] {backup_path}")
        raise SystemExit(1)

    console.print(f"Restore source: [dim]{backup_path.name}[/dim]")
    with open(backup_path) as f:
        backup_notes: list[dict] = json.load(f)
    console.print(f"  {len(backup_notes)} notes in backup")

    # ── Locate missing-notes list ────────────────────────────────────────────
    missing_titles: set[str] | None = None
    proposal_destinations: dict[str, dict] = {}

    missing_path: Path | None
    if missing_file:
        missing_path = Path(missing_file)
    else:
        candidates = sorted(
            DATA_DIR.glob("missing-notes-*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        missing_path = candidates[0] if candidates else None

    if missing_path and missing_path.exists():
        console.print(f"Missing-notes list: [dim]{missing_path.name}[/dim]")
        with open(missing_path) as f:
            missing_data = json.load(f)
        for entry in missing_data.get("notes", []):
            title = entry.get("title", "")
            if title:
                missing_titles = missing_titles or set()
                missing_titles.add(title)
                if title not in proposal_destinations:
                    proposal_destinations[title] = entry
        console.print(f"  {len(missing_titles or set())} missing note title(s) to restore")
    else:
        console.print(
            "[yellow]No missing-notes file found — restoring all notes in backup.[/yellow]"
        )
        for n in backup_notes:
            title = n.get("title", "")
            folder_path = n.get("folder_path") or n.get("folder", "")
            if title and title not in proposal_destinations:
                proposal_destinations[title] = {"folder_path": folder_path}

    # ── Build restore list ───────────────────────────────────────────────────
    entries = _build_restore_entries(backup_notes, missing_titles, proposal_destinations)
    if not entries:
        console.print("[yellow]Nothing to restore.[/yellow]")
        return

    console.print(f"\n[bold]{len(entries)}[/bold] note(s) queued for restore.")
    logger.event("queued", count=len(entries))
    if dry_run:
        console.print("[dim](dry-run — no changes will be made)[/dim]")

    # ── Write temp restore JSON and call AppleScript ─────────────────────────
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(entries, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    script = REPO_ROOT / "scripts" / "restore" / "restore-notes.applescript"
    cmd = ["osascript", str(script)]
    if dry_run:
        cmd.append("--dry-run")
    if container:
        cmd += ["--container", container]
    cmd.append(tmp_path)

    created = exists = errors = 0
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if line.startswith("[CREATED]"):
                console.print(f"[green]{line}[/green]")
                logger.event("note", line=line, status="CREATED")
                created += 1
            elif line.startswith("[EXISTS]"):
                console.print(f"[dim]{line}[/dim]")
                logger.event("note", line=line, status="EXISTS")
                exists += 1
            elif line.startswith("[DRY RUN]"):
                console.print(f"[cyan]{line}[/cyan]")
                logger.event("note", line=line, status="DRY_RUN")
            elif line.startswith("[ERROR]"):
                console.print(f"[red]{line}[/red]")
                logger.event("note", line=line, status="ERROR")
                logger.error(line)
                errors += 1
            elif line:
                console.print(line)
        proc.wait()
        logger.finish(
            summary={"created": created, "exists": exists, "errors": errors},
            dry_run=dry_run,
            params={"backup_file": str(backup_path)},
        )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
