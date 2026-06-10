"""Detect duplicate notes using a three-pass funnel and write a dedup proposal."""

from __future__ import annotations

import hashlib
import json
import re
import string
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

from rich.console import Console

from scripts.config import export_age_hours, find_latest_export, load_settings
from scripts.json_output import emit_result
from scripts.json_utils import extract_json_array
from scripts.providers import LLMProvider, get_max_tokens, get_provider
from scripts.run_logger import RunLogger, logs_dir_path

console = Console()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
PROPOSALS_DIR = REPO_ROOT / "data" / "proposals"
DEDUP_PROPOSALS_DIR = REPO_ROOT / "data" / "dedup-proposals"


def find_latest_proposal() -> Path | None:
    files = sorted(PROPOSALS_DIR.glob("proposal-*.json"), reverse=True)
    return files[0] if files else None


def load_prompt_template() -> str:
    path = PROMPTS_DIR / "deduplicate-notes.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    text = path.read_text()
    marker = "\nCandidate groups:\n"
    if marker not in text:
        raise ValueError(f"Prompt template missing '{marker.strip()}' separator")
    system_part, _ = text.split(marker, 1)
    return system_part.strip()


def _normalize_body(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text).strip()


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _build_entries(notes: list[dict], proposal_index: dict) -> list[dict]:
    entries = []
    for note in notes:
        note_id = note["id"]
        proposal_note = proposal_index.get(note_id, {})
        proposed_folder_path = (
            proposal_note.get("proposed_folder_path")
            or note.get("folder_path")
            or note.get("folder", "")
        )
        body = note.get("body", "") or ""
        normalized = _normalize_body(body)
        entries.append(
            {
                "id": note_id,
                "title": note.get("title", ""),
                "folder": note.get("folder", ""),
                "folder_path": note.get("folder_path") or note.get("folder", ""),
                "proposed_folder_path": proposed_folder_path,
                "modified": note.get("modified", ""),
                "word_count": _word_count(body),
                "body": body,
                "_normalized": normalized,
                "_hash": _md5(normalized) if normalized else None,
            }
        )
    return entries


def _choose_keep(notes: list[dict]) -> tuple[str, str]:
    def score(n: dict) -> tuple:
        in_correct = 1 if n["folder_path"] == n["proposed_folder_path"] else 0
        return (n["word_count"], in_correct, n.get("modified", "") or "", len(n.get("title", "")))

    best = max(notes, key=score)
    reasons = []
    if best["word_count"] >= max(n["word_count"] for n in notes):
        reasons.append("most complete content")
    if best["folder_path"] == best["proposed_folder_path"]:
        reasons.append("already in correct folder")
    if not reasons:
        reasons.append("most recently modified")
    return best["id"], "; ".join(reasons).capitalize() + "."


def _note_summary(n: dict, preview_chars: int) -> dict:
    return {
        "id": n["id"],
        "title": n["title"],
        "folder": n["folder"],
        "proposed_folder_path": n["proposed_folder_path"],
        "modified": n["modified"],
        "word_count": n["word_count"],
        "content_preview": n["body"][:preview_chars],
    }


def pass1_exact(entries: list[dict], preview_chars: int) -> tuple[list[dict], set[str]]:
    hash_groups: dict[str, list[dict]] = {}
    for e in entries:
        if e["_hash"] and e["_normalized"]:
            hash_groups.setdefault(e["_hash"], []).append(e)

    groups: list[dict] = []
    consumed: set[str] = set()
    for group_notes in hash_groups.values():
        if len(group_notes) < 2:
            continue
        keep_id, keep_reason = _choose_keep(group_notes)
        groups.append(
            {
                "duplicate_type": "exact",
                "resolution": "delete",
                "notes": [_note_summary(n, preview_chars) for n in group_notes],
                "keep_id": keep_id,
                "delete_ids": [n["id"] for n in group_notes if n["id"] != keep_id],
                "keep_reason": keep_reason,
                "review_note": None,
            }
        )
        for n in group_notes:
            consumed.add(n["id"])
    return groups, consumed


