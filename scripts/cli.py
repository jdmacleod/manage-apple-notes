import typer
from dotenv import load_dotenv

load_dotenv()

from scripts.classify.classify_notes import run_classify
from scripts.classify.deduplicate_notes import run_dedup
from scripts.classify.discover_themes import run_discover
from scripts.classify.draft_taxonomy import run_draft
from scripts.execute.apply_dedup import run_apply_dedup
from scripts.execute.run_apply import run_apply
from scripts.execute.run_revert import run_revert
from scripts.export.run_export import run_backup, run_export
from scripts.forever_notes.sync_hubs import run_sync_hubs
from scripts.maintenance.audit import run_audit
from scripts.maintenance.process_inbox import run_inbox
from scripts.maintenance.repair_restored_notes import run_repair_restored
from scripts.restore.run_restore import run_restore
from scripts.setup.run_setup import run_setup

app = typer.Typer(
    help="Organize Apple Notes using AI classification into a user-defined folder taxonomy."
)


_JSON_HELP = "Output result as JSON to stdout (progress goes to stderr)."


@app.command()
def setup(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be written without touching files."
    ),
    no_corpus: bool = typer.Option(
        False,
        "--no-corpus",
        help="Skip corpus analysis even if an export file is available.",
    ),
) -> None:
    """Interactive wizard: pick a framework, name your folders, write config files."""
    run_setup(dry_run=dry_run, no_corpus=no_corpus)


@app.command()
def discover(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview batches and estimated cost without calling the API."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Discover thematic clusters in the library for subfolder planning."""
    run_discover(export_file=export_file, dry_run=dry_run, json_output=json_output)


@app.command()
def draft(
    theme_map_file: str | None = typer.Argument(
        default=None,
        help="Path to theme-map JSON. Defaults to most recent in data/theme-maps/.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview proposed additions without writing a file."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Generate a draft taxonomy YAML from theme discovery results."""
    run_draft(theme_map_file=theme_map_file, dry_run=dry_run, json_output=json_output)


@app.command()
def classify(
    export_file: str | None = typer.Argument(
        default=None,
        help="Path to export JSON. Defaults to most recent file in data/exports/.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview batches and estimated API cost without calling the API."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Classify notes from an export and write a move proposal."""
    run_classify(export_file=export_file, dry_run=dry_run, json_output=json_output)


@app.command()
def triage(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview batches and estimated API cost without calling the API."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Classify Inbox notes and write a move proposal."""
    run_inbox(dry_run=dry_run, json_output=json_output)


@app.command()
def audit(
    output: str | None = typer.Option(
        None, "--output", help="Override the default report output path."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview checks and note counts without writing a report."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Scan the library for quality issues and write a Markdown report."""
    run_audit(export_file=None, output_override=output, dry_run=dry_run, json_output=json_output)


@app.command()
def export(
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Export all notes from Apple Notes to data/exports/."""
    run_export(json_output=json_output)


@app.command()
def backup(
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Export notes and save a timestamped backup to data/backups/."""
    run_backup(json_output=json_output)


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
        False, "--dry-run", help="Preview what would be created without touching Notes."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Restore notes from a backup — recreates notes lost during move operations."""
    run_restore(
        backup_file=backup_file, missing_file=missing_file, dry_run=dry_run, json_output=json_output
    )


@app.command()
def move(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Proposal JSON to apply. Defaults to most recent file in data/proposals/.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview moves without touching Notes."),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Move notes in Apple Notes according to an approved proposal."""
    run_apply(proposal_file=proposal_file, dry_run=dry_run, json_output=json_output)


@app.command()
def revert(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Proposal JSON to reverse. Defaults to most recent file in data/proposals/.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview moves without touching Notes."),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Reverse a previous move — returns notes to their original folders."""
    run_revert(proposal_file=proposal_file, dry_run=dry_run, json_output=json_output)


@app.command()
def dedup(
    export_file: str | None = typer.Argument(
        default=None, help="Path to export JSON. Defaults to most recent file in data/exports/."
    ),
    proposal: str | None = typer.Option(
        None,
        "--proposal",
        help="Path to a classify proposal JSON to use as folder placement signal.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Run algorithmic passes only; no LLM calls and no file written."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Detect duplicate notes and write a dedup proposal."""
    run_dedup(
        export_file=export_file, proposal_file=proposal, dry_run=dry_run, json_output=json_output
    )


@app.command()
def purge(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Dedup proposal JSON to apply. Defaults to most recent file in data/dedup-proposals/.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually delete notes. Without this flag the command is a dry-run.",
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Purge confirmed duplicates from an approved dedup proposal."""
    run_apply_dedup(proposal_file=proposal_file, execute=execute, json_output=json_output)


@app.command()
def sync_hubs(
    export_file: str | None = typer.Argument(
        default=None, help="Path to export JSON. Defaults to most recent file in data/exports/."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview hub content without writing to Apple Notes."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Create or update ✱ Home and ✱ Hub notes (strict mode only)."""
    run_sync_hubs(export_file=export_file, dry_run=dry_run, json_output=json_output)


@app.command()
def repair(
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
        False, "--dry-run", help="Preview what would be rewritten without touching Notes."
    ),
    json_output: bool = typer.Option(False, "--json", help=_JSON_HELP),
) -> None:
    """Repair notes corrupted after an iCloud Recently Deleted restore (duplicate title, missing newlines)."""
    run_repair_restored(
        missing_file=missing_file,
        old_export_file=old_export,
        dry_run=dry_run,
        json_output=json_output,
    )


if __name__ == "__main__":
    app()
