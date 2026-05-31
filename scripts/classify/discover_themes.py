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
    price_per_million,
)
from scripts.config import find_latest_export, load_settings, load_taxonomy, reorganization_mode
from scripts.folder_utils import (
    effective_max_depth,
    enumerate_paths,
    folder_name,
    max_taxonomy_depth,
    nesting_mode,
    path_depth,
)
from scripts.json_utils import extract_json_object, is_context_overflow
from scripts.providers import LLMProvider, get_provider
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


_CONSERVATISM_GUIDANCE: dict[str, str] = {
    "conservative": (
        "Most notes in this library are deliberately organized in their current folders. "
        "Only propose a new theme or subfolder path when you see a strong cluster of notes "
        "that genuinely lacks a good home in the existing structure. "
        "Do not propose reorganization of notes already in stable, purposeful locations. "
        "Strong evidence — many notes, a clear and distinct topic — is required before "
        "suggesting any new path."
    ),
    "standard": "",
    "full": (
        "Treat the entire library as if it has no established structure. "
        "Propose themes freely based purely on note content, ignoring current folder locations."
    ),
}


def _established_paths(taxonomy: dict) -> list[str]:
    """Return all subfolder paths (depth ≥ 2) currently defined in the taxonomy."""
    fn = taxonomy.get("taxonomy", {})
    return sorted(
        {p for entry in fn.values() for p in enumerate_paths(entry) if path_depth(p) >= 2}
    )


def _export_folder_tree(notes: list[dict]) -> list[str]:
    """Return all unique, non-empty folder paths present in the export, sorted."""
    return sorted({fp for n in notes if (fp := n.get("folder_path") or n.get("folder", ""))})


def inject_discover_taxonomy(
    system_prompt: str,
    taxonomy: dict,
    settings: dict | None = None,
    notes: list[dict] | None = None,
) -> str:
    """Replace {CATEGORIES}, {ESTABLISHED_PATHS}, and {NESTING_GUIDANCE} in the discover prompt."""
    fn = taxonomy.get("taxonomy", {})
    # Build "Folder — description" lines so the LLM knows each category's intent
    category_lines = [
        f"{folder_name(fn[key])} — {desc}"
        for key, desc in _CATEGORY_META
        if key in fn and folder_name(fn[key])
    ]

    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)
    discover_mode = (settings or {}).get("llm", {}).get("theme_discovery_mode", "anchored")

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

    reorg_mode = reorganization_mode(settings)

    if mode == "flat" or discover_mode == "full" or reorg_mode == "full":
        established_block = (
            "No subfolder paths are established yet. "
            "Propose suggested_path values freely where theme clusters warrant them."
        )
    else:
        # Prefer export folder tree (actual Apple Notes structure) as the primary anchor;
        # fall back to taxonomy-defined paths when no notes are supplied (e.g. tests).
        export_paths = _export_folder_tree(notes) if notes is not None else []
        taxonomy_paths = _established_paths(taxonomy)
        paths = export_paths or taxonomy_paths

        if paths:
            path_list = "\n".join(f"  - {p}" for p in paths)
            if reorg_mode == "conservative":
                established_block = (
                    "The following folders currently exist in your Apple Notes library:\n"
                    f"{path_list}\n\n"
                    "These represent your deliberate organizational structure. "
                    "For each theme, prefer a suggested_path that maps to one of these existing paths. "
                    "Only propose a new path when the theme clearly has no appropriate home "
                    "among these existing folders."
                )
            else:
                established_block = (
                    "The following folders currently exist in your Apple Notes library:\n"
                    f"{path_list}\n\n"
                    "For each theme, prefer a suggested_path that maps to one of these existing paths. "
                    "Only propose a new path when no existing path fits the theme well. "
                    "Prefer existing names and structure over synonyms or new hierarchies."
                )
        else:
            established_block = (
                "No subfolder paths are established yet. "
                "Propose suggested_path values freely where theme clusters warrant them."
            )
    conservatism = _CONSERVATISM_GUIDANCE.get(reorg_mode, "")

    return (
        system_prompt.replace("{CATEGORIES}", "\n".join(category_lines))
        .replace("{ESTABLISHED_PATHS}", established_block)
        .replace("{NESTING_GUIDANCE}", guidance)
        .replace("{CONSERVATISM_GUIDANCE}", conservatism)
    )


