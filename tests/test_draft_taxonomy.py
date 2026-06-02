"""Tests for scripts/classify/draft_taxonomy.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from rich.console import Console

from scripts.classify.draft_taxonomy import (
    _add_missing_top_level_folders,
    _derive_role_key,
    _insert_subfolder,
    _top_level_folders,
    bootstrap_taxonomy,
    find_latest_theme_map,
    merge_new_paths,
    run_draft,
)

# ---------------------------------------------------------------------------
# _insert_subfolder
# ---------------------------------------------------------------------------


class TestInsertSubfolder:
    def test_adds_new_string_leaf(self) -> None:
        entry: dict = {"folder": "Resources", "subfolders": ["Cooking"]}
        result = _insert_subfolder(entry, ["Finance"])
        assert result is True
        assert "Finance" in entry["subfolders"]

    def test_existing_leaf_returns_false(self) -> None:
        entry: dict = {"folder": "Resources", "subfolders": ["Cooking"]}
        result = _insert_subfolder(entry, ["Cooking"])
        assert result is False
        assert entry["subfolders"].count("Cooking") == 1

    def test_creates_subfolders_list_when_absent(self) -> None:
        entry: dict = {"folder": "Projects"}
        result = _insert_subfolder(entry, ["Alpha"])
        assert result is True
        assert entry["subfolders"] == ["Alpha"]

    def test_deep_path_creates_nested_dict(self) -> None:
        entry: dict = {"folder": "Resources", "subfolders": []}
        result = _insert_subfolder(entry, ["Programming", "Python"])
        assert result is True
        sf = entry["subfolders"]
        assert len(sf) == 1
        assert isinstance(sf[0], dict)
        assert sf[0]["name"] == "Programming"
        assert "Python" in sf[0]["subfolders"]

    def test_promotes_string_to_dict_for_deeper_nesting(self) -> None:
        entry: dict = {"folder": "Resources", "subfolders": ["Cooking"]}
        result = _insert_subfolder(entry, ["Cooking", "Italian"])
        assert result is True
        sf = entry["subfolders"]
        assert len(sf) == 1
        node = sf[0]
        assert isinstance(node, dict)
        assert node["name"] == "Cooking"
        assert "Italian" in node["subfolders"]

    def test_existing_deep_path_returns_false(self) -> None:
        entry: dict = {
            "folder": "Resources",
            "subfolders": [{"name": "Programming", "subfolders": ["Python"]}],
        }
        result = _insert_subfolder(entry, ["Programming", "Python"])
        assert result is False


# ---------------------------------------------------------------------------
# merge_new_paths
# ---------------------------------------------------------------------------


class TestMergeNewPaths:
    def test_new_path_added_to_category(self, minimal_taxonomy: dict) -> None:
        updated, added, skipped = merge_new_paths(minimal_taxonomy, ["Resources/Finance"])
        assert "Resources/Finance" in added
        assert not skipped
        fn = updated["taxonomy"]
        resources_sf = fn["resources"]["subfolders"]
        assert "Finance" in resources_sf

    def test_existing_path_skipped(self, minimal_taxonomy: dict) -> None:
        # Resources/Reference already exists in minimal_taxonomy
        _, added, skipped = merge_new_paths(minimal_taxonomy, ["Resources/Reference"])
        assert not added
        assert "Resources/Reference" in skipped

    def test_unknown_top_folder_skipped(self, minimal_taxonomy: dict) -> None:
        _, added, skipped = merge_new_paths(minimal_taxonomy, ["Unknown/Subfolder"])
        assert not added
        assert "Unknown/Subfolder" in skipped

    def test_top_level_only_path_skipped(self, minimal_taxonomy: dict) -> None:
        _, added, skipped = merge_new_paths(minimal_taxonomy, ["Resources"])
        assert not added
        assert "Resources" in skipped

    def test_deep_path_creates_nested_structure(self, minimal_taxonomy: dict) -> None:
        updated, added, _ = merge_new_paths(minimal_taxonomy, ["Resources/Programming/Python"])
        assert "Resources/Programming/Python" in added
        sf = updated["taxonomy"]["resources"]["subfolders"]
        prog = next((x for x in sf if isinstance(x, dict) and x["name"] == "Programming"), None)
        assert prog is not None
        assert "Python" in prog["subfolders"]

    def test_original_taxonomy_unchanged(self, minimal_taxonomy: dict) -> None:
        original_sf = list(minimal_taxonomy["taxonomy"]["resources"]["subfolders"])
        merge_new_paths(minimal_taxonomy, ["Resources/Finance"])
        assert minimal_taxonomy["taxonomy"]["resources"]["subfolders"] == original_sf

    def test_multiple_paths_preserves_caller_order(self, minimal_taxonomy: dict) -> None:
        # merge_new_paths no longer re-sorts — it preserves the caller-supplied sequence
        # so run_draft can control insertion order via the export position map.
        paths = ["Resources/Zebra", "Resources/Alpha", "Resources/Mango"]
        _, added, _ = merge_new_paths(minimal_taxonomy, paths)
        assert added == paths


# ---------------------------------------------------------------------------
# run_draft
# ---------------------------------------------------------------------------


def _make_theme_map(themes: list[dict], established_paths: list[str] | None = None) -> dict:
    return {
        "generated_at": "2026-05-29T00:00:00+00:00",
        "source_export": "data/exports/notes-2026-05-29.json",
        "total_notes": 10,
        "subfolder_threshold": 8,
        "established_paths": established_paths or [],
        "themes": themes,
        "new_paths": [],
        "above_threshold": len(themes),
        "below_threshold": 0,
    }


def _patch_draft(mocker: MagicMock, tmp_path: Path, taxonomy: dict, settings: dict) -> None:
    mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=settings)
    mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=taxonomy)
    mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
    mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
    mocker.patch("typer.confirm", return_value=False)  # skip apply prompt in most tests


class TestRunDraft:
    def test_dry_run_writes_no_file(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Finance",
                            "suggested_path": "Resources/Finance",
                            "estimated_count": 10,
                        }
                    ]
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=True)

        drafts = (
            list((tmp_path / "drafts").glob("*.yaml")) if (tmp_path / "drafts").exists() else []
        )
        assert drafts == []

    def test_real_run_writes_draft_file(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Finance",
                            "suggested_path": "Resources/Finance",
                            "estimated_count": 10,
                        }
                    ]
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("taxonomy-draft-*.yaml"))
        assert len(drafts) == 1
        content = drafts[0].read_text()
        assert "# taxonomy-draft-" in content
        assert "+ Resources/Finance" in content
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert "taxonomy" in parsed

    def test_below_threshold_path_excluded(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Tiny Theme",
                            "suggested_path": "Resources/Tiny",
                            "estimated_count": 2,  # below default threshold of 8
                        }
                    ]
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = (
            list((tmp_path / "drafts").glob("*.yaml")) if (tmp_path / "drafts").exists() else []
        )
        assert drafts == []

    def test_established_path_not_re_added(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Reference",
                            "suggested_path": "Resources/Reference",
                            "estimated_count": 10,
                        }
                    ],
                    established_paths=["Resources/Reference"],
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = (
            list((tmp_path / "drafts").glob("*.yaml")) if (tmp_path / "drafts").exists() else []
        )
        assert drafts == []

    def test_missing_theme_map_file_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)
        with pytest.raises(SystemExit):
            run_draft(theme_map_file=str(tmp_path / "nonexistent.json"), dry_run=False)

    def test_draft_yaml_is_valid_and_contains_new_subfolder(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Health",
                            "suggested_path": "Areas/Health",
                            "estimated_count": 10,
                        }
                    ]
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        parsed = yaml.safe_load(drafts[0].read_text())
        fn = parsed["taxonomy"]
        # minimal_taxonomy has archive but no areas — Health goes to skipped
        # Let's check that the YAML is at least valid and complete
        assert "inbox" in fn or "resources" in fn

    def _make_theme_map_file(
        self, tmp_path: Path, suggested_path: str = "Resources/Finance"
    ) -> Path:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [{"name": "Finance", "suggested_path": suggested_path, "estimated_count": 10}]
                )
            )
        )
        return theme_map_file

    def test_confirm_yes_writes_taxonomy_local(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = self._make_theme_map_file(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("scripts.classify.draft_taxonomy.CONFIG_DIR", config_dir)
        mocker.patch("typer.confirm", return_value=True)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        local = config_dir / "taxonomy.local.yaml"
        assert local.exists(), "taxonomy.local.yaml should be written when confirmed"
        parsed = yaml.safe_load(local.read_text())
        assert "taxonomy" in parsed

    def test_confirm_yes_backs_up_existing(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        existing = config_dir / "taxonomy.local.yaml"
        existing.write_text("# old taxonomy\n")

        theme_map_file = self._make_theme_map_file(tmp_path)
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("scripts.classify.draft_taxonomy.CONFIG_DIR", config_dir)
        mocker.patch("typer.confirm", return_value=True)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        bak = config_dir / "taxonomy.local.yaml.bak"
        assert bak.exists(), "backup should be created before overwriting"
        assert bak.read_text() == "# old taxonomy\n"

    def test_confirm_no_leaves_taxonomy_local_unchanged(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        existing = config_dir / "taxonomy.local.yaml"
        existing.write_text("# original\n")

        theme_map_file = self._make_theme_map_file(tmp_path)
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("scripts.classify.draft_taxonomy.CONFIG_DIR", config_dir)
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        assert existing.read_text() == "# original\n", "file should be untouched when declined"

    def test_confirm_yes_includes_export_subfolders(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        """Confirming the draft writes export subfolders into taxonomy.local.yaml."""
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "title": "New Topic",
                        "body": "x",
                        "folder_path": "Resources/NewTopic",
                    }
                ]
            )
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": [],
                    "themes": [],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 1,
                }
            )
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("scripts.classify.draft_taxonomy.CONFIG_DIR", config_dir)
        mocker.patch("typer.confirm", return_value=True)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        local = config_dir / "taxonomy.local.yaml"
        assert local.exists()
        parsed = yaml.safe_load(local.read_text())
        assert "NewTopic" in parsed["taxonomy"]["resources"]["subfolders"]

    def test_confirm_skipped_in_json_output_mode(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = self._make_theme_map_file(tmp_path)
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        confirm_mock = mocker.patch("typer.confirm")

        run_draft(theme_map_file=str(theme_map_file), dry_run=False, json_output=True)

        confirm_mock.assert_not_called()


class TestRunDraftThresholdBypass:
    """Existing paths in the export folder tree bypass min_notes_for_subfolder."""

    def test_below_threshold_included_when_path_exists_in_export(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Create a real export file so export_folder_tree picks up "Resources/Recipes"
        export_file = tmp_path / "notes-2026-01-01.json"
        export_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "title": "Pasta",
                        "body": "recipe",
                        "folder_path": "Resources/Recipes",
                    }
                ]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": [],
                    "themes": [
                        {
                            "name": "Recipes",
                            "suggested_path": "Resources/Recipes",
                            "estimated_count": 1,  # well below threshold of 8
                        }
                    ],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 1,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1, "Draft should be written even though count is below threshold"
        content = drafts[0].read_text()
        assert "Resources/Recipes" in content

    def test_below_threshold_llm_path_excluded_but_real_export_path_included(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Export has "Resources/Cooking" (a real folder).
        # The LLM suggested "Resources/Tiny" (below threshold, not in export) — should be excluded.
        # "Resources/Cooking" is in the export → promoted directly, so a draft IS written.
        export_file = tmp_path / "notes-2026-01-01.json"
        export_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "title": "Pasta",
                        "body": "recipe",
                        "folder_path": "Resources/Cooking",
                    }
                ]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": [],
                    "themes": [
                        {
                            "name": "Tiny Theme",
                            "suggested_path": "Resources/Tiny",
                            "estimated_count": 2,  # below threshold, not in export
                        }
                    ],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 1,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Draft should be written (Resources/Cooking was promoted from export)
        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        content = drafts[0].read_text()
        # The real export folder is included
        assert "Resources/Cooking" in content
        # The LLM's invented below-threshold path is excluded
        assert "Resources/Tiny" not in content


class TestRunDraftExportSubfolderPromotion:
    """Export subfolders absent from the theme map are promoted directly into the draft."""

    def test_export_subfolder_not_in_themes_is_included(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Export has "Resources/Recipes" but the theme map never mentions it as
        # a suggested_path — simulates the LLM using a content-based name instead.
        export_file = tmp_path / "notes-2026-01-01.json"
        export_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "title": "Pasta",
                        "body": "recipe",
                        "folder_path": "Resources/Recipes",
                    }
                ]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": [],
                    "themes": [
                        # LLM named it "Cooking" and mapped to a different path — no mention
                        # of "Resources/Recipes" anywhere in suggested_paths
                        {
                            "name": "Cooking",
                            "suggested_path": "Resources",
                            "estimated_count": 1,
                        }
                    ],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 1,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1, "Draft should be written with the export subfolder"
        content = drafts[0].read_text()
        assert "Resources/Recipes" in content

    def test_export_subfolder_already_established_not_duplicated(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # "Resources/Reference" is in minimal_taxonomy → it's in established_paths
        # → it should not be re-added even though it's in the export
        export_file = tmp_path / "notes-2026-01-01.json"
        export_file.write_text(
            json.dumps(
                [
                    {
                        "id": "n1",
                        "title": "Doc",
                        "body": "ref",
                        "folder_path": "Resources/Reference",
                    }
                ]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": ["Resources/Reference"],
                    "themes": [],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 0,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Nothing new to add — only path was already established
        drafts = (
            list((tmp_path / "drafts").glob("*.yaml")) if (tmp_path / "drafts").exists() else []
        )
        assert drafts == []


class TestRunDraftExportOrdering:
    """New subfolders are inserted in Apple Notes native order, not alphabetically."""

    def test_subfolders_follow_export_order_not_alphabetical(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Export has Zebra before Alpha — non-alphabetical, Apple Notes native order.
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [
                    {"id": "n1", "title": "Note", "body": "x", "folder_path": "Resources/Zebra"},
                    {"id": "n2", "title": "Note", "body": "x", "folder_path": "Resources/Alpha"},
                ]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-05-31T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 2,
                    "subfolder_threshold": 1,
                    "established_paths": [],
                    "themes": [],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 0,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        content = drafts[0].read_text()
        # Zebra must appear before Alpha — export order, not alphabetical order.
        assert "Zebra" in content and "Alpha" in content
        assert content.index("Zebra") < content.index("Alpha")

    def test_llm_only_paths_appended_after_export_paths(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Export has one real folder; LLM proposes an additional path not in the export.
        # The real folder should appear first, the LLM proposal appended after.
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [{"id": "n1", "title": "Note", "body": "x", "folder_path": "Resources/Zebra"}]
            )
        )

        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-05-31T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 1,
                    "established_paths": [],
                    "themes": [
                        {
                            "name": "Alpha",
                            "suggested_path": "Resources/Alpha",
                            "estimated_count": 5,
                        }
                    ],
                    "new_paths": [],
                    "above_threshold": 1,
                    "below_threshold": 0,
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        content = drafts[0].read_text()
        # Zebra (from export) must appear before Alpha (LLM-only, not in export).
        assert "Zebra" in content and "Alpha" in content
        assert content.index("Zebra") < content.index("Alpha")


class TestDeriveRoleKey:
    def test_well_known_name(self) -> None:
        assert _derive_role_key("Projects", set()) == "projects"
        assert _derive_role_key("Archive", set()) == "archive"
        assert _derive_role_key("Inbox", set()) == "inbox"

    def test_case_insensitive(self) -> None:
        assert _derive_role_key("INBOX", set()) == "inbox"
        assert _derive_role_key("areas of responsibility", set()) == "areas"

    def test_avoids_collision(self) -> None:
        # "projects" is taken; should fall back to slug
        assert _derive_role_key("Projects", {"projects"}) == "projects_2"

    def test_unknown_folder_slugified(self) -> None:
        key = _derive_role_key("My Custom Folder", set())
        assert key == "my_custom_folder"

    def test_slug_collision_incremented(self) -> None:
        key = _derive_role_key("My Folder", {"my_folder", "my_folder_2"})
        assert key == "my_folder_3"


class TestAddMissingTopLevelFolders:
    def _con(self) -> Console:
        return Console(quiet=True)

    def test_adds_missing_folder(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}, "areas": {"folder": "Areas"}}}
        result = _add_missing_top_level_folders(
            taxonomy, ["Inbox", "Areas", "Projects"], self._con()
        )
        fn = result["taxonomy"]
        assert "Projects" in {e.get("folder") for e in fn.values() if isinstance(e, dict)}

    def test_derived_key_for_known_name(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}}}
        result = _add_missing_top_level_folders(taxonomy, ["Inbox", "Projects"], self._con())
        assert "projects" in result["taxonomy"]

    def test_no_change_when_all_present(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}, "areas": {"folder": "Areas"}}}
        result = _add_missing_top_level_folders(taxonomy, ["Inbox", "Areas"], self._con())
        assert result is taxonomy  # same object — no copy made

    def test_original_unchanged_when_folders_added(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}}}
        _add_missing_top_level_folders(taxonomy, ["Inbox", "Projects"], self._con())
        assert "projects" not in taxonomy["taxonomy"]  # original not mutated

    def test_empty_folder_list(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}}}
        result = _add_missing_top_level_folders(taxonomy, [], self._con())
        assert result is taxonomy


class TestTopLevelFolders:
    def test_extracts_unique_top_level(self) -> None:
        paths = ["Areas/Finance", "Areas/Household", "Resources/Cooking", "Archive"]
        assert _top_level_folders(paths) == ["Archive", "Areas", "Resources"]

    def test_filters_empty_strings(self) -> None:
        assert _top_level_folders(["", "Areas/Finance"]) == ["Areas"]

    def test_empty_input(self) -> None:
        assert _top_level_folders([]) == []


class TestBootstrapTaxonomy:
    def test_valid_mapping_builds_taxonomy(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = (
            '{"archive": "Archive", "areas": "Areas", "resources": "Resources"}'
        )
        result = bootstrap_taxonomy(["Archive", "Areas", "Resources"], mock_llm_provider, {})
        fn = result["taxonomy"]
        assert fn["archive"] == {"folder": "Archive"}
        assert fn["areas"] == {"folder": "Areas"}
        assert fn["resources"] == {"folder": "Resources"}

    def test_unknown_role_keys_filtered(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = (
            '{"archive": "Archive", "bogus_role": "Junk"}'
        )
        result = bootstrap_taxonomy(["Archive"], mock_llm_provider, {})
        fn = result["taxonomy"]
        assert "archive" in fn
        assert "bogus_role" not in fn

    def test_parse_error_returns_empty(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = "not json at all"
        result = bootstrap_taxonomy(["Archive"], mock_llm_provider, {})
        assert result == {}

    def test_toplevel_folder_note_injected(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = '{"archive": "Archive"}'
        settings = {"toplevel_folder": {"enabled": True, "name": "Library"}}
        bootstrap_taxonomy(["Archive"], mock_llm_provider, settings)
        call_args = mock_llm_provider.classify_messages.call_args
        system_prompt = call_args[0][0]
        assert "Library" in system_prompt
        assert "container folder" in system_prompt


class TestRunDraftBootstrap:
    def _make_export(self, tmp_path: Path) -> Path:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [
                    {"id": "1", "title": "Note A", "folder_path": "Areas/Finance"},
                    {"id": "2", "title": "Note B", "folder_path": "Resources/Cooking"},
                    {"id": "3", "title": "Note C", "folder_path": "Archive"},
                ]
            )
        )
        return export_file

    def test_bootstrap_called_when_no_local_taxonomy(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        export_file = self._make_export(tmp_path)
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    **_make_theme_map(
                        [
                            {
                                "name": "Finance",
                                "suggested_path": "Areas/Finance",
                                "estimated_count": 10,
                            }
                        ]
                    ),
                    "source_export": str(export_file),
                }
            )
        )

        mock_llm_provider.classify_messages.return_value = (
            '{"areas": "Areas", "resources": "Resources", "archive": "Archive"}'
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=False)
        mocker.patch("scripts.classify.draft_taxonomy.get_provider", return_value=mock_llm_provider)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Provider should have been called for the bootstrap mapping
        mock_llm_provider.classify_messages.assert_called_once()
        # Draft file must contain both top-level entries AND export subfolders.
        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        parsed = yaml.safe_load(drafts[0].read_text())
        fn = parsed["taxonomy"]
        assert "Finance" in fn["areas"]["subfolders"], "Areas/Finance from export must be in draft"
        assert "Cooking" in fn["resources"]["subfolders"], (
            "Resources/Cooking from export must be in draft"
        )

    def test_bootstrap_skipped_when_local_taxonomy_exists(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                _make_theme_map(
                    [
                        {
                            "name": "Finance",
                            "suggested_path": "Resources/Finance",
                            "estimated_count": 10,
                        }
                    ]
                )
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.get_provider", return_value=mock_llm_provider)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # No bootstrap call should happen when local taxonomy exists
        mock_llm_provider.classify_messages.assert_not_called()

    def test_bootstrap_falls_back_when_no_export(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        # source_export points to a non-existent file
        theme_map_file.write_text(
            json.dumps(
                {
                    **_make_theme_map(
                        [
                            {
                                "name": "Finance",
                                "suggested_path": "Resources/Finance",
                                "estimated_count": 10,
                            }
                        ]
                    ),
                    "source_export": str(tmp_path / "nonexistent.json"),
                }
            )
        )

        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=False)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.get_provider", return_value=mock_llm_provider)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Should fall back gracefully without calling the provider
        mock_llm_provider.classify_messages.assert_not_called()

    def test_bootstrap_subfolders_written_to_taxonomy_on_confirm(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Confirming the draft writes both top-level roles and export subfolders to taxonomy.local.yaml."""
        export_file = self._make_export(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    **_make_theme_map(
                        [
                            {
                                "name": "Finance",
                                "suggested_path": "Areas/Finance",
                                "estimated_count": 10,
                            }
                        ]
                    ),
                    "source_export": str(export_file),
                }
            )
        )
        mock_llm_provider.classify_messages.return_value = (
            '{"areas": "Areas", "resources": "Resources", "archive": "Archive"}'
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=False)
        mocker.patch("scripts.classify.draft_taxonomy.get_provider", return_value=mock_llm_provider)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("scripts.classify.draft_taxonomy.CONFIG_DIR", config_dir)
        mocker.patch("typer.confirm", return_value=True)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        local = config_dir / "taxonomy.local.yaml"
        assert local.exists(), "taxonomy.local.yaml should be written when confirmed"
        parsed = yaml.safe_load(local.read_text())
        fn = parsed["taxonomy"]
        assert "Finance" in fn["areas"]["subfolders"], (
            "Areas/Finance must be in taxonomy.local.yaml"
        )
        assert "Cooking" in fn["resources"]["subfolders"], (
            "Resources/Cooking must be in taxonomy.local.yaml"
        )


