"""Classify Apple Notes from an export file using the configured LLM provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from scripts.folder_utils import (
    clamp_path,
    effective_max_depth,
    enumerate_paths,
    nesting_mode,
    path_depth,
)
from scripts.providers import LLMProvider, get_provider
from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = REPO_ROOT / "prompts"
EXPORTS_DIR = REPO_ROOT / "data" / "exports"
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"

# Approximate input token pricing per million tokens by model prefix
_PRICE_PER_M: dict[str, float] = {
    "claude-opus": 15.0,
    "claude-sonnet": 3.0,
    "claude-haiku": 0.25,
}


def _load_yaml(local_path: Path, example_path: Path) -> dict:
    for path in (local_path, example_path):
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


def load_settings() -> dict:
    return _load_yaml(
        CONFIG_DIR / "settings.local.yaml",
        CONFIG_DIR / "settings.example.yaml",
    )


def load_taxonomy() -> dict:
    return _load_yaml(
        CONFIG_DIR / "taxonomy.local.yaml",
        CONFIG_DIR / "taxonomy.example.yaml",
    )


def find_latest_export() -> Path:
    files = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No export files found in {EXPORTS_DIR}. Run export-notes.applescript first."
        )
    return files[0]


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


def _folder_name(entry: dict | str) -> str:
    """Extract the folder name from a taxonomy entry (nested dict or legacy string)."""
    if isinstance(entry, dict):
        return entry.get("folder", "")
    return entry or ""


def _subfolders(entry: dict | str) -> list[str]:
    """Extract the subfolders list from a taxonomy entry."""
    if isinstance(entry, dict):
        return entry.get("subfolders", []) or []
    return []


def _subfolder_str(subfolders: list[str]) -> str:
    return ", ".join(subfolders) if subfolders else "none"


# Canonical ordering and descriptions for all supported taxonomy categories.
# Only categories present in the user's taxonomy are included in the prompt.
_CATEGORY_META = [
    ("inbox", "temporary capture, no subfolders"),
    ("fleeting", "quick thoughts, no subfolders"),
    ("literature", "notes tied to a specific source (book, article, talk)"),
    ("permanent", "atomic, evergreen concepts in your own words"),
    ("projects", "notes tied to a specific active project"),
    ("areas", "ongoing responsibilities and reference for areas of life/work"),
    ("resources", "reference material, how-tos, collections"),
    ("archive", "inactive, completed, or outdated notes"),
    ("review", "use when classification is genuinely unclear, no subfolders"),
]


def inject_taxonomy(
    system_prompt: str,
    taxonomy: dict,
    settings: dict | None = None,
) -> str:
    """Inject the user's taxonomy into the classify prompt template.

    Replaces {CATEGORY_LIST} with only the categories present in the taxonomy.
    In flat mode only top-level folder names are listed; in natural/deep modes
    all available sub-paths are shown indented by depth, up to max_folder_depth.
    Replaces {CATCHALL} with the review folder name, or inbox as a fallback.
    """
    fn = taxonomy.get("forever_notes", {})
    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)

    lines: list[str] = []
    for key, description in _CATEGORY_META:
        entry = fn.get(key)
        if not entry:
            continue
        folder = _folder_name(entry)
        if not folder:
            continue
        lines.append(f"{folder} — {description}")

        if mode != "flat":
            for path in enumerate_paths(entry):
                d = path_depth(path)
                if d < 2 or d > max_depth:
                    continue
                indent = "  " * (d - 1)
                leaf = path.split("/")[-1]
                lines.append(f"{indent}{leaf}  [{path}]")

    catchall = _folder_name(fn.get("review")) or _folder_name(fn.get("inbox")) or "Inbox"

    return system_prompt.replace("{CATEGORY_LIST}", "\n".join(lines)).replace(
        "{CATCHALL}", catchall
    )


def _extract_json_array(text: str) -> list:
    """Extract a JSON array from an LLM response that may include prose or fences."""
    if "```" in text:
        start = text.find("[", text.find("```"))
    else:
        start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in response:\n{text[:300]}")
    return json.loads(text[start:end])


def _is_context_overflow(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "exceed_context",
            "context_length",
            "context size",
            "context window",
            "maximum context",
        )
    )


def classify_batch(
    provider: LLMProvider,
    notes_batch: list[dict],
    system_prompt: str,
    settings: dict,
) -> list[dict]:
    max_body = settings.get("export", {}).get("max_body_chars", 2000)

    batch_payload = [
        {
            "id": n["id"],
            "title": n.get("title", ""),
            "body": n.get("body", "")[:max_body],
            "current_folder": n.get("folder_path") or n.get("folder", ""),
        }
        for n in notes_batch
    ]

    text = provider.classify_messages(
        system_prompt,
        json.dumps(batch_payload, indent=2, ensure_ascii=False),
    )
    return _extract_json_array(text)


def classify_batch_resilient(
    provider: LLMProvider,
    notes_batch: list[dict],
    system_prompt: str,
    settings: dict,
) -> list[dict]:
    """Classify a batch; on context overflow or truncated output, split and retry."""
    if not notes_batch:
        return []
    try:
        return classify_batch(provider, notes_batch, system_prompt, settings)
    except Exception as exc:
        is_recoverable = _is_context_overflow(exc) or isinstance(
            exc, (ValueError, json.JSONDecodeError)
        )
        if is_recoverable and len(notes_batch) > 1:
            mid = len(notes_batch) // 2
            console.print(
                f"[yellow]Batch failed ({type(exc).__name__}) — splitting ({len(notes_batch)} → {mid}+{len(notes_batch) - mid})[/yellow]"
            )
            return classify_batch_resilient(
                provider, notes_batch[:mid], system_prompt, settings
            ) + classify_batch_resilient(provider, notes_batch[mid:], system_prompt, settings)
        console.print(f"[yellow]Warning:[/yellow] skipping note — batch of 1 failed: {exc}")
        return []


def price_per_million(model: str) -> float | None:
    for prefix, price in _PRICE_PER_M.items():
        if model.startswith(prefix):
            return price
    return None  # local / unknown model — no per-token cost


def _build_folder_path(folder: str, subfolder: str | None) -> str:
    return f"{folder}/{subfolder}" if subfolder else folder


def run_classify(export_file: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt_template = load_prompt_template()
    system_prompt = inject_taxonomy(system_prompt_template, taxonomy, settings)

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())
    skip_empty = settings.get("export", {}).get("skip_empty", True)
    notes = (
        [n for n in all_notes if (n.get("body") or "").strip() or (n.get("title") or "").strip()]
        if skip_empty
        else all_notes
    )

    fn = taxonomy.get("forever_notes", {})
    archive_folder = _folder_name(fn.get("archive", ""))
    exclude_archive = settings.get("classify", {}).get("exclude_archive", True)

    archive_notes: list[dict] = []
    if exclude_archive and archive_folder:
        archive_paths = set(enumerate_paths(fn.get("archive", {})))

        def _is_archive(n: dict) -> bool:
            fp = n.get("folder_path") or n.get("folder", "")
            return fp == archive_folder or fp in archive_paths

        archive_notes = [n for n in notes if _is_archive(n)]
        notes = [n for n in notes if not _is_archive(n)]
        if archive_notes:
            console.print(
                f"  [dim]Skipping {len(archive_notes)} Archive note(s) "
                f"(classify.exclude_archive = true)[/dim]"
            )

    llm_cfg = settings.get("llm") or settings.get("claude", {})
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

        console.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        console.print(f"Export:       {export_path}")
        console.print(f"Notes found:  {len(all_notes)}  ({len(notes)} after filtering)")
        console.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        console.print(f"Provider:     {provider.name}")
        console.print(f"Model:        {model}")
        console.print(f"Est. tokens:  ~{est_total_tokens:,}  (~{est_tokens_per_batch:,}/batch)")
        console.print(f"Est. cost:    {cost_str}")
        estimate = estimate_duration("classify", len(notes), logs_dir_path(settings))
        if estimate:
            console.print(f"Est. time:    {estimate}")
        console.print(f"\nOutput would be written to: {PROPOSALS_DIR}/proposal-{date_str}.json")
        RunLogger("classify", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(notes), "batches": len(batches)},
            dry_run=True,
            params={"export_file": str(export_path), "model": model, "batch_size": batch_size},
        )
        return

    logger = RunLogger("classify", logs_dir_path(settings))
    estimate = estimate_duration("classify", len(notes), logs_dir_path(settings))
    if estimate:
        console.print(f"[dim]Estimated duration: {estimate}[/dim]")

    review_folder = _folder_name(fn.get("review", ""))

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
        console=console,
        speed_estimate_period=3600.0,
    ) as progress:
        task = progress.add_task("Classifying...", total=len(batches))
        for i, batch in enumerate(batches):
            results = classify_batch_resilient(provider, batch, system_prompt, settings)
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
                    pf = result.get("proposed_folder", "")
                    ps = result.get("proposed_subfolder") or ""
                    proposed_folder_path_raw = f"{pf}/{ps}" if ps else pf
                proposed_folder_path = clamp_path(
                    proposed_folder_path_raw, effective_max_depth(settings)
                )
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

    for n in archive_notes:
        no_change.append(
            {
                "id": n["id"],
                "title": n.get("title", ""),
                "current_folder": n.get("folder", ""),
            }
        )

    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = PROPOSALS_DIR / f"proposal-{date_str}.json"

    proposal = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
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
        params={"export_file": str(export_path), "model": model, "batch_size": batch_size},
    )
