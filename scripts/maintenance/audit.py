"""Scan the Apple Notes library for quality issues and write a Markdown report."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console

from scripts.config import (
    export_age_hours,
    find_latest_export,
    get_category_meta,
    load_settings,
    load_taxonomy,
    local_taxonomy_exists,
    reorganization_mode,
)
from scripts.folder_utils import (
    effective_max_depth,
    enumerate_paths,
    folder_name,
    has_taxonomy_ancestor,
    nesting_mode,
    path_depth,
)
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "reports"

STUB_MAX_WORDS = 5
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
    max_depth: int = 3,
) -> list[dict]:
    """Find folders shallow enough to warrant deeper nesting.

    Groups notes in known category folders by the first significant word of their
    title as a rough theme proxy. Flags folders where any word group exceeds
    min_notes as a candidate for subfolder creation. Notes already at max_depth
    or beyond are excluded — they can't go deeper.
    """
    flat_notes: dict[str, list[dict]] = defaultdict(list)
    for note in notes:
        folder_path = note.get("folder_path") or note.get("folder", "")
        folder = note.get("folder", "")
        if folder in known_category_folders and path_depth(folder_path) < max_depth:
            flat_notes[folder_path or folder].append(note)

    candidates = []
    stopwords = {"a", "an", "the", "my", "i", "on", "in", "of", "for", "to", "and", "or", "how"}

    for folder, folder_notes in flat_notes.items():
        if len(folder_notes) < min_notes:
            continue
        word_counts: Counter = Counter()
        for note in folder_notes:
            title_words = (note.get("title") or "").lower().split()
            for word in title_words:
                word = re.sub(r"[^\w]", "", word)
                if word and word not in stopwords and len(word) > 2:
                    word_counts[word] += 1
                    break
        top_words = [
            (word, count) for word, count in word_counts.most_common(5) if count >= min_notes
        ]
        if top_words:
            candidates.append(
                {
                    "folder": folder,
                    "note_count": len(folder_notes),
                    "theme_signals": ", ".join(f"{w} ({c})" for w, c in top_words),
                }
            )

    return candidates


def run_audit(
    export_file: str | None,
    output_override: str | None,
    dry_run: bool,
    json_output: bool = False,
) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    logger = RunLogger("audit", logs_dir_path(settings))
    taxonomy = load_taxonomy()
    if not local_taxonomy_exists():
        con.print(
            "[yellow]Warning:[/yellow] config/taxonomy.local.yaml not found — "
            "audit results will not reflect your actual Apple Notes folder structure.\n"
            "  Run 'uv run notes setup' to configure your taxonomy, or copy a template:\n"
            "  taxonomy.zettelkasten.yaml / taxonomy.para.yaml / taxonomy.gtd.yaml"
        )
    fn = taxonomy.get("taxonomy", {})
    cat_meta = get_category_meta(settings)

    thresholds = settings.get("thresholds", {})
    stub_words = thresholds.get("stub_words", STUB_MAX_WORDS)
    min_subfolder = thresholds.get("min_notes_for_subfolder", MIN_NOTES_FOR_SUBFOLDER)

    # Excluded folders: categories with exclude_from_classify (archive-like)
    excluded_folders: set[str] = {
        folder_name(fn[k])
        for k, v in cat_meta.items()
        if v.get("exclude_from_classify") and k in fn and folder_name(fn[k])
    }

    # Stale thresholds: categories with stale_days (e.g. inbox, fleeting)
    stale_thresholds: list[tuple[str, int]] = [
        (folder_name(fn[k]), int(v["stale_days"]))
        for k, v in cat_meta.items()
        if v.get("stale_days") and k in fn and folder_name(fn[k])
    ]

    # Activity thresholds: categories with active_days (e.g. projects)
    active_thresholds: list[tuple[str, int]] = [
        (folder_name(fn[k]), int(v["active_days"]))
        for k, v in cat_meta.items()
        if v.get("active_days") and k in fn and folder_name(fn[k])
    ]

    # Build complete set of all known taxonomy paths for orphan detection
    all_taxonomy_paths: set[str] = set()
    for entry in fn.values():
        for path in enumerate_paths(entry):
            all_taxonomy_paths.add(path)

    # Collect known top-level category folder names for subfolder candidate check
    category_folders = {
        folder_name(v) for v in fn.values() if folder_name(v) and not folder_name(v).startswith("[")
    }

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        msg = f"Export file not found: {export_path}"
        if json_output:
            emit_result("audit", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    max_age = (settings.get("safety") or {}).get("export_max_age_hours", 24)
    if max_age:
        age_h = export_age_hours(export_path)
        if age_h > max_age:
            con.print(
                f"[yellow]Warning:[/yellow] Export is {age_h:.0f}h old"
                " — consider re-running 'notes export' first."
            )

    notes = json.loads(export_path.read_text())
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    report_path = Path(output_override) if output_override else REPORTS_DIR / f"audit-{date_str}.md"

    checks = [
        "Untitled notes — no meaningful title",
        f"Stub notes — ≤{stub_words} combined title+body words, no attachments",
        "Duplicate titles",
        *[
            f"Stale {cat_folder!r} — not updated in >{days} days"
            for cat_folder, days in stale_thresholds
        ],
        *[
            f"Inactive {cat_folder!r} — not modified in >{days} days"
            for cat_folder, days in active_thresholds
        ],
        "Untracked folders — children of taxonomy paths, not yet in taxonomy",
        "Uncategorized notes — no taxonomy relationship",
        f"Subfolder candidates — flat folders with >{min_subfolder} notes sharing a theme",
    ]

    if dry_run:
        con.print("[bold]Dry run — no API calls will be made.[/bold] (Audit makes no API calls.)\n")
        con.print(f"Export:      {export_path}")
        con.print(f"Notes found: {len(notes)}\n")
        con.print("Checks:")
        for check in checks:
            con.print(f"  • {check}")
        con.print(f"\nReport would be written to: {report_path}")
        log_file = logger.finish(
            summary={"notes_scanned": len(notes)},
            dry_run=True,
            params={"export_file": str(export_path)},
        )
        if json_output:
            emit_result(
                "audit",
                dry_run=True,
                output_file=report_path,
                log_file=log_file,
                summary={"notes_scanned": len(notes)},
            )
        return

    # ── Run checks ───────────────────────────────────────────────────────────

    with con.status(f"Scanning {len(notes)} notes…"):
        untitled_notes = [n for n in notes if not (n.get("title") or "").strip()]
        untitled_display = [{**n, "body": (n.get("body") or "")[:80]} for n in untitled_notes]

        stub_notes = [
            n
            for n in notes
            if (n.get("attachment_count") or 0) == 0
            and n.get("folder") not in excluded_folders
            and (n.get("word_count") or 0) + len((n.get("title") or "").split()) <= stub_words
        ]

        title_groups: dict[str, list[dict]] = defaultdict(list)
        for note in notes:
            key = _normalize_title(note.get("title") or "")
            if key:
                title_groups[key].append(note)
        duplicate_groups = {k: v for k, v in title_groups.items() if len(v) > 1}

        # Stale checks: one per category with stale_days configured
        stale_by_folder: dict[str, list[dict]] = {}
        for cat_folder, days in stale_thresholds:
            cutoff = now - timedelta(days=days)
            stale = [
                n
                for n in notes
                if n.get("folder") == cat_folder
                and (d := _parse_date(n.get("modified", ""))) is not None
                and d < cutoff
            ]
            stale_by_folder[cat_folder] = stale

        # Activity checks: one per category with active_days configured
        inactive_by_folder: dict[str, list[dict]] = {}
        for cat_folder, days in active_thresholds:
            cutoff = now - timedelta(days=days)
            inactive = sorted(
                [
                    n
                    for n in notes
                    if (
                        n.get("folder") == cat_folder
                        or (n.get("folder_path") or "").startswith(cat_folder + "/")
                    )
                    and (d := _parse_date(n.get("modified", ""))) is not None
                    and d < cutoff
                ],
                key=lambda n: n.get("modified", ""),
            )
            inactive_by_folder[cat_folder] = inactive

        untracked_folder_notes: list[dict] = []
        uncategorized_notes: list[dict] = []
        for n in notes:
            path = n.get("folder_path") or n.get("folder", "")
            folder = n.get("folder", "")
            if path in all_taxonomy_paths or folder in all_taxonomy_paths:
                continue
            if has_taxonomy_ancestor(path, all_taxonomy_paths):
                untracked_folder_notes.append(n)
            else:
                uncategorized_notes.append(n)

        untracked_by_folder = Counter(
            n.get("folder_path") or n.get("folder", "") for n in untracked_folder_notes
        )
        untracked_folder_rows = [
            {"folder_path": fp, "note_count": cnt}
            for fp, cnt in sorted(untracked_by_folder.items())
        ]

        max_depth = effective_max_depth(settings)
        mode = nesting_mode(settings)
        reorg_mode = reorganization_mode(settings)
        subfolder_candidates = (
            _find_subfolder_candidates(notes, category_folders, min_subfolder, max_depth)
            if mode != "flat" and reorg_mode != "conservative"
            else []
        )

        # ── Library statistics ───────────────────────────────────────────────

        category_counts: list[tuple[str, str, int]] = []
        for key, entry in fn.items():
            folder = folder_name(entry)
            if not folder or folder.startswith("["):
                continue
            count = sum(
                1
                for n in notes
                if n.get("folder") == folder
                or (n.get("folder_path") or "").startswith(folder + "/")
            )
            category_counts.append((key.capitalize(), folder, count))

        total_in_taxonomy = sum(c for _, _, c in category_counts)
        uncategorized_count = len(notes) - total_in_taxonomy

        age_buckets: dict[str, int] = {
            "< 30 days": 0,
            "30–90 days": 0,
            "90 days – 1 year": 0,
            "1–5 years": 0,
            "5+ years": 0,
        }
        no_date_count = 0
        for note in notes:
            d = _parse_date(note.get("modified", ""))
            if d is None:
                no_date_count += 1
                continue
            age = (now - d).days
            if age < 30:
                age_buckets["< 30 days"] += 1
            elif age < 90:
                age_buckets["30–90 days"] += 1
            elif age < 365:
                age_buckets["90 days – 1 year"] += 1
            elif age < 1825:
                age_buckets["1–5 years"] += 1
            else:
                age_buckets["5+ years"] += 1

    # ── Build report ─────────────────────────────────────────────────────────

    def _pct(n: int) -> str:
        return f"{round(100 * n / len(notes))}%" if notes else "0%"

    lines: list[str] = [
        f"# Library Audit — {date_str}",
        "",
        f"Generated from: `{export_path}`  ",
        f"Total notes: {len(notes)}",
        "",
        "---",
        "",
        "## Library Statistics",
        "",
        "### By Taxonomy Category",
        "",
        "| Category | Folder | Notes | Share |",
        "| --- | --- | --- | --- |",
    ]
    for para_label, cat_folder, count in category_counts:
        lines.append(f"| {para_label} | {cat_folder} | {count} | {_pct(count)} |")
    if uncategorized_count > 0 or not category_counts:
        lines.append(
            f"| *(uncategorized)* | — | {uncategorized_count} | {_pct(uncategorized_count)} |"
        )
    lines += [
        "",
        "### Age Distribution (by last-modified date)",
        "",
        "| Window | Notes | Share |",
        "| --- | --- | --- |",
    ]
    for window, count in age_buckets.items():
        lines.append(f"| {window} | {count} | {_pct(count)} |")
    if no_date_count:
        lines.append(f"| *(no date)* | {no_date_count} | {_pct(no_date_count)} |")
    # Dynamic inactive-activity sections (one per category with active_days)
    for cat_folder, days in active_thresholds:
        inactive_notes = inactive_by_folder.get(cat_folder, [])
        lines += [
            "",
            "---",
            "",
            f"## Inactive {cat_folder!r} — not modified in >{days} days",
            "",
            f"Found {len(inactive_notes)} notes.",
            "",
            "Notes untouched for this long may be completed, stalled, or abandoned. "
            "Consider archiving completed items or reactivating stalled ones.",
            "",
            *_md_table(
                inactive_notes,
                [("Title", "title"), ("Folder", "folder"), ("Last Modified", "modified")],
            ),
        ]

    lines += [
        "---",
        "",
        "## Untitled Notes",
        "",
        f"Found {len(untitled_notes)} notes.",
        "",
        *_md_table(untitled_display, [("Folder", "folder"), ("Body preview", "body")]),
        "---",
        "",
        f"## Stub Notes — ≤{stub_words} combined title+body words, no attachments",
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
        for group in sorted(
            duplicate_groups.values(), key=lambda g: (g[0].get("title") or "").lower()
        ):
            lines.append(f"**{group[0].get('title', '(untitled)')}** — {len(group)} notes")
            for note in group:
                modified = (note.get("modified") or "")[:10]
                lines.append(f"- Folder: {note.get('folder', '')}  |  Modified: {modified}")
            lines.append("")
    else:
        lines += ["_None._", ""]

    # Dynamic stale sections (one per category with stale_days)
    for cat_folder, days in stale_thresholds:
        stale_notes = stale_by_folder.get(cat_folder, [])
        lines += [
            "---",
            "",
            f"## Stale {cat_folder!r} — not updated in >{days} days",
            "",
            f"Found {len(stale_notes)} notes.",
            "",
            *_md_table(stale_notes, [("Title", "title"), ("Modified", "modified")]),
        ]

    lines += [
        "---",
        "",
        "## Untracked Folders — in Apple Notes, not defined in taxonomy",
        "",
        f"Found {len(untracked_folder_rows)} folder(s) with {len(untracked_folder_notes)} note(s).",
        "",
        "These folders sit under known taxonomy categories but aren't in `taxonomy.local.yaml`. "
        "They may be intentional manual additions. Add them to the taxonomy or run `notes discover`.",
        "",
        *_md_table(untracked_folder_rows, [("Folder", "folder_path"), ("Notes", "note_count")]),
        "---",
        "",
        "## Uncategorized Notes — no taxonomy relationship",
        "",
        f"Found {len(uncategorized_notes)} notes.",
        "",
        "These notes are in folders with no connection to the taxonomy (e.g. the container "
        "root or a completely foreign folder). Run `notes classify` to organize them.",
        "",
        *_md_table(uncategorized_notes, [("Title", "title"), ("Folder", "folder")]),
        "---",
        "",
        *(
            [
                f"## Subfolder Candidates — flat folders with >{min_subfolder} notes sharing a theme",
                "",
                "These folders are large enough to benefit from subfolders. Run `notes discover`",
                "for a full theme analysis, then add subfolders to `taxonomy.local.yaml`.",
                "",
                f"Found {len(subfolder_candidates)} candidate(s).",
                "",
                *_md_table(
                    subfolder_candidates,
                    [
                        ("Folder", "folder"),
                        ("Notes", "note_count"),
                        ("Theme Signals", "theme_signals"),
                    ],
                ),
            ]
            if reorg_mode != "conservative"
            else [
                "## Subfolder Candidates",
                "",
                "Skipped — `reorganization_mode` is `conservative`. "
                "Your existing folder structure is preserved as-is.",
                "",
            ]
        ),
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    con.print(f"[green]Done.[/green] Report written to [bold]{report_path}[/bold]")
    con.print(f"  Untitled:           {len(untitled_notes)}")
    con.print(f"  Stubs:              {len(stub_notes)}")
    con.print(f"  Duplicate titles:   {len(duplicate_groups)}")
    for cat_folder, _days in stale_thresholds:
        count = len(stale_by_folder.get(cat_folder, []))
        con.print(f"  Stale {cat_folder!r}:{' ' * max(1, 14 - len(cat_folder))}{count}")
    for cat_folder, _days in active_thresholds:
        count = len(inactive_by_folder.get(cat_folder, []))
        con.print(f"  Inactive {cat_folder!r}:{' ' * max(1, 11 - len(cat_folder))}{count}")
    con.print(
        f"  Untracked folders:  {len(untracked_folder_rows)} folder(s), {len(untracked_folder_notes)} note(s)"
    )
    con.print(f"  Uncategorized:      {len(uncategorized_notes)}")
    if reorg_mode == "conservative":
        con.print("  Subfolder candid.:  (skipped — conservative mode)")
    else:
        con.print(f"  Subfolder candid.:  {len(subfolder_candidates)}")

    total_stale = sum(len(v) for v in stale_by_folder.values())
    total_inactive = sum(len(v) for v in inactive_by_folder.values())
    audit_summary: dict[str, object] = {
        "notes_scanned": len(notes),
        "untitled": len(untitled_notes),
        "stubs": len(stub_notes),
        "duplicate_title_groups": len(duplicate_groups),
        "stale_notes": total_stale,
        "inactive_notes": total_inactive,
        "untracked_folders": len(untracked_folder_rows),
        "untracked_folder_notes": len(untracked_folder_notes),
        "uncategorized": len(uncategorized_notes),
        "subfolder_candidates": len(subfolder_candidates),
    }
    log_file = logger.finish(
        summary=audit_summary,
        dry_run=False,
        params={"export_file": str(export_path), "report_path": str(report_path)},
    )
    if json_output:
        emit_result("audit", output_file=report_path, log_file=log_file, summary=audit_summary)
