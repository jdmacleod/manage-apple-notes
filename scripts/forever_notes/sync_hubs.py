"""Create and maintain ✱ Home and ✱ Hub notes (strict mode only)."""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

import yaml
from rich.console import Console

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"
EXPORTS_DIR = REPO_ROOT / "data" / "exports"

HEAVY_ASTERISK = "✱"


def _load_yaml(local_path: Path, example_path: Path) -> dict:
    for path in (local_path, example_path):
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


def load_settings() -> dict:
    return _load_yaml(
        CONFIG_DIR / "settings.local.yaml",
        CONFIG_DIR / "settings.example.yaml",
    )


def load_taxonomy() -> dict:
    return _load_yaml(
        CONFIG_DIR / "taxonomy.local.yaml",
        CONFIG_DIR / "taxonomy.example.yaml",
    )


def find_latest_export() -> Path:
    files = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No export files found in {EXPORTS_DIR}. Run 'uv run notes export' first."
        )
    return files[0]


def _folder_name(entry: dict) -> str:
    return entry.get("folder", "") if isinstance(entry, dict) else str(entry)


def _subfolders(entry: dict) -> list[dict]:
    """Return subfolders as a list of dicts with at least a 'name' key."""
    raw = entry.get("subfolders", []) if isinstance(entry, dict) else []
    result = []
    for item in raw:
        if isinstance(item, dict):
            result.append(item)
        else:
            result.append({"name": str(item)})
    return result


def _hub_title(subfolder_def: dict, prefix: str) -> str:
    return subfolder_def.get("hub_title") or f"{prefix}{subfolder_def['name']}"


def _hub_tag(subfolder_def: dict) -> str:
    if "hub_tag" in subfolder_def:
        return subfolder_def["hub_tag"]
    name = subfolder_def["name"].lower()
    name = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return f"#{name}"


def _url_id(nid: str) -> str:
    """Extract the numeric note identifier for use in applenotes:// URLs.

    Apple Notes x-coredata:// URIs end in pNNN (e.g. x-coredata://UUID/ICNote/p123).
    The applenotes://showNote?identifier= scheme requires the plain numeric part (123),
    not the 'p'-prefixed form.
    """
    raw = nid.rpartition("/")[2] if nid else ""
    return raw[1:] if raw.startswith("p") else raw


def _note_link(title: str, nid: str) -> str:
    """Return an HTML link to a note, or plain escaped text if no ID available."""
    escaped = html.escape(title)
    uid = _url_id(nid)
    if not uid:
        return escaped
    return f'<a href="applenotes://showNote?identifier={uid}">{escaped}</a>'


def _build_theme_index(
    taxonomy: dict,
    notes: list[dict],
    min_count: int,
) -> dict[str, dict]:
    """
    Returns a dict keyed by theme name. Each value:
      {
        "_sf_def": {...},
        "categories": {
            "Areas": [("Note Title A", "x-coredata://..."), ...],
        },
        "total": 26,
      }
    Only themes meeting min_count across ALL categories are included.
    """
    cats = taxonomy.get("forever_notes", {})

    # Build lookup: folder_path → (category_display_name, subfolder_name)
    path_to_cat: dict[str, tuple[str, str]] = {}
    subfolder_defs: dict[str, dict] = {}  # theme_name → subfolder def dict

    for cat_key, cat_val in cats.items():
        if not isinstance(cat_val, dict):
            continue
        folder = _folder_name(cat_val)
        cat_display = cat_key.capitalize()
        for sf in _subfolders(cat_val):
            sf_name = sf["name"]
            path_to_cat[f"{folder}/{sf_name}"] = (cat_display, sf_name)
            # Also match bare subfolder name for flat Notes structures where
            # parent folder detection returns empty (e.g. -1728 on container access).
            path_to_cat.setdefault(sf_name, (cat_display, sf_name))
            subfolder_defs.setdefault(sf_name, sf)

    # Accumulate (title, nid) pairs per theme per category
    theme_cats: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for note in notes:
        fp = note.get("folder_path", "")
        if fp in path_to_cat:
            cat_display, sf_name = path_to_cat[fp]
            theme_cats.setdefault(sf_name, {}).setdefault(cat_display, []).append(
                (note.get("title", "(untitled)"), note.get("id", ""))
            )

    # Filter by min_count
    result: dict[str, dict] = {}
    for theme_name, cats_map in theme_cats.items():
        total = sum(len(note_pairs) for note_pairs in cats_map.values())
        if total >= min_count:
            sf_def = subfolder_defs.get(theme_name, {"name": theme_name})
            result[theme_name] = {
                "_sf_def": sf_def,
                "categories": cats_map,
                "total": total,
            }
    return result


