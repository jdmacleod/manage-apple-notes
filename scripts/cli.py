from typing import Optional

import typer
from dotenv import load_dotenv

load_dotenv()

from scripts.classify.classify_notes import run_classify
from scripts.classify.deduplicate_notes import run_dedup
from scripts.classify.discover_themes import run_discover
from scripts.execute.apply_dedup import run_apply_dedup
from scripts.execute.run_apply import run_apply
from scripts.export.run_export import run_export
from scripts.maintenance.audit import run_audit
from scripts.maintenance.process_inbox import run_inbox

app = typer.Typer(help="Manage Apple Notes using the Forever Notes framework.")


@app.command()
def discover(
    export_file: Optional[str] = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated cost without calling the API.",
    ),
):
    """Discover thematic clusters in the library for subfolder planning (Pass 1)."""
    run_discover(export_file=export_file, dry_run=dry_run)


@app.command()
def classify(
    export_file: Optional[str] = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated API cost without calling the API.",
    ),
):
    """Classify notes from an export and write a move proposal."""
    run_classify(export_file=export_file, dry_run=dry_run)


@app.command()
def inbox(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated API cost without calling the API.",
    ),
):
    """Classify Inbox notes and write a move proposal."""
    run_inbox(dry_run=dry_run)


@app.command()
def audit(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Override the default report output path.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview checks and note counts without writing a report.",
    ),
):
    """Scan the library for stale, duplicate, and orphaned notes."""
    run_audit(export_file=None, output_override=output, dry_run=dry_run)


@app.command()
def export():
    """Export all notes from Apple Notes to data/exports/."""
    run_export()


@app.command()
def apply(
    proposal_file: Optional[str] = typer.Argument(
        default=None,
        help="Proposal JSON to apply. Defaults to most recent file in data/proposals/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview moves without touching Notes.",
    ),
):
    """Apply an approved move proposal to Apple Notes."""
    run_apply(proposal_file=proposal_file, dry_run=dry_run)


@app.command()
def dedup(
    export_file: Optional[str] = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    proposal: Optional[str] = typer.Option(
        None,
        "--proposal",
        help="Path to a classify proposal JSON to use as folder placement signal.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run algorithmic passes only; no LLM calls and no file written.",
    ),
):
    """Detect duplicate notes and write a dedup proposal (Pass 3)."""
    run_dedup(export_file=export_file, proposal_file=proposal, dry_run=dry_run)


@app.command()
def apply_dedup(
    proposal_file: Optional[str] = typer.Argument(
        default=None,
        help="Dedup proposal JSON to apply. Defaults to most recent file in data/dedup-proposals/.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually delete notes. Without this flag the command is a dry-run.",
    ),
):
    """Apply an approved dedup proposal — delete confirmed duplicates."""
    run_apply_dedup(proposal_file=proposal_file, execute=execute)


if __name__ == "__main__":
    app()