def pass2_fuzzy(
    entries: list[dict],
    consumed: set[str],
    settings: dict,
) -> list[tuple[dict, dict, float]]:
    from thefuzz import fuzz

    dedup_cfg = settings.get("deduplication", {})
    title_threshold = float(dedup_cfg.get("fuzzy_title_threshold", 85))
    content_threshold = float(dedup_cfg.get("jaccard_content_threshold", 80))

    folder_groups: dict[str, list[dict]] = {}
    for e in entries:
        if e["id"] not in consumed:
            folder_groups.setdefault(e["proposed_folder_path"], []).append(e)

    candidates: list[tuple[dict, dict, float]] = []
    seen_pairs: set[frozenset] = set()

    for folder_entries in folder_groups.values():
        if len(folder_entries) < 2:
            continue
        for note_a, note_b in combinations(folder_entries, 2):
            pair = frozenset([note_a["id"], note_b["id"]])
            if pair in seen_pairs:
                continue
            title_score = fuzz.token_sort_ratio(note_a["title"], note_b["title"])
            if title_score < title_threshold:
                continue
            body_score = fuzz.token_set_ratio(note_a["body"][:500], note_b["body"][:500])
            if body_score < content_threshold:
                continue
            candidates.append((note_a, note_b, (title_score + body_score) / 2))
            seen_pairs.add(pair)

    return candidates


def pass3_llm(
    candidates: list[tuple[dict, dict, float]],
    system_prompt: str,
    provider: LLMProvider,
    preview_chars: int,
    max_tokens: int = 4096,
) -> list[dict]:
    groups_payload = [
        {
            "group_id": i + 1,
            "similarity_score": round(score / 100, 2),
            "notes": [
                {
                    "id": note_a["id"],
                    "title": note_a["title"],
                    "folder": note_a["folder"],
                    "proposed_folder_path": note_a["proposed_folder_path"],
                    "modified": note_a["modified"],
                    "word_count": note_a["word_count"],
                    "body": note_a["body"][:1000],
                },
                {
                    "id": note_b["id"],
                    "title": note_b["title"],
                    "folder": note_b["folder"],
                    "proposed_folder_path": note_b["proposed_folder_path"],
                    "modified": note_b["modified"],
                    "word_count": note_b["word_count"],
                    "body": note_b["body"][:1000],
                },
            ],
        }
        for i, (note_a, note_b, score) in enumerate(candidates)
    ]

    text = provider.classify_messages(
        system_prompt,
        json.dumps(groups_payload, indent=2, ensure_ascii=False),
        max_tokens=max_tokens,
    )
    result: list[dict] = extract_json_array(text)
    return result


