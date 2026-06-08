"""notes arrange — interactive Home page category ordering."""

from __future__ import annotations

import json
import re

import typer
from rich.console import Console

from scripts.config import CONFIG_DIR, load_settings, load_taxonomy
from scripts.folder_utils import folder_name

console = Console()


def _read_settings_text() -> str | None:
    path = CONFIG_DIR / "settings.local.yaml"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _write_folder_order(order: list[str], dry_run: bool) -> None:
    path = CONFIG_DIR / "settings.local.yaml"
    content = _read_settings_text()
    if content is None:
        console.print(
            "[red]settings.local.yaml not found.[/red] Run [bold]notes setup[/bold] first."
        )
        raise typer.Exit(1)

    order_str = json.dumps(order)
    new_content = re.sub(
        r"^(\s+folder_order:).*$",
        f"\\1 {order_str}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    if new_content == content and not order:
        return

    if dry_run:
        console.print(
            f"  [dim]Would set Home page folder_order: {order_str} in settings.local.yaml[/dim]"
        )
        return

    path.write_text(new_content, encoding="utf-8")


def _taxonomy_folders(taxonomy: dict) -> list[str]:
    return [
        folder_name(v) or k.capitalize()
        for k, v in taxonomy.get("taxonomy", {}).items()
        if isinstance(v, dict)
    ]


def run_arrange(dry_run: bool = False, reset: bool = False) -> None:
    settings = load_settings()
    mode = settings.get("forever_notes_mode", "loose")
    if mode != "strict":
        console.print(
            "[yellow]Strict mode is not enabled.[/yellow] "
            "Set [bold]forever_notes_mode: strict[/bold] in settings.local.yaml to use arrange. "
            "The Home page is only available in strict mode."
        )
        raise typer.Exit(1)

    taxonomy = load_taxonomy()
    folders = _taxonomy_folders(taxonomy)
    if not folders:
        console.print(
            "[yellow]No top-level taxonomy folders found.[/yellow] Check taxonomy.local.yaml."
        )
        raise typer.Exit(1)

    if reset:
        _write_folder_order([], dry_run)
        if dry_run:
            console.print(
                "  [dim]Would clear Home page folder order (restore automatic ordering).[/dim]"
            )
        else:
            console.print(
                "[green]Home page folder order cleared.[/green] "
                "Automatic ordering (sidebar / export) restored."
            )
        return

    strict = settings.get("strict_mode", {})
    saved: list[str] = strict.get("folder_order") or []
    saved_valid = [f for f in saved if f in folders]

    if len(saved_valid) == len(folders):
        current = saved_valid
    else:
        current = folders

    console.print(
        "\nHome page category order — type new order as space-separated numbers, or Enter to keep:\n"
    )
    for i, name in enumerate(current, 1):
        console.print(f"  {i}. {name}")

    default_str = " ".join(str(i) for i in range(1, len(current) + 1))

    while True:
        raw = typer.prompt(f"\nNew order [{default_str}]", default="").strip()
        if not raw:
            console.print("  [dim]Order unchanged.[/dim]")
            return

        parts = raw.split()
        try:
            indices = [int(p) for p in parts]
        except ValueError:
            console.print(f"  [red]Enter numbers only (e.g. {default_str}).[/red]")
            continue

        if len(indices) != len(folders):
            console.print(f"  [red]Enter exactly {len(folders)} numbers.[/red]")
            continue
        if len(set(indices)) != len(indices):
            console.print("  [red]No duplicates allowed.[/red]")
            continue
        if any(i < 1 or i > len(folders) for i in indices):
            console.print(f"  [red]Numbers must be between 1 and {len(folders)}.[/red]")
            continue

        new_order = [current[i - 1] for i in indices]
        break

    console.print("\nNew order:")
    for i, name in enumerate(new_order, 1):
        console.print(f"  {i}. {name}")
    console.print()

    if not typer.confirm("Save this order?", default=True):
        console.print("  [dim]Cancelled — no changes written.[/dim]")
        return

    _write_folder_order(new_order, dry_run)
    if not dry_run:
        console.print(
            "[green]Home page folder order saved.[/green] Run [bold]notes sync-hubs[/bold] to apply."
        )
