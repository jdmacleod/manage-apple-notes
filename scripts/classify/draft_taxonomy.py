"""Generate a draft taxonomy YAML by merging discovered themes into the current taxonomy."""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console

from scripts.classify.classify_notes import _CATEGORY_META
from scripts.config import load_settings, load_taxonomy, local_taxonomy_exists
from scripts.folder_utils import enumerate_paths
from scripts.json_utils import extract_json_object
from scripts.providers import LLMProvider, get_provider
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


def _top_level_folders(folder_paths: list[str]) -> list[str]:
    """Return sorted unique top-level folder names from a list of folder paths."""
    return sorted({p.split("/")[0] for p in folder_paths if p})


def load_bootstrap_prompt() -> str:
    path = REPO_ROOT / "prompts" / "bootstrap-taxonomy.md"
    if not path.exists():
        raise FileNotFoundError(f"Bootstrap prompt not found: {path}")
    return path.read_text()


def bootstrap_taxonomy(
    top_level_folders: list[str],
    provider: LLMProvider,
    settings: dict,
) -> dict:
    """Use LLM to map actual Apple Notes top-level folders to taxonomy roles.

    Returns a taxonomy dict like {"taxonomy": {"areas": {"folder": "Areas"}, ...}}.
    Returns {} on any LLM or parse error so the caller can fall back gracefully.
    """
    valid_roles = {key for key, _ in _CATEGORY_META}

    folder_list = "\n".join(f"- {f}" for f in top_level_folders)

    tl_cfg = settings.get("toplevel_folder", {})
    if tl_cfg.get("enabled") and tl_cfg.get("name"):
        toplevel_note = (
            f'Note: "{tl_cfg["name"]}" is a container folder, not a taxonomy category — '
            "do not map it to any role."
        )
    else:
        toplevel_note = ""

    system = (
        load_bootstrap_prompt()
        .replace("{FOLDER_LIST}", folder_list)
        .replace("{TOPLEVEL_NOTE}", toplevel_note)
    )

    try:
        response = provider.classify_messages(system, "")
        mapping = extract_json_object(response)
    except Exception as exc:
        console.print(f"[yellow]Warning:[/yellow] Bootstrap LLM call failed — {exc}")
        return {}

    taxonomy_entries = {
        role: {"folder": folder}
        for role, folder in mapping.items()
        if role in valid_roles and isinstance(folder, str) and folder
    }
    return {"taxonomy": taxonomy_entries} if taxonomy_entries else {}


def _insert_subfolder(entry: dict, parts: list[str]) -> bool:
    """Recursively insert remaining path components into entry's subfolders list.

    Promotes a plain-string subfolder to a dict when deeper nesting is needed.
    Returns True if the path was inserted, False if it already existed.
    """
    target = parts[0]
    subfolders: list = entry.get("subfolders") or []
    entry["subfolders"] = subfolders

    for i, item in enumerate(subfolders):
        name = (
            item
            if isinstance(item, str)
            else (item.get("name", "") if isinstance(item, dict) else "")
        )
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


