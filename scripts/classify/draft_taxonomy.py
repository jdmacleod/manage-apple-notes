"""Generate a draft taxonomy YAML by merging discovered themes into the current taxonomy."""

from __future__ import annotations

import copy
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import typer
import yaml
from rich.console import Console

from scripts.config import get_category_meta, load_settings, load_taxonomy, local_taxonomy_exists
from scripts.folder_utils import enumerate_paths
from scripts.json_output import emit_result
from scripts.json_utils import extract_json_object
from scripts.providers import LLMProvider, get_max_tokens, get_provider
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


# Well-known Apple Notes folder names → taxonomy role keys.
# Used by _derive_role_key to map common folder names without an LLM call.
_CANONICAL_ROLE_KEYS: dict[str, str] = {
    "inbox": "inbox",
    "projects": "projects",
    "areas": "areas",
    "areas of responsibility": "areas",
    "resources": "resources",
    "archive": "archive",
    "fleeting": "fleeting",
    "fleeting notes": "fleeting",
    "literature": "literature",
    "literature notes": "literature",
    "permanent": "permanent",
    "permanent notes": "permanent",
    "notes": "permanent",
    "review": "review",
    "next actions": "next_actions",
    "next action": "next_actions",
    "waiting for": "waiting_for",
    "someday maybe": "someday_maybe",
    "someday/maybe": "someday_maybe",
    "reference": "reference",
}


def _derive_role_key(folder: str, used_keys: set[str]) -> str:
    """Derive a taxonomy role key for a folder name not already in the taxonomy.

    Tries well-known names first; falls back to a slugified version that avoids
    collisions with existing role keys.
    """
    normalized = folder.lower().strip()
    candidate = _CANONICAL_ROLE_KEYS.get(normalized)
    if candidate and candidate not in used_keys:
        return candidate
    base = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "folder"
    candidate = base
    i = 2
    while candidate in used_keys:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


def _add_missing_top_level_folders(
    taxonomy: dict, top_level_folders: list[str], con: Console
) -> dict:
    """Add top-level folders from the export that are absent from the taxonomy.

    Called after bootstrap or load_taxonomy() so that folders the bootstrap LLM
    omitted — or folders created in Apple Notes since the taxonomy was last written —
    always end up in the taxonomy, allowing their subfolders to be merged in below.
    Returns a deep copy of the taxonomy if any folders were added, otherwise the
    original object unchanged.
    """
    fn = taxonomy.get("taxonomy", {})
    existing_folder_names = {
        entry.get("folder", "") for entry in fn.values() if isinstance(entry, dict)
    }
    missing = [f for f in top_level_folders if f not in existing_folder_names]
    if not missing:
        return taxonomy

    used_keys = set(fn.keys())
    updated = copy.deepcopy(taxonomy)
    updated_fn = updated.setdefault("taxonomy", {})
    for folder in missing:
        key = _derive_role_key(folder, used_keys)
        used_keys.add(key)
        updated_fn[key] = {"folder": folder}

    names = ", ".join(missing)
    con.print(
        f"[dim]Auto-added {len(missing)} top-level folder(s) from export not in taxonomy: {names}[/dim]"
    )
    return updated


def load_bootstrap_prompt() -> str:
    path = REPO_ROOT / "prompts" / "bootstrap-taxonomy.md"
    if not path.exists():
        raise FileNotFoundError(f"Bootstrap prompt not found: {path}")
    return path.read_text()


def _build_role_list(taxonomy: dict, settings: dict) -> str:
    """Build a human-readable role list for the bootstrap prompt.

    If the user already has taxonomy categories defined, describe those.
    Otherwise fall back to the full built-in / settings-configured category list.
    """
    fn = taxonomy.get("taxonomy", {})
    cat_meta = get_category_meta(settings)
    if fn:
        lines = [
            f"- {key}: {(cat_meta.get(key) or {}).get('description', '') or 'user-defined category'}"
            for key, entry in fn.items()
            if (cat_meta.get(key) or {}).get("description") or key in cat_meta
        ]
        if lines:
            return "\n".join(lines)
    # Fresh install — list all configured/built-in categories
    return "\n".join(
        f"- {key}: {cfg['description']}" for key, cfg in cat_meta.items() if cfg.get("description")
    )


def bootstrap_taxonomy(
    top_level_folders: list[str],
    provider: LLMProvider,
    settings: dict,
    taxonomy: dict | None = None,
) -> dict:
    """Use LLM to map actual Apple Notes top-level folders to taxonomy roles.

    Returns a taxonomy dict like {"taxonomy": {"areas": {"folder": "Areas"}, ...}}.
    Returns {} on any LLM or parse error so the caller can fall back gracefully.
    """
    cat_meta = get_category_meta(settings)
    valid_roles = set(cat_meta.keys())
    role_list = _build_role_list(taxonomy or {}, settings)

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
        .replace("{ROLE_LIST}", role_list)
        .replace("{FOLDER_LIST}", folder_list)
        .replace("{TOPLEVEL_NOTE}", toplevel_note)
    )

    try:
        response = provider.classify_messages(
            system, "", max_tokens=get_max_tokens(settings, provider)
        )
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

    for path in new_paths:
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


