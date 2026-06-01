"""Interactive proposal review — `notes review` command."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scripts.config import CONFIG_DIR, load_taxonomy

REPO_ROOT = CONFIG_DIR.parent
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"
DEDUP_PROPOSALS_DIR = REPO_ROOT / "data" / "dedup-proposals"

con = Console()


# ── File finders ───────────────────────────────────────────────────────────────


def find_latest_proposal() -> Path:
    files = sorted(PROPOSALS_DIR.glob("proposal-*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(
            f"No proposal files found in {PROPOSALS_DIR}. Run 'uv run notes classify' first."
        )
    return files[-1]


def find_latest_dedup_proposal() -> Path:
    files = sorted(DEDUP_PROPOSALS_DIR.glob("dedup-*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(
            f"No dedup proposals found in {DEDUP_PROPOSALS_DIR}. Run 'uv run notes dedup' first."
        )
    return files[-1]


# ── Helpers ────────────────────────────────────────────────────────────────────


def build_folder_choices(taxonomy: dict) -> list[dict]:
    """Return an ordered list of {folder, subfolder, path} for all taxonomy destinations."""
    choices: list[dict] = []
    for _key, cat in taxonomy.get("taxonomy", {}).items():
        if not isinstance(cat, dict):
            continue
        folder = cat.get("folder", "")
        if not folder:
            continue
        choices.append({"folder": folder, "subfolder": "", "path": folder})
        for sub in cat.get("subfolders", []):
            sub_name = sub.get("name", "") if isinstance(sub, dict) else str(sub)
            if sub_name:
                choices.append(
                    {"folder": folder, "subfolder": sub_name, "path": f"{folder}/{sub_name}"}
                )
    return choices


def filter_by_confidence(moves: list[dict], threshold: str) -> tuple[list[dict], int]:
    """Remove moves below the threshold. Returns (filtered_list, count_removed)."""
    order = {"high": 2, "medium": 1, "low": 0}
    min_level = order.get(threshold, 0)
    kept = [m for m in moves if order.get(m.get("confidence", "low"), 0) >= min_level]
    return kept, len(moves) - len(kept)


# ── Review flows ───────────────────────────────────────────────────────────────


def review_classify_proposal(proposal: dict, path: Path, confidence: str | None) -> dict:
    """Walk through a classify/triage proposal interactively."""
    moves: list[dict] = list(proposal.get("moves", []))
    needs_review: list[dict] = list(proposal.get("needs_review", []))
    no_change: list[dict] = list(proposal.get("no_change", []))

    # Summary table
    by_conf: dict[str, int] = {}
    for m in moves:
        c = m.get("confidence", "unknown")
        by_conf[c] = by_conf.get(c, 0) + 1

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")
    table.add_row("Moves (high):", str(by_conf.get("high", 0)))
    table.add_row("Moves (medium):", str(by_conf.get("medium", 0)))
    table.add_row("Moves (low):", str(by_conf.get("low", 0)))
    table.add_row("Needs review:", str(len(needs_review)))
    table.add_row("No change:", str(len(no_change)))
    con.print(Panel(table, title=f"Proposal: {path.name}", border_style="blue"))

    # Confidence filter
    if confidence:
        moves, dropped = filter_by_confidence(moves, confidence)
        if dropped:
            con.print(
                f"  Dropped [yellow]{dropped}[/yellow] low-confidence move(s) "
                f"(--confidence {confidence})"
            )

    if not needs_review:
        con.print("  [dim]No needs-review items — nothing to place.[/dim]")
        proposal["moves"] = moves
        return proposal

    # Place needs_review items
    taxonomy = load_taxonomy()
    folder_choices = build_folder_choices(taxonomy)
    if not folder_choices:
        con.print(
            "  [yellow]No taxonomy folders found — cannot place needs-review items. "
            "Run 'uv run notes setup' first.[/yellow]"
        )
        proposal["moves"] = moves
        return proposal

    con.print(f"\n[bold]Placing {len(needs_review)} needs-review note(s)…[/bold]")
    placed_ids: set[str] = set()
    options = [c["path"] for c in folder_choices] + ["Skip — leave in needs_review"]

    for item in needs_review:
        title = item.get("title", "(untitled)")
        current = item.get("current_folder", "")
        reason = item.get("reason", "")

        con.print(f'\n  [bold]"{title}"[/bold]')
        con.print(f"  [dim]Current folder: {current}[/dim]")
        if reason:
            con.print(f"  [dim]Reason: {reason}[/dim]")

        for i, opt in enumerate(options, 1):
            con.print(f"    {i}) {opt}")

        selected = len(options)
        while True:
            raw = typer.prompt("\n  Your choice").strip()
            try:
                val = int(raw)
                if 1 <= val <= len(options):
                    selected = val
                    break
            except ValueError:
                pass
            con.print(f"  [red]Please enter a number between 1 and {len(options)}.[/red]")

        if selected == len(options):
            continue

        dest = folder_choices[selected - 1]
        placed_ids.add(item.get("id", ""))
        moves.append(
            {
                "id": item.get("id", ""),
                "title": title,
                "current_folder": current,
                "proposed_folder": dest["folder"],
                "proposed_subfolder": dest["subfolder"],
                "proposed_folder_path": dest["path"],
                "confidence": "medium",
                "reason": "manually placed by notes review",
            }
        )
        con.print(f"  → [green]{dest['path']}[/green]")

    proposal["moves"] = moves
    proposal["needs_review"] = [r for r in needs_review if r.get("id", "") not in placed_ids]
    return proposal


def review_dedup_proposal(proposal: dict, path: Path) -> dict:
    """Walk through a dedup proposal interactively, confirming each deletion group."""
    groups: list[dict] = list(proposal.get("groups", []))
    delete_groups = [g for g in groups if g.get("resolution") == "delete"]
    review_groups = [g for g in groups if g.get("resolution") == "review"]

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")
    table.add_row("Confirmed duplicates (will delete):", str(len(delete_groups)))
    table.add_row("Needs manual review (not touched):", str(len(review_groups)))
    con.print(Panel(table, title=f"Dedup proposal: {path.name}", border_style="blue"))

    if review_groups:
        con.print(
            f"  [dim]{len(review_groups)} group(s) marked 'review' — "
            "merge or rename these manually in Apple Notes.[/dim]"
        )

    if not delete_groups:
        con.print("  [dim]No confirmed duplicates to review.[/dim]")
        return proposal

    con.print(f"\n[bold]Reviewing {len(delete_groups)} deletion group(s)…[/bold]")
    confirmed_groups: list[dict] = list(review_groups)

    for group in delete_groups:
        notes = group.get("notes", [])
        keep_id = group.get("keep_id", "")
        keep_note = next((n for n in notes if n.get("id") == keep_id), None)
        delete_notes = [n for n in notes if n.get("id") != keep_id]

        con.print(
            f"\n  [bold]Group {group.get('group_id', '?')}[/bold]  "
            f"[dim]({group.get('duplicate_type', 'duplicate')})[/dim]"
        )
        if keep_note:
            preview = (keep_note.get("content_preview") or "")[:120]
            con.print(f"  Keep:   [green]{keep_note.get('title', '(untitled)')}[/green]")
            if preview:
                con.print(f"          [dim]{preview}[/dim]")
        for dn in delete_notes:
            con.print(f"  Delete: [red]{dn.get('title', '(untitled)')}[/red]")
            d_preview = (dn.get("content_preview") or "")[:80]
            if d_preview:
                con.print(f"          [dim]{d_preview}[/dim]")

        if typer.confirm("  Confirm deletion?", default=True):
            confirmed_groups.append(group)
        else:
            con.print("  [dim]Skipped — both notes will survive purge.[/dim]")

    proposal["groups"] = confirmed_groups
    return proposal


# ── Main entrypoint ────────────────────────────────────────────────────────────


def run_review(
    proposal_file: str | None,
    dedup: bool,
    confidence: str | None,
) -> None:
    """Interactive review of a classify/triage proposal or a dedup proposal."""
    if dedup:
        path = Path(proposal_file) if proposal_file else None
        if path is None:
            try:
                path = find_latest_dedup_proposal()
            except FileNotFoundError as exc:
                con.print(f"[red]{exc}[/red]")
                raise SystemExit(1) from exc
    else:
        path = Path(proposal_file) if proposal_file else None
        if path is None:
            try:
                path = find_latest_proposal()
            except FileNotFoundError as exc:
                con.print(f"[red]{exc}[/red]")
                raise SystemExit(1) from exc

    if not path.exists():
        con.print(f"[red]Proposal not found:[/red] {path}")
        raise SystemExit(1)

    proposal = json.loads(path.read_text(encoding="utf-8"))

    bak = path.with_suffix(".json.pre-review.bak")
    shutil.copy2(path, bak)

    if dedup:
        updated = review_dedup_proposal(proposal, path)
        next_cmd = "uv run notes purge"
    else:
        updated = review_classify_proposal(proposal, path, confidence)
        next_cmd = "uv run notes move"

    path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
    con.print(f"\n[green]Proposal updated:[/green] {path.name}  [dim](backup: {bak.name})[/dim]")
    con.print(f"[dim]Ready — run `{next_cmd}` to apply.[/dim]")
