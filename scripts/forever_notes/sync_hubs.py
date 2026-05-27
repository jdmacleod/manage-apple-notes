"""Create and maintain ✱ Home and ✱ Hub notes (strict mode only)."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console

from scripts.providers import get_provider

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = REPO_ROOT / "prompts"
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


def _build_theme_index(
    taxonomy: dict,
    notes: list[dict],
    min_count: int,
) -> dict[str, dict]:
    """
    Returns a dict keyed by theme name. Each value:
      {
        "hub_title": "✱ Health",
        "hub_tag": "#health",
        "categories": {
            "Permanent": ["Note Title A", "Note Title B"],
            "Literature": ["Note Title C"],
        }
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
            path = f"{folder}/{sf_name}"
            path_to_cat[path] = (cat_display, sf_name)
            subfolder_defs.setdefault(sf_name, sf)

    # Accumulate note titles per theme per category
    theme_cats: dict[str, dict[str, list[str]]] = {}
    for note in notes:
        fp = note.get("folder_path", "")
        if fp in path_to_cat:
            cat_display, sf_name = path_to_cat[fp]
            theme_cats.setdefault(sf_name, {}).setdefault(cat_display, []).append(
                note.get("title", "(untitled)")
            )

    # Filter by min_count
    result: dict[str, dict] = {}
    for theme_name, cats_map in theme_cats.items():
        total = sum(len(titles) for titles in cats_map.values())
        if total >= min_count:
            sf_def = subfolder_defs.get(theme_name, {"name": theme_name})
            # We need the strict_mode prefix from settings — caller passes it
            result[theme_name] = {
                "_sf_def": sf_def,
                "categories": cats_map,
                "total": total,
            }
    return result


def _generate_hub_body(
    hub_name: str,
    categories: dict[str, list[str]],
    provider,
    prompt_template: str,
    dry_run: bool,
) -> str:
    """Call the LLM to generate a Hub note body. Returns plain text."""
    notes_by_cat = json.dumps(categories, ensure_ascii=False, indent=2)
    user_content = (
        prompt_template
        .replace("{HUB_NAME}", hub_name)
        .replace("{NOTES_BY_CATEGORY_JSON}", notes_by_cat)
    )
    if dry_run:
        lines = [f"[ {HEAVY_ASTERISK} Home ]", ""]
        for cat, titles in sorted(categories.items()):
            lines.append(cat)
            lines.extend(titles)
            lines.append("")
        tag = "#" + hub_name.lower().replace(" ", "-")
        lines.append(f"#hub {tag} #ForeverNotes")
        return "\n".join(lines)

    return provider.classify_messages(
        system_prompt="You generate plain-text Hub note bodies for Apple Notes.",
        user_content=user_content,
        max_tokens=2048,
    )


def _write_note_applescript(title: str, body: str, folder: str | None, dry_run: bool) -> str:
    """
    Create or update a note in Apple Notes with the given title and body.
    Returns a status string: "created", "updated", or "[DRY RUN]".
    """
    if dry_run:
        return "[DRY RUN]"

    script = REPO_ROOT / "scripts" / "forever-notes" / "sync-hubs.applescript"
    cmd = [
        "osascript",
        str(script),
        title,
        body,
        folder or "",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()
    if result.returncode != 0 or result.stderr.strip():
        err = result.stderr.strip() or output
        console.print(f"[red][ERROR] {title}: {err}[/red]")
        return "error"
    return output or "updated"


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

    prompt_template = (PROMPTS_DIR / "sync-hubs.md").read_text()

    theme_index = _build_theme_index(taxonomy, notes, min_count)

    if not theme_index:
        console.print("[yellow]No Hub-eligible themes found (no subfolders meet the note count threshold).[/yellow]")
        return

    console.print(f"\nFound [bold]{len(theme_index)}[/bold] Hub-eligible theme(s).")

    if not dry_run:
        provider = get_provider(settings)
        console.print(f"Using provider: [dim]{provider.name} / {provider.model}[/dim]\n")
    else:
        provider = None
        console.print("[dim](dry-run — no LLM calls, no writes)[/dim]\n")

    created = updated = unchanged = errors = 0
    hub_titles: list[str] = []

    for theme_name, theme_data in sorted(theme_index.items()):
        sf_def = theme_data["_sf_def"]
        h_title = _hub_title(sf_def, hub_prefix)
        hub_titles.append(h_title)
        categories = theme_data["categories"]
        total = theme_data["total"]

        console.print(f"  [bold]{h_title}[/bold] — {total} notes across {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}")

        body = _generate_hub_body(theme_name, categories, provider, prompt_template, dry_run)
        status = _write_note_applescript(h_title, body, hub_folder, dry_run)

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

    # ✱ Home
    console.print(f"\n  [bold]{home_title}[/bold] — root index")
    home_body_lines = [f"[ {HEAVY_ASTERISK} Home ]", "", "## Hubs"]
    home_body_lines.extend(hub_titles)
    home_body_lines += ["", "#ForeverNotes"]
    home_body = "\n".join(home_body_lines)

    home_status = _write_note_applescript(home_title, home_body, home_folder, dry_run)
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
