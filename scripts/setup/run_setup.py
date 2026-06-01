"""Interactive setup wizard — `notes setup` command."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scripts.config import CONFIG_DIR, find_latest_export
from scripts.setup.frameworks import FRAMEWORKS, framework_choices, get_framework
from scripts.setup.scorer import score

con = Console()


# ── Corpus analysis ────────────────────────────────────────────────────────────


def _find_export_optional() -> Path | None:
    try:
        return find_latest_export()
    except FileNotFoundError:
        return None


def analyze_corpus(export_path: Path) -> dict:
    """Extract organizational signals from an export JSON."""
    with open(export_path) as f:
        notes = json.load(f)

    if not notes:
        return {}

    note_count = len(notes)
    folder_count = len({n.get("folder", "") for n in notes if n.get("folder")})

    _TASK_RE = re.compile(r"\bTODO\b|\bWAITING\b|\bnext:\s|\bDONE\b|@[a-zA-Z]|- \[ \]", re.I)
    _XREF_RE = re.compile(r"\[\[[^\]]+\]\]")

    word_counts: list[int] = []
    task_count = 0
    cross_ref_count = 0
    oldest_dt: datetime | None = None

    for note in notes:
        body = note.get("body", "") or ""
        word_counts.append(len(body.split()))
        if _TASK_RE.search(body):
            task_count += 1
        if _XREF_RE.search(body):
            cross_ref_count += 1
        modified_str = note.get("modified", "")
        if modified_str:
            try:
                dt = datetime.fromisoformat(modified_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if oldest_dt is None or dt < oldest_dt:
                    oldest_dt = dt
            except ValueError:
                pass

    avg_word_count = mean(word_counts) if word_counts else 0.0
    now = datetime.now(tz=UTC)
    oldest_note_days = (now - oldest_dt).days if oldest_dt else 0

    return {
        "note_count": note_count,
        "folder_count": folder_count,
        "avg_word_count": avg_word_count,
        "task_keyword_pct": task_count / note_count if note_count else 0.0,
        "cross_ref_pct": cross_ref_count / note_count if note_count else 0.0,
        "oldest_note_days": oldest_note_days,
    }


def _display_corpus_summary(corpus: dict) -> None:
    note_count = corpus["note_count"]
    folder_count = corpus["folder_count"]
    avg_words = corpus["avg_word_count"]
    task_pct = int(corpus["task_keyword_pct"] * 100)
    xref_pct = int(corpus["cross_ref_pct"] * 100)
    oldest_days = corpus["oldest_note_days"]

    if oldest_days >= 365:
        oldest_label = f"{oldest_days // 365} year(s) ago"
    elif oldest_days >= 30:
        oldest_label = f"{oldest_days // 30} month(s) ago"
    else:
        oldest_label = f"{oldest_days} day(s) ago"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")
    table.add_row("Notes found:", str(note_count))
    table.add_row("Folders:", str(folder_count))
    table.add_row("Avg note length:", f"{int(avg_words)} words")
    table.add_row("Task-style notes:", f"{task_pct}%")
    table.add_row("Cross-references:", f"{xref_pct}%")
    table.add_row("Oldest note:", oldest_label)

    con.print(Panel(table, title="Your Notes at a Glance", border_style="blue"))


# ── Dialogue helpers ───────────────────────────────────────────────────────────


def _ask_numbered(question: str, options: list[str]) -> int:
    """Print numbered options and return 1-based selection (loops until valid)."""
    con.print(f"\n[bold]{question}[/bold]")
    for i, opt in enumerate(options, 1):
        con.print(f"  {i}) {opt}")
    while True:
        raw = typer.prompt("\nYour choice")
        try:
            val = int(raw.strip())
            if 1 <= val <= len(options):
                return val
        except ValueError:
            pass
        con.print(f"[red]Please enter a number between 1 and {len(options)}.[/red]")


# ── Folder name collection ─────────────────────────────────────────────────────


def _collect_folder_names(framework_key: str) -> dict[str, str]:
    """Prompt for a folder name for each category in the chosen framework."""
    fw = get_framework(framework_key)
    con.print(
        "\n[bold]Name your folders.[/bold]  Press Enter to accept the default, "
        "or type your preferred name.\n"
    )
    folder_map: dict[str, str] = {}
    for key in fw["category_keys"]:
        default = fw["canonical_names"][key]
        prompt_label = fw["category_prompts"][key]
        name = typer.prompt(f"  {prompt_label}", default=default).strip()
        folder_map[key] = name or default
    return folder_map


def _collect_existing_folders() -> dict[str, str]:
    """For the Existing path: map user's current folders to category keys."""
    mapping_prompts = FRAMEWORKS["EXISTING"]["mapping_prompts"]
    con.print(
        "\n[bold]Let's map your existing folders.[/bold]  "
        "Enter your folder name for each role, or press Enter to skip.\n"
    )
    folder_map: dict[str, str] = {}
    for key, prompt in mapping_prompts.items():
        name = typer.prompt(f"  {prompt}", default="").strip()
        if name:
            folder_map[key] = name
    return folder_map


