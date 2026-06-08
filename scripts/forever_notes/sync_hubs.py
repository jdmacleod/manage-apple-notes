"""Create and maintain ✱ Home and ✱ Hub notes (strict mode only)."""

from __future__ import annotations

import html
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from scripts.config import find_latest_export, load_settings, load_taxonomy, local_taxonomy_exists
from scripts.folder_utils import enumerate_paths, folder_name, path_depth
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

HEAVY_ASTERISK = "✱"

NOTESTORE_DB = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.notes" / "NoteStore.sqlite"
)


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


def _find_sf_def(entry: dict, target_path: str) -> dict:
    """Walk the taxonomy tree to find the subfolder dict for a given path.

    Returns a minimal dict with at least a 'name' key if the entry is not found.
    Used to preserve hub_title / hub_tag overrides for deeper paths.
    """
    parts = target_path.split("/")
    if not parts:
        return {"name": target_path}
    # Skip the root folder component (index 0) when walking subfolders
    node: dict | str = entry
    for part in parts[1:]:
        if not isinstance(node, dict):
            return {"name": part}
        for child in node.get("subfolders") or []:
            child_name = child.get("name", "") if isinstance(child, dict) else str(child)
            if child_name == part:
                node = child
                break
        else:
            return {"name": part}
    if isinstance(node, dict):
        return node
    return {"name": str(node)}


def _hub_title(subfolder_def: dict, prefix: str) -> str:
    return str(subfolder_def.get("hub_title") or f"{prefix}{subfolder_def['name']}")


def _hub_tag(subfolder_def: dict) -> str:
    if "hub_tag" in subfolder_def:
        return str(subfolder_def["hub_tag"])
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


def _lookup_uuids(primary_keys: list[str], _con: Console | None = None) -> dict[str, str]:
    """Query NoteStore.sqlite for stable note UUIDs given numeric primary keys.

    Returns a dict mapping primary key string (e.g. "123") to UUID string.
    Falls back gracefully when Full Disk Access is not granted or the DB is absent.
    """
    _c = _con or console
    pks_int = [int(pk) for pk in primary_keys if pk.isdigit()]
    if not pks_int or not NOTESTORE_DB.exists():
        return {}

    tmp_dir = tempfile.mkdtemp()
    db_copy = Path(tmp_dir) / "NoteStore_copy.sqlite"
    try:
        shutil.copy2(NOTESTORE_DB, db_copy)
        for ext in ("-wal", "-shm"):
            src = Path(str(NOTESTORE_DB) + ext)
            if src.exists():
                shutil.copy2(src, Path(str(db_copy) + ext))
    except PermissionError:
        _c.print(
            "[yellow]Note UUIDs unavailable:[/yellow] Full Disk Access for Terminal is required "
            "to read NoteStore.sqlite.\n"
            "  Grant it in System Settings → Privacy & Security → Full Disk Access, then re-run.\n"
            "  Hub links will fall back to numeric identifiers until access is granted."
        )
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {}

    try:
        placeholders = ",".join("?" * len(pks_int))
        db_con = sqlite3.connect(str(db_copy))
        rows = db_con.execute(
            f"SELECT Z_PK, ZIDENTIFIER FROM ZICCLOUDSYNCINGOBJECT WHERE Z_PK IN ({placeholders})",
            pks_int,
        ).fetchall()
        db_con.close()
        return {str(pk): uuid for pk, uuid in rows if uuid}
    except Exception as exc:
        _c.print(f"[yellow]SQLite UUID lookup failed: {exc}[/yellow]")
        return {}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _note_link(title: str, nid: str, uuid: str = "") -> str:
    """Return an HTML link to a note, or plain escaped text if no ID available.

    Prefers applenotes://showNote?identifier=UUID (stable iCloud UUID from NoteStore.sqlite)
    over the applenotes://showNote?identifier=NNN fallback (numeric x-coredata PK).
    """
    escaped = html.escape(title)
    if uuid:
        return f'<a href="applenotes://showNote?identifier={uuid}">{escaped}</a>'
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
    cats = taxonomy.get("taxonomy", {})

    # Build lookup: folder_path → (category_display_name, subfolder_name)
    path_to_cat: dict[str, tuple[str, str]] = {}
    subfolder_defs: dict[str, dict] = {}  # theme_name → subfolder def dict

    for cat_key, cat_val in cats.items():
        if not isinstance(cat_val, dict):
            continue
        cat_display = cat_key.capitalize()
        for path in enumerate_paths(cat_val):
            if path_depth(path) < 2:
                continue
            leaf = path.split("/")[-1]
            path_to_cat[path] = (cat_display, leaf)
            # Also match bare leaf name for flat Notes structures where
            # parent folder detection returns empty (e.g. -1728 on container access).
            path_to_cat.setdefault(leaf, (cat_display, leaf))
            subfolder_defs.setdefault(leaf, _find_sf_def(cat_val, path))

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
    uuid_map: dict[str, str] | None = None,
    use_links: bool = False,
    cat_order: dict[str, int] | None = None,
) -> str:
    """Generate HTML body for a Hub note directly from export data.

    When use_links=True (internal_links: "html" in settings), note titles are
    rendered as applenotes:// links using UUIDs from uuid_map when available.
    When use_links=False (default, internal_links: "text"), titles are plain text.
    Category sections appear in taxonomy key order when cat_order is supplied;
    alphabetical order is used as fallback (e.g. in tests that don't pass it).
    """
    tag = _hub_tag(sf_def)
    h_title = _hub_title(sf_def, hub_prefix)
    parts: list[str] = [f"<h1>{html.escape(h_title)}</h1>"]

    multi_cat = len(categories) > 1
    _order = cat_order or {}
    n_cats = len(_order)
    for cat_display, note_pairs in sorted(
        categories.items(),
        key=lambda x: (_order.get(x[0], n_cats), x[0]),
    ):
        if multi_cat:
            parts.append(f"<h2>{html.escape(cat_display)}</h2>")
        parts.append("<ul>")
        for title, nid in note_pairs:
            if use_links:
                pk = _url_id(nid)
                uuid = uuid_map.get(pk, "") if uuid_map else ""
                parts.append(f"<li>{_note_link(title, nid, uuid)}</li>")
            else:
                parts.append(f"<li>{html.escape(title)}</li>")
        parts.append("</ul>")

    parts.append("<br>")
    parts.append(f"<p>#hub {tag} #ForeverNotes</p>")
    return "\n".join(parts)