def merge_new_paths(taxonomy: dict, new_paths: list[str]) -> tuple[dict, list[str], list[str]]:
    """Merge new folder paths into a deep copy of the taxonomy.

    Returns (updated_taxonomy, added_paths, skipped_paths).
    Paths are skipped if they already exist, have fewer than 2 components, or
    the top-level folder doesn't match any category in the taxonomy.
    """
    updated = copy.deepcopy(taxonomy)
    fn = updated.get("taxonomy", {})

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

    theme_map_path = Path(theme_map_file) if theme_map_file else find_latest_theme_map()
    if not theme_map_path.exists():
        console.print(f"[red]Theme-map file not found:[/red] {theme_map_path}")
        raise SystemExit(1)

    theme_map: dict = json.loads(theme_map_path.read_text())

    # ── Bootstrap: map actual Apple Notes folders to taxonomy roles ───────────
    # When no taxonomy.local.yaml exists, use an LLM call to infer the taxonomy
    # from the actual folder structure in the export rather than the generic example.
    if not local_taxonomy_exists():
        source_export = theme_map.get("source_export", "")
        export_path = (
            Path(source_export) if source_export and Path(source_export).exists() else None
        )

        if export_path:
            all_notes: list[dict] = json.loads(export_path.read_text())
            folder_paths = sorted(
                {fp for n in all_notes if (fp := n.get("folder_path") or n.get("folder", ""))}
            )
            top_level = _top_level_folders(folder_paths)

            tl_cfg = settings.get("toplevel_folder", {})
            if tl_cfg.get("enabled") and tl_cfg.get("name"):
                top_level = [f for f in top_level if f != tl_cfg["name"]]

            if dry_run:
                console.print("[bold]Bootstrap:[/bold] No taxonomy.local.yaml found.")
                console.print(f"  Folders to map: {', '.join(top_level)}")
                console.print(
                    "  (No API call in dry-run — bootstrap skipped; using example taxonomy below.)\n"
                )
                taxonomy = load_taxonomy()
            else:
                provider = get_provider(settings)
                taxonomy = bootstrap_taxonomy(top_level, provider, settings)
                if not taxonomy.get("taxonomy"):
                    console.print(
                        "[yellow]Warning:[/yellow] Bootstrap failed — falling back to example taxonomy."
                    )
                    taxonomy = load_taxonomy()
                else:
                    console.print(
                        "[dim]Bootstrapped taxonomy from Apple Notes folder structure.[/dim]"
                    )
        else:
            console.print(
                "[yellow]Warning:[/yellow] No source export found — "
                "falling back to example taxonomy as base.\n"
                "  Run 'uv run notes export' then 'uv run notes discover' to generate a theme map\n"
                "  that references an export, then re-run 'uv run notes draft'."
            )
            taxonomy = load_taxonomy()
    else:
        taxonomy = load_taxonomy()
    themes: list[dict] = theme_map.get("themes", [])
    established: set[str] = set(theme_map.get("established_paths", []))
    threshold: int = theme_map.get("subfolder_threshold", 8)

    candidate_paths = [
        t["suggested_path"]
        for t in themes
        if (t.get("estimated_count") or 0) >= threshold and t.get("suggested_path")
    ]
    new_paths = sorted(set(candidate_paths) - established)

    if not new_paths:
        console.print("[dim]No new paths to add — taxonomy is already up to date.[/dim]")
        return

    updated_taxonomy, added, skipped = merge_new_paths(taxonomy, new_paths)

    # Split skipped into two buckets so the user gets an actionable message for each:
    # - already_present: top-level matches a taxonomy category, path just exists already
    # - no_match: top-level doesn't match any category folder — usually means the LLM used
    #   a generic/wrong name (e.g. "Permanent/X" instead of the user's actual folder "Notes/X")
    category_folders = {
        entry.get("folder", "")
        for entry in updated_taxonomy.get("taxonomy", {}).values()
        if isinstance(entry, dict)
    }
    already_present = [p for p in skipped if "/" in p and p.split("/")[0] in category_folders]
    no_match = [p for p in skipped if "/" not in p or p.split("/")[0] not in category_folders]

    date_str = datetime.now().strftime("%Y-%m-%d")
    output = _build_output(updated_taxonomy, added, skipped, theme_map_path.name, date_str)

    if dry_run:
        console.print("[bold]Dry run — no file will be written.[/bold]\n")
        console.print(output)
        if no_match:
            console.print(
                f"\n[yellow]Warning:[/yellow] {len(no_match)} path(s) could not be matched "
                "to any taxonomy category (top-level folder name not recognised):"
            )
            for p in no_match:
                console.print(f"  [dim]-[/dim] {p}")
            console.print(
                "  Edit these paths in the theme map to use your actual folder names,\n"
                "  then re-run: uv run notes draft"
            )
        RunLogger("draft", logs_dir_path(settings)).finish(
            summary={
                "added": len(added),
                "already_present": len(already_present),
                "no_match": len(no_match),
            },
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
    if already_present:
        console.print(f"  Already present:  {len(already_present)}")
    if no_match:
        console.print(
            f"\n[yellow]Warning:[/yellow] {len(no_match)} path(s) could not be matched "
            "to any taxonomy category (top-level folder name not recognised):"
        )
        for p in no_match:
            console.print(f"  [dim]-[/dim] {p}")
        console.print(
            "  Edit these paths in the theme map to use your actual folder names,\n"
            "  then re-run: uv run notes draft"
        )
    console.print(
        "\n[dim]Review the draft, edit as needed, then copy to config/taxonomy.local.yaml[/dim]"
    )

    RunLogger("draft", logs_dir_path(settings)).finish(
        summary={
            "added": len(added),
            "already_present": len(already_present),
            "no_match": len(no_match),
        },
        dry_run=False,
        params={"theme_map": str(theme_map_path), "output": str(output_path)},
    )
