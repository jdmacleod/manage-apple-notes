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

console = Console()


def run_inbox(dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt = inject_taxonomy(load_prompt_template(), taxonomy)

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
        cost_str = f"~${(est_total_tokens / 1_000_000) * ppm:.2f}  (@ ${ppm:.2f}/M input tokens)" if ppm is not None else "$0.00 (local inference)"
        date_str = datetime.now().strftime("%Y-%m-%d")

        console.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        console.print(f"Inbox folder: {inbox_folder!r}  (from taxonomy config)")
        console.print(f"Notes found:  {len(notes)}")
        console.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        console.print(f"Provider:     {provider.name}")
        console.print(f"Model:        {model}")
        console.print(f"Est. tokens:  ~{est_total_tokens:,}")
        console.print(f"Est. cost:    {cost_str}")
        console.print(f"\nOutput would be written to: {PROPOSALS_DIR}/inbox-{date_str}.json")
        return

    review_folder = _folder_name(taxonomy.get("forever_notes", {}).get("review", ""))

    moves: list[dict] = []
    needs_review: list[dict] = []
    no_change: list[dict] = []
    note_index = {n["id"]: n for n in notes}

    for batch in track(batches, description="Processing inbox..."):
        results = classify_batch(provider, batch, system_prompt, settings)

        for result in results:
            note_id = result.get("id", "")
            note = note_index.get(note_id, {})
            current_folder = note.get("folder", "")
            proposed_folder = result.get("proposed_folder", "")
            confidence = result.get("confidence", "low")
            reason = result.get("reason", "")

            if confidence == "low" or proposed_folder == review_folder:
                needs_review.append({
                    "id": note_id,
                    "title": note.get("title", ""),
                    "current_folder": current_folder,
                    "reason": reason,
                })
            elif proposed_folder == current_folder:
                no_change.append({
                    "id": note_id,
                    "title": note.get("title", ""),
                    "current_folder": current_folder,
                })
            else:
                moves.append({
                    "id": note_id,
                    "title": note.get("title", ""),
                    "current_folder": current_folder,
                    "proposed_folder": proposed_folder,
                    "confidence": confidence,
                    "reason": reason,
                })

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