def _theme_order(taxonomy: dict) -> dict[str, int]:
    """Map each theme (subfolder leaf name) to its first-appearance index in taxonomy order.

    Used to iterate Hub notes in the same order as the user's sidebar rather than
    alphabetically by theme name.
    """
    order: dict[str, int] = {}
    idx = 0
    for cat_val in taxonomy.get("taxonomy", {}).values():
        if not isinstance(cat_val, dict):
            continue
        for path in enumerate_paths(cat_val):
            if path_depth(path) >= 2:
                leaf = path.split("/")[-1]
                if leaf not in order:
                    order[leaf] = idx
                    idx += 1
    return order


def _write_note_applescript(
    title: str,
    body: str,
    folder: str | None,
    dry_run: bool,
    container: str = "",
    account: str = "",
    _con: Console | None = None,
) -> tuple[str, str]:
    """Create or update a note in Apple Notes with the given title and body.

    Returns (status, local_id).
    status is one of: "created", "updated", "[DRY RUN]", "error".
    local_id is the note's local identifier (e.g. "p123") for applenotes:// links,
    or empty string for dry-run and error cases.
    """
    _c = _con or console
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
        account,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout.strip()
    if result.returncode != 0 or result.stderr.strip():
        err = result.stderr.strip() or output
        _c.print(f"[red][ERROR] {title}: {err}[/red]")
        return "error", ""
    status, _, local_id = output.partition(":")
    return status or "updated", local_id


