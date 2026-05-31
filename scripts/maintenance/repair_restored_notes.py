"""Repair notes whose HTML body was corrupted after an iCloud Recently Deleted restore.

Symptoms: body starts with <div>Title</div><div>Title all-content-run-together</div>
Cause:    old plain-text notes (IMAPNote/pre-iCloud format) lose their newlines when
          restored from Recently Deleted; the title also appears twice.
Fix:      rebuild the body from the original plaintext in an earlier export, converting
          each newline-separated line to a <div> element.
"""

from __future__ import annotations

import html as html_mod
import json
import subprocess
from pathlib import Path

from rich.console import Console

from scripts.config import load_settings
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXPORTS_DIR = REPO_ROOT / "data" / "exports"
DATA_DIR = REPO_ROOT / "data"
SCRIPT = REPO_ROOT / "scripts" / "repair-note.applescript"


def _find_missing_notes_file() -> Path | None:
    candidates = sorted(DATA_DIR.glob("missing-notes-*.json"), reverse=True)
    return candidates[0] if candidates else None


def _find_old_export(exclude: Path) -> Path | None:
    """Return the most recent export file that is not `exclude`."""
    candidates = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
    for p in candidates:
        if p != exclude and not p.name.endswith(".bak"):
            return p
    return None


def _plaintext_to_html(text: str) -> str:
    """Convert newline-separated plaintext to Apple Notes HTML.

    Each non-empty line becomes <div>line</div>; empty lines become <div><br></div>.
    The first line (the note title in old Notes format) is preserved as-is so that
    Apple Notes continues to use it as the note title — it is not duplicated because
    the rest of the lines begin at line index 1.
    """
    parts: list[str] = []
    for line in text.split("\n"):
        line = line.replace("\xa0", " ")
        if line.strip():
            parts.append(f"<div>{html_mod.escape(line)}</div>")
        else:
            parts.append("<div><br></div>")
    return "\n".join(parts)


def _repair_note(title: str, new_body: str, dry_run: bool) -> str:
    """Write new_body to every note with the given title. Returns status string."""
    if dry_run:
        return "[DRY RUN]"

    result = subprocess.run(
        ["osascript", str(SCRIPT), title, new_body],
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if result.returncode != 0 or output.startswith("error:"):
        err = result.stderr.strip() or output
        return f"error: {err}"
    _, _, count = output.partition(":")
    return f"updated ({count} note{'s' if count != '1' else ''})"


def run_repair_restored(
    missing_file: str | None = None,
    old_export_file: str | None = None,
    dry_run: bool = False,
    json_output: bool = False,
) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    logger = RunLogger("repair", logs_dir_path(settings))
    # Resolve missing-notes file
    missing_path: Path | None
    if missing_file:
        missing_path = Path(missing_file)
    else:
        missing_path = _find_missing_notes_file()
        if missing_path is None:
            msg = "No missing-notes-*.json file found in data/. Pass --missing-file explicitly."
            if json_output:
                emit_result("repair", status="error", dry_run=dry_run, error=msg)
            else:
                con.print(f"[red]{msg}[/red]")
            raise SystemExit(1)

    con.print(f"Missing notes file: [dim]{missing_path.name}[/dim]")
    with open(missing_path) as f:
        missing_data = json.load(f)
    missing_notes = (
        missing_data.get("notes", missing_data) if isinstance(missing_data, dict) else missing_data
    )
    con.print(f"  {len(missing_notes)} notes listed as restored")

    # Resolve old export (source of original content)
    old_path: Path | None
    if old_export_file:
        old_path = Path(old_export_file)
    else:
        current_exports = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
        current = current_exports[0] if current_exports else None
        old_path = _find_old_export(current) if current else None
        if old_path is None:
            msg = "Could not find an earlier export to use as source. Pass --old-export explicitly."
            if json_output:
                emit_result("repair", status="error", dry_run=dry_run, error=msg)
            else:
                con.print(f"[red]{msg}[/red]")
            raise SystemExit(1)

    con.print(f"Original content source: [dim]{old_path.name}[/dim]")
    with open(old_path) as f:
        old_notes_list: list[dict] = json.load(f)

    # Index old export by title (keep all copies for duplicate-title notes)
    old_by_title: dict[str, list[str]] = {}
    for n in old_notes_list:
        t = n.get("title", "")
        body = n.get("body", "")
        if t:
            old_by_title.setdefault(t, [])
            if body not in old_by_title[t]:
                old_by_title[t].append(body)

    if dry_run:
        con.print("[dim](dry-run — no writes)[/dim]")

    con.print()

    repaired = skipped = errors = 0
    seen_titles: set[str] = set()

    for entry in missing_notes:
        title = entry.get("title", "")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        bodies = old_by_title.get(title)
        if not bodies:
            con.print(f"  [yellow]SKIP[/yellow]  {title!r} — not found in old export")
            skipped += 1
            continue

        # Use the first available original body (all copies should match)
        original_body = bodies[0]
        new_html = _plaintext_to_html(original_body)

        status = _repair_note(title, new_html, dry_run)

        if "error" in status.lower():
            con.print(f"  [red]ERROR[/red] {title!r} — {status}")
            logger.event("note", title=title, status="ERROR", detail=status)
            logger.error(f"{title!r}: {status}")
            errors += 1
        elif dry_run:
            lines = original_body.count("\n") + 1
            con.print(f"  [cyan][DRY RUN][/cyan] {title!r} — {lines} lines → HTML")
            logger.event("note", title=title, status="DRY_RUN")
            repaired += 1
        else:
            con.print(f"  [green]OK[/green]    {title!r} — {status}")
            logger.event("note", title=title, status="REPAIRED")
            repaired += 1

    con.print(
        f"\n[bold]Done.[/bold] {repaired} repaired"
        + (f", {skipped} skipped (not in old export)" if skipped else "")
        + (f", {errors} errors" if errors else "")
        + ("." if not dry_run else " (dry-run — no changes written).")
    )
    repair_summary: dict[str, object] = {"repaired": repaired, "skipped": skipped, "errors": errors}
    log_file = logger.finish(
        summary=repair_summary,
        dry_run=dry_run,
        params={
            "missing_file": str(missing_path) if missing_path else None,
            "old_export_file": str(old_path) if old_path else None,
        },
    )
    if json_output:
        emit_result("repair", dry_run=dry_run, log_file=log_file, summary=repair_summary)