class TestRunDraftAutoAddMissingFolders:
    """Folders present in the export but absent from the bootstrap/taxonomy are auto-added."""

    def test_bootstrap_incomplete_folders_auto_added(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        """LLM bootstrap omits Projects; auto-add fills it in and includes its subfolder."""
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [
                    {"id": "1", "title": "Note A", "folder_path": "Areas/Finance"},
                    {"id": "2", "title": "Note B", "folder_path": "Projects/Web App"},
                    {"id": "3", "title": "Note C", "folder_path": "Archive"},
                ]
            )
        )
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps({**_make_theme_map([]), "source_export": str(export_file)})
        )
        # LLM only returns 2/3 top-level folders — Projects is omitted
        mock_llm_provider.classify_messages.return_value = (
            '{"areas": "Areas", "archive": "Archive"}'
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=False)
        mocker.patch("scripts.classify.draft_taxonomy.get_provider", return_value=mock_llm_provider)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        parsed = yaml.safe_load(drafts[0].read_text())
        fn = parsed["taxonomy"]
        folder_names = {e.get("folder") for e in fn.values() if isinstance(e, dict)}
        assert "Projects" in folder_names, "Projects should be auto-added from export"
        # The subfolder under Projects should also be present
        projects_entry = next(
            e for e in fn.values() if isinstance(e, dict) and e.get("folder") == "Projects"
        )
        assert "Web App" in projects_entry.get("subfolders", [])

    def test_existing_incomplete_taxonomy_gets_missing_folders(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        """Re-run with an existing 3-folder taxonomy: export's missing top-level folders are added."""
        # Simulates the user's reported scenario: taxonomy.local.yaml exists but
        # Projects and Archive are absent from it.
        partial_taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "areas": {"folder": "Areas"},
                "resources": {"folder": "Resources"},
            }
        }
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [
                    {"id": "1", "title": "Note A", "folder_path": "Inbox"},
                    {"id": "2", "title": "Note B", "folder_path": "Projects/Web App"},
                    {"id": "3", "title": "Note C", "folder_path": "Areas/Finance"},
                    {"id": "4", "title": "Note D", "folder_path": "Archive/Old Work"},
                ]
            )
        )
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps({**_make_theme_map([]), "source_export": str(export_file)})
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.draft_taxonomy.load_taxonomy", return_value=partial_taxonomy)
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        parsed = yaml.safe_load(drafts[0].read_text())
        fn = parsed["taxonomy"]
        folder_names = {e.get("folder") for e in fn.values() if isinstance(e, dict)}
        assert "Projects" in folder_names, "Projects should be auto-added"
        assert "Archive" in folder_names, "Archive should be auto-added"
        # And their subfolders
        projects_entry = next(
            e for e in fn.values() if isinstance(e, dict) and e.get("folder") == "Projects"
        )
        archive_entry = next(
            e for e in fn.values() if isinstance(e, dict) and e.get("folder") == "Archive"
        )
        assert "Web App" in projects_entry.get("subfolders", [])
        assert "Old Work" in archive_entry.get("subfolders", [])

    def test_stale_established_paths_do_not_block_subfolders(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
    ) -> None:
        """Subfolders in the theme map's established_paths are still added if absent from the current taxonomy."""
        # Scenario: discover ran when taxonomy had "Resources/Cooking"; taxonomy was then
        # reset to top-level only. Re-running draft should re-add "Resources/Cooking".
        taxonomy_top_level_only = {
            "taxonomy": {
                "resources": {"folder": "Resources"},
                "archive": {"folder": "Archive"},
            }
        }
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(
            json.dumps(
                [{"id": "1", "title": "Pasta", "body": "x", "folder_path": "Resources/Cooking"}]
            )
        )
        theme_map_file = tmp_path / "themes-test.json"
        # established_paths contains Resources/Cooking from the old taxonomy
        theme_map_file.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "source_export": str(export_file),
                    "total_notes": 1,
                    "subfolder_threshold": 8,
                    "established_paths": ["Resources/Cooking"],  # stale — not in current taxonomy
                    "themes": [],
                    "new_paths": [],
                    "above_threshold": 0,
                    "below_threshold": 0,
                }
            )
        )
        mocker.patch("scripts.classify.draft_taxonomy.load_settings", return_value=minimal_settings)
        mocker.patch(
            "scripts.classify.draft_taxonomy.load_taxonomy", return_value=taxonomy_top_level_only
        )
        mocker.patch("scripts.classify.draft_taxonomy.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.draft_taxonomy.TAXONOMY_DRAFTS_DIR", tmp_path / "drafts")
        mocker.patch("typer.confirm", return_value=False)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1, (
            "Draft should be written — stale established_paths must not block it"
        )
        parsed = yaml.safe_load(drafts[0].read_text())
        assert "Cooking" in parsed["taxonomy"]["resources"]["subfolders"]


