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
from scripts.forever_notes.arrange_folders import run_arrange
from scripts.forever_notes.sync_hubs import run_sync_hubs
from scripts.maintenance.audit import run_audit
from scripts.maintenance.process_inbox import run_inbox
from scripts.restore.run_restore import run_restore
from scripts.review.run_review import run_review
from scripts.setup.run_setup import run_setup

app = typer.Typer(
    help="Organize Apple Notes using AI classification into a user-defined folder taxonomy."
)


_JSON_HELP = "Output result as JSON to stdout (progress goes to stderr)."


@app.command()
def review(
    proposal_file: str | None = typer.Argument(
        default=None,
        help="Proposal JSON to review. Defaults to most recent in data/proposals/ (or data/dedup-proposals/ with --dedup).",
    ),
    dedup: bool = typer.Option(
        False,
        "--dedup",
        help="Review a dedup proposal instead of a classify/triage proposal.",
    ),
    confidence: str | None = typer.Option(
        None,
        "--confidence",
        help="Drop moves below this confidence level before reviewing. One of: high, medium.",
    ),
) -> None:
    """Interactively review a proposal: place needs-review items, optionally filter low-confidence moves."""
    if confidence is not None and confidence not in ("high", "medium"):
        raise typer.BadParameter(
            "--confidence must be 'high' or 'medium'", param_hint="--confidence"
        )
    run_review(proposal_file=proposal_file, dedup=dedup, confidence=confidence)


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
    debug: bool = typer.Option(
        False, "--debug", help="Print per-batch diagnostics: non-ASCII char counts, retry errors."
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Process only the first N notes. Useful for quick smoke-tests."
    ),
) -> None:
    """Discover thematic clusters in the library for subfolder planning."""
    run_discover(
        export_file=export_file, dry_run=dry_run, json_output=json_output, debug=debug, limit=limit
    )


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
def arrange(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview without writing."
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Clear saved Home page order; restore automatic ordering."
    ),
) -> None:
    """Interactively set the Home page category order (strict mode only)."""
    run_arrange(dry_run=dry_run, reset=reset)


if __name__ == "__main__":
    app()
