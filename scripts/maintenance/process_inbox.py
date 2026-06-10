"""Classify notes in the Inbox folder and write a move proposal."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from scripts.classify.classify_notes import (
    PROPOSALS_DIR,
    classify_batch_resilient,
    inject_taxonomy,
    load_prompt_template,
    price_per_million,
)
from scripts.config import (
    export_age_hours,
    find_latest_export,
    get_llm_config,
    load_settings,
    load_taxonomy,
)
from scripts.folder_utils import folder_name
from scripts.json_output import emit_result
from scripts.providers import get_provider
from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path

console = Console()


def run_inbox(dry_run: bool, json_output: bool = False) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt = inject_taxonomy(load_prompt_template(), taxonomy, settings)

    inbox_folder = folder_name(taxonomy.get("taxonomy", {}).get("inbox", ""))
    if not inbox_folder or inbox_folder.startswith("["):
        msg = "Inbox folder not configured. Set 'taxonomy.inbox' in config/taxonomy.local.yaml."
        if json_output:
            emit_result("triage", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(
                "[red]Inbox folder not configured.[/red] "
                "Set 'taxonomy.inbox' in config/taxonomy.local.yaml."
            )
        raise SystemExit(1)

    export_path = find_latest_export()

    max_age = (settings.get("safety") or {}).get("export_max_age_hours", 24)
    if max_age:
        age_h = export_age_hours(export_path)
        if age_h > max_age:
            con.print(
                f"[yellow]Warning:[/yellow] Export is {age_h:.0f}h old"
                " — consider re-running 'notes export' first."
            )

    all_notes = json.loads(export_path.read_text())
    notes = [n for n in all_notes if n.get("folder", "") == inbox_folder]

    if not notes:
        con.print(f"[yellow]No notes found in inbox folder[/yellow] {inbox_folder!r}")
        con.print(f"(Export: {export_path})")
        if json_output:
            emit_result("triage", dry_run=dry_run, summary={"notes_processed": 0, "moves": 0})
        return

    llm_cfg = get_llm_config(settings)
    batch_size = llm_cfg.get("batch_size", 20)
    provider = get_provider(settings, dry_run=dry_run)
    model = provider.model
    batches = [notes[i : i + batch_size] for i in range(0, len(notes), batch_size)]

    if dry_run:
        est_tokens_per_note = 700
        est_system_tokens = 1500
        est_total_tokens = len(notes) * est_tokens_per_note + len(batches) * est_system_tokens
        ppm = price_per_million(model)
        cost_str = (
            f"~${(est_total_tokens / 1_000_000) * ppm:.2f}  (@ ${ppm:.2f}/M input tokens)"
            if ppm is not None
            else "$0.00 (local inference)"
        )
        date_str = datetime.now().strftime("%Y-%m-%d")

        con.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        con.print(f"Inbox folder: {inbox_folder!r}  (from taxonomy config)")
        con.print(f"Notes found:  {len(notes)}")
        con.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        con.print(f"Provider:     {provider.name}")
        con.print(f"Model:        {model}")
        con.print(f"Est. tokens:  ~{est_total_tokens:,}")
        con.print(f"Est. cost:    {cost_str}")
        estimate = estimate_duration("triage", len(notes), logs_dir_path(settings))
        if estimate:
            con.print(f"Est. time:    {estimate}")
        con.print(f"\nOutput would be written to: {PROPOSALS_DIR}/inbox-{date_str}.json")
        log_file = RunLogger("triage", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(notes), "batches": len(batches)},
            dry_run=True,
            params={"model": model, "batch_size": batch_size},
        )
        if json_output:
            emit_result(
                "triage",
                dry_run=True,
                output_file=PROPOSALS_DIR / f"inbox-{date_str}.json",
                log_file=log_file,
                summary={"notes_processed": len(notes), "batches": len(batches)},
            )
        return

    logger = RunLogger("triage", logs_dir_path(settings))
    con.print(f"[dim]{provider.name} / {model}[/dim]")
    estimate = estimate_duration("triage", len(notes), logs_dir_path(settings))
    if estimate:
        con.print(f"[dim]Estimated duration: {estimate}[/dim]")

    review_folder = folder_name(taxonomy.get("taxonomy", {}).get("review", ""))

    moves: list[dict] = []
    needs_review: list[dict] = []
    no_change: list[dict] = []
    note_index = {n["id"]: n for n in notes}
    batch_errors = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(elapsed_when_finished=True),
        console=con,
        speed_estimate_period=3600.0,
    ) as progress:
        task = progress.add_task("Processing inbox...", total=len(batches))
        for i, batch in enumerate(batches):
            results = classify_batch_resilient(provider, batch, system_prompt, settings, con=con)
            if not results:
                logger.event("batch", batch=i + 1, count=len(batch), status="error")
                batch_errors += 1
            else:
                logger.event("batch", batch=i + 1, count=len(batch), status="ok")

            for result in results:
                note_id = result.get("id", "")
                note = note_index.get(note_id, {})
                current_folder = note.get("folder", "")
                confidence = result.get("confidence", "low")
                reason = result.get("reason", "")

                proposed_folder_path_raw = result.get("proposed_folder_path") or ""
                if not proposed_folder_path_raw:
                    pf = result.get("proposed_folder", "")
                    ps = result.get("proposed_subfolder") or ""
                    proposed_folder_path_raw = f"{pf}/{ps}" if ps else pf
                proposed_folder_path = proposed_folder_path_raw
                parts = proposed_folder_path.split("/", 1)
                proposed_folder = parts[0]
                proposed_subfolder = parts[1] if len(parts) > 1 else None

                current_path = note.get("folder_path") or note.get("folder", "")
                if confidence == "low" or proposed_folder == review_folder:
                    needs_review.append(
                        {
                            "id": note_id,
                            "title": note.get("title", ""),
                            "current_folder": current_folder,
                            "reason": reason,
                        }
                    )
                elif proposed_folder_path == current_path:
                    no_change.append(
                        {
                            "id": note_id,
                            "title": note.get("title", ""),
                            "current_folder": current_folder,
                        }
                    )
                else:
                    moves.append(
                        {
                            "id": note_id,
                            "title": note.get("title", ""),
                            "current_folder": current_folder,
                            "proposed_folder": proposed_folder,
                            "proposed_subfolder": proposed_subfolder,
                            "proposed_folder_path": proposed_folder_path,
                            "confidence": confidence,
                            "reason": reason,
                        }
                    )

            progress.advance(task)

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = PROPOSALS_DIR / f"inbox-{date_str}.json"

    proposal = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
        "inbox_folder": inbox_folder,
        "moves": moves,
        "needs_review": needs_review,
        "no_change": no_change,
    }
    output_path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False))

    con.print(f"\n[green]Done.[/green] Proposal written to [bold]{output_path}[/bold]")
    con.print(f"  Moves:        {len(moves)}")
    con.print(f"  Needs review: {len(needs_review)}")
    con.print(f"  No change:    {len(no_change)}")

    summary: dict[str, object] = {
        "notes_processed": len(notes),
        "moves": len(moves),
        "needs_review": len(needs_review),
        "no_change": len(no_change),
        "batch_errors": batch_errors,
    }
    log_file = logger.finish(
        summary=summary,
        dry_run=False,
        params={"model": model, "batch_size": batch_size},
    )
    if json_output:
        emit_result("triage", output_file=output_path, log_file=log_file, summary=summary)
