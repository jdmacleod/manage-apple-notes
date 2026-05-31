"""Reverse a previous move — sends notes back to their original folders."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console

from scripts.config import load_settings
from scripts.execute.run_apply import find_latest_proposal
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_reverse_moves(proposal: dict) -> list[dict]:
    """Swap current_folder ↔ proposed_folder_path for each move entry.

    Entries without both fields are skipped — they cannot be reversed.
    """
    reversed_moves = []
    for m in proposal.get("moves", []):
        origin = m.get("current_folder", "")
        destination = m.get("proposed_folder_path", "")
        if not destination:
            pf = m.get("proposed_folder", "")
            ps = m.get("proposed_subfolder") or ""
            destination = f"{pf}/{ps}" if ps else pf
        if origin and destination:
            reversed_moves.append(
                {
                    "id": m.get("id", ""),
                    "title": m.get("title", ""),
                    "current_folder": destination,
                    "proposed_folder_path": origin,
                }
            )
    return reversed_moves


def run_revert(proposal_file: str | None, dry_run: bool, json_output: bool = False) -> None:
    con = Console(stderr=True) if json_output else console

    if proposal_file:
        path = Path(proposal_file)
    else:
        try:
            path = find_latest_proposal()
        except FileNotFoundError as exc:
            if json_output:
                emit_result("revert", status="error", dry_run=dry_run, error=str(exc))
            else:
                con.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    if not path.exists():
        msg = f"Proposal not found: {path}"
        if json_output:
            emit_result("revert", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Proposal not found:[/red] {path}")
        raise SystemExit(1)

    proposal: dict = json.loads(path.read_text())
    reverse_moves = _build_reverse_moves(proposal)

    if not reverse_moves:
        con.print("[yellow]No moves found in proposal — nothing to revert.[/yellow]")
        if json_output:
            emit_result("revert", dry_run=dry_run, summary={"moved": 0, "skipped": 0, "errors": 0})
        return

    con.print(f"Reverting [bold]{len(reverse_moves)}[/bold] move(s) from [dim]{path.name}[/dim]")

    settings = load_settings()
    cfg = settings.get("toplevel_folder", {})
    logger = RunLogger("revert", logs_dir_path(settings))

    reverse_proposal = {"moves": reverse_moves}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(reverse_proposal, tmp, ensure_ascii=False)
        tmp_path = tmp.name

    script = REPO_ROOT / "scripts" / "execute" / "apply-proposal.applescript"
    cmd = ["osascript", str(script)]
    if dry_run:
        cmd.append("--dry-run")
    if cfg.get("enabled", False):
        cmd += ["--container", cfg.get("name", "Library")]
    cmd.append(tmp_path)

    moved = skipped = errors = 0
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            line = line.rstrip()
            if line.startswith("[MOVED]"):
                con.print(f"[green]{line}[/green]")
                logger.event("revert", line=line, status="MOVED")
                moved += 1
            elif line.startswith("[SKIP]"):
                con.print(f"[yellow]{line}[/yellow]")
                logger.event("revert", line=line, status="SKIP")
                skipped += 1
            elif line.startswith("[AMBIGUOUS]"):
                con.print(f"[yellow]{line}[/yellow]")
                logger.event("revert", line=line, status="AMBIGUOUS")
                skipped += 1
            elif line.startswith("[DRY RUN]"):
                con.print(f"[cyan]{line}[/cyan]")
            elif line.startswith("[ERROR]"):
                con.print(f"[red]{line}[/red]")
                logger.event("revert", line=line, status="ERROR")
                logger.error(line)
                errors += 1
            elif line:
                con.print(line)
        proc.wait()
        summary: dict[str, object] = {"moved": moved, "skipped": skipped, "errors": errors}
        log_file = logger.finish(
            summary=summary, dry_run=dry_run, params={"proposal_file": str(path)}
        )
        if json_output:
            emit_result("revert", dry_run=dry_run, log_file=log_file, summary=summary)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
