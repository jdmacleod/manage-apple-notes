"""Discover thematic clusters in an Apple Notes export (Pass 1 of classification)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import track

from scripts.classify.classify_notes import (
    find_latest_export,
    load_settings,
    load_taxonomy,
    price_per_million,
)
from scripts.providers import get_provider

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


def _is_context_overflow(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("exceed_context", "context_length", "context size", "context window", "maximum context"))


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
            console.print(f"[yellow]Context overflow — splitting batch ({len(batch)} → {mid}+{len(batch)-mid})[/yellow]")
            return _discover_batch(provider, system_prompt, batch[:mid]) + _discover_batch(provider, system_prompt, batch[mid:])
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
    system_prompt = load_discover_prompt()

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        console.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())

    llm_cfg = settings.get("llm") or settings.get("claude", {})
    sample_size = llm_cfg.get("theme_discovery_sample", _DEFAULT_SAMPLE)
    min_subfolder = settings.get("thresholds", {}).get("min_notes_for_subfolder", _MIN_SUBFOLDER_DEFAULT)
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
        console.print(f"+ 1 synthesis call\n")
        console.print(f"Provider:       {provider.name}")
        console.print(f"Model:          {model}")
        console.print(f"Est. tokens:    ~{est_total_tokens:,}")
        console.print(f"Est. cost:      {cost_str}")
        console.print(f"\nOutput would be written to: {THEME_MAPS_DIR}/themes-{date_str}.json")
        console.print("\nNext steps after reviewing the theme map:")
        console.print("  1. Edit theme names in the JSON (merge, split, rename as needed)")
        console.print("  2. Add approved subfolder names to config/taxonomy.local.yaml")
        console.print("  3. Run: uv run notes classify")
        return

    # ── Discovery batches ────────────────────────────────────────────────────

    raw_theme_lists: list[list] = []

    for batch in track(batches, description="Discovering themes..."):
        themes = _discover_batch(provider, system_prompt, batch)
        if themes:
            raw_theme_lists.append(themes)

    if not raw_theme_lists:
        console.print("[red]No themes found in any batch. Check the prompt template and LLM output.[/red]")
        raise SystemExit(1)

    # ── Synthesis call — merge and deduplicate themes across batches ─────────

    synthesis_prompt = (
        "You received theme lists from multiple batches of notes. "
        "Merge, deduplicate, and consolidate into a single ranked list. "
        "Combine similar themes (e.g. 'Health', 'Health & Fitness', 'Fitness' → 'Health & Fitness'). "
        "Sum estimated_counts for merged themes. "
        f"Flag themes with estimated_count < {min_subfolder} as below the subfolder threshold. "
        "Return a JSON object with a single 'themes' array using the same schema as before."
    )

    all_raw = [theme for batch in raw_theme_lists for theme in batch]
    try:
        synthesis_response = provider.classify_messages(
            synthesis_prompt,
            json.dumps(all_raw, indent=2, ensure_ascii=False),
        )
        synthesized = _extract_json_object(synthesis_response)
        final_themes = synthesized.get("themes", all_raw)
    except Exception as exc:
        if _is_context_overflow(exc):
            console.print("[yellow]Synthesis context overflow — skipping dedup, using raw theme list.[/yellow]")
        else:
            console.print(f"[yellow]Synthesis error — using raw theme list. ({exc})[/yellow]")
        final_themes = all_raw

    # ── Build and write theme map ────────────────────────────────────────────

    above_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) >= min_subfolder]
    below_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) < min_subfolder]

    theme_map = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_export": str(export_path),
        "total_notes": len(all_notes),
        "subfolder_threshold": min_subfolder,
        "themes": final_themes,
        "above_threshold": len(above_threshold),
        "below_threshold": len(below_threshold),
    }

    THEME_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