def _discover_batch(provider: LLMProvider, system_prompt: str, batch: list) -> list:
    """Send one batch to the LLM; on context overflow, split recursively and merge."""
    try:
        response = provider.classify_messages(
            system_prompt,
            json.dumps(batch, indent=2, ensure_ascii=False),
        )
        result = extract_json_object(response)
        return list(result.get("themes") or [])
    except (ValueError, json.JSONDecodeError) as exc:
        console.print(f"[yellow]Warning:[/yellow] batch parse error — {exc}")
        return []
    except Exception as exc:
        if is_context_overflow(exc) and len(batch) > 1:
            mid = len(batch) // 2
            console.print(
                f"[yellow]Context overflow — splitting batch ({len(batch)} → {mid}+{len(batch) - mid})[/yellow]"
            )
            return _discover_batch(provider, system_prompt, batch[:mid]) + _discover_batch(
                provider, system_prompt, batch[mid:]
            )
        raise


def run_discover(export_file: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())
    system_prompt = inject_discover_taxonomy(
        load_discover_prompt(), taxonomy, settings, notes=all_notes
    )

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
        console.print(f"Mode:           {reorganization_mode(settings)}")
        console.print(f"Est. tokens:    ~{est_total_tokens:,}")
        console.print(f"Est. cost:      {cost_str}")
        estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
        if estimate:
            console.print(f"Est. time:      {estimate}")
        console.print(f"\nOutput would be written to: {THEME_MAPS_DIR}/themes-{date_str}.json")
        console.print("\nNext steps after reviewing the theme map:")
        console.print("  1. Edit theme names, merge or split as needed")
        console.print(
            "  2. Run: uv run notes draft  — generates a draft taxonomy YAML from this theme map"
        )
        console.print("  3. Review the draft, then copy to config/taxonomy.local.yaml")
        console.print("  4. Run: uv run notes classify")
        RunLogger("discover", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(summaries), "batches": len(batches)},
            dry_run=True,
            params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
        )
        return

    logger = RunLogger("discover", logs_dir_path(settings))
    console.print(f"[dim]Mode: {reorganization_mode(settings)}[/dim]")
    estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
    if estimate:
        console.print(f"[dim]Estimated duration: {estimate}[/dim]")

    # ── Pre-compute synthesis prompt (no I/O) ────────────────────────────────

    fn = taxonomy.get("taxonomy", {})
    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)
    discover_mode = (settings or {}).get("llm", {}).get("theme_discovery_mode", "anchored")

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

    established = _established_paths(taxonomy)
    if established and mode != "flat" and discover_mode != "full":
        est_list = "\n".join(f"  - {p}" for p in established)
        anchor_guidance = (
            f"Established taxonomy paths — prefer these for suggested_path:\n{est_list}\n"
            "Only propose a new path when no established path fits."
        )
    else:
        anchor_guidance = "No established subfolder paths yet; propose freely."

    # The synthesis step merges batch results without seeing the original batch system prompt,
    # so it would otherwise have no knowledge of the user's actual folder names. Injecting the
    # category list here prevents the synthesis LLM from drifting to generic names (e.g.
    # "Permanent/Topic" instead of the user's actual folder name "Notes/Topic").
    category_names = [
        folder_name(fn[key]) for key, _ in _CATEGORY_META if key in fn and folder_name(fn[key])
    ]
    top_level_constraint = (
        f"The valid top-level folder names are exactly: {', '.join(category_names)}. "
        "Use these exact names as the first component of every suggested_path — "
        "do not rename or substitute them."
        if category_names
        else ""
    )

    reorg_mode = reorganization_mode(settings)
    conservatism_guidance = _CONSERVATISM_GUIDANCE.get(reorg_mode, "")

    # Give the synthesis step the same holistic folder context as the batch prompt so it
    # doesn't drift to generic names when merging results from multiple batches.
    export_folders = _export_folder_tree(all_notes)
    if export_folders and reorg_mode != "full":
        folder_list = ", ".join(export_folders[:30])
        folder_anchor = (
            f"The existing Apple Notes folder structure is: {folder_list}. "
            "Prefer suggested_path values drawn from this list. "
            "Only deviate when a strong theme cluster genuinely lacks an appropriate home here."
        )
    else:
        folder_anchor = ""

    synthesis_prompt = (
        "You received theme lists from multiple batches of notes. "
        "Merge, deduplicate, and consolidate into a single ranked list. "
        "Combine similar themes (e.g. 'Health', 'Health & Fitness', 'Fitness' → 'Health & Fitness'). "
        "Sum estimated_counts for merged themes. "
        f"Flag themes with estimated_count < {min_subfolder} as below the subfolder threshold. "
        f"{nesting_guidance} "
        f"{top_level_constraint} "
        f"{anchor_guidance} "
        + (f"{folder_anchor} " if folder_anchor else "")
        + (f"{conservatism_guidance} " if conservatism_guidance else "")
        + "Every theme must include a suggested_path field. "
        "Return a JSON object with a single 'themes' array using the same schema as before."
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
        speed_estimate_period=3600.0,
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
            progress.update(task, description="Synthesizing themes...")
            all_raw = [theme for batch_list in raw_theme_lists for theme in batch_list]
            try:
                synthesis_response = provider.classify_messages(
                    synthesis_prompt,
                    json.dumps(all_raw, indent=2, ensure_ascii=False),
                )
                synthesized = extract_json_object(synthesis_response)
                final_themes = synthesized.get("themes", all_raw)
            except Exception as exc:
                if is_context_overflow(exc):
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

    established_set = set(established)
    new_paths = sorted(
        {
            t["suggested_path"]
            for t in final_themes
            if t.get("suggested_path") and t["suggested_path"] not in established_set
        }
    )

    theme_map = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
        "total_notes": len(all_notes),
        "subfolder_threshold": min_subfolder,
        "established_paths": established,
        "themes": final_themes,
        "new_paths": new_paths,
        "above_threshold": len(above_threshold),
        "below_threshold": len(below_threshold),
    }

    THEME_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = THEME_MAPS_DIR / f"themes-{date_str}.json"
    output_path.write_text(json.dumps(theme_map, indent=2, ensure_ascii=False))

    # ── Per-category breakdown ───────────────────────────────────────────────

    top_level_folders = {
        folder_name(fn[key]) for key, _ in _CATEGORY_META if key in fn and folder_name(fn[key])
    }
    by_category: dict[str, list[dict]] = {}
    for theme in final_themes:
        sp = theme.get("suggested_path") or ""
        top = sp.split("/")[0] if sp else ""
        bucket = top if top in top_level_folders else "Uncategorised"
        by_category.setdefault(bucket, []).append(theme)

    existing_count = sum(1 for t in final_themes if t.get("suggested_path") in established_set)
    new_count = len(final_themes) - existing_count

    console.print(f"\n[green]Done.[/green] Theme map written to [bold]{output_path}[/bold]")
    new_label = f"  ({existing_count} existing paths, {new_count} new)" if established else ""
    console.print(f"  Themes found:        {len(final_themes)}{new_label}")
    console.print(f"  Above threshold:     {len(above_threshold)}  (suggest subfolders)")
    console.print(f"  Below threshold:     {len(below_threshold)}  (keep flat)")

    if by_category:
        console.print("\n  [bold]By category:[/bold]")
        for cat in sorted(by_category, key=lambda c: (c == "Uncategorised", c)):
            themes_in_cat = by_category[cat]
            new_in_cat = sum(
                1 for t in themes_in_cat if t.get("suggested_path") not in established_set
            )
            new_suffix = f"  [dim]({new_in_cat} new)[/dim]" if new_in_cat else ""
            console.print(f"    {cat + ':':<20} {len(themes_in_cat)} theme(s){new_suffix}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. Review {output_path}")
    console.print("  2. Edit theme names, merge or split as needed")
    console.print(
        "  3. Run: uv run notes draft  — generates a draft taxonomy YAML from this theme map"
    )
    console.print("  4. Review the draft, then copy to config/taxonomy.local.yaml")
    console.print("  5. Run: uv run notes classify")

    logger.finish(
        summary={
            "notes_processed": len(summaries),
            "themes_found": len(final_themes),
            "new_paths": len(new_paths),
            "above_threshold": len(above_threshold),
            "below_threshold": len(below_threshold),
            "batch_errors": batch_errors,
        },
        dry_run=False,
        params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
    )