def _build_home_body(
    taxonomy: dict,
    hub_index: dict[str, dict],
    home_index: dict[str, dict],
    hub_prefix: str,
    home_title: str,
    hub_ids: dict[str, str] | None = None,
    hub_uuids: dict[str, str] | None = None,
    use_links: bool = False,
    export_sf_order: dict[str, int] | None = None,
) -> str:
    """Build the taxonomy-driven ✱ Home note body as HTML.

    Categories appear in taxonomy file order; headings use the folder: value.
    hub_index: subfolders that have a Hub note (>= min_notes_for_hub). These
      receive Hub-title rendering and, when use_links=True, applenotes:// links.
    home_index: all subfolders listed on Home (>= min_notes_for_home_link).
      Entries present here but absent from hub_index appear as plain leaf names
      (no Hub note exists to link to).
    export_sf_order: path → position from the loaded export (Apple Notes native
      sidebar order). When provided, subfolders within each category are sorted
      by this order so the Home page reflects the user's current Notes arrangement.
      Taxonomy subfolders absent from the export fall to the end, then alphabetical.
    The home_title is placed first so Apple Notes uses it as the note title.
    """
    hub_eligible: set[str] = set(hub_index.keys())
    hub_ids = hub_ids or {}
    hub_uuids = hub_uuids or {}
    cats = taxonomy.get("taxonomy", {})
    parts: list[str] = [f"<h1>{html.escape(home_title)}</h1>", "<br>"]
    _n_sf = len(export_sf_order) if export_sf_order else 0

    for cat_key, cat_val in cats.items():
        if not isinstance(cat_val, dict):
            continue
        heading = folder_name(cat_val) or cat_key.capitalize()
        parts.append(f"<h2>{html.escape(heading)}</h2>")
        deep_paths = [p for p in enumerate_paths(cat_val) if path_depth(p) >= 2]
        if deep_paths:
            # Sort subfolders by Apple Notes native sidebar order when available;
            # fall back to taxonomy list order for paths not yet in the export.
            if export_sf_order:
                deep_paths = sorted(
                    deep_paths,
                    key=lambda p: (export_sf_order.get(p, _n_sf), p),
                )
            parts.append("<ul>")
            for path in deep_paths:
                depth = path_depth(path)
                leaf = path.split("/")[-1]
                indent = "&nbsp;&nbsp;" * (depth - 2)
                if leaf in hub_eligible:
                    h_title = _hub_title(hub_index[leaf]["_sf_def"], hub_prefix)
                    if use_links:
                        uuid = hub_uuids.get(h_title, "")
                        local_id = hub_ids.get(h_title, "")
                        parts.append(f"<li>{indent}{_note_link(h_title, local_id, uuid)}</li>")
                    else:
                        parts.append(f"<li>{indent}{html.escape(h_title)}</li>")
                elif leaf in home_index:
                    parts.append(f"<li>{indent}{html.escape(leaf)}</li>")
            parts.append("</ul>")
        parts.append("<br>")

    parts.append("<p>#ForeverNotes</p>")
    return "\n".join(parts)