# ── YAML generation ────────────────────────────────────────────────────────────


def _build_taxonomy_yaml(framework_key: str, folder_map: dict[str, str]) -> str:
    fw = get_framework(framework_key)
    data: dict = {"taxonomy": {}}
    for key in fw["category_keys"]:
        folder_name = folder_map.get(key, "")
        if folder_name:
            data["taxonomy"][key] = {"folder": folder_name}
    header = (
        f"# taxonomy.local.yaml — generated by `notes setup`\n"
        f"# Framework: {fw['full_name'] if framework_key != 'EXISTING' else 'Custom (existing folders)'}\n"
        f"# Edit this file to rename folders or add subfolders.\n\n"
    )
    return header + str(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def _build_existing_taxonomy_yaml(folder_map: dict[str, str]) -> str:
    data: dict = {"taxonomy": {}}
    for key, name in folder_map.items():
        data["taxonomy"][key] = {"folder": name}
    header = (
        "# taxonomy.local.yaml — generated by `notes setup`\n"
        "# Framework: Custom (existing folders)\n"
        "# Edit this file to rename folders or add subfolders.\n\n"
    )
    return header + str(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def _gtd_categories_snippet() -> str:
    """Return YAML snippet for the GTD-specific category keys to add to settings."""
    extra = FRAMEWORKS["GTD"]["extra_categories"]
    return str(
        yaml.dump(
            {"categories": extra}, default_flow_style=False, allow_unicode=True, sort_keys=False
        )
    )


# ── Provider selection ─────────────────────────────────────────────────────────


def _write_provider_to_settings(provider: str, dry_run: bool) -> None:
    settings_path = CONFIG_DIR / "settings.local.yaml"
    if not settings_path.exists():
        return
    content = settings_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^llm_provider:.*$",
        f'llm_provider: "{provider}"',
        content,
        flags=re.MULTILINE,
        count=1,
    )
    if dry_run:
        con.print(f'  [dim]Would set llm_provider: "{provider}" in settings.local.yaml[/dim]')
        return
    settings_path.write_text(new_content, encoding="utf-8")
    con.print(f'  Set [green]llm_provider: "{provider}"[/green] in settings.local.yaml')


def _write_env_line(key: str, value: str, dry_run: bool) -> None:
    """Append KEY=value to .env if the key is not already present."""
    env_path = CONFIG_DIR.parent / ".env"
    if dry_run:
        con.print(f"  [dim]Would write {key}=... to .env (not written)[/dim]")
        return
    line = f"{key}={value}\n"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        if re.search(rf"^{re.escape(key)}=", content, flags=re.MULTILINE):
            con.print(f"  [dim]{key} already set in .env — not overwritten[/dim]")
            return
        env_path.write_text(content.rstrip("\n") + "\n" + line, encoding="utf-8")
    else:
        env_path.write_text(line, encoding="utf-8")
    con.print(f"  Wrote [green]{key}[/green] to .env")


def _select_provider(dry_run: bool) -> bool:
    """Ask which LLM provider to use and write config. Returns True if a provider was selected."""
    con.print("\n[bold]LLM provider[/bold]")
    choice = _ask_numbered(
        "Which LLM provider do you want to use?",
        [
            "Apple Intelligence — on-device, free, requires macOS 26 + Apple Silicon",
            "Anthropic API — cloud-based, fast, requires an API key",
            "Ollama (local) — open-weight models, self-hosted, no API key needed",
            "AWS-Ollama — cloud GPU via SSH tunnel, self-hosted",
            "Skip — I'll configure this manually in config/settings.local.yaml",
        ],
    )

    if choice == 1:
        _write_provider_to_settings("apple", dry_run)
        con.print(
            "\n[dim]Apple Intelligence requires the Swift bridge to be compiled first:\n"
            "  make -C swift/apple-llm build\n"
            "See GUIDE.md → Apple Intelligence provider for prerequisites.[/dim]"
        )
        return True
    elif choice == 2:
        _write_provider_to_settings("anthropic", dry_run)
        api_key = typer.prompt(
            "\n  Anthropic API key (leave blank to add to .env manually)",
            default="",
            hide_input=True,
        ).strip()
        if api_key:
            _write_env_line("ANTHROPIC_API_KEY", api_key, dry_run)
        else:
            con.print(
                "  [dim]Add ANTHROPIC_API_KEY=sk-ant-... to .env before running classify.[/dim]"
            )
        return True
    elif choice == 3:
        _write_provider_to_settings("ollama", dry_run)
        url = typer.prompt(
            "\n  Ollama base URL",
            default="http://localhost:11434",
        ).strip()
        if url and url != "http://localhost:11434":
            _write_env_line("OLLAMA_BASE_URL", url, dry_run)
        return True
    elif choice == 4:
        _write_provider_to_settings("aws-ollama", dry_run)
        con.print(
            "\n[dim]AWS-Ollama requires deploying the EC2 stack first.\n"
            "See docs/aws-infrastructure.md for full prerequisites and setup steps.[/dim]"
        )
        return True
    else:
        return False


# ── File writing ───────────────────────────────────────────────────────────────


def _write_taxonomy(taxonomy_yaml: str, dry_run: bool) -> None:
    taxonomy_path = CONFIG_DIR / "taxonomy.local.yaml"
    if dry_run:
        con.print("\n[dim]── taxonomy.local.yaml (dry run — not written) ──[/dim]")
        con.print(taxonomy_yaml)
        return
    if taxonomy_path.exists():
        bak = taxonomy_path.with_suffix(".yaml.bak")
        shutil.copy2(taxonomy_path, bak)
        con.print(f"  Backed up existing taxonomy → [dim]{bak.name}[/dim]")
    taxonomy_path.write_text(taxonomy_yaml, encoding="utf-8")
    con.print(f"  Wrote [green]{taxonomy_path.relative_to(taxonomy_path.parent.parent)}[/green]")


def _ensure_settings(dry_run: bool) -> bool:
    """Copy settings.example.yaml to settings.local.yaml if not present.
    Returns True if the file was created (or would be created) during this call."""
    settings_path = CONFIG_DIR / "settings.local.yaml"
    example_path = CONFIG_DIR / "settings.example.yaml"
    if settings_path.exists():
        return False
    if dry_run:
        con.print(
            "  [dim]settings.local.yaml not found — would copy from settings.example.yaml[/dim]"
        )
        return True
    shutil.copy2(example_path, settings_path)
    con.print("  Copied [green]settings.local.yaml[/green] from settings.example.yaml")
    return True


# ── Main entrypoint ────────────────────────────────────────────────────────────


def run_setup(dry_run: bool = False, no_corpus: bool = False) -> None:
    con.print(
        Panel(
            "[bold]notes setup[/bold]\n\n"
            "This wizard picks a note organization framework for you, collects your "
            "folder names, and writes [cyan]config/taxonomy.local.yaml[/cyan].\n\n"
            "It takes about 2 minutes.",
            title="Welcome",
            border_style="green",
        )
    )

    # ── Phase 1: Corpus analysis ───────────────────────────────────────────────
    corpus: dict | None = None
    if not no_corpus:
        export_path = _find_export_optional()
        if export_path:
            with con.status("Analyzing notes…", spinner="dots"):
                corpus = analyze_corpus(export_path)
            if corpus:
                _display_corpus_summary(corpus)
        else:
            con.print(
                "[dim]No export found — run `uv run notes export` first to include corpus "
                "signals in the recommendation. Continuing with questions only.[/dim]\n"
            )

    # ── Phase 2: Dialogue ──────────────────────────────────────────────────────
    q1 = _ask_numbered(
        "What matters most to you going forward?",
        [
            "Get on top of tasks and commitments — I need clarity on what to do next",
            "Find anything instantly — organisation and retrieval is the main problem",
            "Develop ideas over time — I want my notes to think with me",
            "My current system mostly works — I want small improvements, not an overhaul",
        ],
    )

    q2: int | None = None
    q3: int | None = None

    if q1 != 4:
        q2 = _ask_numbered(
            "How much time are you willing to spend maintaining your note system each week?",
            [
                "As little as possible — it should mostly run itself",
                "10–15 minutes — a light weekly tidy",
                "30+ minutes — I'm willing to invest if the payoff is there",
            ],
        )

        q3 = _ask_numbered(
            "Which best describes how your work or thinking actually unfolds?",
            [
                "Deadline-driven — I'm juggling projects with clear finish lines",
                "Ongoing — I maintain areas of responsibility that never really end",
                "Cumulative — my best ideas build on older ones over months or years",
            ],
        )

    # ── Phase 3: Score ─────────────────────────────────────────────────────────
    recommendation = score(corpus, q1, q2, q3)
    winner = recommendation["winner"]

    # ── Phase 4: Display recommendation ───────────────────────────────────────
    if winner == "EXISTING":
        con.print(
            Panel(
                recommendation["rationale"],
                title="Recommendation: Use Your Existing System",
                border_style="yellow",
            )
        )
    else:
        fw = get_framework(winner)
        confidence = recommendation["confidence"]

        confidence_color = {"high": "green", "moderate": "yellow", "low": "dim"}.get(
            confidence, "white"
        )
        body = (
            f"[bold]{fw['full_name']}[/bold]  "
            f"[{confidence_color}](confidence: {confidence})[/{confidence_color}]\n\n"
            f"{recommendation['rationale']}\n\n"
            f"[dim]Folders:[/dim]  {fw['folder_preview']}\n"
            f"[dim]Maintenance:[/dim]  {fw['maintenance']}\n"
            f"[dim]Best for:[/dim]  {fw['best_for']}"
        )
        con.print(Panel(body, title="Recommendation", border_style="green"))

    # Allow the user to override the recommendation
    choices = framework_choices()
    if winner == "EXISTING":
        accept = typer.confirm("\nProceed with mapping your existing folders?", default=True)
        if not accept:
            selected = _ask_numbered("Which framework would you like instead?", choices[:3])
            framework_map = ["PARA", "GTD", "ZETTELKASTEN"]
            winner = framework_map[selected - 1]
        else:
            winner = "EXISTING"
    else:
        fw = get_framework(winner)
        accept = typer.confirm(f"\nUse {fw['name']}?", default=True)
        if not accept:
            selected = _ask_numbered("Which framework would you prefer?", choices)
            framework_map = ["PARA", "GTD", "ZETTELKASTEN", "EXISTING"]
            winner = framework_map[selected - 1]

    # ── Phase 5: Collect folder names ─────────────────────────────────────────
    if winner == "EXISTING":
        folder_map = _collect_existing_folders()
        taxonomy_yaml = _build_existing_taxonomy_yaml(folder_map)
    else:
        folder_map = _collect_folder_names(winner)
        taxonomy_yaml = _build_taxonomy_yaml(winner, folder_map)

    # ── Phase 6: Write config files ────────────────────────────────────────────
    con.print("\n[bold]Writing config files…[/bold]")
    _write_taxonomy(taxonomy_yaml, dry_run)
    settings_created = _ensure_settings(dry_run)

    # GTD: show snippet to add manually (avoids rewriting a potentially customised settings file)
    if winner == "GTD":
        snippet = _gtd_categories_snippet()
        con.print(
            Panel(
                "GTD uses category keys not in the built-in defaults "
                "([cyan]next_actions[/cyan], [cyan]waiting_for[/cyan], etc.).\n\n"
                "Add the following block to the [cyan]categories:[/cyan] section of "
                "[cyan]config/settings.local.yaml[/cyan] so the classifier and audit "
                "use the correct descriptions:\n\n"
                f"[dim]{snippet}[/dim]",
                title="Action needed: settings.local.yaml",
                border_style="yellow",
            )
        )

    # ── Phase 7: LLM provider selection ───────────────────────────────────────
    provider_configured = False
    if settings_created:
        provider_configured = _select_provider(dry_run)

    # ── Next steps ─────────────────────────────────────────────────────────────
    next_steps: list[str] = []
    if not provider_configured:
        next_steps.append("Set your LLM provider in config/settings.local.yaml  (see GUIDE.md)")
    if corpus is None:
        next_steps.append("uv run notes export    — pull notes from Apple Notes")
    next_steps += [
        "uv run notes discover  — map thematic clusters → data/theme-maps/",
        "uv run notes classify  — AI classification → proposal",
        "uv run notes review    — review the proposal (place needs-review items)",
        "uv run notes move      — apply the approved proposal",
    ]
    if winner == "EXISTING":
        suggestions = FRAMEWORKS["EXISTING"]["improvement_suggestions"]
        next_steps += [
            "",
            "Lightweight improvements to consider:",
            *[f"  • {s}" for s in suggestions],
        ]

    steps_text = "\n".join(next_steps)
    con.print(
        Panel(
            steps_text,
            title="Next Steps",
            border_style="blue",
        )
    )
