"""Classify Apple Notes from an export file using Claude."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import yaml
from rich.console import Console
from rich.progress import track

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
        raise FileNotFoundError(f"No export files found in {EXPORTS_DIR}. Run export-notes.applescript first.")
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


def inject_taxonomy(system_prompt: str, taxonomy: dict) -> str:
    fn = taxonomy.get("forever_notes", {})
    replacements = {
        "{INBOX}": fn.get("inbox", "[INBOX]"),
        "{FLEETING}": fn.get("fleeting", "[FLEETING]"),
        "{LITERATURE}": fn.get("literature", "[LITERATURE]"),
        "{PERMANENT}": fn.get("permanent", "[PERMANENT]"),
        "{PROJECTS}": fn.get("projects", "[PROJECTS]"),
        "{AREAS}": fn.get("areas", "[AREAS]"),
        "{RESOURCES}": fn.get("resources", "[RESOURCES]"),
        "{ARCHIVE}": fn.get("archive", "[ARCHIVE]"),
        "{REVIEW}": fn.get("review", "[REVIEW]"),
    }
    for placeholder, value in replacements.items():
        system_prompt = system_prompt.replace(placeholder, value)
    return system_prompt


def _extract_json_array(text: str) -> list:
    """Extract a JSON array from a Claude response that may include prose or fences."""
    # Strip ```json ... ``` fences if present
    if "```" in text:
        start = text.find("[", text.find("```"))
    else:
        start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in response:\n{text[:300]}")
    return json.loads(text[start:end])


def classify_batch(
    client: anthropic.Anthropic,
    notes_batch: list[dict],
    system_prompt: str,
    settings: dict,
) -> list[dict]:
    model = settings.get("claude", {}).get("model", "claude-opus-4-6")
    max_body = settings.get("export", {}).get("max_body_chars", 2000)

    batch_payload = [
        {
            "id": n["id"],
            "title": n.get("title", ""),
            "body": n.get("body", "")[:max_body],
            "current_folder": n.get("folder", ""),
        }
        for n in notes_batch
    ]

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": json.dumps(batch_payload, indent=2, ensure_ascii=False),
            }
        ],
    )

    return _extract_json_array(response.content[0].text)


def price_per_million(model: str) -> float:
    for prefix, price in _PRICE_PER_M.items():
        if model.startswith(prefix):
            return price
    return 15.0  # conservative fallback


def run_classify(export_file: str | None, dry_run: bool) -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt_template = load_prompt_template()
    system_prompt = inject_taxonomy(system_prompt_template, taxonomy)

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

    batch_size = settings.get("claude", {}).get("batch_size", 20)
    model = settings.get("claude", {}).get("model", "claude-opus-4-6")
    batches = [notes[i : i + batch_size] for i in range(0, len(notes), batch_size)]

    if dry_run:
        est_tokens_per_note = 700  # ~700 input tokens per note (title + truncated body)
        est_system_tokens = 1500   # system prompt, cached after first batch
        est_total_tokens = len(notes) * est_tokens_per_note + len(batches) * est_system_tokens
        est_tokens_per_batch = batch_size * est_tokens_per_note + est_system_tokens
        est_cost = (est_total_tokens / 1_000_000) * price_per_million(model)
        date_str = datetime.now().strftime("%Y-%m-%d")

        console.print("[bold]Dry run — no API calls will be made.[/bold]\n")
        console.print(f"Export:       {export_path}")
        console.print(f"Notes found:  {len(all_notes)}  ({len(notes)} after filtering)")
        console.print(f"Batches:      {len(batches)}  (batch size: {batch_size})\n")
        console.print(f"Model:        {model}")
        console.print(f"Est. tokens:  ~{est_total_tokens:,}  (~{est_tokens_per_batch:,}/batch)")
        console.print(f"Est. cost:    ~${est_cost:.2f}  (@ ${price_per_million(model):.2f}/M input tokens)")
        console.print(f"\nOutput would be written to: {PROPOSALS_DIR}/proposal-{date_str}.json")
        return

    client = anthropic.Anthropic()
    review_folder = taxonomy.get("forever_notes", {}).get("review", "")

    moves: list[dict] = []
    needs_review: list[dict] = []
    no_change: list[dict] = []
    note_index = {n["id"]: n for n in notes}

    for batch in track(batches, description="Classifying..."):
        results = classify_batch(client, batch, system_prompt, settings)

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
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = PROPOSALS_DIR / f"proposal-{date_str}.json"

    proposal = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
