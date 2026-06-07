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

from scripts.classify.classify_notes import price_per_million
from scripts.config import (
    find_latest_export,
    get_category_meta,
    get_llm_config,
    load_settings,
    load_taxonomy,
    reorganization_mode,
)
from scripts.folder_utils import (
    effective_max_depth,
    enumerate_paths,
    folder_name,
    max_taxonomy_depth,
    nesting_mode,
    path_depth,
)
from scripts.json_output import emit_result
from scripts.json_utils import (
    extract_json_object,
    extract_json_themes,
    is_context_overflow,
    is_locale_error,
    normalize_for_apple,
    normalize_slug_title,
)
from scripts.providers import LLMProvider, get_max_tokens, get_provider
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
        "Most notes in this library are deliberately organized. "
        "You MUST map each theme to one of the existing folder paths listed above. "
        "Only use a path not in that list when the theme is clearly distinct and large "
        "enough to warrant a genuinely new folder — this should be rare. "
        "When in doubt, use the closest existing path."
    ),
    "static": (
        "This library's folder structure is FIXED and must not change. "
        "You MUST use only the existing folder paths listed above for suggested_path. "
        "Do not propose any new folder or subfolder under any circumstances. "
        "Map every theme to the most appropriate existing path."
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
    """Return unique folder paths from the export in first-appearance order.

    Preserves Apple Notes' native folder arrangement — AppleScript walks folders
    in the order they appear in the app, so first-appearance reflects the user's
    actual arrangement rather than an alphabetical sort.
    """
    seen: set[str] = set()
    result: list[str] = []
    for n in notes:
        fp = n.get("folder_path") or n.get("folder", "")
        if fp and fp not in seen:
            seen.add(fp)
            result.append(fp)
    return result


def inject_discover_taxonomy(
    system_prompt: str,
    taxonomy: dict,
    settings: dict | None = None,
    notes: list[dict] | None = None,
) -> str:
    """Replace {CATEGORIES}, {ESTABLISHED_PATHS}, and {NESTING_GUIDANCE} in the discover prompt."""
    fn = taxonomy.get("taxonomy", {})
    cat_meta = get_category_meta(settings or {})
    # Build "Folder — description" lines so the LLM knows each category's intent
    category_lines = [
        f"{folder_name(fn[key])}{' — ' + (cat_meta.get(key) or {}).get('description', '') if (cat_meta.get(key) or {}).get('description') else ''}"
        for key in fn
        if folder_name(fn[key])
    ]

    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)
    discover_mode = get_llm_config(settings or {}).get("theme_discovery_mode", "anchored")

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
            if reorg_mode == "static":
                established_block = (
                    "The following folders currently exist in your Apple Notes library:\n"
                    f"{path_list}\n\n"
                    "Your folder structure is FIXED. You MUST use only these exact paths "
                    "for suggested_path. Using any other path is an error."
                )
            elif reorg_mode == "conservative":
                established_block = (
                    "The following folders currently exist in your Apple Notes library:\n"
                    f"{path_list}\n\n"
                    "These represent your deliberate organizational structure. "
                    "For each theme you MUST use one of these paths as the suggested_path. "
                    "Only use a path not listed above if the theme is clearly distinct and "
                    "has no appropriate home in any existing folder."
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


def _sanitize_batch_for_locale(batch: list[dict]) -> list[dict]:
    """Strip unsupported characters and normalise slug titles for Apple Intelligence."""
    return [
        {
            **item,
            "title": normalize_slug_title(normalize_for_apple(item.get("title") or "")),
            "excerpt": normalize_for_apple(item.get("excerpt") or ""),
            "folder_path": normalize_for_apple(item.get("folder_path") or ""),
        }
        for item in batch
    ]


def _build_discover_payload(batch: list[dict]) -> str:
    """Serialise a discover batch as user content for the LLM.

    The 'id' field (x-coredata://UUID/ICNote/pN) is excluded: the discover
    action never references note IDs in its output, and the x-coredata URL
    format adds opaque non-English tokens that confuse Apple Intelligence's
    language detector.

    A plain-English preamble is prepended so the language detector sees English
    prose at the start of the user content rather than a bare JSON array.  The
    preamble also matches the 'Notes sample:' marker in the discover prompt
    template, which was designed to precede the batch.
    """
    items = [{k: v for k, v in item.items() if k != "id"} for item in batch]
    return "Notes sample:\n\n" + json.dumps(items, indent=2, ensure_ascii=False)


def _non_ascii_count(text: str) -> int:
    """Return the number of non-ASCII (> U+007F) characters in text."""
    return sum(1 for ch in text if ord(ch) >= 0x80)


def _non_ascii_sample(text: str, n: int = 6) -> str:
    """Return up to n unique non-ASCII characters found in text, for debug display."""
    seen: list[str] = []
    for ch in text:
        if ord(ch) >= 0x80 and ch not in seen:
            seen.append(ch)
        if len(seen) >= n:
            break
    return "".join(seen)


def _python_dedup_themes(themes: list[dict]) -> list[dict]:
    """Merge themes with identical suggested_path, summing estimated_count.

    First-occurrence wins for all other fields (name, description, reasoning,
    appears_in_categories).  Used as a pre-filter before Apple synthesis to
    collapse the many near-identical per-batch themes down to distinct paths,
    making the payload small enough for Apple's 4096-token context budget.
    """
    by_path: dict[str, dict] = {}
    for theme in themes:
        path = theme.get("suggested_path") or ""
        if path in by_path:
            by_path[path]["estimated_count"] = (by_path[path].get("estimated_count") or 0) + (
                theme.get("estimated_count") or 0
            )
        else:
            by_path[path] = dict(theme)
    return list(by_path.values())


def _strip_for_synthesis(themes: list[dict]) -> list[dict]:
    """Reduce themes to the 3 fields the LLM needs to merge/dedup.

    Strips description, reasoning, and appears_in_categories so each theme
    is ~25 tokens instead of ~90, letting the synthesis payload fit comfortably
    within Apple's 4096-token context.  Use _reattach_theme_details afterwards
    to restore the full fields from the original raw themes.
    """
    return [
        {
            "name": t.get("name") or "",
            "estimated_count": t.get("estimated_count") or 0,
            "suggested_path": t.get("suggested_path") or "",
        }
        for t in themes
    ]


def _reattach_theme_details(merged: list[dict], originals: list[dict]) -> list[dict]:
    """Re-attach description/reasoning/appears_in_categories after Apple synthesis.

    Synthesis returns only the 3 stripped fields; this function restores the
    remaining fields by matching each merged theme to its best original via
    suggested_path.  If no match is found the stripped theme is kept as-is.
    """
    by_path: dict[str, dict] = {}
    for t in originals:
        path = t.get("suggested_path") or ""
        if path and path not in by_path:
            by_path[path] = t
    result = []
    for theme in merged:
        path = theme.get("suggested_path") or ""
        original = by_path.get(path)
        if original:
            # Overlay merged name/count/path on the original's full field set
            result.append({**original, **theme})
        else:
            result.append(theme)
    return result


def _apple_synthesis_prompt(
    category_names: list[str],
    reorg_mode: str = "standard",
    established_paths: list[str] | None = None,
) -> str:
    """Minimal synthesis prompt for Apple's tight 4096-token context budget.

    ~80-130 tokens vs ~1000 for the full synthesis prompt.  Conservative and
    static modes include the established paths list as a compact hint so the
    synthesis step is anchored to existing structure, not just category names.
    """
    folders = ", ".join(category_names)
    if reorg_mode in ("conservative", "static"):
        path_hint = ", ".join(established_paths[:20]) if established_paths else ""
        return (
            "Merge and deduplicate these themes. Only merge themes that are clearly similar. "
            "Preserve the suggested_path values already present — do not rename or replace them. "
            f"Top-level folders: {folders}. "
            + (f"Existing paths (use only these): {path_hint}. " if path_hint else "")
            + 'Return JSON: {"themes": [{"name": "...", "estimated_count": N, "suggested_path": "..."}]}'
        )
    return (
        "Merge and deduplicate these themes. Combine similar themes, sum estimated_counts, "
        f"and keep the best suggested_path. Top-level folders: {folders}. "
        'Return JSON: {"themes": [{"name": "...", "estimated_count": N, "suggested_path": "..."}]}'
    )


def _discover_batch(
    provider: LLMProvider,
    system_prompt: str,
    batch: list,
    con: Console | None = None,
    max_tokens: int = 4096,
    debug: bool = False,
) -> list:
    """Send one batch to the LLM; on context overflow split; on locale error probe individually."""
    _con = con or console

    # For Apple Intelligence, normalize content for locale compatibility before the first
    # call.  Normalizing proactively avoids the fail/retry cycle for every batch
    # containing accented letters, curly quotes, or other characters that Apple autocorrect
    # inserts into ordinary English notes.
    if provider.name == "apple":
        if debug:
            raw_payload = _build_discover_payload(batch)
            orig_batch_non_ascii = _non_ascii_count(raw_payload)
            orig_prompt_non_ascii = _non_ascii_count(system_prompt)
            if orig_batch_non_ascii or orig_prompt_non_ascii:
                _con.print(
                    f"[dim][debug] apple pre-sanitize: "
                    f"batch non-ASCII={orig_batch_non_ascii}, "
                    f"prompt non-ASCII={orig_prompt_non_ascii}[/dim]"
                )
        batch = _sanitize_batch_for_locale(batch)
        system_prompt = normalize_for_apple(system_prompt)

    user_payload = _build_discover_payload(batch)

    if debug:
        batch_non_ascii = _non_ascii_count(user_payload)
        prompt_non_ascii = _non_ascii_count(system_prompt)
        _con.print(
            f"[dim][debug] batch {len(batch)} notes: "
            f"payload non-ASCII={batch_non_ascii}, "
            f"system-prompt non-ASCII={prompt_non_ascii}[/dim]"
        )
        if batch_non_ascii:
            _con.print(
                f"[dim][debug]   payload sample chars: {_non_ascii_sample(user_payload)!r}[/dim]"
            )
        if prompt_non_ascii:
            _con.print(
                f"[dim][debug]   prompt sample chars: {_non_ascii_sample(system_prompt)!r}[/dim]"
            )

    response: str = ""
    try:
        response = provider.classify_messages(
            system_prompt,
            user_payload,
            max_tokens=max_tokens,
        )
        return extract_json_themes(response)
    except (ValueError, json.JSONDecodeError) as exc:
        # Apple Intelligence caps output at 1600 tokens and truncates silently —
        # it never raises a context-overflow exception, so truncated batches
        # surface here as parse errors instead.  Split and retry rather than
        # dropping the whole batch; single-note failures are skipped as usual.
        if len(batch) > 1:
            mid = len(batch) // 2
            _con.print(
                f"[yellow]Parse error — splitting batch "
                f"({len(batch)} → {mid}+{len(batch) - mid})[/yellow]"
            )
            return _discover_batch(
                provider, system_prompt, batch[:mid], con=_con, max_tokens=max_tokens, debug=debug
            ) + _discover_batch(
                provider, system_prompt, batch[mid:], con=_con, max_tokens=max_tokens, debug=debug
            )
        preview = f"\n  Response: {response[:300]!r}" if response else ""
        _con.print(f"[yellow]Warning:[/yellow] batch parse error — {exc}{preview}")
        return []
    except Exception as exc:
        if is_context_overflow(exc) and len(batch) > 1:
            mid = len(batch) // 2
            _con.print(
                f"[yellow]Context overflow — splitting batch ({len(batch)} → {mid}+{len(batch) - mid})[/yellow]"
            )
            return _discover_batch(
                provider, system_prompt, batch[:mid], con=_con, max_tokens=max_tokens, debug=debug
            ) + _discover_batch(
                provider, system_prompt, batch[mid:], con=_con, max_tokens=max_tokens, debug=debug
            )
        if is_locale_error(exc):
            # Pre-sanitization already ran for Apple, so a locale error here means the
            # content itself triggers the filter (e.g. dense acronyms, structured data that
            # the language detector scores as non-English).  A "sanitized retry" on the
            # whole batch is a no-op and will always fail — skip it.
            #
            # Instead, probe each note individually in O(n) calls.  Notes that pass the
            # locale filter contribute their themes directly; notes that fail are skipped.
            # This replaces the prior O(n log n) binary-split cascade.
            if len(batch) == 1:
                note_title = (batch[0].get("title") or "").strip()[:60]
                _con.print(
                    f"[yellow]Warning:[/yellow] skipping note '{note_title}'"
                    " — Apple Intelligence locale error (unsupported language)"
                )
                return []
            _con.print(
                f"[yellow]Locale error — probing {len(batch)} notes individually "
                "to isolate failures[/yellow]"
            )
            # A single-note probe needs at most 2–3 themes; cap response tokens tightly
            # so verbose reasoning doesn't overflow Apple's 4096-token context budget.
            probe_max_tokens = min(400, max_tokens)
            themes: list = []
            for note in batch:
                note_payload = _build_discover_payload([note])
                try:
                    note_response = provider.classify_messages(
                        system_prompt, note_payload, max_tokens=probe_max_tokens
                    )
                    note_themes = extract_json_themes(note_response)
                    themes.extend(note_themes)
                except Exception as note_exc:
                    if is_locale_error(note_exc):
                        note_title = (note.get("title") or "").strip()[:60]
                        _con.print(
                            f"[yellow]Warning:[/yellow] skipping note '{note_title}'"
                            " — Apple Intelligence locale error (unsupported language)"
                        )
                    elif debug:
                        _con.print(
                            f"[dim][debug]   note probe failed "
                            f"({type(note_exc).__name__}): {note_exc}[/dim]"
                        )
            return themes
        _con.print(f"[yellow]Warning:[/yellow] skipping discover batch of {len(batch)} — {exc}")
        return []


def run_discover(
    export_file: str | None,
    dry_run: bool,
    json_output: bool = False,
    debug: bool = False,
    limit: int | None = None,
) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    taxonomy = load_taxonomy()

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        msg = f"Export file not found: {export_path}"
        if json_output:
            emit_result("discover", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    all_notes = json.loads(export_path.read_text())
    system_prompt = inject_discover_taxonomy(
        load_discover_prompt(), taxonomy, settings, notes=all_notes
    )

    llm_cfg = get_llm_config(settings)
    sample_size = llm_cfg.get("theme_discovery_sample", _DEFAULT_SAMPLE)
    min_subfolder = settings.get("thresholds", {}).get(
        "min_notes_for_subfolder", _MIN_SUBFOLDER_DEFAULT
    )
    provider = get_provider(settings, dry_run=dry_run)
    model = provider.model
    max_tokens = get_max_tokens(settings, provider)

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
    if limit is not None:
        summaries = summaries[:limit]

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

        con.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        con.print(f"Export:         {export_path}")
        notes_label = f"{len(summaries)}" + (f"  (limited to {limit})" if limit is not None else "")
        con.print(f"Notes sampled:  {notes_label}")
        con.print(f"Batches:        {len(batches)}  (sample size: {sample_size})")
        con.print("+ 1 synthesis call\n")
        con.print(f"Provider:       {provider.name}")
        con.print(f"Model:          {model}")
        con.print(f"Mode:           {reorganization_mode(settings)}")
        con.print(f"Est. tokens:    ~{est_total_tokens:,}")
        con.print(f"Est. cost:      {cost_str}")
        estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
        if estimate:
            con.print(f"Est. time:      {estimate}")
        con.print(f"\nOutput would be written to: {THEME_MAPS_DIR}/themes-{date_str}.json")
        _dr_reorg = reorganization_mode(settings)
        con.print("\nTo proceed:")
        if _dr_reorg == "static":
            con.print("  1. uv run notes discover  — themes are informational in static mode")
            con.print("  2. uv run notes classify")
        else:
            con.print("  1. uv run notes discover  — generates the theme map")
            con.print(
                "  2. uv run notes draft    — turns themes into an editable YAML draft;"
                " review before applying"
            )
            con.print("  3. uv run notes classify")
        log_file = RunLogger("discover", logs_dir_path(settings)).finish(
            summary={"notes_processed": len(summaries), "batches": len(batches)},
            dry_run=True,
            params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
        )
        if json_output:
            emit_result(
                "discover",
                dry_run=True,
                output_file=THEME_MAPS_DIR / f"themes-{date_str}.json",
                log_file=log_file,
                summary={"notes_processed": len(summaries), "batches": len(batches)},
            )
        return

    logger = RunLogger("discover", logs_dir_path(settings))
    limit_note = f"  ·  {len(summaries)} notes (limit={limit})" if limit is not None else ""
    con.print(
        f"[dim]Mode: {reorganization_mode(settings)}  ·  {provider.name} / {model}{limit_note}[/dim]"
    )
    estimate = estimate_duration("discover", len(summaries), logs_dir_path(settings))
    if estimate:
        con.print(f"[dim]Estimated duration: {estimate}[/dim]")

    # ── Pre-compute synthesis prompt (no I/O) ────────────────────────────────

    fn = taxonomy.get("taxonomy", {})
    mode = nesting_mode(settings)
    max_depth = effective_max_depth(settings)
    current_depth = max_taxonomy_depth(taxonomy)
    discover_mode = llm_cfg.get("theme_discovery_mode", "anchored")

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
    category_names = [folder_name(fn[key]) for key in fn if folder_name(fn[key])]
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
        if reorg_mode == "static":
            folder_anchor = (
                f"The existing Apple Notes folder structure is: {folder_list}. "
                "You MUST use only these paths for suggested_path — no exceptions."
            )
        else:
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
        console=con,
        speed_estimate_period=3600.0,
    ) as progress:
        task = progress.add_task("Discovering themes...", total=len(batches) + 1)

        for i, batch in enumerate(batches):
            themes = _discover_batch(
                provider, system_prompt, batch, con=con, max_tokens=max_tokens, debug=debug
            )
            if themes:
                raw_theme_lists.append(themes)
                logger.event("batch", batch=i + 1, count=len(batch), status="ok")
            else:
                logger.event("batch", batch=i + 1, count=len(batch), status="error")
                batch_errors += 1
            progress.advance(task)

        if raw_theme_lists:
            all_raw = [theme for batch_list in raw_theme_lists for theme in batch_list]
            progress.update(task, description="Synthesizing themes...")
            if provider.name == "apple":
                # Two-step synthesis for Apple's 4096-token context budget:
                #
                # Step 1 (Python, no API cost): exact dedup by suggested_path.
                #   Many batches produce the same path (e.g. "Resources/Health").
                #   Collapsing identical paths first shrinks ~200 raw themes to
                #   ~30-50 distinct-path themes before any LLM call.
                #
                # Step 2 (LLM, 1 API call): semantic dedup using a stripped
                #   payload (name + count + path only, ~25 tokens each vs ~90
                #   for the full schema) and a minimal system prompt (~80 tokens).
                #   Token budget: 80 system + 50 themes × 25 = 1330 input,
                #   leaving ~2766 for response (capped at 1600) — fits 4096 ✓
                deduped = _python_dedup_themes(all_raw)
                stripped = _strip_for_synthesis(deduped)
                apple_prompt = _apple_synthesis_prompt(
                    category_names, reorg_mode=reorg_mode, established_paths=established
                )
                try:
                    # Prepend English prose so Apple's language detector anchors
                    # to English rather than scoring the bare JSON array as non-English.
                    synthesis_user = "Themes to merge:\n\n" + json.dumps(
                        stripped, indent=2, ensure_ascii=False
                    )
                    response = provider.classify_messages(
                        apple_prompt,
                        synthesis_user,
                        max_tokens=max_tokens,
                    )
                    merged = extract_json_themes(response)
                    final_themes = _reattach_theme_details(merged, all_raw)
                except Exception as exc:
                    if is_context_overflow(exc):
                        con.print(
                            "[yellow]Synthesis context overflow — using Python-deduped themes.[/yellow]"
                        )
                    else:
                        con.print(
                            f"[yellow]Synthesis error ({type(exc).__name__})"
                            " — using Python-deduped themes.[/yellow]"
                        )
                    final_themes = deduped
            else:
                try:
                    synthesis_response = provider.classify_messages(
                        synthesis_prompt,
                        json.dumps(all_raw, indent=2, ensure_ascii=False),
                        max_tokens=max_tokens,
                    )
                    synthesized = extract_json_object(synthesis_response)
                    final_themes = synthesized.get("themes", all_raw)
                except Exception as exc:
                    if is_context_overflow(exc):
                        con.print(
                            "[yellow]Synthesis context overflow — skipping dedup, using raw theme list.[/yellow]"
                        )
                    else:
                        con.print(
                            f"[yellow]Synthesis error — using raw theme list. ({exc})[/yellow]"
                        )
                    final_themes = all_raw
            progress.advance(task)

    if not raw_theme_lists:
        msg = "No themes found in any batch. Check the prompt template and LLM output."
        if json_output:
            emit_result("discover", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]{msg}[/red]")
        raise SystemExit(1)

    # ── Build and write theme map ────────────────────────────────────────────

    above_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) >= min_subfolder]
    below_threshold = [t for t in final_themes if (t.get("estimated_count") or 0) < min_subfolder]

    established_set = set(established)

    # Annotate each theme with its disposition so the JSON is self-documenting.
    # "use-existing": suggested_path already in the taxonomy — no structural change needed.
    # "create-new": suggested_path is a net-new proposal — gated by threshold and user review.
    for theme in final_themes:
        sp = theme.get("suggested_path") or ""
        theme["status"] = "use-existing" if sp in established_set else "create-new"

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

    top_level_folders = {folder_name(fn[key]) for key in fn if folder_name(fn[key])}
    by_category: dict[str, list[dict]] = {}
    for theme in final_themes:
        sp = theme.get("suggested_path") or ""
        top = sp.split("/")[0] if sp else ""
        bucket = top if top in top_level_folders else "Uncategorized"
        by_category.setdefault(bucket, []).append(theme)

    existing_count = sum(1 for t in final_themes if t.get("suggested_path") in established_set)
    new_count = len(final_themes) - existing_count

    con.print(f"\n[green]Done.[/green] Theme map written to [bold]{output_path}[/bold]")
    new_label = f"  ({existing_count} existing paths, {new_count} new)" if established else ""
    con.print(f"  Themes found:        {len(final_themes)}{new_label}")
    con.print(f"  Above threshold:     {len(above_threshold)}  (suggest subfolders)")
    con.print(f"  Below threshold:     {len(below_threshold)}  (keep flat)")

    if by_category:
        con.print("\n  [bold]By category:[/bold]")
        for cat in sorted(by_category, key=lambda c: (c == "Uncategorized", c)):
            themes_in_cat = by_category[cat]
            new_in_cat = sum(
                1 for t in themes_in_cat if t.get("suggested_path") not in established_set
            )
            new_suffix = f"  [dim]({new_in_cat} new)[/dim]" if new_in_cat else ""
            con.print(f"    {cat + ':':<20} {len(themes_in_cat)} theme(s){new_suffix}")

    con.print("\n[bold]Next steps:[/bold]")
    if reorg_mode == "static":
        con.print(
            "  [dim]Themes are informational in static mode — "
            "your folder structure is fixed and no new subfolders will be proposed.[/dim]"
        )
        con.print("  1. Run: uv run notes classify")
    elif len(above_threshold) == 0:
        con.print(
            f"  [dim]No themes reached the subfolder threshold ({min_subfolder} notes). "
            "Running notes draft would add nothing — skip directly to classify.[/dim]"
        )
        con.print("  1. Run: uv run notes classify")
    else:
        if reorg_mode == "conservative":
            con.print(
                "  1. Run: uv run notes draft"
                "  — proposes subfolders only where the evidence is strong"
            )
        else:
            con.print("  1. Run: uv run notes draft  — turns themes into an editable YAML draft")
        con.print(
            "     [dim]The draft YAML shows exactly what would change"
            " and is easy to edit — review it before applying.[/dim]"
        )
        con.print("  2. Run: uv run notes classify")
        con.print(
            f"  [dim]Advanced: inspect {output_path}"
            " to rename or merge themes before drafting.[/dim]"
        )

    summary: dict[str, object] = {
        "notes_processed": len(summaries),
        "themes_found": len(final_themes),
        "new_paths": len(new_paths),
        "above_threshold": len(above_threshold),
        "below_threshold": len(below_threshold),
        "batch_errors": batch_errors,
    }
    log_file = logger.finish(
        summary=summary,
        dry_run=False,
        params={"export_file": str(export_path), "model": model, "sample_size": sample_size},
    )
    if json_output:
        emit_result("discover", output_file=output_path, log_file=log_file, summary=summary)
