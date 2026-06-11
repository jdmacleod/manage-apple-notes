"""Python wrapper for apply-proposal.applescript with streaming colored output."""

from __future__ import annotations

import json as _json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

from scripts.config import find_latest_export, load_settings
from scripts.json_output import emit_result
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"


def find_latest_proposal() -> Path:
    files = sorted(PROPOSALS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No proposal files found in {PROPOSALS_DIR}")
    return files[-1]


def _check_proposal_freshness(
    path: Path, settings: dict, con: Console, force: bool, json_output: bool, dry_run: bool
) -> None:
    try:
        data = _json.loads(path.read_text())
    except Exception:
        return

    warnings: list[str] = []

    generated_at_str = data.get("generated_at")
    if generated_at_str:
        max_age_h = (settings.get("safety") or {}).get("proposal_max_age_hours", 48)
        if max_age_h:
            try:
                age = datetime.now(UTC) - datetime.fromisoformat(generated_at_str)
                if age > timedelta(hours=max_age_h):
                    days, rem = age.days, age.seconds
                    warnings.append(
                        f"Proposal is {days}d {rem // 3600}h old"
                        f" (generated {generated_at_str[:16]}Z)"
                    )
            except (TypeError, ValueError):
                pass

    source_export_str = data.get("source_export")
    if source_export_str:
        try:
            latest = find_latest_export()
            if latest.resolve() != Path(source_export_str).resolve():
                warnings.append(
                    f"Newer export exists: {latest.name}\n"
                    f"  Proposal was built from: {Path(source_export_str).name}\n"
                    f"  Re-run 'notes classify' or use --force to proceed anyway."
                )
        except FileNotFoundError:
            pass

    if not warnings:
        return
    for w in warnings:
        con.print(f"[yellow]Warning:[/yellow] {w}")
    if not force:
        msg = "Refusing to apply stale proposal. Use --force to override."
        if json_output:
            emit_result("move", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]{msg}[/red]")
        raise SystemExit(1)


def run_apply(
    proposal_file: str | None, dry_run: bool, json_output: bool = False, force: bool = False
) -> None:
    con = Console(stderr=True) if json_output else console

    if proposal_file:
        path = Path(proposal_file)
    else:
        try:
            path = find_latest_proposal()
        except FileNotFoundError as exc:
            if json_output:
                emit_result("move", status="error", dry_run=dry_run, error=str(exc))
            else:
                con.print(f"[red]{exc}[/red]")
            raise SystemExit(1) from exc

    if not path.exists():
        msg = f"Proposal not found: {path}"
        if json_output:
            emit_result("move", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Proposal not found:[/red] {path}")
        raise SystemExit(1)

    settings = load_settings()
    cfg = settings.get("toplevel_folder", {})
    logger = RunLogger("move", logs_dir_path(settings))

    _check_proposal_freshness(path, settings, con, force, json_output, dry_run)

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
            con.print(f"[green]{line}[/green]")
            logger.event("move", line=line, status="MOVED")
            moved += 1
        elif line.startswith("[SKIP]"):
            con.print(f"[yellow]{line}[/yellow]")
            logger.event("move", line=line, status="SKIP")
            skipped += 1
        elif line.startswith("[AMBIGUOUS]"):
            con.print(f"[yellow]{line}[/yellow]")
            logger.event("move", line=line, status="AMBIGUOUS")
            skipped += 1
        elif line.startswith("[DRY RUN]"):
            con.print(f"[cyan]{line}[/cyan]")
        elif line.startswith("[ERROR]"):
            con.print(f"[red]{line}[/red]")
            logger.event("move", line=line, status="ERROR")
            logger.error(line)
            errors += 1
        elif line:
            con.print(line)
    proc.wait()
    summary: dict[str, object] = {"moved": moved, "skipped": skipped, "errors": errors}
    log_file = logger.finish(summary=summary, dry_run=dry_run, params={"proposal_file": str(path)})
    if json_output:
        emit_result("move", dry_run=dry_run, log_file=log_file, summary=summary)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
