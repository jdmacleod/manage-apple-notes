"""Classify notes in the Inbox folder and write a move proposal."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from rich.console import Console
from rich.progress import track

from scripts.classify.classify_notes import (
    PROPOSALS_DIR,
    _folder_name,
    classify_batch,
    find_latest_export,
    inject_taxonomy,
    load_prompt_template,
    load_settings,
    load_taxonomy,
    price_per_million,
)
from scripts.providers import get_provider
from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path

console = Console()


def run_inbox(dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt = inject_taxonomy(load_prompt_template(), taxonomy, settings)

    inbox_folder = _folder_name(taxonomy.get("forever_notes", {}).get("inbox", ""))
    if not inbox_folder or inbox_folder.startswith("["):
        console.print(
            "[red]Inbox folder not configured.[/red] "
            "Set 'forever_notes.inbox' in config/taxonomy.local.yaml."
        )
        raise SystemExit(1)

    export_path = find_latest_export()
    all_notes = json.loads(export_path.read_text())
    notes = [n for n in all_notes if n.get("folder", "") == inbox_folder]

    if not notes:
        console.print(f"[yellow]No notes found in inbox folder[/yellow] {inbox_folder!r}")
        console.print(f"(Export: {export_path})")
        return

    llm_cfg = settings.get("llm") or settings.get("claude", {})
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

        console.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        console.print(f"Inbox folder: {inbox_folder!r}  (from taxonomy config)")
        console.print(f"Notes found:  {len(notes)}")
        console.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        console.print(f"Provider:     {provider.name}")
        console.print(f"Model:        {model}")
        console.print(f"Est. tokens:  ~{est_total_tokens:,}")
        console.print(f"Est. cost:    {cost_str}")
        estimate = estimate_duration("inbox", len(notes), logs_dir_path(settings))
        if estimate:
            console.print(f"Est. time:    {estimate}")
        console.print(f"\nOutput would be written to: {PROPOSALS_DIR}/inbox-{date_str}.json")
        RunLogger("inbox", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(notes), "batches": len(batches)},
            dry_run=True,
            params={"model": model, "batch_size": batch_size},
        )
        return

    logger = RunLogger("inbox", logs_dir_path(settings))
    estimate = estimate_duration("inbox", len(notes), logs_dir_path(settings))
    if estimate:
        console.print(f"[dim]Estimated duration: {estimate}[/dim]")

    review_folder = _folder_name(taxonomy.get("forever_notes", {}).get("review", ""))

    moves: list[dict] = []
    needs_review: list[dict] = []
    no_change: list[dict] = []
    note_index = {n["id"]: n for n in notes}
    batch_errors = 0

    for i, batch in enumerate(track(batches, description="Processing inbox...")):
        results = classify_batch(provider, batch, system_prompt, settings)
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

            if confidence == "low" or proposed_folder == review_folder:
                needs_review.append(
                    {
                        "id": note_id,
                        "title": note.get("title", ""),
                        "current_folder": current_folder,
                        "reason": reason,
                    }
                )
            elif proposed_folder_path == current_folder or proposed_folder == current_folder:
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

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
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

    console.print(f"\n[green]Done.[/green] Proposal written to [bold]{output_path}[/bold]")
    console.print(f"  Moves:        {len(moves)}")
    console.print(f"  Needs review: {len(needs_review)}")
    console.print(f"  No change:    {len(no_change)}")

    logger.finish(
        summary={
            "notes_processed": len(notes),
            "moves": len(moves),
            "needs_review": len(needs_review),
            "no_change": len(no_change),
            "batch_errors": batch_errors,
        },
        dry_run=False,
        params={"model": model, "batch_size": batch_size},
    )
