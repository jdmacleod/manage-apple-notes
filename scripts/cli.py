from typing import Optional

import typer

from scripts.classify.classify_notes import run_classify
from scripts.maintenance.audit import run_audit
from scripts.maintenance.process_inbox import run_inbox

app = typer.Typer(help="Manage Apple Notes using the Forever Notes framework.")


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


if __name__ == "__main__":
    app()
