"""Python wrapper for apply-proposal.applescript with streaming colored output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import load_settings
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"


def find_latest_proposal() -> Path:
    files = sorted(PROPOSALS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No proposal files found in {PROPOSALS_DIR}")
    return files[-1]


def run_apply(proposal_file: str | None, dry_run: bool) -> None:
    if proposal_file:
        path = Path(proposal_file)
    else:
        try:
            path = find_latest_proposal()
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    if not path.exists():
        console.print(f"[red]Proposal not found:[/red] {path}")
        raise SystemExit(1)

    settings = load_settings()
    cfg = settings.get("toplevel_folder", {})
    logger = RunLogger("move", logs_dir_path(settings))

    script = REPO_ROOT / "scripts" / "execute" / "apply-proposal.applescript"
    cmd = ["osascript", str(script)]
    if dry_run:
        cmd.append("--dry-run")
    if cfg.get("enabled", False):
        cmd += ["--container", cfg.get("name", "Library")]
    cmd.append(str(path.resolve()))

    moved = skipped = errors = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip()
        if line.startswith("[MOVED]"):
            console.print(f"[green]{line}[/green]")
            logger.event("move", line=line, status="MOVED")
            moved += 1
        elif line.startswith("[SKIP]"):
            console.print(f"[yellow]{line}[/yellow]")
            logger.event("move", line=line, status="SKIP")
            skipped += 1
        elif line.startswith("[ERROR]"):
            console.print(f"[red]{line}[/red]")
            logger.event("move", line=line, status="ERROR")
            logger.error(line)
            errors += 1
        elif line:
            console.print(line)
    proc.wait()
    logger.finish(
        summary={"moved": moved, "skipped": skipped, "errors": errors},
        dry_run=dry_run,
        params={"proposal_file": str(path)},
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
