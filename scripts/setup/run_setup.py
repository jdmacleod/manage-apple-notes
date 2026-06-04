"""Interactive setup wizard — `notes setup` command."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

import questionary
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scripts.config import CONFIG_DIR, find_latest_export, load_settings
from scripts.setup.frameworks import FRAMEWORKS, framework_choices, get_framework
from scripts.setup.scorer import score

con = Console()


# ── Corpus analysis ────────────────────────────────────────────────────────────


def _find_export_optional() -> Path | None:
    try:
        return find_latest_export()
    except FileNotFoundError:
        return None


def analyze_corpus(export_path: Path) -> dict:
    """Extract organizational signals from an export JSON."""
    with open(export_path) as f:
        notes = json.load(f)

    if not notes:
        return {}

    note_count = len(notes)
    folder_count = len({n.get("folder", "") for n in notes if n.get("folder")})

    _TASK_RE = re.compile(r"\bTODO\b|\bWAITING\b|\bnext:\s|\bDONE\b|@[a-zA-Z]|- \[ \]", re.I)
    _XREF_RE = re.compile(r"\[\[[^\]]+\]\]")

    word_counts: list[int] = []
    task_count = 0
    cross_ref_count = 0
    oldest_dt: datetime | None = None

    for note in notes:
        body = note.get("body", "") or ""
        word_counts.append(len(body.split()))
        if _TASK_RE.search(body):
            task_count += 1
        if _XREF_RE.search(body):
            cross_ref_count += 1
        modified_str = note.get("modified", "")
        if modified_str:
            try:
                dt = datetime.fromisoformat(modified_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if oldest_dt is None or dt < oldest_dt:
                    oldest_dt = dt
            except ValueError:
                pass

    avg_word_count = mean(word_counts) if word_counts else 0.0
    now = datetime.now(tz=UTC)
    oldest_note_days = (now - oldest_dt).days if oldest_dt else 0

    return {
        "note_count": note_count,
        "folder_count": folder_count,
        "avg_word_count": avg_word_count,
        "task_keyword_pct": task_count / note_count if note_count else 0.0,
        "cross_ref_pct": cross_ref_count / note_count if note_count else 0.0,
        "oldest_note_days": oldest_note_days,
    }


def _display_corpus_summary(corpus: dict) -> None:
    note_count = corpus["note_count"]
    folder_count = corpus["folder_count"]
    avg_words = corpus["avg_word_count"]
    task_pct = int(corpus["task_keyword_pct"] * 100)
    xref_pct = int(corpus["cross_ref_pct"] * 100)
    oldest_days = corpus["oldest_note_days"]

    if oldest_days >= 365:
        oldest_label = f"{oldest_days // 365} year(s) ago"
    elif oldest_days >= 30:
        oldest_label = f"{oldest_days // 30} month(s) ago"
    else:
        oldest_label = f"{oldest_days} day(s) ago"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")
    table.add_row("Notes found:", str(note_count))
    table.add_row("Folders:", str(folder_count))
    table.add_row("Avg note length:", f"{int(avg_words)} words")
    table.add_row("Task-style notes:", f"{task_pct}%")
    table.add_row("Cross-references:", f"{xref_pct}%")
    table.add_row("Oldest note:", oldest_label)

    con.print(Panel(table, title="Your Notes at a Glance", border_style="blue"))


# ── Dialogue helpers ───────────────────────────────────────────────────────────


def _ask_numbered(question: str, options: list[str], default: int | None = None) -> int:
    """Print numbered options and return 1-based selection (loops until valid).

    If default is provided, pressing Enter without typing accepts that choice.
    """
    con.print(f"\n[bold]{question}[/bold]")
    for i, opt in enumerate(options, 1):
        marker = " [dim](default)[/dim]" if i == default else ""
        con.print(f"  {i}) {opt}{marker}")
    prompt_text = f"\nYour choice [{default}]" if default is not None else "\nYour choice"
    while True:
        raw = typer.prompt(prompt_text, default="")
        if raw.strip() == "" and default is not None:
            return default
        try:
            val = int(raw.strip())
            if 1 <= val <= len(options):
                return val
        except ValueError:
            pass
        con.print(f"[red]Please enter a number between 1 and {len(options)}.[/red]")


# ── Folder name collection ─────────────────────────────────────────────────────


def _collect_folder_names(framework_key: str, existing_folders: list[str]) -> dict[str, str]:
    """Prompt for a folder name for each category in the chosen framework.

    When existing_folders is non-empty, uses questionary.autocomplete() so the
    user can pick an existing Apple Notes folder or type a new name. Falls back
    to plain typer.prompt() when no folder list is available.
    """
    fw = get_framework(framework_key)
    if existing_folders:
        con.print(
            "\n[bold]Name your folders.[/bold]  Select an existing folder or type a new name.\n"
        )
    else:
        con.print(
            "\n[bold]Name your folders.[/bold]  Press Enter to accept the default, "
            "or type your preferred name.\n"
        )
    folder_map: dict[str, str] = {}
    for key in fw["category_keys"]:
        default = fw["canonical_names"][key]
        prompt_label = fw["category_prompts"][key]
        if existing_folders:
            answer = questionary.autocomplete(
                f"  {prompt_label}",
                choices=existing_folders,
                default=default,
            ).ask()
            if answer is None:
                raise typer.Abort()
            name = answer.strip() or default
        else:
            name = typer.prompt(f"  {prompt_label}", default=default).strip() or default
        folder_map[key] = name
    return folder_map


def _collect_existing_folders(
    existing_folders: list[str], container: str | None = None
) -> dict[str, str]:
    """For the Existing path: map user's current folders to category keys.

    When existing_folders is non-empty, uses questionary.select() so the user
    can pick directly from their Apple Notes folders. Falls back to typer.prompt()
    when no folder list is available.

    When container is provided, the picker shows leaf names but the stored value
    is the full path (e.g. "Library/Inbox") so the taxonomy is immediately usable.
    """
    mapping_prompts = FRAMEWORKS["EXISTING"]["mapping_prompts"]
    if existing_folders:
        location = f"inside '{container}'" if container else "at the account root"
        con.print(
            f"\n[bold]Map your existing folders to each role.[/bold]  "
            f"Select your Apple Notes folder ({location}) for each role.\n"
        )
    else:
        con.print(
            "\n[bold]Map your existing folders to each role.[/bold]  "
            "Type your Apple Notes folder name for each role, or press Enter to skip.\n"
        )
    folder_map: dict[str, str] = {}
    _skip = "--- skip ---"
    for key, prompt in mapping_prompts.items():
        if existing_folders:
            answer = questionary.select(
                f"  {prompt}",
                choices=existing_folders + [_skip],
            ).ask()
            if answer is None:
                raise typer.Abort()
            if answer != _skip:
                folder_map[key] = f"{container}/{answer}" if container else answer
        else:
            name = typer.prompt(f"  {prompt}", default="").strip()
            if name:
                folder_map[key] = name
    return folder_map


# ── YAML generation ────────────────────────────────────────────────────────────


def _build_taxonomy_yaml(framework_key: str, folder_map: dict[str, str]) -> str:
    fw = get_framework(framework_key)
    data: dict = {"taxonomy": {}}
    for key in fw["category_keys"]:
        folder_name = folder_map.get(key, "")
        if folder_name:
            data["taxonomy"][key] = {"folder": folder_name}
    header = (
        f"# taxonomy.local.yaml - generated by `notes setup`\n"
        f"# Framework: {fw['full_name'] if framework_key != 'EXISTING' else 'Custom (existing folders)'}\n"
        f"# Edit this file to rename folders or add subfolders.\n\n"
    )
    return header + str(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def _build_existing_taxonomy_yaml(folder_map: dict[str, str]) -> str:
    data: dict = {"taxonomy": {}}
    for key, name in folder_map.items():
        data["taxonomy"][key] = {"folder": name}
    header = (
        "# taxonomy.local.yaml - generated by `notes setup`\n"
        "# Framework: Custom (existing folders)\n"
        "# Edit this file to rename folders or add subfolders.\n\n"
    )
    return header + str(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


# ── Export-based taxonomy detection ───────────────────────────────────────────

_ROLE_KEYWORDS: dict[str, list[str]] = {
    "inbox": ["inbox", "capture", "collect"],
    "fleeting": ["fleeting", "scratch", "quick"],
    "literature": ["literature", "reading", "books"],
    "permanent": ["permanent", "evergreen", "zettel"],
    "projects": ["project"],
    "areas": ["area"],
    "resources": ["resource", "reference"],
    "archive": ["archive"],
    "review": ["review", "triage"],
}

# Roles that belong to each paradigm — used for framework inference
_PARA_ROLES: frozenset[str] = frozenset({"projects", "areas", "resources", "archive"})
_ZK_ROLES: frozenset[str] = frozenset({"fleeting", "literature", "permanent"})
# Roles surfaced regardless of inferred framework
_UNIVERSAL_ROLES: frozenset[str] = frozenset({"inbox", "archive"})

# Display order within each framework group (most to least important)
_ROLE_DISPLAY_ORDER: list[str] = [
    "inbox",
    "archive",
    "projects",
    "areas",
    "resources",
    "fleeting",
    "literature",
    "permanent",
    "review",
]

_ROLE_DESC: dict[str, str] = {
    "inbox": "landing zone for new notes; required by `notes triage`",
    "archive": "stores completed or inactive notes",
    "projects": "active projects with a defined outcome",
    "areas": "ongoing responsibilities without an end date",
    "resources": "reference material and notes on topics of interest",
    "fleeting": "quick captures before processing",
    "literature": "reading notes and summaries",
    "permanent": "permanent/evergreen knowledge notes",
    "review": "notes awaiting triage or decision",
}


def _infer_framework(role_map: dict[str, str]) -> str:
    """Infer the organisational framework from which roles are already present.

    Returns "para", "zettelkasten", or "unknown".
    """
    covered = set(role_map.keys())
    para_score = len(_PARA_ROLES & covered)
    zk_score = len(_ZK_ROLES & covered)
    if zk_score >= 2 and zk_score >= para_score:
        return "zettelkasten"
    if para_score >= 2:
        return "para"
    return "unknown"


def _relevant_missing_roles(missing_roles: list[str], role_map: dict[str, str]) -> list[str]:
    """Filter missing roles to those relevant for the inferred framework.

    PARA users see PARA + universal roles; Zettelkasten users see ZK + universal roles.
    When the framework is unclear, only universal roles (inbox, archive) are suggested —
    the user can always add more by editing taxonomy.local.yaml.
    """
    framework = _infer_framework(role_map)
    if framework == "para":
        relevant = _PARA_ROLES | _UNIVERSAL_ROLES
    elif framework == "zettelkasten":
        relevant = _ZK_ROLES | _UNIVERSAL_ROLES
    else:
        relevant = _UNIVERSAL_ROLES
    filtered = [r for r in missing_roles if r in relevant]
    # Preserve _ROLE_DISPLAY_ORDER within the filtered set
    ordered = [r for r in _ROLE_DISPLAY_ORDER if r in filtered]
    ordered += [r for r in filtered if r not in _ROLE_DISPLAY_ORDER]
    return ordered


def _extract_folders_from_export(export_path: Path) -> tuple[list[str], dict[str, int]]:
    """Return unique folder_path values in first-seen order plus per-path note counts.

    First-seen order reflects Apple Notes' sidebar arrangement because the export script
    walks folders top-to-bottom. Uses folder_path (full slash-delimited path) in
    preference to folder (leaf only).
    """
    with open(export_path) as f:
        notes = json.load(f)
    counts: dict[str, int] = {}
    for n in notes:
        path = n.get("folder_path", "") or n.get("folder", "")
        if path:
            counts[path] = counts.get(path, 0) + 1
    return list(counts.keys()), counts


def _group_paths_into_tree(full_paths: list[str]) -> dict[str, list[str]]:
    """Group full slash-delimited paths into {top_level: [direct_child_names]}.

    Preserves first-seen order for both top-level keys and children, reflecting
    the user's Apple Notes sidebar arrangement (Apple Notes sidebar order is
    preserved through the export). Only the first two path components are used;
    deeper nesting is collapsed to the second level.
    """
    tree: dict[str, list[str]] = {}
    for path in full_paths:
        parts = path.split("/")
        top = parts[0]
        if top not in tree:
            tree[top] = []
        if len(parts) > 1:
            child = parts[1]
            if child not in tree[top]:
                tree[top].append(child)
    return {k: v for k, v in tree.items()}


def _auto_map_roles(top_level_folders: list[str]) -> dict[str, str]:
    """Heuristically assign standard taxonomy role keys to top-level folder names."""
    mapping: dict[str, str] = {}
    for folder in top_level_folders:
        leaf = folder.lower().strip()
        for role, keywords in _ROLE_KEYWORDS.items():
            if role not in mapping and any(kw in leaf for kw in keywords):
                mapping[role] = folder
                break
    return mapping


def _build_taxonomy_from_export(
    tree: dict[str, list[str]],
    role_map: dict[str, str],
) -> str:
    """Build taxonomy YAML from a folder tree derived from the export.

    Top-level folders that match a standard role use semantic keys (inbox,
    projects, …) and include their subfolders list. Unmatched folders get keys
    derived from their name with collision handling.
    """
    role_reverse = {v: k for k, v in role_map.items()}
    data: dict = {"taxonomy": {}}
    used_keys: set[str] = set()
    for top_level, subfolders in tree.items():
        role_key = role_reverse.get(top_level)
        if role_key and role_key not in used_keys:
            key = role_key
        else:
            base = re.sub(r"[^a-z0-9]+", "_", top_level.lower()).strip("_") or "folder"
            key = base
            suffix = 2
            while key in used_keys:
                key = f"{base}_{suffix}"
                suffix += 1
        used_keys.add(key)
        entry: dict = {"folder": top_level}
        if subfolders:
            entry["subfolders"] = subfolders
        data["taxonomy"][key] = entry
    header = (
        "# taxonomy.local.yaml - generated by `notes setup`\n"
        "# Framework: Custom (derived from export)\n"
        "# Edit this file to rename folders or add subfolders.\n\n"
    )
    return header + str(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def _gtd_categories_snippet() -> str:
    """Return YAML snippet for the GTD-specific category keys to add to settings."""
    extra = FRAMEWORKS["GTD"]["extra_categories"]
    return str(
        yaml.dump(
            {"categories": extra}, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
    )


# ── Account and folder detection ──────────────────────────────────────────────

_LIST_ACCOUNTS_SCRIPT = CONFIG_DIR.parent / "scripts" / "export" / "list-accounts.applescript"
_LIST_FOLDERS_SCRIPT = CONFIG_DIR.parent / "scripts" / "export" / "list-folders.applescript"
_LIST_SUBFOLDERS_SCRIPT = CONFIG_DIR.parent / "scripts" / "export" / "list-subfolders.applescript"
_SETUP_ACCOUNT_FILE = Path("/tmp/notes_setup_account.tmp")
_SETUP_CONTAINER_FILE = Path("/tmp/notes_setup_container.tmp")
_APPLE_LLM_BINARY = CONFIG_DIR.parent / "swift" / "apple-llm" / ".build" / "release" / "apple-llm"


def _detect_accounts() -> list[str]:
    """Return Apple Notes account names via AppleScript. Empty list if detection fails."""
    if not _LIST_ACCOUNTS_SCRIPT.exists():
        return []
    try:
        result = subprocess.run(
            ["osascript", str(_LIST_ACCOUNTS_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [n.strip() for n in result.stdout.strip().splitlines() if n.strip()]
    except (subprocess.TimeoutExpired, OSError):
        return []


def _fetch_top_level_folders(account: str | None) -> list[str]:
    """Return top-level Apple Notes folder names via AppleScript, or [] on any failure.

    Writes the account name to a temp file so the AppleScript can filter to one
    account (same pattern as export-notes.applescript). Returns a sorted list.
    """
    if not _LIST_FOLDERS_SCRIPT.exists():
        return []
    try:
        if account:
            _SETUP_ACCOUNT_FILE.write_text(account)
        else:
            _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        result = subprocess.run(
            ["osascript", str(_LIST_FOLDERS_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        if result.returncode != 0:
            return []
        return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    except Exception:
        _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        return []


def _fetch_subfolders(container: str, account: str | None) -> list[str]:
    """Return subfolder names inside a container folder via AppleScript, or [] on failure."""
    if not _LIST_SUBFOLDERS_SCRIPT.exists():
        return []
    try:
        _SETUP_CONTAINER_FILE.write_text(container)
        if account:
            _SETUP_ACCOUNT_FILE.write_text(account)
        else:
            _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        result = subprocess.run(
            ["osascript", str(_LIST_SUBFOLDERS_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        _SETUP_CONTAINER_FILE.unlink(missing_ok=True)
        _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        if result.returncode != 0:
            return []
        return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    except Exception:
        _SETUP_CONTAINER_FILE.unlink(missing_ok=True)
        _SETUP_ACCOUNT_FILE.unlink(missing_ok=True)
        return []


def _detect_container(
    top_level_folders: list[str], account: str | None
) -> tuple[str | None, list[str]]:
    """Ask whether taxonomy folders are nested inside a container folder.

    Called only when top_level_folders is non-empty. Returns (container_name, folder_list):
    - container_name is None if the user opted out, or the chosen container folder name
    - folder_list is the subfolders of the container (leaf names), or top_level_folders unchanged

    For new-framework paths the leaf names go straight into the taxonomy and the container
    is written to settings.  For the EXISTING path the caller prepends the container name
    to produce full paths (e.g. Library/Inbox) before writing the taxonomy.
    """
    if not top_level_folders:
        return None, top_level_folders

    _NO_CONTAINER = "No container — folders are at the account root"

    con.print("\n[bold]Container folder[/bold]")
    con.print(
        "  Some people nest all taxonomy folders inside a single container\n"
        "  (e.g. Library/Inbox, Library/Projects) to keep the sidebar tidy.\n"
        "  Others keep them at the account root.\n"
    )
    answer = questionary.select(
        "  Do your taxonomy folders live inside a container?",
        choices=top_level_folders + [_NO_CONTAINER],
    ).ask()

    if answer is None:
        raise typer.Abort()

    if answer == _NO_CONTAINER:
        return None, top_level_folders

    container = answer
    subfolders = _fetch_subfolders(container, account)
    if not subfolders:
        con.print(
            f"\n  [dim]No subfolders found inside '{container}' — "
            "using top-level folders instead.[/dim]"
        )
        return None, top_level_folders

    con.print(f"  [dim]Found {len(subfolders)} subfolder(s) inside '{container}'[/dim]")
    return container, subfolders


def _handle_multiple_accounts(accounts: list[str]) -> str:
    """Display a multiple-accounts panel and return the account the user selects."""
    account_list = "\n".join(f"  {i + 1}) {a}" for i, a in enumerate(accounts))
    con.print(
        Panel(
            f"[bold]Multiple Apple Notes accounts detected:[/bold]\n\n"
            f"{account_list}\n\n"
            "Classifying and moving notes across accounts can cause confusion — "
            "folders may share names across accounts and the pipeline will treat "
            "them as one library.\n\n"
            "Select the account you want to organize. Notes from other accounts "
            "will not be exported or moved.",
            title="Multiple accounts",
            border_style="yellow",
        )
    )
    selected = _ask_numbered("Which account do you want to organize?", accounts)
    account = accounts[selected - 1]
    con.print(f"  [dim]Selected {selected}) {account}[/dim]")
    return account


def _write_primary_account_to_settings(account: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^(\s+primary_account:)\s+"[^"]*"',
        rf'\g<1> "{account}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(f'  [dim]Would set primary_account: "{account}" in settings.local.yaml[/dim]')
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]primary_account: "{account}"[/green] in settings.local.yaml')


# ── Provider selection ─────────────────────────────────────────────────────────


def _write_provider_to_settings(provider: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^llm_provider:.*$",
        f'llm_provider: "{provider}"',
        content,
        flags=re.MULTILINE,
        count=1,
    )
    if dry_run:
        con.print(f'  [dim]Would set llm_provider: "{provider}" in settings.local.yaml[/dim]')
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]llm_provider: "{provider}"[/green] in settings.local.yaml')


def _write_env_line(key: str, value: str, dry_run: bool) -> None:
    """Append KEY=value to .env if the key is not already present."""
    env_path = CONFIG_DIR.parent / ".env"
    if dry_run:
        con.print(f"  [dim]Would write {key}=... to .env (not written)[/dim]")
        return
    line = f"{key}={value}\n"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        if re.search(rf"^{re.escape(key)}=", content, flags=re.MULTILINE):
            con.print(f"  [dim]{key} already set in .env — not overwritten[/dim]")
            return
        env_path.write_text(content.rstrip("\n") + "\n" + line, encoding="utf-8")
    else:
        env_path.write_text(line, encoding="utf-8")
    con.print(f"  Wrote [green]{key}[/green] to .env")


def _write_reorganization_mode_to_settings(mode: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^reorganization_mode:.*$",
        f'reorganization_mode: "{mode}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(f'  [dim]Would set reorganization_mode: "{mode}" in settings.local.yaml[/dim]')
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]reorganization_mode: "{mode}"[/green] in settings.local.yaml')


def _write_subfolder_threshold_to_settings(threshold: int, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(\s+min_notes_for_subfolder:)\s+\d+",
        rf"\g<1> {threshold}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(
            f"  [dim]Would set thresholds.min_notes_for_subfolder: {threshold}"
            " in settings.local.yaml[/dim]"
        )
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(
        f"  Set [green]thresholds.min_notes_for_subfolder: {threshold}[/green]"
        " in settings.local.yaml"
    )


def _write_folder_nesting_to_settings(nesting: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(folder_nesting:).*$",
        f'\\1 "{nesting}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(f'  [dim]Would set folder_nesting: "{nesting}" in settings.local.yaml[/dim]')
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]folder_nesting: "{nesting}"[/green] in settings.local.yaml')


def _write_classify_exclude_archive_to_settings(exclude: bool, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(\s+exclude_archive:)\s+\S+",
        rf"\g<1> {str(exclude).lower()}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(
            f"  [dim]Would set classify.exclude_archive: {str(exclude).lower()}"
            " in settings.local.yaml[/dim]"
        )
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(
        f"  Set [green]classify.exclude_archive: {str(exclude).lower()}[/green]"
        " in settings.local.yaml"
    )


def _write_ollama_model_to_settings(model: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    # Match `model:` inside the `ollama:` block specifically to avoid clobbering
    # the anthropic or aws-ollama model keys (which also use `model:`).
    new_content = re.sub(
        r'(  ollama:\n(?:    [^\n]*\n)*?    model:)\s+"[^"]*"',
        rf'\1 "{model}"',
        content,
        count=1,
    )
    if dry_run:
        con.print(
            f'  [dim]Would set llm_providers.ollama.model: "{model}" in settings.local.yaml[/dim]'
        )
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]llm_providers.ollama.model: "{model}"[/green] in settings.local.yaml')


def _write_forever_notes_to_settings(
    mode: str,
    dry_run: bool,
    home_title: str | None = None,
    hub_prefix: str | None = None,
) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(forever_notes_mode:).*$",
        f'\\1 "{mode}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if home_title is not None:
        new_content = re.sub(
            r"^(\s+home_note_title:).*$",
            f'\\1 "{home_title}"',
            new_content,
            count=1,
            flags=re.MULTILINE,
        )
    if hub_prefix is not None:
        new_content = re.sub(
            r"^(\s+hub_title_prefix:).*$",
            f'\\1 "{hub_prefix}"',
            new_content,
            count=1,
            flags=re.MULTILINE,
        )
    parts = [f'forever_notes_mode: "{mode}"']
    if home_title is not None:
        parts.append(f'home_note_title: "{home_title}"')
    if hub_prefix is not None:
        parts.append(f'hub_title_prefix: "{hub_prefix}"')
    if dry_run:
        con.print(f"  [dim]Would set {', '.join(parts)} in settings.local.yaml[/dim]")
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f"  Set [green]{', '.join(parts)}[/green] in settings.local.yaml")


def _ask_forever_notes(dry_run: bool) -> None:
    """Ask whether to enable Hub/Home structure and collect naming preferences."""
    con.print("\n[bold]Forever Notes Hub structure[/bold]")
    con.print(
        "  Hub notes index all your notes on a topic across every folder.\n"
        "  A ✱ Home note serves as a navigable overview of your entire library.\n"
        "  Enable this after your taxonomy is stable; run [cyan]notes sync-hubs[/cyan]\n"
        "  after each classify/move cycle to keep indexes current."
    )
    enable = typer.confirm("\nEnable Hub and Home structure?", default=False)
    if not enable:
        _write_forever_notes_to_settings("loose", dry_run)
        return

    con.print()
    home_title = typer.prompt("  Home note title", default="✱ Home").strip() or "✱ Home"
    hub_prefix = typer.prompt(
        "  Hub note prefix (e.g. '✱ ' → '✱ Health', '✱ Projects')",
        default="✱ ",
    )
    _write_forever_notes_to_settings(
        "strict", dry_run, home_title=home_title, hub_prefix=hub_prefix
    )


def _ask_organization_style(dry_run: bool) -> None:
    """Ask reorganization mode, subfolder threshold, and archive exclusion."""
    con.print("\n[bold]Organization style[/bold]")

    mode_choice = _ask_numbered(
        "How should the AI treat your existing folder structure?",
        [
            "Suggest improvements — reorganize and add subfolders where content warrants it",
            "Respect my structure — prefer existing folders; add subfolders sparingly",
            "Keep structure fixed — no new folders or subfolders",
        ],
        default=2,
    )
    mode_map = {1: "standard", 2: "conservative", 3: "static"}
    nesting_map = {"standard": "natural", "conservative": "natural", "static": "flat"}
    selected_mode = mode_map[mode_choice]
    _write_reorganization_mode_to_settings(selected_mode, dry_run)
    _write_folder_nesting_to_settings(nesting_map[selected_mode], dry_run)

    con.print()
    threshold_choice = _ask_numbered(
        "How many notes on a topic before creating a new subfolder?",
        [
            "A few (5)   — more granular; good for large collections",
            "Several (8) — balanced [recommended]",
            "Many (15)  — fewer folders; simpler; better for small libraries or iPhone",
        ],
        default=2,
    )
    threshold_map = {1: 5, 2: 8, 3: 15}
    _write_subfolder_threshold_to_settings(threshold_map[threshold_choice], dry_run)

    con.print()
    exclude_archive = typer.confirm(
        "Exclude Archive notes from classification?"
        " (Recommended — keeps completed notes out of the reorganization cycle)",
        default=True,
    )
    _write_classify_exclude_archive_to_settings(exclude_archive, dry_run)


def _write_toplevel_folder_to_settings(enabled: bool, name: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^(\s*enabled:)\s*\S+",
        rf"\g<1> {str(enabled).lower()}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    new_content = re.sub(
        r'^(\s*name:)\s*"[^"]*"',
        rf'\g<1> "{name}"',
        new_content,
        count=1,
        flags=re.MULTILINE,
    )
    if dry_run:
        con.print(
            f"  [dim]Would set toplevel_folder.enabled: {str(enabled).lower()}"
            f"{f', name: {name!r}' if enabled else ''} in settings.local.yaml[/dim]"
        )
        return
    settings_path.write_text(new_content, encoding="utf-8")
    if enabled:
        con.print(
            f"  Set [green]toplevel_folder.enabled: true[/green], "
            f"[green]name: {name!r}[/green] in settings.local.yaml"
        )
    else:
        con.print("  Set [green]toplevel_folder.enabled: false[/green] in settings.local.yaml")


def _ask_container(dry_run: bool) -> None:
    """Ask whether to nest taxonomy folders inside a container. Writes to settings."""
    con.print("\n[bold]Folder structure[/bold]")
    con.print(
        "  By default, taxonomy folders are placed at the Apple Notes account root\n"
        "  (e.g. Inbox, Projects, Areas, Resources at the top level).\n\n"
        "  Alternatively, you can nest them all inside a single container folder\n"
        "  (e.g. Library/Inbox, Library/Projects) to keep the sidebar tidy."
    )
    use_container = typer.confirm("\nNest all folders inside a container folder?", default=False)
    if use_container:
        name = typer.prompt("  Container folder name", default="Library").strip() or "Library"
        _write_toplevel_folder_to_settings(enabled=True, name=name, dry_run=dry_run)
    else:
        _write_toplevel_folder_to_settings(enabled=False, name="Library", dry_run=dry_run)


def _check_apple_intelligence_prerequisites() -> None:
    """Check Xcode, Swift bridge binary, and Apple Intelligence availability; print status."""
    con.print("\n  Checking Apple Intelligence prerequisites...")
    all_ok = True

    # 1. Xcode developer tools (required to build the Swift bridge)
    xcode_needs_install = False
    try:
        xcode = subprocess.run(
            ["xcodebuild", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if xcode.returncode == 0:
            first_line = xcode.stdout.strip().splitlines()[0]  # e.g. "Xcode 26.0"
            parts = first_line.split()
            try:
                major = int(parts[1].split(".")[0]) if len(parts) >= 2 else 0
            except (ValueError, IndexError):
                major = 0
            if major >= 26:
                con.print(f"  [green]✓[/green] {first_line}")
            else:
                con.print(f"  [yellow]![/yellow] {first_line} — Xcode 26 required")
                con.print("    [dim]Download Xcode 26: developer.apple.com/xcode[/dim]")
                all_ok = False
                xcode_needs_install = True
        else:
            con.print("  [red]✗[/red] Xcode not installed or not licensed")
            con.print("    [dim]Download Xcode 26: developer.apple.com/xcode[/dim]")
            all_ok = False
            xcode_needs_install = True
    except FileNotFoundError:
        con.print("  [red]✗[/red] Xcode not found")
        con.print("    [dim]Download Xcode 26: developer.apple.com/xcode[/dim]")
        all_ok = False
        xcode_needs_install = True
    except subprocess.TimeoutExpired:
        con.print("  [yellow]![/yellow] Xcode check timed out — skipped")

    if xcode_needs_install:
        _GB = 1024**3
        _XCODE_MIN_GB = 50
        free_gb = shutil.disk_usage("/").free / _GB
        if free_gb < _XCODE_MIN_GB:
            con.print(
                f"  [yellow]![/yellow] {free_gb:.1f} GB free — Xcode needs ~30 GB to download and install"
            )
            con.print(
                "    [dim]You can try the install anyway; it may fail if space runs low.[/dim]"
            )

    # 2. Swift bridge binary
    if _APPLE_LLM_BINARY.is_file():
        con.print("  [green]✓[/green] Swift bridge binary found")
    else:
        con.print("  [red]✗[/red] Swift bridge not yet built")
        if all_ok:
            con.print("    [dim]Build it: make -C swift/apple-llm build[/dim]")
        else:
            con.print(
                "    [dim]Build it after installing Xcode: make -C swift/apple-llm build[/dim]"
            )
        all_ok = False

    # 3. Probe Apple Intelligence availability (fast: unavailable cases exit before inference)
    if _APPLE_LLM_BINARY.is_file():
        try:
            probe = json.dumps({"system": "reply ok", "user": "ok", "max_tokens": 5})
            probe_result = subprocess.run(
                [str(_APPLE_LLM_BINARY)],
                input=probe,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if probe_result.returncode == 0:
                con.print("  [green]✓[/green] Apple Intelligence available")
            elif probe_result.returncode == 2:
                msg = probe_result.stderr.strip().removeprefix("error: ")
                con.print(f"  [yellow]![/yellow] Apple Intelligence: {msg}")
                all_ok = False
            # Exit 1/3/4: unexpected at probe stage but binary is functional; skip
        except subprocess.TimeoutExpired:
            # Inference is running — the device is eligible and AI is responding
            con.print("  [green]✓[/green] Apple Intelligence available")

    if not all_ok:
        con.print(
            "\n  [dim]See GUIDE.md → Apple Intelligence provider for full prerequisites.[/dim]"
        )


def _select_provider(dry_run: bool) -> bool:
    """Ask which LLM provider to use and write config. Returns True if a provider was selected."""
    con.print("\n[bold]LLM provider[/bold]")
    choice = _ask_numbered(
        "Which LLM provider do you want to use?",
        [
            "Apple Intelligence — on-device, free, requires macOS 26 + Apple Silicon",
            "Anthropic API — cloud-based, fast, requires an API key",
            "Ollama (local) — open-weight models, self-hosted, no API key needed",
            "AWS-Ollama — cloud GPU via SSH tunnel, self-hosted",
            "Skip — I'll configure this manually in config/settings.local.yaml",
        ],
        default=1,
    )

    if choice == 1:
        _write_provider_to_settings("apple", dry_run)
        _check_apple_intelligence_prerequisites()
        return True
    elif choice == 2:
        _write_provider_to_settings("anthropic", dry_run)
        api_key = typer.prompt(
            "\n  Anthropic API key (leave blank to add to .env manually)",
            default="",
            hide_input=True,
        ).strip()
        if api_key:
            _write_env_line("ANTHROPIC_API_KEY", api_key, dry_run)
        else:
            con.print(
                "  [dim]Add ANTHROPIC_API_KEY=sk-ant-... to .env before running classify.[/dim]"
            )
        return True
    elif choice == 3:
        _write_provider_to_settings("ollama", dry_run)
        url = typer.prompt(
            "\n  Ollama base URL",
            default="http://localhost:11434",
        ).strip()
        if url and url != "http://localhost:11434":
            _write_env_line("OLLAMA_BASE_URL", url, dry_run)
        model = typer.prompt("\n  Ollama model name", default="llama3.2").strip() or "llama3.2"
        _write_ollama_model_to_settings(model, dry_run)
        return True
    elif choice == 4:
        _write_provider_to_settings("aws-ollama", dry_run)
        con.print(
            "\n[dim]AWS-Ollama requires deploying the EC2 stack first.\n"
            "See docs/aws-infrastructure.md for full prerequisites and setup steps.[/dim]"
        )
        return True
    else:
        return False


# ── File writing ───────────────────────────────────────────────────────────────


def _write_taxonomy(taxonomy_yaml: str, dry_run: bool) -> None:
    taxonomy_path = CONFIG_DIR / "taxonomy.local.yaml"
    if dry_run:
        con.print("\n[dim]── taxonomy.local.yaml (dry run — not written) ──[/dim]")
        con.print(taxonomy_yaml)
        return
    if taxonomy_path.exists():
        bak = taxonomy_path.with_suffix(".yaml.bak")
        shutil.copy2(taxonomy_path, bak)
        con.print(f"  Backed up existing taxonomy → [dim]{bak.name}[/dim]")
    taxonomy_path.write_text(taxonomy_yaml, encoding="utf-8")
    con.print(f"  Wrote [green]{taxonomy_path.relative_to(taxonomy_path.parent.parent)}[/green]")


def _ensure_settings(dry_run: bool) -> bool:
    """Copy settings.example.yaml to settings.local.yaml if not present.
    Returns True if the file was created (or would be created) during this call."""
    settings_path = CONFIG_DIR / "settings.local.yaml"
    example_path = CONFIG_DIR / "settings.example.yaml"
    if settings_path.exists():
        return False
    if dry_run:
        con.print(
            "  [dim]settings.local.yaml not found — would copy from settings.example.yaml[/dim]"
        )
        return True
    shutil.copy2(example_path, settings_path)
    con.print("  Copied [green]settings.local.yaml[/green] from settings.example.yaml")
    return True


# ── Main entrypoint ────────────────────────────────────────────────────────────


def run_setup(dry_run: bool = False, no_corpus: bool = False) -> None:
    con.print(
        Panel(
            "[bold]notes setup[/bold]\n\n"
            "This wizard picks a note organization framework for you, collects your "
            "folder names, and writes [cyan]config/taxonomy.local.yaml[/cyan] and "
            "(on first run) [cyan]config/settings.local.yaml[/cyan].\n\n"
            "It takes about 2 minutes.",
            title="Welcome",
            border_style="green",
        )
    )

    # ── Phase 0: Account detection + folder list ──────────────────────────────
    accounts = _detect_accounts()
    selected_account: str | None = None
    if len(accounts) > 1:
        selected_account = _handle_multiple_accounts(accounts)
    elif len(accounts) == 1:
        con.print(f"[dim]Apple Notes account: {accounts[0]}[/dim]\n")
    else:
        con.print(
            "[dim]Account detection skipped — grant Automation permission "
            "(System Settings → Privacy & Security → Automation) before running "
            "notes export if you haven't already.[/dim]\n"
        )

    # Fetch top-level folder names, then ask whether they live inside a container.
    # Best-effort throughout: empty lists fall back to plain text prompts.
    _primary = selected_account or (accounts[0] if accounts else None)
    raw_top_level = _fetch_top_level_folders(_primary)
    container, existing_folders = _detect_container(raw_top_level, _primary)
    container_question_shown = len(raw_top_level) > 0

    # ── Phase 1: Corpus analysis ───────────────────────────────────────────────
    export_path = _find_export_optional()
    corpus: dict | None = None
    if not no_corpus:
        if export_path:
            with con.status("Analyzing notes…", spinner="dots"):
                corpus = analyze_corpus(export_path)
            if corpus:
                _display_corpus_summary(corpus)
        else:
            con.print(
                "[dim]No export found — run `uv run notes export` first to include corpus "
                "signals in the recommendation. Continuing with questions only.[/dim]\n"
            )

    # ── Phase 2: Dialogue ──────────────────────────────────────────────────────
    q1 = _ask_numbered(
        "What matters most to you going forward?",
        [
            "Get on top of tasks and commitments — I need clarity on what to do next",
            "Keep active work organized — I want clear structure for projects, responsibilities, and reference material",
            "Develop ideas over time — I want my notes to think with me",
            "My current system mostly works — I want small improvements, not an overhaul",
        ],
    )

    q2: int | None = None
    q3: int | None = None

    if q1 != 4:
        q2 = _ask_numbered(
            "How much time are you willing to spend maintaining your note system each week?",
            [
                "As little as possible — it should mostly run itself",
                "10–15 minutes — a light weekly tidy",
                "30+ minutes — I'm willing to invest if the payoff is there",
            ],
        )

        q3 = _ask_numbered(
            "Which best describes how your work or thinking actually unfolds?",
            [
                "Deadline-driven — I'm juggling projects with clear finish lines",
                "Ongoing — I maintain areas of responsibility that never really end",
                "Cumulative — my best ideas build on older ones over months or years",
            ],
        )

    # ── Phase 3: Score ─────────────────────────────────────────────────────────
    recommendation = score(corpus, q1, q2, q3)
    winner = recommendation["winner"]

    # ── Phase 4: Display recommendation ───────────────────────────────────────
    if winner == "EXISTING":
        con.print(
            Panel(
                recommendation["rationale"],
                title="Recommendation: Use Your Existing System",
                border_style="yellow",
            )
        )
    else:
        fw = get_framework(winner)
        confidence = recommendation["confidence"]

        confidence_color = {"high": "green", "moderate": "yellow", "low": "dim"}.get(
            confidence, "white"
        )
        body = (
            f"[bold]{fw['full_name']}[/bold]  "
            f"[{confidence_color}](confidence: {confidence})[/{confidence_color}]\n\n"
            f"{recommendation['rationale']}\n\n"
            f"[dim]Folders:[/dim]  {fw['folder_preview']}\n"
            f"[dim]Maintenance:[/dim]  {fw['maintenance']}\n"
            f"[dim]Best for:[/dim]  {fw['best_for']}"
        )
        con.print(Panel(body, title="Recommendation", border_style="green"))

    # Allow the user to override the recommendation
    choices = framework_choices()
    if winner == "EXISTING":
        accept = typer.confirm("\nProceed with your existing folder structure?", default=True)
        if not accept:
            selected = _ask_numbered("Which framework would you like instead?", choices[:3])
            framework_map = ["PARA", "GTD", "ZETTELKASTEN"]
            winner = framework_map[selected - 1]
        else:
            winner = "EXISTING"
    else:
        fw = get_framework(winner)
        accept = typer.confirm(f"\nUse {fw['name']}?", default=True)
        if not accept:
            selected = _ask_numbered("Which framework would you prefer?", choices)
            framework_map = ["PARA", "GTD", "ZETTELKASTEN", "EXISTING"]
            winner = framework_map[selected - 1]

    # ── Phase 5: Collect folder names ─────────────────────────────────────────
    if winner == "EXISTING":
        if export_path is not None:
            all_paths, note_counts = _extract_folders_from_export(export_path)

            # The export strips "Container/..." prefixes from folder_path, but
            # notes sitting directly IN the container keep folder_path == container_name
            # (the strip uses startswith("Library/"), not an exact match on "Library").
            # Exclude those paths so the container doesn't appear as a taxonomy category.
            effective_container = container  # from Phase 0 AppleScript detection
            if effective_container is None:
                _tlf = load_settings().get("toplevel_folder") or {}
                if _tlf.get("enabled"):
                    effective_container = _tlf.get("name") or None
            if effective_container is not None and effective_container in note_counts:
                n_direct = note_counts[effective_container]
                all_paths = [p for p in all_paths if p != effective_container]
                note_counts = {k: v for k, v in note_counts.items() if k != effective_container}
                con.print(
                    f"\n  [dim]{n_direct} note(s) found directly in "
                    f"'{effective_container}' (container folder) — excluded from taxonomy.[/dim]"
                )

            tree = _group_paths_into_tree(all_paths)
            role_map = _auto_map_roles(list(tree.keys()))
            role_reverse = {v: k for k, v in role_map.items()}

            # Compute per-top-level note counts (sum of all subfolder notes)
            top_counts: dict[str, int] = {}
            for path, count in note_counts.items():
                top = path.split("/")[0]
                top_counts[top] = top_counts.get(top, 0) + count

            con.print(f"\n[dim]Found {len(tree)} top-level folder(s) in your latest export.[/dim]")
            folder_table = Table(
                show_header=True, header_style="bold dim", box=None, padding=(0, 2)
            )
            folder_table.add_column("Folder")
            folder_table.add_column("Notes", justify="right", style="dim")
            folder_table.add_column("Subfolders", justify="right", style="dim")
            folder_table.add_column("Role", style="dim")
            for top_level, subfolders in tree.items():
                role_label = role_reverse.get(top_level, "")
                subfolder_str = str(len(subfolders)) if subfolders else ""
                folder_table.add_row(
                    top_level,
                    str(top_counts.get(top_level, 0)),
                    subfolder_str,
                    role_label,
                )
            con.print(folder_table)

            # Detect standard roles with no matching folder in the export,
            # filtered to roles relevant for the user's apparent framework.
            missing_roles = [r for r in _ROLE_KEYWORDS if r not in role_map]
            missing_in_order = _relevant_missing_roles(missing_roles, role_map)
            added: list[str] = []
            if missing_in_order:
                con.print(
                    "\n  [dim]Some standard folders weren't found in your export."
                    " This can happen when Notes folders are empty —"
                    " the export only includes folders that contain at least one note.[/dim]"
                    "\n  [dim]You'll need to create any added folders in Apple Notes.[/dim]\n"
                )
                for role in missing_in_order:
                    desc = _ROLE_DESC.get(role, "standard taxonomy folder")
                    if typer.confirm(
                        f"  Add '{role.title()}' ({desc})?",
                        default=True,
                    ):
                        tree[role.title()] = []
                        role_map[role] = role.title()
                        added.append(role.title())
                if added:
                    con.print(
                        f"\n  [dim]Added {len(added)} folder(s): {', '.join(added)}. "
                        "Create them in Apple Notes before running `notes move`.[/dim]"
                    )

            if typer.confirm(
                f"\nGenerate taxonomy from these {len(tree)} top-level folder(s)?", default=True
            ):
                taxonomy_yaml = _build_taxonomy_from_export(tree, role_map)
                inbox_in_taxonomy = "inbox" in role_map
            else:
                con.print("  Falling back to manual folder mapping.\n")
                folder_map = _collect_existing_folders(existing_folders, container)
                taxonomy_yaml = _build_existing_taxonomy_yaml(folder_map)
                inbox_in_taxonomy = bool(folder_map.get("inbox", ""))
        else:
            con.print(
                "\n[yellow]No export found.[/yellow]  "
                "Run [cyan]uv run notes export[/cyan] first, then re-run "
                "[cyan]notes setup[/cyan] to auto-generate your taxonomy from your "
                "actual folder structure.\n"
                "Continuing with manual folder mapping.\n"
            )
            folder_map = _collect_existing_folders(existing_folders, container)
            taxonomy_yaml = _build_existing_taxonomy_yaml(folder_map)
            inbox_in_taxonomy = bool(folder_map.get("inbox", ""))
    else:
        folder_map = _collect_folder_names(winner, existing_folders)
        taxonomy_yaml = _build_taxonomy_yaml(winner, folder_map)
        inbox_in_taxonomy = True  # all built-in frameworks include Inbox

    # ── Phase 6: Write config files ────────────────────────────────────────────
    con.print("\n[bold]Writing config files…[/bold]")
    _write_taxonomy(taxonomy_yaml, dry_run)
    settings_created = _ensure_settings(dry_run)

    # GTD: show snippet to add manually (avoids rewriting a potentially customised settings file)
    if winner == "GTD":
        snippet = _gtd_categories_snippet()
        con.print(
            Panel(
                "GTD uses category keys not in the built-in defaults "
                "([cyan]next_actions[/cyan], [cyan]waiting_for[/cyan], etc.).\n\n"
                "Add the following block to the [cyan]categories:[/cyan] section of "
                "[cyan]config/settings.local.yaml[/cyan] so the classifier and audit "
                "use the correct descriptions:\n\n"
                f"[dim]{snippet}[/dim]",
                title="Action needed: settings.local.yaml",
                border_style="yellow",
            )
        )

    # ── Phase 7: Organization style preferences ───────────────────────────────
    if settings_created:
        _ask_organization_style(dry_run)
        _ask_forever_notes(dry_run)

    # ── Phase 8: LLM provider selection ───────────────────────────────────────
    provider_configured = False
    if settings_created:
        provider_configured = _select_provider(dry_run)

    # ── Phase 9: Container folder structure ───────────────────────────────────
    # EXISTING path: taxonomy has full paths already — skip container setting entirely.
    # New framework + container confirmed in Phase 0.5: write directly, no question needed.
    # New framework + user explicitly opted out: leave default (enabled: false) in place.
    # New framework + no folders detected: ask the classic question.
    if settings_created and winner != "EXISTING":
        if container is not None:
            _write_toplevel_folder_to_settings(enabled=True, name=container, dry_run=dry_run)
        elif not container_question_shown:
            _ask_container(dry_run)

    # ── Phase 10: Primary account ──────────────────────────────────────────────
    if settings_created and selected_account is not None:
        _write_primary_account_to_settings(selected_account, dry_run)

    # ── Decision summary ──────────────────────────────────────────────────────
    if not dry_run:
        _fw_labels = {
            "PARA": "PARA",
            "GTD": "GTD",
            "ZETTELKASTEN": "Zettelkasten",
            "EXISTING": "Existing (custom)",
        }
        _reorg_labels = {
            "standard": "Standard  (suggest improvements, add subfolders naturally)",
            "conservative": "Conservative  (prefer existing folders, add subfolders sparingly)",
            "static": "Static  (no new folders or subfolders)",
            "full": "Full  (reorganize freely)",
        }
        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("key", style="dim")
        summary_table.add_column("val")
        summary_table.add_row("Framework:", _fw_labels.get(winner, winner))
        if settings_created:
            _s = load_settings()
            _provider = _s.get("llm_provider") or "—"
            _reorg = _s.get("reorganization_mode", "standard")
            _forever = _s.get("forever_notes_mode", "loose")
            summary_table.add_row("AI Provider:", _provider)
            summary_table.add_row("Reorganization:", _reorg_labels.get(_reorg, _reorg))
            if _forever == "strict":
                _home = (_s.get("strict_mode") or {}).get("home_note_title", "✱ Home")
                summary_table.add_row("Hub/Home notes:", f"Enabled  ({_home})")
        con.print(Panel(summary_table, title="Setup complete", border_style="green"))

    # ── Next steps ─────────────────────────────────────────────────────────────
    next_steps: list[str] = []
    if not provider_configured:
        next_steps.append("Set your LLM provider in config/settings.local.yaml  (see GUIDE.md)")
    if export_path is None:
        if winner == "EXISTING":
            next_steps.append(
                "uv run notes export    — then re-run `notes setup` to auto-detect your taxonomy"
            )
        else:
            next_steps.append("uv run notes export    — pull notes from Apple Notes")
    next_steps += [
        "uv run notes discover  — map thematic clusters → data/theme-maps/",
        "uv run notes classify  — AI classification → proposal",
        "uv run notes review    — review the proposal (place needs-review items)",
        "uv run notes move      — apply the approved proposal",
    ]
    if winner == "EXISTING":
        suggestions = [
            s
            for s in FRAMEWORKS["EXISTING"]["improvement_suggestions"]
            if not (inbox_in_taxonomy and "Inbox" in s)
        ]
        if suggestions:
            next_steps += [
                "",
                "Lightweight improvements to consider:",
                *[f"  • {s}" for s in suggestions],
            ]

    steps_text = "\n".join(next_steps)
    con.print(
        Panel(
            steps_text,
            title="Next Steps",
            border_style="blue",
        )
    )
