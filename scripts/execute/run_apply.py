"""Python wrapper for apply-proposal.applescript with streaming colored output."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from scripts.classify.classify_notes import load_settings

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
            raise SystemExit(1)

    if not path.exists():
        console.print(f"[red]Proposal not found:[/red] {path}")
        raise SystemExit(1)

    settings = load_settings()
    cfg = settings.get("toplevel_folder", {})

    script = REPO_ROOT / "scripts" / "execute" / "apply-proposal.applescript"
    cmd = ["osascript", str(script)]
    if dry_run:
        cmd.append("--dry-run")
    if cfg.get("enabled", False):
        cmd += ["--container", cfg.get("name", "All Notes")]
    cmd.append(str(path.resolve()))

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip()
        if line.startswith("[MOVED]"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("[SKIP]"):
            console.print(f"[yellow]{line}[/yellow]")
        elif line.startswith("[ERROR]"):
            console.print(f"[red]{line}[/red]")
        elif line:
            console.print(line)
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
