"""Shared configuration loading for all manage-apple-notes scripts."""

from __future__ import annotations

import sys
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


_SETTINGS_EXAMPLE = CONFIG_DIR / "settings.example.yaml"


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
