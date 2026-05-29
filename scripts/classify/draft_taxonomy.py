"""Generate a draft taxonomy YAML by merging discovered themes into the current taxonomy."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from rich.console import Console

from scripts.classify.classify_notes import load_settings, load_taxonomy
from scripts.folder_utils import enumerate_paths
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"
THEME_MAPS_DIR = REPO_ROOT / "data" / "theme-maps"
TAXONOMY_DRAFTS_DIR = REPO_ROOT / "data" / "taxonomy-drafts"


def find_latest_theme_map() -> Path:
    files = sorted(THEME_MAPS_DIR.glob("themes-*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No theme-map files found in {THEME_MAPS_DIR}. Run 'uv run notes discover' first."
        )
    return files[0]


def _insert_subfolder(entry: dict, parts: list[str]) -> bool:
    """Recursively insert remaining path components into entry's subfolders list.

    Promotes a plain-string subfolder to a dict when deeper nesting is needed.
    Returns True if the path was inserted, False if it already existed.
    """
    target = parts[0]
    subfolders: list = entry.get("subfolders") or []
    entry["subfolders"] = subfolders

    for i, item in enumerate(subfolders):
        name = item if isinstance(item, str) else (item.get("name", "") if isinstance(item, dict) else "")
        if name == target:
            if len(parts) == 1:
                return False  # already exists at this level
            if isinstance(item, str):
                subfolders[i] = {"name": item, "subfolders": []}
                item = subfolders[i]
            return _insert_subfolder(item, parts[1:])

    if len(parts) == 1:
        subfolders.append(target)
    else:
        new_node: dict = {"name": target, "subfolders": []}
        subfolders.append(new_node)
        _insert_subfolder(new_node, parts[1:])
    return True


def merge_new_paths(
    taxonomy: dict, new_paths: list[str]
) -> tuple[dict, list[str], list[str]]:
    """Merge new folder paths into a deep copy of the taxonomy.

    Returns (updated_taxonomy, added_paths, skipped_paths).
    Paths are skipped if they already exist, have fewer than 2 components, or
    the top-level folder doesn't match any category in the taxonomy.
    """
    updated = copy.deepcopy(taxonomy)
    fn = updated.get("forever_notes", {})

    existing: set[str] = set()
    for entry in fn.values():
        for p in enumerate_paths(entry):
            existing.add(p)

    added: list[str] = []
    skipped: list[str] = []

    for path in sorted(new_paths):
        parts = path.split("/")
        if len(parts) < 2:
            skipped.append(path)
            continue
        if path in existing:
            skipped.append(path)
            continue

        top = parts[0]
        matched = False
        for entry in fn.values():
            if isinstance(entry, dict) and entry.get("folder") == top:
                if _insert_subfolder(entry, parts[1:]):
                    added.append(path)
                else:
                    skipped.append(path)
                matched = True
                break
        if not matched:
            skipped.append(path)

    return updated, added, skipped


def _build_output(
    updated_taxonomy: dict,
    added: list[str],
    skipped: list[str],
    theme_map_name: str,
    date_str: str,
) -> str:
    """Serialize the updated taxonomy to a YAML string with a header comment."""
    header_lines = [
        f"taxonomy-draft-{date_str}.yaml",
        f"Generated from: {theme_map_name}",
        "Review, edit, then copy to config/taxonomy.local.yaml",
        "",
        f"New paths added ({len(added)}):",
    ] + [f"  + {p}" for p in added]

    if skipped:
        header_lines += [
            "",
            f"Skipped — already present or no matching category ({len(skipped)}):",
        ] + [f"  - {p}" for p in skipped]

    comment_block = "\n".join(f"# {line}" if line else "#" for line in header_lines)
    body: str = yaml.dump(
        updated_taxonomy,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )
    return comment_block + "\n\n" + body


def run_draft(theme_map_file: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()

    theme_map_path = Path(theme_map_file) if theme_map_file else find_latest_theme_map()
    if not theme_map_path.exists():
        console.print(f"[red]Theme-map file not found:[/red] {theme_map_path}")
        raise SystemExit(1)

    theme_map: dict = json.loads(theme_map_path.read_text())
    themes: list[dict] = theme_map.get("themes", [])
    established: set[str] = set(theme_map.get("established_paths", []))

    candidate_paths = [
        t["suggested_path"]
        for t in themes
        if not t.get("below_subfolder_threshold", False) and t.get("suggested_path")
    ]
    new_paths = sorted(set(candidate_paths) - established)

    if not new_paths:
        console.print("[dim]No new paths to add — taxonomy is already up to date.[/dim]")
        return

    updated_taxonomy, added, skipped = merge_new_paths(taxonomy, new_paths)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output = _build_output(updated_taxonomy, added, skipped, theme_map_path.name, date_str)

    if dry_run:
        console.print("[bold]Dry run — no file will be written.[/bold]\n")
        console.print(output)
        RunLogger("draft", logs_dir_path(settings)).finish(
            summary={"added": len(added), "skipped": len(skipped)},
            dry_run=True,
            params={"theme_map": str(theme_map_path)},
        )
        return

    TAXONOMY_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TAXONOMY_DRAFTS_DIR / f"taxonomy-draft-{date_str}.yaml"
    output_path.write_text(output, encoding="utf-8")

    console.print(f"[green]Draft written[/green] → {output_path}")
    if added:
        console.print(f"  New paths added:  {len(added)}")
        for p in added:
            console.print(f"    [green]+[/green] {p}")
    if skipped:
        console.print(f"  Already present:  {len(skipped)}")
    console.print(
        "\n[dim]Review the draft, edit as needed, then copy to config/taxonomy.local.yaml[/dim]"
    )

    RunLogger("draft", logs_dir_path(settings)).finish(
        summary={"added": len(added), "skipped": len(skipped)},
        dry_run=False,
        params={"theme_map": str(theme_map_path), "output": str(output_path)},
    )
