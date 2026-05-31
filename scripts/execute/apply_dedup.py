"""Python wrapper for apply-dedup-proposal.applescript with streaming colored output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from scripts.config import load_settings
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEDUP_PROPOSALS_DIR = REPO_ROOT / "data" / "dedup-proposals"


def find_latest_dedup_proposal() -> Path:
    files = sorted(DEDUP_PROPOSALS_DIR.glob("dedup-*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No dedup proposal files found in {DEDUP_PROPOSALS_DIR}")
    return files[-1]


def run_apply_dedup(proposal_file: str | None, execute: bool, json_output: bool = False) -> None:
    dry_run = not execute
    con = Console(stderr=True) if json_output else console

    if proposal_file:
        path = Path(proposal_file)
    else:
        try:
            path = find_latest_dedup_proposal()
        except FileNotFoundError as exc:
            if json_output:
                emit_result("purge", status="error", dry_run=dry_run, error=str(exc))
            else:
                con.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    if not path.exists():
        msg = f"Dedup proposal not found: {path}"
        if json_output:
            emit_result("purge", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Dedup proposal not found:[/red] {path}")
        raise SystemExit(1)

    settings = load_settings()
    logger = RunLogger("purge", logs_dir_path(settings))

    script = REPO_ROOT / "scripts" / "execute" / "apply-dedup-proposal.applescript"
    cmd = ["osascript", str(script)]
    if execute:
        cmd.append("--execute")
    cmd.append(str(path.resolve()))

    deleted = skipped = errors = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip()
        if line.startswith("[DELETED]"):
            con.print(f"[red]{line}[/red]")
            logger.event("delete", line=line, status="DELETED")
            deleted += 1
        elif line.startswith("[DRY RUN]"):
            con.print(f"[cyan]{line}[/cyan]")
            logger.event("delete", line=line, status="DRY_RUN")
        elif line.startswith("[SKIP]"):
            con.print(f"[yellow]{line}[/yellow]")
            logger.event("delete", line=line, status="SKIP")
            skipped += 1
        elif line.startswith("[ERROR]"):
            con.print(f"[red]{line}[/red]")
            logger.event("delete", line=line, status="ERROR")
            logger.error(line)
            errors += 1
        elif line:
            con.print(line)
    proc.wait()
    summary: dict[str, object] = {"deleted": deleted, "skipped": skipped, "errors": errors}
    log_file = logger.finish(summary=summary, dry_run=dry_run, params={"proposal_file": str(path)})
    if json_output:
        emit_result("purge", dry_run=dry_run, log_file=log_file, summary=summary)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