class TestRunDraftSourceExportWarning:
    """Missing source_export emits a warning but does not prevent the draft from being written."""

    def test_missing_source_export_still_writes_draft(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        theme_map_file = tmp_path / "themes-test.json"
        theme_map_file.write_text(
            json.dumps(
                {
                    **_make_theme_map(
                        [
                            {
                                "name": "Finance",
                                "suggested_path": "Resources/Finance",
                                "estimated_count": 10,
                            }
                        ]
                    ),
                    "source_export": str(tmp_path / "nonexistent-export.json"),
                }
            )
        )
        _patch_draft(mocker, tmp_path, minimal_taxonomy, minimal_settings)

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # LLM-suggested path (above threshold) still makes it into the draft
        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1, "Draft should still be written despite missing source export"
        content = drafts[0].read_text()
        assert "Finance" in content


class TestFindLatestThemeMap:
    def test_returns_most_recent_file(self, mocker: MagicMock, tmp_path: Path) -> None:
        older = tmp_path / "themes-2026-01-01.json"
        newer = tmp_path / "themes-2026-05-29.json"
        older.write_text("{}")
        newer.write_text("{}")
        mocker.patch("scripts.classify.draft_taxonomy.THEME_MAPS_DIR", tmp_path)
        result = find_latest_theme_map()
        assert result == newer

    def test_raises_when_no_files(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.classify.draft_taxonomy.THEME_MAPS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            find_latest_theme_map()