def run_dedup(
    export_file: str | None,
    proposal_file: str | None,
    dry_run: bool,
    json_output: bool = False,
) -> None:
    con = Console(stderr=True) if json_output else console
    settings = load_settings()
    dedup_cfg = settings.get("deduplication", {})
    preview_chars = int(dedup_cfg.get("content_preview_chars", 300))

    export_path = Path(export_file) if export_file else find_latest_export()
    if not export_path.exists():
        msg = f"Export file not found: {export_path}"
        if json_output:
            emit_result("dedup", status="error", dry_run=dry_run, error=msg)
        else:
            con.print(f"[red]Export file not found:[/red] {export_path}")
        raise SystemExit(1)

    max_age = (settings.get("safety") or {}).get("export_max_age_hours", 24)
    if max_age:
        age_h = export_age_hours(export_path)
        if age_h > max_age:
            con.print(
                f"[yellow]Warning:[/yellow] Export is {age_h:.0f}h old"
                " — consider re-running 'notes export' first."
            )

    all_notes = json.loads(export_path.read_text())

    proposal_index: dict[str, dict] = {}
    source_proposal: str | None = None

    if proposal_file:
        p_path: Path | None = Path(proposal_file)
    else:
        p_path = find_latest_proposal()

    if p_path and p_path.exists():
        proposal = json.loads(p_path.read_text())
        source_proposal = str(p_path)
        for entry in proposal.get("moves", []) + proposal.get("no_change", []):
            proposal_index[entry["id"]] = entry

    entries = _build_entries(all_notes, proposal_index)

    # Pass 1: exact hash matches — always run (free)
    with con.status("Pass 1: finding exact duplicates…"):
        exact_groups, consumed = pass1_exact(entries, preview_chars)
    con.print(
        f"Pass 1: [green]{len(exact_groups)}[/green] exact duplicate group(s) "
        f"({len(consumed)} note(s) consumed)"
    )

    # Pass 2: fuzzy candidates — always run (free)
    with con.status("Pass 2: finding fuzzy candidates…"):
        candidates = pass2_fuzzy(entries, consumed, settings)
    con.print(f"Pass 2: [green]{len(candidates)}[/green] fuzzy candidate pair(s)")

    if dry_run:
        con.print(
            f"\n[bold]Dry run complete.[/bold] "
            f"{len(exact_groups)} exact group(s), {len(candidates)} fuzzy pair(s) found."
        )
        con.print(
            "Run without --dry-run to review fuzzy candidates with the LLM and write a proposal."
        )
        dry_summary: dict[str, object] = {
            "notes_processed": len(entries),
            "exact_groups": len(exact_groups),
            "fuzzy_candidates": len(candidates),
        }
        log_file = RunLogger("dedup", logs_dir_path(settings)).finish(
            summary=dry_summary,
            dry_run=True,
            params={"export_file": str(export_path)},
        )
        if json_output:
            emit_result("dedup", dry_run=True, log_file=log_file, summary=dry_summary)
        return

    logger = RunLogger("dedup", logs_dir_path(settings))
    logger.event("pass", n=1, count=len(exact_groups), status="ok")
    logger.event("pass", n=2, count=len(candidates), status="ok")

    # Pass 3: LLM review of fuzzy candidates
    llm_groups: list[dict] = []
    if candidates:
        system_prompt = load_prompt_template()
        provider = get_provider(settings)
        with con.status(
            f"Pass 3: reviewing {len(candidates)} pair(s) with {provider.model}…", spinner="dots"
        ):
            try:
                llm_results = pass3_llm(
                    candidates,
                    system_prompt,
                    provider,
                    preview_chars,
                    max_tokens=get_max_tokens(settings, provider),
                )
                logger.event("pass", n=3, count=len(candidates), status="ok")
            except Exception as exc:
                con.print(f"[yellow]Warning:[/yellow] LLM review failed: {exc}")
                logger.error(f"pass3 LLM failed: {exc}")
                llm_results = []

        result_by_gid = {r.get("group_id"): r for r in llm_results}

        for i, (note_a, note_b, score) in enumerate(candidates):
            result = result_by_gid.get(i + 1, {})
            if not result.get("is_duplicate", False):
                continue
            resolution = result.get("resolution", "review")
            group: dict = {
                "duplicate_type": "near_duplicate",
                "similarity_score": round(score / 100, 2),
                "resolution": resolution,
                "notes": [
                    _note_summary(note_a, preview_chars),
                    _note_summary(note_b, preview_chars),
                ],
            }
            if resolution == "delete":
                group["keep_id"] = result.get("keep_id")
                group["delete_ids"] = result.get("delete_ids", [])
                group["keep_reason"] = result.get("keep_reason")
                group["review_note"] = None
            else:
                group["keep_id"] = None
                group["delete_ids"] = []
                group["keep_reason"] = None
                group["review_note"] = result.get(
                    "review_note",
                    "Both contain unique content — merge manually in Apple Notes.",
                )
            llm_groups.append(group)

    all_groups = []
    for gid, g in enumerate(exact_groups + llm_groups, start=1):
        g["group_id"] = gid
        all_groups.append(g)

    recommended_delete = sum(1 for g in all_groups if g["resolution"] == "delete")
    needs_review_count = sum(1 for g in all_groups if g["resolution"] == "review")

    summary: dict[str, object] = {
        "total_groups": len(all_groups),
        "exact_duplicates": len(exact_groups),
        "near_duplicates": len(llm_groups),
        "llm_reviewed": len(candidates),
        "recommended_delete": recommended_delete,
        "needs_review": needs_review_count,
    }

    DEDUP_PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = DEDUP_PROPOSALS_DIR / f"dedup-{date_str}.json"

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_export": str(export_path),
        "source_proposal": source_proposal,
        "summary": summary,
        "groups": all_groups,
    }
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    con.print(f"\n[green]Done.[/green] Dedup proposal written to [bold]{output_path}[/bold]")
    con.print(f"  Total groups:       {summary['total_groups']}")
    con.print(f"  Exact duplicates:   {summary['exact_duplicates']}")
    con.print(f"  Near duplicates:    {summary['near_duplicates']}")
    con.print(f"  Recommended delete: {summary['recommended_delete']}")
    con.print(f"  Needs review:       {summary['needs_review']}")

    log_summary: dict[str, object] = {
        "notes_processed": len(entries),
        "total_groups": summary["total_groups"],
        "exact_duplicates": summary["exact_duplicates"],
        "near_duplicates": summary["near_duplicates"],
        "llm_reviewed": summary["llm_reviewed"],
        "recommended_delete": summary["recommended_delete"],
        "needs_review": summary["needs_review"],
    }
    log_file = logger.finish(
        summary=log_summary,
        dry_run=False,
        params={"export_file": str(export_path), "source_proposal": source_proposal},
    )
    if json_output:
        emit_result("dedup", output_file=output_path, log_file=log_file, summary=log_summary)