def run_draft(theme_map_file: str | None, dry_run: bool, json_output: bool = False) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()

    theme_map_path = Path(theme_map_file) if theme_map_file else find_latest_theme_map()
    if not theme_map_path.exists():
        msg = f"Theme-map file not found: {theme_map_path}"
        if json_output:
            emit_result("draft", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Theme-map file not found:[/red] {theme_map_path}")
        raise SystemExit(1)

    theme_map: dict = json.loads(theme_map_path.read_text())

    if not dry_run:
        con.print(f"[dim]Theme map: {theme_map_path.name}[/dim]")

    # ── Export folder tree — used for threshold bypass and bootstrap ──────────
    # Load once here so both the bootstrap block and the candidate_paths filter
    # can use it.  Paths that already exist in the user's library bypass the
    # min_notes_for_subfolder threshold: the threshold prevents creating thin new
    # folders, not recognising ones the user deliberately created.
    source_export_path = theme_map.get("source_export", "")
    export_path = (
        Path(source_export_path)
        if source_export_path and Path(source_export_path).exists()
        else None
    )
    if source_export_path and not export_path:
        con.print(
            f"[yellow]Warning:[/yellow] Source export not found: {source_export_path}\n"
            "  Existing subfolders cannot be promoted from the export.\n"
            "  Only LLM-suggested paths above the threshold will be added.\n"
            "  Re-run 'uv run notes export' then 'uv run notes discover' to fix this."
        )
    if export_path:
        _export_notes: list[dict] = json.loads(export_path.read_text())
        _seen_fps: set[str] = set()
        ordered_export_paths: list[str] = []
        for _n in _export_notes:
            _fp = _n.get("folder_path") or _n.get("folder", "")
            if _fp and _fp not in _seen_fps:
                _seen_fps.add(_fp)
                ordered_export_paths.append(_fp)
        export_folder_tree: set[str] = set(ordered_export_paths)
    else:
        _export_notes = []
        ordered_export_paths = []
        export_folder_tree = set()

    # Position map: path → index in Apple Notes native order.
    # Paths absent from the export (LLM-only proposals) sort after all export paths.
    export_order: dict[str, int] = {p: i for i, p in enumerate(ordered_export_paths)}

    # ── Compute top-level folders for bootstrap and auto-add ─────────────────
    # Done once here so both the bootstrap block and _add_missing_top_level_folders
    # can use the same filtered list.
    if export_folder_tree:
        _all_top_level = _top_level_folders(list(export_folder_tree))
        _tl_cfg = settings.get("toplevel_folder", {})
        if _tl_cfg.get("enabled") and _tl_cfg.get("name"):
            _all_top_level = [f for f in _all_top_level if f != _tl_cfg["name"]]
    else:
        _all_top_level = []

    # ── Bootstrap: map actual Apple Notes folders to taxonomy roles ───────────
    # When no taxonomy.local.yaml exists, use an LLM call to infer the taxonomy
    # from the actual folder structure in the export rather than the generic example.
    if not local_taxonomy_exists():
        if export_path:
            if dry_run:
                con.print("[bold]Bootstrap:[/bold] No taxonomy.local.yaml found.")
                con.print(f"  Folders to map: {', '.join(_all_top_level)}")
                con.print(
                    "  (No API call in dry-run — bootstrap skipped; using example taxonomy below.)\n"
                )
                taxonomy = load_taxonomy()
            else:
                provider = get_provider(settings)
                model = provider.model
                con.print(f"[dim]Bootstrap  ·  {provider.name} / {model}[/dim]")
                with con.status("Bootstrapping taxonomy from folder structure…", spinner="dots"):
                    taxonomy = bootstrap_taxonomy(
                        _all_top_level, provider, settings, taxonomy=load_taxonomy()
                    )
                if not taxonomy.get("taxonomy"):
                    con.print(
                        "[yellow]Warning:[/yellow] Bootstrap failed — falling back to example taxonomy."
                    )
                    taxonomy = load_taxonomy()
                else:
                    con.print("[dim]Bootstrapped taxonomy from Apple Notes folder structure.[/dim]")
        else:
            con.print(
                "[yellow]Warning:[/yellow] No source export found — "
                "falling back to example taxonomy as base.\n"
                "  Run 'uv run notes export' then 'uv run notes discover' to generate a theme map\n"
                "  that references an export, then re-run 'uv run notes draft'."
            )
            taxonomy = load_taxonomy()
    else:
        taxonomy = load_taxonomy()

    # ── Auto-add top-level folders missing from the taxonomy ──────────────────
    # Ensures folders the bootstrap LLM omitted — or folders added to Apple Notes
    # since the taxonomy was last written — always appear in the taxonomy so their
    # subfolders can be merged in below.
    taxonomy = _add_missing_top_level_folders(taxonomy, _all_top_level, con)

    themes: list[dict] = theme_map.get("themes", [])

    # Compute established paths from the CURRENT taxonomy (not the discover-time
    # theme map) so that re-runs after a taxonomy reset correctly re-add subfolders
    # that were in the old taxonomy but are absent from the newly bootstrapped one.
    established: set[str] = {
        p
        for entry in taxonomy.get("taxonomy", {}).values()
        for p in enumerate_paths(entry)
        if "/" in p
    }

    threshold: int = theme_map.get("subfolder_threshold", 8)

    candidate_paths = [
        t["suggested_path"]
        for t in themes
        if t.get("suggested_path")
        and (
            (t.get("estimated_count") or 0) >= threshold
            or t["suggested_path"] in export_folder_tree
        )
    ]

    # Also promote any subfolder that exists in the library but wasn't named in
    # a theme suggested_path.  The LLM performs content-based discovery and may
    # route structural subfolders (e.g. "Archive/Animation Guild") to a flat
    # parent path rather than the actual folder name, so the theme map alone is
    # not a reliable source for existing subfolder structure.
    if export_folder_tree:
        export_subfolders = {p for p in export_folder_tree if "/" in p and p not in established}
        candidate_set = set(candidate_paths) | export_subfolders
    else:
        candidate_set = set(candidate_paths)

    # Sort by Apple Notes native position so subfolders land in the draft in the
    # same sequence the user arranged them in the app.  Paths absent from the export
    # (LLM-only proposals) fall after all export-ordered entries and sort
    # alphabetically among themselves via the secondary key.
    def _export_key(p: str) -> tuple[int, str]:
        return (export_order.get(p, len(ordered_export_paths)), p)

    new_paths = sorted(candidate_set - established, key=_export_key)

    if not new_paths:
        con.print("[dim]No new paths to add — taxonomy is already up to date.[/dim]")
        if json_output:
            emit_result(
                "draft",
                dry_run=dry_run,
                summary={"added": 0, "already_present": 0, "no_match": 0},
            )
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

    draft_summary: dict[str, object] = {
        "added": len(added),
        "already_present": len(already_present),
        "no_match": len(no_match),
    }

    if dry_run:
        con.print("[bold]Dry run — no file will be written.[/bold]\n")
        con.print(output)
        if no_match:
            con.print(
                f"\n[yellow]Warning:[/yellow] {len(no_match)} path(s) could not be matched "
                "to any taxonomy category (top-level folder name not recognised):"
            )
            for p in no_match:
                con.print(f"  [dim]-[/dim] {p}")
            con.print(
                "  Edit these paths in the theme map to use your actual folder names,\n"
                "  then re-run: uv run notes draft"
            )
        log_file = RunLogger("draft", logs_dir_path(settings)).finish(
            summary=draft_summary,
            dry_run=True,
            params={"theme_map": str(theme_map_path)},
        )
        if json_output:
            emit_result(
                "draft",
                dry_run=True,
                output_file=TAXONOMY_DRAFTS_DIR / f"taxonomy-draft-{date_str}.yaml",
                log_file=log_file,
                summary=draft_summary,
            )
        return

    TAXONOMY_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TAXONOMY_DRAFTS_DIR / f"taxonomy-draft-{date_str}.yaml"
    output_path.write_text(output, encoding="utf-8")

    con.print(f"[green]Draft written[/green] → {output_path}")
    if added:
        con.print(f"  New paths added:  {len(added)}")
        for p in added:
            con.print(f"    [green]+[/green] {p}")
    if already_present:
        con.print(f"  Already present:  {len(already_present)}")
    if no_match:
        con.print(
            f"\n[yellow]Warning:[/yellow] {len(no_match)} path(s) could not be matched "
            "to any taxonomy category (top-level folder name not recognised):"
        )
        for p in no_match:
            con.print(f"  [dim]-[/dim] {p}")
        con.print(
            "  Edit these paths in the theme map to use your actual folder names,\n"
            "  then re-run: uv run notes draft"
        )
    # ── Offer to apply draft to taxonomy.local.yaml ───────────────────────────
    local_taxonomy_path = CONFIG_DIR / "taxonomy.local.yaml"
    if not json_output and typer.confirm("\nApply to config/taxonomy.local.yaml?", default=True):
        if local_taxonomy_path.exists():
            bak = local_taxonomy_path.with_suffix(".yaml.bak")
            shutil.copy2(local_taxonomy_path, bak)
            con.print(f"  [dim]Backed up existing taxonomy → {bak.name}[/dim]")
        local_yaml: str = yaml.dump(
            updated_taxonomy,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )
        local_taxonomy_path.write_text(local_yaml, encoding="utf-8")
        con.print("[green]Updated[/green] config/taxonomy.local.yaml")
    else:
        con.print(
            "\n[dim]Review the draft, edit as needed, then copy to config/taxonomy.local.yaml[/dim]"
        )

    log_file = RunLogger("draft", logs_dir_path(settings)).finish(
        summary=draft_summary,
        dry_run=False,
        params={"theme_map": str(theme_map_path), "output": str(output_path)},
    )
    if json_output:
        emit_result("draft", output_file=output_path, log_file=log_file, summary=draft_summary)
