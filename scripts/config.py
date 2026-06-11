"""Shared configuration loading for all manage-apple-notes scripts."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
EXPORTS_DIR = REPO_ROOT / "data" / "exports"


def _load_yaml(local_path: Path, example_path: Path) -> dict:
    for path in (local_path, example_path):
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f) or {}
    return {}


def load_settings() -> dict:
    local = CONFIG_DIR / "settings.local.yaml"
    example = CONFIG_DIR / "settings.example.yaml"
    if not local.exists():
        print(
            "Warning: config/settings.local.yaml not found — using example defaults.\n"
            "  To configure your LLM provider and preferences:\n"
            "  cp config/settings.example.yaml config/settings.local.yaml",
            file=sys.stderr,
        )
    return _load_yaml(local, example)


def load_taxonomy() -> dict:
    return _load_yaml(
        CONFIG_DIR / "taxonomy.local.yaml",
        CONFIG_DIR / "taxonomy.example.yaml",
    )


def local_taxonomy_exists() -> bool:
    """Return True if config/taxonomy.local.yaml is present."""
    return (CONFIG_DIR / "taxonomy.local.yaml").exists()


def reorganization_mode(settings: dict | None) -> str:
    """Read reorganization_mode from settings, defaulting to 'standard'."""
    return str((settings or {}).get("reorganization_mode") or "standard")


def find_latest_export() -> Path:
    files = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No export files found in {EXPORTS_DIR}. Run 'uv run notes export' first."
        )
    return files[0]


def export_age_hours(export_path: Path) -> float:
    """Return age of export_path in fractional hours based on file mtime."""
    mtime = datetime.fromtimestamp(export_path.stat().st_mtime, tz=UTC)
    return (datetime.now(UTC) - mtime).total_seconds() / 3600


_SETTINGS_EXAMPLE = CONFIG_DIR / "settings.example.yaml"

# Built-in defaults for the nine standard taxonomy roles.
# Any key a user defines in their taxonomy.yaml works regardless of whether it appears here;
# these entries supply description / semantic flags when the user has not overridden them.
_BUILTIN_CATEGORY_META: dict[str, dict] = {
    "inbox": {"description": "temporary capture", "transit": True},
    "fleeting": {"description": "quick, short-lived thoughts", "transit": True},
    "literature": {"description": "notes tied to a specific source (book, article, talk)"},
    "permanent": {"description": "refined, evergreen concepts in your own words"},
    "projects": {"description": "notes tied to active projects"},
    "areas": {"description": "ongoing responsibilities"},
    "resources": {"description": "reference material and collections"},
    "archive": {
        "description": "inactive, completed, or outdated notes",
        "exclude_from_classify": True,
        "exclude_from_discover": True,
    },
    "review": {
        "description": "use when classification is genuinely unclear",
        "catchall": True,
    },
}


def get_category_meta(settings: dict) -> dict[str, dict]:
    """Return resolved per-category metadata keyed by taxonomy role name.

    Resolution order (later wins):
      1. Built-in defaults for the nine standard roles
      2. settings categories: block — adds new keys and overrides built-ins
      3. Legacy threshold keys (inbox_stale_days etc.) for backward compat

    Supported flags per category:
      description            str   — sent to the LLM alongside the folder name
      transit                bool  — conservative mode: notes here may be freely moved
      stale_days             int   — audit: flag notes not modified within this many days
      active_days            int   — audit: flag notes not modified FOR this many days
      exclude_from_classify  bool  — skip notes in this folder during notes classify
      exclude_from_discover  bool  — skip notes in this folder during notes discover
      catchall               bool  — route unclassifiable notes here
    """
    thresholds = settings.get("thresholds", {})
    meta: dict[str, dict] = {k: dict(v) for k, v in _BUILTIN_CATEGORY_META.items()}

    for key, cfg in (settings.get("categories") or {}).items():
        meta.setdefault(key, {}).update(cfg or {})

    # Backward compat: legacy threshold keys populate the new per-category flags
    if "inbox_stale_days" in thresholds:
        meta.setdefault("inbox", {})["stale_days"] = int(thresholds["inbox_stale_days"])
    if "fleeting_stale_days" in thresholds:
        meta.setdefault("fleeting", {})["stale_days"] = int(thresholds["fleeting_stale_days"])
    if "inactive_project_days" in thresholds:
        meta.setdefault("projects", {})["active_days"] = int(thresholds["inactive_project_days"])

    return meta


def get_llm_config(settings: dict) -> dict:
    """Resolve the active LLM config by merging provider defaults with user overrides.

    Resolution order (later wins):
      1. provider block from llm_providers (loaded settings if present, else example.yaml)
      2. llm_overrides from settings
    The returned dict always contains a "provider" key.
    """
    if "llm" in settings and "llm_provider" not in settings:
        raise SystemExit(
            "settings.local.yaml uses the old 'llm:' format.\n"
            'Replace it with:\n  llm_provider: "<name>"\n'
            "See config/settings.example.yaml for the new structure."
        )

    provider_name = str(settings.get("llm_provider") or "anthropic")

    # Use llm_providers from loaded settings if present (user may have customised it);
    # fall back to example.yaml so settings.local.yaml only needs llm_provider.
    providers = settings.get("llm_providers")
    if providers is None:
        try:
            with open(_SETTINGS_EXAMPLE) as f:
                example = yaml.safe_load(f) or {}
            providers = example.get("llm_providers", {})
        except OSError:
            providers = {}

    provider_defaults = dict((providers or {}).get(provider_name) or {})
    overrides = dict(settings.get("llm_overrides") or {})

    return {**provider_defaults, "provider": provider_name, **overrides}