def _generate_hub_body(
    sf_def: dict,
    categories: dict[str, list[tuple[str, str]]],
    hub_prefix: str,
) -> str:
    """Generate HTML body for a Hub note directly from export data."""
    tag = _hub_tag(sf_def)
    h_title = _hub_title(sf_def, hub_prefix)
    # Apple Notes uses the first element of the body as the note title.
    parts: list[str] = [f"<h1>{html.escape(h_title)}</h1>"]

    multi_cat = len(categories) > 1
    for cat_display, note_pairs in sorted(categories.items()):
        if multi_cat:
            parts.append(f"<h2>{html.escape(cat_display)}</h2>")
        parts.append("<ul>")
        for title, nid in note_pairs:
            parts.append(f"<li>{_note_link(title, nid)}</li>")
        parts.append("</ul>")

    parts.append("<br>")
    parts.append(f"<p>#hub {tag} #ForeverNotes</p>")
    return "\n".join(parts)


def _write_note_applescript(
    title: str, body: str, folder: str | None, dry_run: bool, container: str = ""
) -> tuple[str, str]:
    """Create or update a note in Apple Notes with the given title and body.

    Returns (status, local_id).
    status is one of: "created", "updated", "[DRY RUN]", "error".
    local_id is the note's local identifier (e.g. "p123") for applenotes:// links,
    or empty string for dry-run and error cases.
    """
    if dry_run:
        return "[DRY RUN]", ""

    script = REPO_ROOT / "scripts" / "forever_notes" / "sync-hubs.applescript"
    cmd = [
        "osascript",
        str(script),
        title,
        body,
        folder or "",
        container,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()
    if result.returncode != 0 or result.stderr.strip():
        err = result.stderr.strip() or output
        console.print(f"[red][ERROR] {title}: {err}[/red]")
        return "error", ""
    status, _, local_id = output.partition(":")
    return status or "updated", local_id


def _build_home_body(
    taxonomy: dict,
    theme_index: dict[str, dict],
    hub_prefix: str,
    home_title: str,
    hub_ids: dict[str, str] | None = None,
) -> str:
    """Build the taxonomy-driven ✱ Home note body as HTML.

    Categories appear in taxonomy file order; headings use the folder: value.
    Hub-eligible subfolders appear as applenotes:// links when hub_ids provides
    their local identifiers; otherwise as plain text.
    The home_title is placed first so Apple Notes uses it as the note title.
    """
    hub_eligible: set[str] = set(theme_index.keys())
    hub_ids = hub_ids or {}
    cats = taxonomy.get("forever_notes", {})
    parts: list[str] = [f"<h1>{html.escape(home_title)}</h1>", "<br>"]

    for cat_key, cat_val in cats.items():
        if not isinstance(cat_val, dict):
            continue
        heading = _folder_name(cat_val) or cat_key.capitalize()
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        subfolders = _subfolders(cat_val)
        if subfolders:
            parts.append("<ul>")
            for sf in subfolders:
                sf_name = sf["name"]
                if sf_name in hub_eligible:
                    h_title = _hub_title(theme_index[sf_name]["_sf_def"], hub_prefix)
                    local_id = hub_ids.get(h_title, "")
                    uid = _url_id(local_id) if local_id else ""
                    if uid:
                        parts.append(f'<li><a href="applenotes://showNote?identifier={uid}">{html.escape(h_title)}</a></li>')
                    else:
                        parts.append(f"<li>{html.escape(h_title)}</li>")
                else:
                    parts.append(f"<li>{html.escape(sf_name)}</li>")
            parts.append("</ul>")
        parts.append("<br>")

    parts.append("<p>#ForeverNotes</p>")
    return "\n".join(parts)


def run_sync_hubs(export_file: str | None = None, dry_run: bool = False) -> None:
    settings = load_settings()

    mode = settings.get("forever_notes_mode", "loose")
    if mode != "strict":
        console.print(
            "[yellow]Strict mode is not enabled.[/yellow] "
            "Set [bold]forever_notes_mode: strict[/bold] in settings.local.yaml to use sync-hubs."
        )
        return

    strict = settings.get("strict_mode", {})
    hub_prefix = strict.get("hub_title_prefix", f"{HEAVY_ASTERISK} ")
    home_title = strict.get("home_note_title", f"{HEAVY_ASTERISK} Home")
    home_folder = strict.get("home_note_folder") or None
    hub_folder = strict.get("hub_note_folder") or None

    tl_cfg = settings.get("toplevel_folder", {})
    container = tl_cfg.get("name", "") if tl_cfg.get("enabled", False) else ""

    thresholds = settings.get("thresholds", {})
    min_count = int(thresholds.get("min_notes_for_subfolder", 8))

    taxonomy = load_taxonomy()

    if export_file:
        export_path = Path(export_file)
    else:
        try:
            export_path = find_latest_export()
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            raise SystemExit(1)

    console.print(f"Loading export: [dim]{export_path.name}[/dim]")
    with open(export_path) as f:
        notes: list[dict] = json.load(f)
    console.print(f"  {len(notes)} notes loaded")

    theme_index = _build_theme_index(taxonomy, notes, min_count)

    if not theme_index:
        console.print("[yellow]No Hub-eligible themes found (no subfolders meet the note count threshold).[/yellow]")
        return

    console.print(f"\nFound [bold]{len(theme_index)}[/bold] Hub-eligible theme(s).")
    if dry_run:
        console.print("[dim](dry-run — no writes)[/dim]\n")

    created = updated = errors = 0
    hub_ids: dict[str, str] = {}  # hub_title → local_id for Home note links

    for theme_name, theme_data in sorted(theme_index.items()):
        sf_def = theme_data["_sf_def"]
        h_title = _hub_title(sf_def, hub_prefix)
        categories = theme_data["categories"]
        total = theme_data["total"]

        console.print(f"  [bold]{h_title}[/bold] — {total} notes across {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}")

        body = _generate_hub_body(sf_def, categories, hub_prefix)
        status, local_id = _write_note_applescript(h_title, body, hub_folder, dry_run, container=container)
        if local_id:
            hub_ids[h_title] = local_id

        if status == "created":
            console.print(f"    [green][CREATED][/green]")
            created += 1
        elif status == "[DRY RUN]":
            console.print(f"    [cyan][DRY RUN][/cyan]")
        elif status == "error":
            errors += 1
        else:
            console.print(f"    [dim][UPDATED][/dim]")
            updated += 1

    # ✱ Home — built after Hubs so hub_ids contains their fresh local identifiers
    console.print(f"\n  [bold]{home_title}[/bold] — root index")
    home_body = _build_home_body(taxonomy, theme_index, hub_prefix, home_title, hub_ids)

    home_status, _ = _write_note_applescript(home_title, home_body, home_folder, dry_run, container=container)
    if home_status == "created":
        console.print(f"    [green][CREATED][/green]")
    elif home_status == "[DRY RUN]":
        console.print(f"    [cyan][DRY RUN][/cyan]")
    elif home_status == "error":
        errors += 1
    else:
        console.print(f"    [dim][UPDATED][/dim]")

    console.print(f"\n[bold]Done.[/bold] Hubs: {created} created, {updated} updated" + (f", {errors} errors" if errors else "") + ".")
    if dry_run:
        console.print("[dim]Dry-run — no changes were made.[/dim]")