def run_sync_hubs(
    export_file: str | None = None, dry_run: bool = False, json_output: bool = False
) -> None:
    _con = Console(stderr=True) if json_output else console
    settings = load_settings()

    mode = settings.get("forever_notes_mode", "loose")
    if mode != "strict":
        _con.print(
            "[yellow]Strict mode is not enabled.[/yellow] "
            "Set [bold]forever_notes_mode: strict[/bold] in settings.local.yaml to use sync-hubs."
        )
        if json_output:
            emit_result(
                "sync-hubs",
                status="error",
                dry_run=dry_run,
                error="Strict mode is not enabled.",
            )
        return

    strict = settings.get("strict_mode", {})
    hub_prefix = strict.get("hub_title_prefix", f"{HEAVY_ASTERISK} ")
    home_title = strict.get("home_note_title", f"{HEAVY_ASTERISK} Home")
    home_folder = strict.get("home_note_folder") or None
    hub_folder = strict.get("hub_note_folder") or None
    use_links = strict.get("internal_links", "text") == "html"
    primary_account = settings.get("primary_account", "")

    tl_cfg = settings.get("toplevel_folder", {})
    container = tl_cfg.get("name", "") if tl_cfg.get("enabled", False) else ""

    thresholds = settings.get("thresholds", {})
    min_hub = int(thresholds.get("min_notes_for_hub", 3))
    min_home = int(thresholds.get("min_notes_for_home_link", 1))

    taxonomy = load_taxonomy()
    if not local_taxonomy_exists():
        _con.print(
            "[yellow]Warning:[/yellow] config/taxonomy.local.yaml not found — "
            "hub notes cannot be generated without real folder names.\n"
            "  Run 'uv run notes setup' to configure your taxonomy, or copy a template:\n"
            "  taxonomy.zettelkasten.yaml / taxonomy.para.yaml / taxonomy.gtd.yaml"
        )

    if export_file:
        export_path = Path(export_file)
    else:
        try:
            export_path = find_latest_export()
        except FileNotFoundError as exc:
            if json_output:
                emit_result("sync-hubs", status="error", dry_run=dry_run, error=str(exc))
            else:
                _con.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    _con.print(f"Loading export: [dim]{export_path.name}[/dim]")
    with open(export_path) as f:
        notes: list[dict] = json.load(f)
    _con.print(f"  {len(notes)} notes loaded")

    # Normalize folder_path values: strip the container prefix when toplevel_folder
    # is enabled, matching what the export script does at write time.  If the export
    # was run before the setting was enabled, paths still carry the container prefix
    # (e.g. "Library/Areas/Finance") and _build_theme_index would find no matches
    # against the taxonomy's bare subfolder paths (e.g. "Areas/Finance").
    if container:
        _cprefix = container + "/"
        notes = [
            {**n, "folder_path": n["folder_path"][len(_cprefix) :]}
            if n.get("folder_path", "").startswith(_cprefix)
            else n
            for n in notes
        ]

    # Build export-derived ordering dicts so Home/Hub rendering reflects the user's
    # current Apple Notes sidebar arrangement rather than (possibly stale) taxonomy
    # list order.  AppleScript returns folders in native UI order, so first-appearance
    # in the export mirrors what the user sees in their Notes sidebar.
    _seen_ep: set[str] = set()
    export_sf_order: dict[str, int] = {}  # subfolder paths (depth ≥ 2) → position
    export_top_order: dict[str, int] = {}  # top-level folder names → position
    _sf_idx = _top_idx = 0
    for _n in notes:
        _fp = _n.get("folder_path", "")
        if not _fp or _fp in _seen_ep:
            continue
        _seen_ep.add(_fp)
        _top = _fp.split("/")[0]
        if _top not in export_top_order:
            export_top_order[_top] = _top_idx
            _top_idx += 1
        if "/" in _fp:
            export_sf_order[_fp] = _sf_idx
            _sf_idx += 1

    hub_index = _build_theme_index(taxonomy, notes, min_hub)
    home_index = _build_theme_index(taxonomy, notes, min_home)

    if not home_index:
        _con.print(
            "[yellow]No home-eligible subfolders found.[/yellow]\n"
            "  Common causes:\n"
            "  1. No subfolders are defined in config/taxonomy.local.yaml\n"
            f"  2. No notes have been moved into subfolders yet — run: uv run notes export, then uv run notes move\n"
            f"  3. All subfolders are below the threshold "
            f"(min_notes_for_home_link: {min_home} in settings.local.yaml)\n"
            "  4. The export was run before toplevel_folder.enabled was set — re-run: uv run notes export"
        )
        if json_output:
            emit_result(
                "sync-hubs",
                dry_run=dry_run,
                summary={"hubs_created": 0, "hubs_updated": 0, "errors": 0},
            )
        return

    _con.print(
        f"\nFound [bold]{len(hub_index)}[/bold] Hub note(s), "
        f"[bold]{len(home_index)}[/bold] Home-listed subfolder(s)."
    )
    if dry_run:
        _con.print("[dim](dry-run — no writes)[/dim]\n")

    # UUID lookups are only needed when internal_links: "html" is set.
    # Skip them (and the Full Disk Access requirement) in the default "text" mode.
    if use_links:
        all_note_pks = [
            _url_id(nid)
            for theme_data in hub_index.values()
            for note_pairs in theme_data["categories"].values()
            for _, nid in note_pairs
            if _url_id(nid)
        ]
        note_uuid_map = _lookup_uuids(all_note_pks, _con=_con)
        if note_uuid_map:
            _con.print(f"  [dim]Resolved {len(note_uuid_map)} note UUID(s) from NoteStore.[/dim]")
    else:
        note_uuid_map = {}

    logger = RunLogger("sync-hubs", logs_dir_path(settings))
    created = updated = errors = 0
    hub_ids: dict[str, str] = {}  # hub_title → local pNNN returned by AppleScript

    # Build cat_order using export top-level folder positions so Hub note category
    # sections appear in the user's current Apple Notes sidebar order.  Fall back to
    # taxonomy position when the folder isn't in the export (e.g. pre-move).
    # cat_display = cat_key.capitalize() is how _build_theme_index sets display names.
    _fn = taxonomy.get("taxonomy", {})
    _n_cats = len(_fn)
    cat_order = {
        folder_name(v) or k.capitalize(): export_top_order.get(
            folder_name(v) or k.capitalize(), _n_cats + i
        )
        for i, (k, v) in enumerate(_fn.items())
    }

    # Process Hub notes in taxonomy subfolder order (matches sidebar); alphabetical fallback.
    t_order = _theme_order(taxonomy)
    n_themes = len(t_order)
    for _theme_name, theme_data in sorted(
        hub_index.items(), key=lambda x: (t_order.get(x[0], n_themes), x[0])
    ):
        sf_def = theme_data["_sf_def"]
        h_title = _hub_title(sf_def, hub_prefix)
        categories = theme_data["categories"]
        total = theme_data["total"]

        _con.print(
            f"  [bold]{h_title}[/bold] — {total} notes across {len(categories)} categor{'y' if len(categories) == 1 else 'ies'}"
        )

        body = _generate_hub_body(
            sf_def,
            categories,
            hub_prefix,
            uuid_map=note_uuid_map,
            use_links=use_links,
            cat_order=cat_order,
        )
        status, local_id = _write_note_applescript(
            h_title,
            body,
            hub_folder,
            dry_run,
            container=container,
            account=primary_account,
            _con=_con,
        )
        if local_id:
            hub_ids[h_title] = local_id

        if status == "created":
            _con.print("    [green][CREATED][/green]")
            logger.event("hub", title=h_title, status="created")
            created += 1
        elif status == "[DRY RUN]":
            _con.print("    [cyan][DRY RUN][/cyan]")
            logger.event("hub", title=h_title, status="dry_run")
        elif status == "error":
            logger.error(f"hub write failed: {h_title}")
            errors += 1
        else:
            _con.print("    [dim][UPDATED][/dim]")
            logger.event("hub", title=h_title, status="updated")
            updated += 1

    # Resolve stable UUIDs for hub notes themselves (for Home → Hub links).
    # Only needed when internal_links: "html"; skip otherwise.
    if use_links and hub_ids:
        hub_pks = [_url_id(lid) for lid in hub_ids.values() if _url_id(lid)]
        hub_pk_to_uuid = _lookup_uuids(hub_pks, _con=_con)
        hub_uuids: dict[str, str] = {
            title: hub_pk_to_uuid.get(_url_id(lid), "") for title, lid in hub_ids.items()
        }
        resolved = sum(1 for v in hub_uuids.values() if v)
        if resolved:
            _con.print(f"  [dim]Resolved {resolved} hub UUID(s) for Home note links.[/dim]")
    else:
        hub_uuids = {}

    # ✱ Home — built after Hubs so hub_ids/hub_uuids contain fresh identifiers
    _con.print(f"\n  [bold]{home_title}[/bold] — root index")
    home_body = _build_home_body(
        taxonomy,
        hub_index,
        home_index,
        hub_prefix,
        home_title,
        hub_ids,
        hub_uuids,
        use_links=use_links,
        export_sf_order=export_sf_order,
    )

    home_status, _ = _write_note_applescript(
        home_title,
        home_body,
        home_folder,
        dry_run,
        container=container,
        account=primary_account,
        _con=_con,
    )
    if home_status == "created":
        _con.print("    [green][CREATED][/green]")
    elif home_status == "[DRY RUN]":
        _con.print("    [cyan][DRY RUN][/cyan]")
    elif home_status == "error":
        errors += 1
    else:
        _con.print("    [dim][UPDATED][/dim]")

    _con.print(
        f"\n[bold]Done.[/bold] Hubs: {created} created, {updated} updated"
        + (f", {errors} errors" if errors else "")
        + "."
    )
    if dry_run:
        _con.print("[dim]Dry-run — no changes were made.[/dim]")

    hubs_summary: dict[str, object] = {
        "hubs_created": created,
        "hubs_updated": updated,
        "errors": errors,
    }
    log_file = logger.finish(
        summary=hubs_summary,
        dry_run=dry_run,
        params={"export_file": str(export_path)},
    )
    if json_output:
        emit_result("sync-hubs", dry_run=dry_run, log_file=log_file, summary=hubs_summary)
