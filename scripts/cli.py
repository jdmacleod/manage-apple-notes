import typer
from dotenv import load_dotenv

load_dotenv()

from scripts.classify.classify_notes import run_classify
from scripts.classify.deduplicate_notes import run_dedup
from scripts.classify.discover_themes import run_discover
from scripts.classify.draft_taxonomy import run_draft
from scripts.execute.apply_dedup import run_apply_dedup
from scripts.execute.run_apply import run_apply
from scripts.export.run_export import run_backup, run_export
from scripts.forever_notes.sync_hubs import run_sync_hubs
from scripts.maintenance.audit import run_audit
from scripts.maintenance.process_inbox import run_inbox
from scripts.maintenance.repair_restored_notes import run_repair_restored
from scripts.restore.run_restore import run_restore

app = typer.Typer(
    help="Organize Apple Notes using AI classification into a user-defined folder taxonomy."
)


@app.command()
def discover(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated cost without calling the API.",
    ),
) -> None:
    """Discover thematic clusters in the library for subfolder planning (Pass 1)."""
    run_discover(export_file=export_file, dry_run=dry_run)


@app.command()
def draft(
    theme_map_file: str | None = typer.Argument(
        default=None,
        help="Path to theme-map JSON. Defaults to most recent in data/theme-maps/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview proposed additions without writing a file.",
    ),
) -> None:
    """Generate a draft taxonomy YAML from theme discovery results."""
    run_draft(theme_map_file=theme_map_file, dry_run=dry_run)


@app.command()
def classify(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated API cost without calling the API.",
    ),
) -> None:
    """Classify notes from an export and write a move proposal."""
    run_classify(export_file=export_file, dry_run=dry_run)


@app.command()
def inbox(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview batches and estimated API cost without calling the API.",
    ),
) -> None:
    """Classify Inbox notes and write a move proposal."""
    run_inbox(dry_run=dry_run)


@app.command()
def audit(
    output: str | None = typer.Option(
        None,
        "--output",
        help="Override the default report output path.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview checks and note counts without writing a report.",
    ),
) -> None:
    """Scan the library for quality issues and write a Markdown report."""
    run_audit(export_file=None, output_override=output, dry_run=dry_run)


@app.command()
def export() -> None:
    """Export all notes from Apple Notes to data/exports/."""
    run_export()


@app.command()
def backup() -> None:
    """Export notes and save a timestamped backup to data/backups/."""
    run_backup()


@app.command()
def restore(
    backup_file: str | None = typer.Option(
        None,
        "--from-backup",
        help="Backup or export JSON to restore from. Defaults to latest in data/backups/ then data/exports/.",
    ),
    missing_file: str | None = typer.Option(
        None,
        "--missing",
        help="missing-notes JSON listing notes to restore. Defaults to latest data/missing-notes-*.json.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be created without touching Notes.",
    ),
) -> None:
    """Restore notes from a backup — recreates notes lost during apply operations."""
    run_restore(backup_file=backup_file, missing_file=missing_file, dry_run=dry_run)


@app.command()
def apply(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Proposal JSON to apply. Defaults to most recent file in data/proposals/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview moves without touching Notes.",
    ),
) -> None:
    """Apply an approved move proposal to Apple Notes."""
    run_apply(proposal_file=proposal_file, dry_run=dry_run)


@app.command()
def dedup(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    proposal: str | None = typer.Option(
        None,
        "--proposal",
        help="Path to a classify proposal JSON to use as folder placement signal.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run algorithmic passes only; no LLM calls and no file written.",
    ),
) -> None:
    """Detect duplicate notes and write a dedup proposal (Pass 3)."""
    run_dedup(export_file=export_file, proposal_file=proposal, dry_run=dry_run)


@app.command()
def apply_dedup(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Dedup proposal JSON to apply. Defaults to most recent file in data/dedup-proposals/.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually delete notes. Without this flag the command is a dry-run.",
    ),
) -> None:
    """Apply an approved dedup proposal — delete confirmed duplicates."""
    run_apply_dedup(proposal_file=proposal_file, execute=execute)


@app.command()
def sync_hubs(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview hub content without writing to Apple Notes.",
    ),
) -> None:
    """Create or update ✱ Home and ✱ Hub notes (strict mode only)."""
    run_sync_hubs(export_file=export_file, dry_run=dry_run)


@app.command()
def repair_restored(
    missing_file: str | None = typer.Option(
        None,
        "--missing-file",
        help="missing-notes JSON listing notes to repair. Defaults to latest data/missing-notes-*.json.",
    ),
    old_export: str | None = typer.Option(
        None,
        "--old-export",
        help="Export JSON containing the original note content. Defaults to the second most recent export.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be rewritten without touching Notes.",
    ),
) -> None:
    """Repair notes corrupted after an iCloud Recently Deleted restore (duplicate title, missing newlines)."""
    run_repair_restored(missing_file=missing_file, old_export_file=old_export, dry_run=dry_run)


if __name__ == "__main__":
    app()
