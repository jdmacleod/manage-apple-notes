"""Classify Apple Notes from an export file using the configured LLM provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from scripts.config import (
    find_latest_export,
    get_category_meta,
    get_llm_config,
    load_settings,
    load_taxonomy,
    local_taxonomy_exists,
    reorganization_mode,
)
from scripts.folder_utils import (
    clamp_path,
    effective_max_depth,
    enumerate_paths,
    folder_name,
    nesting_mode,
    path_depth,
)
from scripts.json_output import emit_result
from scripts.json_utils import (
    extract_json_array,
    is_context_overflow,
    is_locale_error,
    strip_unsupported_chars,
)
from scripts.providers import LLMProvider, get_max_tokens, get_provider
from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"

# Approximate input token pricing per million tokens by model prefix
_PRICE_PER_M: dict[str, float] = {
    "claude-opus": 15.0,
    "claude-sonnet": 3.0,
    "claude-haiku": 0.25,
}


def load_prompt_template() -> str:
    """Return the system prompt portion, split at the 'Notes to classify:' marker."""
    path = PROMPTS_DIR / "classify-notes.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    text = path.read_text()
    marker = "\nNotes to classify:\n"
    if marker not in text:
        raise ValueError(f"Prompt template missing '{marker.strip()}' separator")
    system_part, _ = text.split(marker, 1)
    return system_part.strip()


def _subfolders(entry: dict | str) -> list[str]:
    """Extract the subfolders list from a taxonomy entry."""
    if isinstance(entry, dict):
        return entry.get("subfolders", []) or []
    return []


def _subfolder_str(subfolders: list[str]) -> str:
    return ", ".join(subfolders) if subfolders else "none"


_RELOCATION_GUIDANCE_STANDARD = ""
_RELOCATION_GUIDANCE_FULL = (
    "Classify each note based purely on its content. "
    "The current_folder field is provided for reference only — "
    "do not let it bias your classification."
)


def inject_taxonomy(
    system_prompt: str,
    taxonomy: dict,
    settings: dict | None = None,
) -> str:
    """Inject the user's taxonomy into the classify prompt template.

    Replaces {CATEGORY_LIST} with every category present in the user's taxonomy,
    in definition order. Descriptions come from the settings categories: block.
    Replaces {CATCHALL} with the first catchall-flagged category, falling back to
    the first transit category, then the first category in the taxonomy.
    Replaces {RELOCATION_GUIDANCE} with mode-appropriate conservative guidance.
    """
    fn = taxonomy.get("taxonomy", {})
    cat_meta = get_category_meta(settings or {})
    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)

    lines: list[str] = []
    for key, entry in fn.items():
        fld = folder_name(entry)
        if not fld:
            continue
        desc = (cat_meta.get(key) or {}).get("description", "")
        lines.append(f"{fld}{' — ' + desc if desc else ''}")

        if mode != "flat":
            for path in enumerate_paths(entry):
                d = path_depth(path)
                if d < 2 or d > max_depth:
                    continue
                indent = "  " * (d - 1)
                leaf = path.split("/")[-1]
                lines.append(f"{indent}{leaf}  [{path}]")

    # Catchall: first category with catchall:true → first transit → first folder
    catchall = (
        next(
            (
                folder_name(fn[k])
                for k, v in cat_meta.items()
                if v.get("catchall") and k in fn and folder_name(fn[k])
            ),
            None,
        )
        or next(
            (
                folder_name(fn[k])
                for k, v in cat_meta.items()
                if v.get("transit") and k in fn and folder_name(fn[k])
            ),
            None,
        )
        or next((folder_name(e) for e in fn.values() if folder_name(e)), "Inbox")
    )

    # Relocation guidance for conservative mode: name the actual transit folders
    reorg = reorganization_mode(settings)
    if reorg == "conservative":
        transit_names = [
            folder_name(fn[k])
            for k, v in cat_meta.items()
            if v.get("transit") and k in fn and folder_name(fn[k])
        ]
        if transit_names:
            names_str = " or ".join(f"'{n}'" for n in transit_names)
            relocation = (
                f"Notes not currently in {names_str} are already deliberately organized. "
                "For these notes, only propose moving them if you are HIGH confidence the current "
                "location is wrong — otherwise return their current folder path as the proposed_folder_path."
            )
        else:
            relocation = (
                "Notes already in organized folders should only be moved with HIGH confidence. "
                "Otherwise return the current folder path as the proposed_folder_path."
            )
    elif reorg == "full":
        relocation = _RELOCATION_GUIDANCE_FULL
    else:
        relocation = _RELOCATION_GUIDANCE_STANDARD

    return (
        system_prompt.replace("{CATEGORY_LIST}", "\n".join(lines))
        .replace("{CATCHALL}", catchall)
        .replace("{RELOCATION_GUIDANCE}", relocation)
    )


def _sanitize_notes_for_locale(notes_batch: list[dict]) -> list[dict]:
    """Strip unsupported characters from text fields so Apple Intelligence can process the batch."""
    return [
        {
            **note,
            "title": strip_unsupported_chars(note.get("title") or ""),
            "body": strip_unsupported_chars(note.get("body") or ""),
            "folder": strip_unsupported_chars(note.get("folder") or ""),
            "folder_path": strip_unsupported_chars(note.get("folder_path") or ""),
        }
        for note in notes_batch
    ]


def _build_classify_payload(
    notes_batch: list[dict],
    max_body: int,
    for_apple: bool,
) -> tuple[str, dict[str, str]]:
    """Build the user-content payload and an ID-remapping table for classify_batch.

    For Apple Intelligence, replaces x-coredata:// IDs with short placeholders
    ("note_0", "note_1", ...) so Apple's language detector does not misclassify
    the UUID-heavy URL strings as non-English, and prepends a plain-English
    preamble to anchor language detection.  The returned dict maps each placeholder
    back to the original ID.  For other providers the map is empty and IDs pass
    through unchanged.
    """
    index_to_id: dict[str, str] = {}
    payload = []
    for i, n in enumerate(notes_batch):
        real_id = str(n.get("id", ""))
        note_id = f"note_{i}" if for_apple else real_id
        if for_apple:
            index_to_id[note_id] = real_id
        payload.append(
            {
                "id": note_id,
                "title": n.get("title", ""),
                "body": n.get("body", "")[:max_body],
                "current_folder": n.get("folder_path") or n.get("folder", ""),
            }
        )
    if for_apple:
        payload_str = "Classify these notes:\n\n" + json.dumps(
            payload, indent=2, ensure_ascii=False
        )
    else:
        payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
    return payload_str, index_to_id


def classify_batch(
    provider: LLMProvider,
    notes_batch: list[dict],
    system_prompt: str,
    settings: dict,
) -> list[dict]:
    max_body = settings.get("export", {}).get("max_body_chars", 2000)
    payload_str, index_to_id = _build_classify_payload(
        notes_batch, max_body, for_apple=provider.name == "apple"
    )
    text = provider.classify_messages(
        system_prompt,
        payload_str,
        max_tokens=get_max_tokens(settings, provider),
    )
    results = extract_json_array(text)
    if index_to_id:
        for result in results:
            placeholder = result.get("id", "")
            if placeholder in index_to_id:
                result["id"] = index_to_id[placeholder]
    return results


def classify_batch_resilient(
    provider: LLMProvider,
    notes_batch: list[dict],
    system_prompt: str,
    settings: dict,
    con: Console | None = None,
) -> list[dict]:
    """Classify a batch; on context overflow or truncated output, split and retry."""
    _con = con or console
    if not notes_batch:
        return []
    # For Apple Intelligence, strip non-ASCII before the first call to avoid triggering
    # the locale filter on every batch (discover_themes uses the same pattern).
    if provider.name == "apple":
        notes_batch = _sanitize_notes_for_locale(notes_batch)
        system_prompt = strip_unsupported_chars(system_prompt)
    try:
        return classify_batch(provider, notes_batch, system_prompt, settings)
    except Exception as exc:
        if is_locale_error(exc):
            sanitized = _sanitize_notes_for_locale(notes_batch)
            has_content = any(
                (note.get("title") or "").strip() or (note.get("body") or "").strip()
                for note in sanitized
            )
            if has_content:
                _con.print(
                    f"[yellow]Locale error — retrying {len(notes_batch)}-note batch"
                    " with unsupported characters stripped[/yellow]"
                )
                try:
                    return classify_batch(provider, sanitized, system_prompt, settings)
                except Exception:
                    pass
            if len(notes_batch) == 1:
                _con.print(
                    f"[yellow]Warning:[/yellow] skipping note '{notes_batch[0].get('title', '')}'"
                    " — Apple Intelligence locale error (unsupported characters)"
                )
            else:
                _con.print(
                    f"[yellow]Warning:[/yellow] skipping batch of {len(notes_batch)}"
                    " — Apple Intelligence locale error; rerun with batch_size: 1 to skip only affected notes"
                )
            return []
        is_recoverable = is_context_overflow(exc) or isinstance(
            exc, (ValueError, json.JSONDecodeError)
        )
        if is_recoverable and len(notes_batch) > 1:
            mid = len(notes_batch) // 2
            _con.print(
                f"[yellow]Batch failed ({type(exc).__name__}) — splitting ({len(notes_batch)} → {mid}+{len(notes_batch) - mid})[/yellow]"
            )
            return classify_batch_resilient(
                provider, notes_batch[:mid], system_prompt, settings, con=_con
            ) + classify_batch_resilient(
                provider, notes_batch[mid:], system_prompt, settings, con=_con
            )
        if is_recoverable:
            _con.print(f"[yellow]Warning:[/yellow] skipping note — failed at batch size 1: {exc}")
        else:
            _con.print(
                f"[yellow]Warning:[/yellow] skipping batch of {len(notes_batch)}"
                f" ({type(exc).__name__}) — {exc}"
            )
        return []


def price_per_million(model: str) -> float | None:
    for prefix, price in _PRICE_PER_M.items():
        if model.startswith(prefix):
            return price
    return None  # local / unknown model — no per-token cost


def _build_folder_path(folder: str, subfolder: str | None) -> str:
    return f"{folder}/{subfolder}" if subfolder else folder


def run_classify(export_file: str | None, dry_run: bool, json_output: bool = False) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    taxonomy = load_taxonomy()
    if not local_taxonomy_exists():
        con.print(
            "[yellow]Warning:[/yellow] config/taxonomy.local.yaml not found — "
            "folder names are example placeholders.\n"
            "  Proposals will reference folders that do not exist in Apple Notes.\n"
            "  Run 'uv run notes setup' to configure your taxonomy, or copy a template:\n"
            "  taxonomy.zettelkasten.yaml / taxonomy.para.yaml / taxonomy.gtd.yaml"
        )
    system_prompt_template = load_prompt_template()
    system_prompt = inject_taxonomy(system_prompt_template, taxonomy, settings)

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        msg = f"Export file not found: {export_path}"
        if json_output:
            emit_result("classify", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())
    skip_empty = settings.get("export", {}).get("skip_empty", True)
    notes = (
        [n for n in all_notes if (n.get("body") or "").strip() or (n.get("title") or "").strip()]
        if skip_empty
        else all_notes
    )

    fn = taxonomy.get("taxonomy", {})
    cat_meta = get_category_meta(settings)

    # Build the set of folder paths to exclude from classification.
    # Driven by exclude_from_classify: true in the categories: block.
    # Backward compat: classify.exclude_archive: true maps to archive's built-in flag.
    if settings.get("classify", {}).get("exclude_archive") is False and "archive" in cat_meta:
        cat_meta["archive"] = {
            k: v for k, v in cat_meta["archive"].items() if k != "exclude_from_classify"
        }

    excluded_paths: set[str] = set()
    excluded_notes: list[dict] = []
    excluded_label_parts: list[str] = []
    for key, cfg in cat_meta.items():
        if not cfg.get("exclude_from_classify"):
            continue
        entry = fn.get(key)
        if not entry:
            continue
        top = folder_name(entry)
        if not top:
            continue
        paths = set(enumerate_paths(entry)) | {top}
        excluded_paths |= paths
        excluded_label_parts.append(top)

    if excluded_paths:

        def _is_excluded(n: dict) -> bool:
            fp = n.get("folder_path") or n.get("folder", "")
            return fp in excluded_paths

        excluded_notes = [n for n in notes if _is_excluded(n)]
        notes = [n for n in notes if not _is_excluded(n)]
        if excluded_notes:
            label = ", ".join(f"'{f}'" for f in excluded_label_parts)
            con.print(
                f"  [dim]Skipping {len(excluded_notes)} note(s) in excluded folder(s): {label}[/dim]"
            )

    llm_cfg = get_llm_config(settings)
    batch_size = llm_cfg.get("batch_size", 20)
    provider = get_provider(settings, dry_run=dry_run)
    model = provider.model
    batches = [notes[i : i + batch_size] for i in range(0, len(notes), batch_size)]

    if dry_run:
        est_tokens_per_note = 700
        est_system_tokens = 1500
        est_total_tokens = len(notes) * est_tokens_per_note + len(batches) * est_system_tokens
        est_tokens_per_batch = batch_size * est_tokens_per_note + est_system_tokens
        ppm = price_per_million(model)
        cost_str = (
            f"~${(est_total_tokens / 1_000_000) * ppm:.2f}  (@ ${ppm:.2f}/M input tokens)"
            if ppm is not None
            else "$0.00 (local inference)"
        )
        date_str = datetime.now().strftime("%Y-%m-%d")

        con.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        con.print(f"Export:       {export_path}")
        con.print(f"Notes found:  {len(all_notes)}  ({len(notes)} after filtering)")
        con.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        con.print(f"Provider:     {provider.name}")
        con.print(f"Model:        {model}")
        con.print(f"Mode:         {reorganization_mode(settings)}")
        con.print(f"Est. tokens:  ~{est_total_tokens:,}  (~{est_tokens_per_batch:,}/batch)")
        con.print(f"Est. cost:    {cost_str}")
        estimate = estimate_duration("classify", len(notes), logs_dir_path(settings))
        if estimate:
            con.print(f"Est. time:    {estimate}")
        con.print(f"\nOutput would be written to: {PROPOSALS_DIR}/proposal-{date_str}.json")
        log_file = RunLogger("classify", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(notes), "batches": len(batches)},
            dry_run=True,
            params={"export_file": str(export_path), "model": model, "batch_size": batch_size},
        )
        if json_output:
            emit_result(
                "classify",
                dry_run=True,
                output_file=PROPOSALS_DIR / f"proposal-{date_str}.json",
                log_file=log_file,
                summary={"notes_processed": len(notes), "batches": len(batches)},
            )
        return

    logger = RunLogger("classify", logs_dir_path(settings))
    con.print(f"[dim]Mode: {reorganization_mode(settings)}  ·  {provider.name} / {model}[/dim]")
    estimate = estimate_duration("classify", len(notes), logs_dir_path(settings))
    if estimate:
        con.print(f"[dim]Estimated duration: {estimate}[/dim]")

    # Catchall folder: notes the LLM can't confidently classify go here (needs_review bucket)
    catchall_folder = next(
        (
            folder_name(fn[k])
            for k, v in cat_meta.items()
            if v.get("catchall") and k in fn and folder_name(fn[k])
        ),
        None,
    ) or next(
        (
            folder_name(fn[k])
            for k, v in cat_meta.items()
            if v.get("transit") and k in fn and folder_name(fn[k])
        ),
        None,
    )

    # In conservative mode, notes outside transit folders are deliberately placed.
    # Any non-high-confidence move for such notes goes to needs_review instead of moves.
    reorg_mode = reorganization_mode(settings)
    transit_folders: set[str] = set()
    if reorg_mode == "conservative":
        transit_folders = {
            folder_name(fn[k])
            for k, v in cat_meta.items()
            if v.get("transit") and k in fn and folder_name(fn[k])
        }

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
        task = progress.add_task("Classifying...", total=len(batches))
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

                # Prefer proposed_folder_path (new prompt); fall back to old separate fields
                proposed_folder_path_raw = result.get("proposed_folder_path") or ""
                if not proposed_folder_path_raw:
                    pf = result.get("proposed_folder") or ""
                    ps = result.get("proposed_subfolder") or ""
                    proposed_folder_path_raw = f"{pf}/{ps}" if ps else pf
                proposed_folder_path = clamp_path(
                    proposed_folder_path_raw or "", effective_max_depth(settings)
                )
                parts = proposed_folder_path.split("/", 1)
                proposed_folder = parts[0]
                proposed_subfolder = parts[1] if len(parts) > 1 else None

                current_path = note.get("folder_path") or note.get("folder", "")
                if confidence == "low" or (catchall_folder and proposed_folder == catchall_folder):
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
                    # Conservative mode: non-high-confidence moves for notes already outside
                    # Inbox/Fleeting go to needs_review rather than moves.
                    note_in_transit = current_path.split("/")[0] in transit_folders
                    if transit_folders and not note_in_transit and confidence != "high":
                        needs_review.append(
                            {
                                "id": note_id,
                                "title": note.get("title", ""),
                                "current_folder": current_folder,
                                "reason": f"[conservative] {reason}",
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

    for n in excluded_notes:
        no_change.append(
            {
                "id": n["id"],
                "title": n.get("title", ""),
                "current_folder": n.get("folder", ""),
            }
        )

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = PROPOSALS_DIR / f"proposal-{date_str}.json"

    proposal = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
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
        params={"export_file": str(export_path), "model": model, "batch_size": batch_size},
    )
    if json_output:
        emit_result("classify", output_file=output_path, log_file=log_file, summary=summary)
