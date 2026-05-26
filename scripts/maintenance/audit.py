"""Scan the Apple Notes library for quality issues and write a Markdown report."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import find_latest_export, load_taxonomy

console = Console()

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "reports"

STALE_DAYS = 180
STUB_MAX_CHARS = 50
STALE_INBOX_DAYS = 7
STALE_FLEETING_DAYS = 30


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.fromisoformat(date_str.rstrip("Z"))
    except (ValueError, AttributeError, TypeError):
        return None


def _normalize_title(title: str) -> str:
    """Lowercase + strip punctuation for near-duplicate detection."""
    title = unicodedata.normalize("NFKD", title).lower()
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def _md_table(items: list[dict], cols: list[tuple[str, str]]) -> list[str]:
    if not items:
        return ["_None._", ""]
    header = "| " + " | ".join(label for label, _ in cols) + " |"
    sep = "|" + "|".join(" --- " for _ in cols) + "|"
    rows = [
        "| " + " | ".join(str(item.get(field, "")).replace("|", "\\|") for _, field in cols) + " |"
        for item in items
    ]
    return [header, sep, *rows, ""]


def run_audit(export_file: str | None, output_override: str | None, dry_run: bool) -> None:
    taxonomy = load_taxonomy()
    fn = taxonomy.get("forever_notes", {})
    archive_folder = fn.get("archive", "")
    inbox_folder = fn.get("inbox", "")
    fleeting_folder = fn.get("fleeting", "")

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    notes = json.loads(export_path.read_text())
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    report_path = Path(output_override) if output_override else REPORTS_DIR / f"audit-{date_str}.md"

    checks = [
        f"Stale — not modified >{STALE_DAYS} days, not in Archive",
        f"Stub notes — body <{STUB_MAX_CHARS} characters",
        "Duplicate titles",
        f"Stale inbox — {inbox_folder!r} older than {STALE_INBOX_DAYS} days",
        f"Stale fleeting — {fleeting_folder!r} older than {STALE_FLEETING_DAYS} days",
    ]

    if dry_run:
        console.print("[bold]Dry run — no API calls will be made.[/bold] (Audit makes no API calls.)\n")
        console.print(f"Export:      {export_path}")
        console.print(f"Notes found: {len(notes)}\n")
        console.print("Checks:")
        for check in checks:
            console.print(f"  • {check}")
        console.print(f"\nReport would be written to: {report_path}")
        return

    # ── Run checks ───────────────────────────────────────────────────────────

    stale_cutoff = now - timedelta(days=STALE_DAYS)
    inbox_cutoff = now - timedelta(days=STALE_INBOX_DAYS)
    fleeting_cutoff = now - timedelta(days=STALE_FLEETING_DAYS)

    stale_notes = sorted(
        [
            n for n in notes
            if n.get("folder") != archive_folder
            and (d := _parse_date(n.get("modified", ""))) is not None
            and d < stale_cutoff
        ],
        key=lambda n: n.get("modified", ""),
    )

    stub_notes = [n for n in notes if len((n.get("body") or "").strip()) < STUB_MAX_CHARS]

    title_groups: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        key = _normalize_title(note.get("title") or "")
        if key:
            title_groups[key].append(note)
    duplicate_groups = {k: v for k, v in title_groups.items() if len(v) > 1}

    stale_inbox = [
        n for n in notes
        if n.get("folder") == inbox_folder and inbox_folder
        and (d := _parse_date(n.get("modified", ""))) is not None
        and d < inbox_cutoff
    ]

    stale_fleeting = [
        n for n in notes
        if n.get("folder") == fleeting_folder and fleeting_folder
        and (d := _parse_date(n.get("modified", ""))) is not None
        and d < fleeting_cutoff
    ]

    # ── Build report ─────────────────────────────────────────────────────────

    lines: list[str] = [
        f"# Library Audit — {date_str}",
        "",
        f"Generated from: `{export_path}`  ",
        f"Total notes: {len(notes)}",
        "",
        "---",
        "",
        f"## Stale Notes — not modified in >{STALE_DAYS} days (not in Archive)",
        "",
        f"Found {len(stale_notes)} notes.",
        "",
        *_md_table(stale_notes, [("Title", "title"), ("Folder", "folder"), ("Last Modified", "modified")]),
        "---",
        "",
        f"## Stub Notes — body under {STUB_MAX_CHARS} characters",
        "",
        f"Found {len(stub_notes)} notes.",
        "",
        *_md_table(stub_notes, [("Title", "title"), ("Folder", "folder"), ("Body", "body")]),
        "---",
        "",
        "## Duplicate Titles",
        "",
        f"Found {len(duplicate_groups)} groups.",
        "",
    ]

    if duplicate_groups:
        for group in sorted(duplicate_groups.values(), key=lambda g: (g[0].get("title") or "").lower()):
            lines.append(f"**{group[0].get('title', '(untitled)')}** — {len(group)} notes")
            for note in group:
                modified = (note.get("modified") or "")[:10]
                lines.append(f"- Folder: {note.get('folder', '')}  |  Modified: {modified}")
            lines.append("")
    else:
        lines += ["_None._", ""]

    lines += [
        "---",
        "",
        f"## Stale Inbox — in {inbox_folder!r}, not updated in >{STALE_INBOX_DAYS} days",
        "",
        f"Found {len(stale_inbox)} notes.",
        "",
        *_md_table(stale_inbox, [("Title", "title"), ("Modified", "modified")]),
        "---",
        "",
        f"## Stale Fleeting — in {fleeting_folder!r}, not updated in >{STALE_FLEETING_DAYS} days",
        "",
        f"Found {len(stale_fleeting)} notes.",
        "",
        *_md_table(stale_fleeting, [("Title", "title"), ("Modified", "modified")]),
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    console.print(f"[green]Done.[/green] Report written to [bold]{report_path}[/bold]")
    console.print(f"  Stale:             {len(stale_notes)}")
    console.print(f"  Stubs:             {len(stub_notes)}")
    console.print(f"  Duplicate groups:  {len(duplicate_groups)}")
    console.print(f"  Stale inbox:       {len(stale_inbox)}")
    console.print(f"  Stale fleeting:    {len(stale_fleeting)}")
