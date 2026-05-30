"""Shared configuration loading for all manage-apple-notes scripts."""

from __future__ import annotations

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
        raise FileNotFoundError(
            f"No export files found in {EXPORTS_DIR}. Run 'uv run notes export' first."
        )
    return files[0]
