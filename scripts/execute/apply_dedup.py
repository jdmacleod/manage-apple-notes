"""Python wrapper for apply-dedup-proposal.applescript with streaming colored output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from scripts.config import load_settings
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEDUP_PROPOSALS_DIR = REPO_ROOT / "data" / "dedup-proposals"


def find_latest_dedup_proposal() -> Path:
    files = sorted(DEDUP_PROPOSALS_DIR.glob("dedup-*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No dedup proposal files found in {DEDUP_PROPOSALS_DIR}")
    return files[-1]


def run_apply_dedup(proposal_file: str | None, execute: bool) -> None:
    if proposal_file:
        path = Path(proposal_file)
    else:
        try:
            path = find_latest_dedup_proposal()
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    if not path.exists():
        console.print(f"[red]Dedup proposal not found:[/red] {path}")
        raise SystemExit(1)

    settings = load_settings()
    logger = RunLogger("purge", logs_dir_path(settings))

    script = REPO_ROOT / "scripts" / "execute" / "apply-dedup-proposal.applescript"
    cmd = ["osascript", str(script)]
    if execute:
        cmd.append("--execute")
    cmd.append(str(path.resolve()))

    deleted = skipped = errors = 0
    dry_run = not execute
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip()
        if line.startswith("[DELETED]"):
            console.print(f"[red]{line}[/red]")
            logger.event("delete", line=line, status="DELETED")
            deleted += 1
        elif line.startswith("[DRY RUN]"):
            console.print(f"[cyan]{line}[/cyan]")
            logger.event("delete", line=line, status="DRY_RUN")
        elif line.startswith("[SKIP]"):
            console.print(f"[yellow]{line}[/yellow]")
            logger.event("delete", line=line, status="SKIP")
            skipped += 1
        elif line.startswith("[ERROR]"):
            console.print(f"[red]{line}[/red]")
            logger.event("delete", line=line, status="ERROR")
            logger.error(line)
            errors += 1
        elif line:
            console.print(line)
    proc.wait()
    logger.finish(
        summary={"deleted": deleted, "skipped": skipped, "errors": errors},
        dry_run=dry_run,
        params={"proposal_file": str(path)},
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
