"""Discover thematic clusters in an Apple Notes export (Pass 1 of classification)."""

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

from scripts.classify.classify_notes import (
    _CATEGORY_META,
    _folder_name,
    find_latest_export,
    load_settings,
    load_taxonomy,
    price_per_million,
)
from scripts.folder_utils import effective_max_depth, max_taxonomy_depth, nesting_mode
from scripts.providers import get_provider
from scripts.run_logger import RunLogger, estimate_duration, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
THEME_MAPS_DIR = REPO_ROOT / "data" / "theme-maps"

_DEFAULT_SAMPLE = 50
_MIN_SUBFOLDER_DEFAULT = 8


def load_discover_prompt() -> str:
    path = PROMPTS_DIR / "discover-themes.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    text = path.read_text()
    marker = "\nNotes sample:\n"
    if marker not in text:
        raise ValueError(f"Prompt template missing '{marker.strip()}' separator")
    system_part, _ = text.split(marker, 1)
    return system_part.strip()


def inject_discover_taxonomy(
    system_prompt: str,
    taxonomy: dict,
    settings: dict | None = None,
) -> str:
    """Replace {CATEGORIES} and {NESTING_GUIDANCE} in the discover prompt template."""
    fn = taxonomy.get("forever_notes", {})
    folders = [
        _folder_name(fn[key]) for key, _ in _CATEGORY_META if key in fn and _folder_name(fn[key])
    ]
    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)

    if mode == "flat":
        guidance = "Do not suggest subfolders. All themes should map to top-level categories only."
    elif mode == "deep":
        guidance = (
            f"You may suggest hierarchical folder paths up to {max_depth} levels deep "
            f"where strong theme clusters warrant it. Use '/' to separate path levels, "
            f"e.g. 'Resources/Programming/Python'."
        )
    else:  # natural
        guidance = (
            f"The current taxonomy is {current_depth} level(s) deep. "
            f"Do not suggest paths deeper than {min(current_depth + 1, max_depth)} levels. "
            f"Add one additional tier only where a clear theme cluster warrants it."
        )

    return system_prompt.replace("{CATEGORIES}", ", ".join(folders)).replace(
        "{NESTING_GUIDANCE}", guidance
    )


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


def _discover_batch(provider, system_prompt: str, batch: list) -> list:
    """Send one batch to the LLM; on context overflow, split recursively and merge."""
    try:
        response = provider.classify_messages(
            system_prompt,
            json.dumps(batch, indent=2, ensure_ascii=False),
        )
        result = _extract_json_object(response)
        return result.get("themes", [])
    except (ValueError, json.JSONDecodeError) as exc:
        console.print(f"[yellow]Warning:[/yellow] batch parse error — {exc}")
        return []
    except Exception as exc:
        if _is_context_overflow(exc) and len(batch) > 1:
            mid = len(batch) // 2
            console.print(
                f"[yellow]Context overflow — splitting batch ({len(batch)} → {mid}+{len(batch) - mid})[/yellow]"
            )
            return _discover_batch(provider, system_prompt, batch[:mid]) + _discover_batch(
                provider, system_prompt, batch[mid:]
            )
        raise


def _extract_json_object(text: str) -> dict:
    """Extract a JSON object from an LLM response that may include prose or fences."""
    if "```" in text:
        start = text.find("{", text.find("```"))
    else:
        start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in response:\n{text[:300]}")
    return json.loads(text[start:end])


