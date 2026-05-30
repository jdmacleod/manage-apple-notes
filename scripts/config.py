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


def find_latest_export() -> Path:
    files = sorted(EXPORTS_DIR.glob("notes-*.json"), reverse=True)
    if not files:
        raise FileNotFoundError(
            f"No export files found in {EXPORTS_DIR}. Run 'uv run notes export' first."
        )
    return files[0]
