"""Shared folder path utilities for multi-level taxonomy handling."""

from __future__ import annotations

APPLE_NOTES_MAX_DEPTH = 5


def enumerate_paths(entry: dict | str, parent: str = "") -> list[str]:
    """Recursively collect every folder path defined under a taxonomy entry.

    Handles top-level category dicts (with a 'folder' key), subfolder dicts
    (with a 'name' key), and plain string leaves. Returns a flat list of all
    paths from root to every leaf, in depth-first order.
    """
    if isinstance(entry, str):
        name = entry.strip()
        if not name:
            return []
        return [f"{parent}/{name}" if parent else name]

    name = (entry.get("folder") or entry.get("name") or "").strip()
    if not name:
        return []

    full = f"{parent}/{name}" if parent else name
    paths = [full]
    for child in entry.get("subfolders") or []:
        paths.extend(enumerate_paths(child, full))
    return paths


def path_depth(path: str) -> int:
    """Return the number of components in a slash-delimited path."""
    return len(path.split("/")) if path else 0


def path_components(path: str) -> list[str]:
    """Split a path into its component folder names."""
    return path.split("/") if path else []


def max_taxonomy_depth(taxonomy: dict) -> int:
    """Return the deepest path depth currently present across all categories."""
    fn = taxonomy.get("forever_notes", {})
    depths = [path_depth(p) for entry in fn.values() for p in enumerate_paths(entry)]
    return max(depths) if depths else 1


def clamp_path(path: str, max_depth: int) -> str:
    """Truncate a path to at most max_depth components."""
    if not path:
        return path
    return "/".join(path.split("/")[:max_depth])


def effective_max_depth(settings: dict | None) -> int:
    """Read thresholds.max_folder_depth from settings, clamped to APPLE_NOTES_MAX_DEPTH."""
    if not settings:
        return 3
    raw = (settings.get("thresholds") or {}).get("max_folder_depth", 3)
    return min(int(raw), APPLE_NOTES_MAX_DEPTH)


def nesting_mode(settings: dict | None) -> str:
    """Read folder_nesting from settings, defaulting to 'natural'."""
    if not settings:
        return "natural"
    return str(settings.get("folder_nesting") or "natural")