def run_discover(export_file: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt = inject_discover_taxonomy(load_discover_prompt(), taxonomy, settings)

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())

    llm_cfg = settings.get("llm") or settings.get("claude", {})
    sample_size = llm_cfg.get("theme_discovery_sample", _DEFAULT_SAMPLE)
    min_subfolder = settings.get("thresholds", {}).get(
        "min_notes_for_subfolder", _MIN_SUBFOLDER_DEFAULT
    )
    provider = get_provider(settings, dry_run=dry_run)
    model = provider.model

    # Lightweight summaries — title + first 200 chars of body + folder context
    summaries = [
        {
            "id": n["id"],
            "title": n.get("title", ""),
            "excerpt": (n.get("body") or "")[:200],
            "folder_path": n.get("folder_path") or n.get("folder", ""),
        }
        for n in all_notes
        if (n.get("title") or "").strip() or (n.get("body") or "").strip()
    ]

    batches = [summaries[i : i + sample_size] for i in range(0, len(summaries), sample_size)]

    if dry_run:
        ppm = price_per_million(model)
        est_tokens_per_note = 120  # shorter excerpts than classify pass
        est_total_tokens = len(summaries) * est_tokens_per_note + len(batches) * 1500
        cost_str = (
            f"~${(est_total_tokens / 1_000_000) * ppm:.2f}  (@ ${ppm:.2f}/M input tokens)"
            if ppm is not None
            else "$0.00 (local inference)"
        )
        date_str = datetime.now().strftime("%Y-%m-%d")

        console.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        console.print(f"Export:         {export_path}")
        console.print(f"Notes sampled:  {len(summaries)}")
        console.print(f"Batches:        {len(batches)}  (sample size: {sample_size})")
        console.print("+ 1 synthesis call\n")
        console.print(f"Provider:       {provider.name}")
        console.print(f"Model:          {model}")
        console.print(f"Est. tokens:    ~{est_total_tokens:,}")
        console.print(f"Est. cost:      {cost_str}")
        estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
        if estimate:
            console.print(f"Est. time:      {estimate}")
        console.print(f"\nOutput would be written to: {THEME_MAPS_DIR}/themes-{date_str}.json")
        console.print("\nNext steps after reviewing the theme map:")
        console.print("  1. Edit theme names in the JSON (merge, split, rename as needed)")
        console.print("  2. Add approved subfolder names to config/taxonomy.local.yaml")
        console.print("  3. Run: uv run notes classify")
        RunLogger("discover", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(summaries), "batches": len(batches)},
            dry_run=True,
            params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
        )
        return

    logger = RunLogger("discover", logs_dir_path(settings))
    estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
    if estimate:
        console.print(f"[dim]Estimated duration: {estimate}[/dim]")

    # ── Pre-compute synthesis prompt (no I/O) ────────────────────────────────

    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)
    if mode == "flat":
        nesting_guidance = "Do not suggest subfolders. All themes map to top-level categories only."
    elif mode == "deep":
        nesting_guidance = (
            f"You may suggest hierarchical paths up to {max_depth} levels deep. "
            f"Add a 'suggested_path' field using '/' as the separator, e.g. 'Resources/Programming/Python'."
        )
    else:
        cap = min(current_depth + 1, max_depth)
        nesting_guidance = (
            f"The current taxonomy is {current_depth} level(s) deep. "
            f"Do not suggest paths deeper than {cap} levels. "
            f"Add a 'suggested_path' field only when a clear subfolder is warranted, "
            f"e.g. 'Resources/Programming'."
        )

    synthesis_prompt = (
        "You received theme lists from multiple batches of notes. "
        "Merge, deduplicate, and consolidate into a single ranked list. "
        "Combine similar themes (e.g. 'Health', 'Health & Fitness', 'Fitness' → 'Health & Fitness'). "
        "Sum estimated_counts for merged themes. "
        f"Flag themes with estimated_count < {min_subfolder} as below the subfolder threshold. "
        f"{nesting_guidance} "
        "Return a JSON object with a single 'themes' array using the same schema as before, "
        "adding an optional 'suggested_path' field where appropriate."
    )

    # ── Discovery batches + synthesis (single progress bar) ──────────────────

    raw_theme_lists: list[list] = []
    batch_errors = 0
    final_themes: list = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(elapsed_when_finished=True),
        console=console,
    ) as progress:
        # total=len(batches)+1 accounts for the synthesis call after discovery
        task = progress.add_task("Discovering themes...", total=len(batches) + 1)

        for i, batch in enumerate(batches):
            themes = _discover_batch(provider, system_prompt, batch)
            if themes:
                raw_theme_lists.append(themes)
                logger.event("batch", batch=i + 1, count=len(batch), status="ok")
            else:
                logger.event("batch", batch=i + 1, count=len(batch), status="error")
                batch_errors += 1
            progress.advance(task)

        if raw_theme_lists:
            progress.update(task, description="Synthesising themes...")
            all_raw = [theme for batch_list in raw_theme_lists for theme in batch_list]
            try:
                synthesis_response = provider.classify_messages(
                    synthesis_prompt,
                    json.dumps(all_raw, indent=2, ensure_ascii=False),
                )
                synthesized = _extract_json_object(synthesis_response)
                final_themes = synthesized.get("themes", all_raw)
            except Exception as exc:
                if _is_context_overflow(exc):
                    console.print(
                        "[yellow]Synthesis context overflow — skipping dedup, using raw theme list.[/yellow]"
                    )
                else:
                    console.print(
                        f"[yellow]Synthesis error — using raw theme list. ({exc})[/yellow]"
                    )
                final_themes = all_raw
            progress.advance(task)

    if not raw_theme_lists:
        console.print(
            "[red]No themes found in any batch. Check the prompt template and LLM output.[/red]"
        )
        raise SystemExit(1)

    # ── Build and write theme map ────────────────────────────────────────────

    above_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) >= min_subfolder]
    below_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) < min_subfolder]

    theme_map = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
        "total_notes": len(all_notes),
        "subfolder_threshold": min_subfolder,
        "themes": final_themes,
        "above_threshold": len(above_threshold),
        "below_threshold": len(below_threshold),
    }

    THEME_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = THEME_MAPS_DIR / f"themes-{date_str}.json"
    output_path.write_text(json.dumps(theme_map, indent=2, ensure_ascii=False))

    console.print(f"\n[green]Done.[/green] Theme map written to [bold]{output_path}[/bold]")
    console.print(f"  Themes found:        {len(final_themes)}")
    console.print(f"  Above threshold:     {len(above_threshold)}  (suggest subfolders)")
    console.print(f"  Below threshold:     {len(below_threshold)}  (keep flat)")
    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. Review {output_path}")
    console.print("  2. Edit theme names, merge/split as needed")
    console.print("  3. Add approved subfolders to config/taxonomy.local.yaml")
    console.print("  4. Run: uv run notes classify")

    logger.finish(
        summary={
            "notes_processed": len(summaries),
            "themes_found": len(final_themes),
            "above_threshold": len(above_threshold),
            "below_threshold": len(below_threshold),
            "batch_errors": batch_errors,
        },
        dry_run=False,
        params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
    )
