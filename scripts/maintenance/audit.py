"""Scan the Apple Notes library for quality issues and write a Markdown report."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import (
    _folder_name,
    find_latest_export,
    load_settings,
    load_taxonomy,
)

console = Console()

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "reports"

STALE_DAYS = 180
STUB_MAX_CHARS = 50
STALE_INBOX_DAYS = 7
STALE_FLEETING_DAYS = 30
MIN_NOTES_FOR_SUBFOLDER = 8


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


def _find_subfolder_candidates(
    notes: list[dict],
    known_category_folders: set[str],
    min_notes: int,
) -> list[dict]:
    """Find flat top-level folders that are large enough to warrant subfolders.

    Groups notes in known category folders by the first significant word of their
    title as a rough theme proxy. Flags folders where any word group exceeds
    min_notes as a candidate for subfolder creation.
    """
    # Only consider notes in known flat top-level folders (no "/" in folder path)
    flat_notes: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        folder = note.get("folder", "")
        if folder in known_category_folders and "/" not in (note.get("folder_path") or folder):
            flat_notes[folder].append(note)

    candidates = []
    stopwords = {"a", "an", "the", "my", "i", "on", "in", "of", "for", "to", "and", "or", "how"}

    for folder, folder_notes in flat_notes.items():
        if len(folder_notes) < min_notes:
            continue
        # Count first significant word of each title as rough theme proxy
        word_counts: Counter = Counter()
        for note in folder_notes:
            title_words = (note.get("title") or "").lower().split()
            for word in title_words:
                word = re.sub(r"[^\w]", "", word)
                if word and word not in stopwords and len(word) > 2:
                    word_counts[word] += 1
                    break
        top_words = [(word, count) for word, count in word_counts.most_common(5) if count >= min_notes]
        if top_words:
            candidates.append({
                "folder": folder,
                "note_count": len(folder_notes),
                "theme_signals": ", ".join(f"{w} ({c})" for w, c in top_words),
            })

    return candidates


def run_audit(export_file: str | None, output_override: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    fn = taxonomy.get("forever_notes", {})

    archive_folder = _folder_name(fn.get("archive", ""))
    inbox_folder = _folder_name(fn.get("inbox", ""))
    fleeting_folder = _folder_name(fn.get("fleeting", ""))

    thresholds = settings.get("thresholds", {})
    stale_days = thresholds.get("stale_days", STALE_DAYS)
    stub_chars = thresholds.get("stub_chars", STUB_MAX_CHARS)
    inbox_stale_days = thresholds.get("inbox_stale_days", STALE_INBOX_DAYS)
    fleeting_stale_days = thresholds.get("fleeting_stale_days", STALE_FLEETING_DAYS)
    min_subfolder = thresholds.get("min_notes_for_subfolder", MIN_NOTES_FOR_SUBFOLDER)

    # Collect known top-level category folder names for subfolder candidate check
    category_folders = {
        _folder_name(v)
        for v in fn.values()
        if _folder_name(v) and not _folder_name(v).startswith("[")
    }

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    notes = json.loads(export_path.read_text())
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    report_path = Path(output_override) if output_override else REPORTS_DIR / f"audit-{date_str}.md"

    checks = [
        f"Stale — not modified >{stale_days} days, not in Archive",
        f"Stub notes — body <{stub_chars} characters",
        "Duplicate titles",
        f"Stale inbox — {inbox_folder!r} older than {inbox_stale_days} days",
        f"Stale fleeting — {fleeting_folder!r} older than {fleeting_stale_days} days",
        f"Subfolder candidates — flat folders with >{min_subfolder} notes sharing a theme",
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

    with console.status(f"Scanning {len(notes)} notes…"):
        stale_cutoff = now - timedelta(days=stale_days)
        inbox_cutoff = now - timedelta(days=inbox_stale_days)
        fleeting_cutoff = now - timedelta(days=fleeting_stale_days)

        stale_notes = sorted(
            [
                n for n in notes
                if n.get("folder") != archive_folder
                and (d := _parse_date(n.get("modified", ""))) is not None
                and d < stale_cutoff
            ],
            key=lambda n: n.get("modified", ""),
        )

        stub_notes = [n for n in notes if len((n.get("body") or "").strip()) < stub_chars]

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

        subfolder_candidates = _find_subfolder_candidates(notes, category_folders, min_subfolder)

    # ── Build report ─────────────────────────────────────────────────────────

    lines: list[str] = [
        f"# Library Audit — {date_str}",
        "",
        f"Generated from: `{export_path}`  ",
        f"Total notes: {len(notes)}",
        "",
        "---",
        "",
        f"## Stale Notes — not modified in >{stale_days} days (not in Archive)",
        "",
        f"Found {len(stale_notes)} notes.",
        "",
        *_md_table(stale_notes, [("Title", "title"), ("Folder", "folder"), ("Last Modified", "modified")]),
        "---",
        "",
        f"## Stub Notes — body under {stub_chars} characters",
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
        f"## Stale Inbox — in {inbox_folder!r}, not updated in >{inbox_stale_days} days",
        "",
        f"Found {len(stale_inbox)} notes.",
        "",
        *_md_table(stale_inbox, [("Title", "title"), ("Modified", "modified")]),
        "---",
        "",
        f"## Stale Fleeting — in {fleeting_folder!r}, not updated in >{fleeting_stale_days} days",
        "",
        f"Found {len(stale_fleeting)} notes.",
        "",
        *_md_table(stale_fleeting, [("Title", "title"), ("Modified", "modified")]),
        "---",
        "",
        f"## Subfolder Candidates — flat folders with >{min_subfolder} notes sharing a theme",
        "",
        "These folders are large enough to benefit from subfolders. Run `notes discover`",
        "for a full theme analysis, then add subfolders to `taxonomy.local.yaml`.",
        "",
        f"Found {len(subfolder_candidates)} candidate(s).",
        "",
        *_md_table(
            subfolder_candidates,
            [("Folder", "folder"), ("Notes", "note_count"), ("Theme Signals", "theme_signals")],
        ),
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    console.print(f"[green]Done.[/green] Report written to [bold]{report_path}[/bold]")
    console.print(f"  Stale:              {len(stale_notes)}")
    console.print(f"  Stubs:              {len(stub_notes)}")
    console.print(f"  Duplicate groups:   {len(duplicate_groups)}")
    console.print(f"  Stale inbox:        {len(stale_inbox)}")
    console.print(f"  Stale fleeting:     {len(stale_fleeting)}")
    console.print(f"  Subfolder candid.:  {len(subfolder_candidates)}")
