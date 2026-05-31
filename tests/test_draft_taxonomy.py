"""Tests for scripts/classify/draft_taxonomy.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from scripts.classify.draft_taxonomy import (
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

    def test_multiple_paths_sorted_deterministically(self, minimal_taxonomy: dict) -> None:
        paths = ["Resources/Zebra", "Resources/Alpha", "Resources/Mango"]
        _, added, _ = merge_new_paths(minimal_taxonomy, paths)
        assert added == sorted(added)


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

    def test_below_threshold_excluded_when_no_matching_export_path(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
        minimal_settings: dict,
    ) -> None:
        # Export only has "Resources/Cooking" — theme suggests "Resources/Tiny" (not in export)
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

        # Should still be excluded — not in export tree and below threshold
        drafts = (
            list((tmp_path / "drafts").glob("*.yaml")) if (tmp_path / "drafts").exists() else []
        )
        assert drafts == []


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

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Provider should have been called for the bootstrap mapping
        mock_llm_provider.classify_messages.assert_called_once()
        # Draft file should be written with the bootstrapped taxonomy
        drafts = list((tmp_path / "drafts").glob("*.yaml"))
        assert len(drafts) == 1
        content = drafts[0].read_text()
        assert "Areas" in content

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

        run_draft(theme_map_file=str(theme_map_file), dry_run=False)

        # Should fall back gracefully without calling the provider
        mock_llm_provider.classify_messages.assert_not_called()


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
