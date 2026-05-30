"""Tests for scripts/folder_utils.py."""

from __future__ import annotations

from scripts.folder_utils import (
    APPLE_NOTES_MAX_DEPTH,
    clamp_path,
    effective_max_depth,
    enumerate_paths,
    folder_name,
    max_taxonomy_depth,
    nesting_mode,
    path_components,
    path_depth,
)


class TestFolderName:
    def test_dict_entry(self) -> None:
        assert folder_name({"folder": "Inbox"}) == "Inbox"

    def test_string_entry(self) -> None:
        assert folder_name("Resources") == "Resources"

    def test_dict_missing_folder_key(self) -> None:
        assert folder_name({"name": "Tech"}) == ""

    def test_dict_none_folder_value(self) -> None:
        assert folder_name({"folder": None}) == ""

    def test_empty_string(self) -> None:
        assert folder_name("") == ""

    def test_dict_empty_folder_value(self) -> None:
        assert folder_name({"folder": ""}) == ""


class TestEnumeratePaths:
    def test_leaf_string(self) -> None:
        assert enumerate_paths("Cooking") == ["Cooking"]

    def test_leaf_string_with_parent(self) -> None:
        assert enumerate_paths("Cooking", "Resources") == ["Resources/Cooking"]

    def test_flat_dict_no_subfolders(self) -> None:
        assert enumerate_paths({"folder": "Inbox"}) == ["Inbox"]

    def test_dict_with_empty_subfolders(self) -> None:
        assert enumerate_paths({"folder": "Resources", "subfolders": []}) == ["Resources"]

    def test_dict_with_none_subfolders(self) -> None:
        assert enumerate_paths({"folder": "Resources", "subfolders": None}) == ["Resources"]

    def test_dict_with_string_subfolders(self) -> None:
        result = enumerate_paths({"folder": "Resources", "subfolders": ["Cooking", "Finance"]})
        assert result == ["Resources", "Resources/Cooking", "Resources/Finance"]

    def test_dict_with_dict_subfolder(self) -> None:
        entry = {"folder": "Resources", "subfolders": [{"name": "Tech", "hub_title": "✱ Tech"}]}
        assert enumerate_paths(entry) == ["Resources", "Resources/Tech"]

    def test_nested_two_levels(self) -> None:
        entry = {
            "folder": "Resources",
            "subfolders": [{"name": "Programming", "subfolders": ["Python", "Go"]}],
        }
        assert enumerate_paths(entry) == [
            "Resources",
            "Resources/Programming",
            "Resources/Programming/Python",
            "Resources/Programming/Go",
        ]

    def test_nested_three_levels(self) -> None:
        entry = {
            "folder": "Resources",
            "subfolders": [
                {
                    "name": "Programming",
                    "subfolders": [{"name": "Systems", "subfolders": ["Networking"]}],
                }
            ],
        }
        assert enumerate_paths(entry) == [
            "Resources",
            "Resources/Programming",
            "Resources/Programming/Systems",
            "Resources/Programming/Systems/Networking",
        ]

    def test_mixed_leaf_and_dict_subfolders(self) -> None:
        entry = {
            "folder": "Resources",
            "subfolders": ["Cooking", {"name": "Tech", "subfolders": ["AI"]}],
        }
        assert enumerate_paths(entry) == [
            "Resources",
            "Resources/Cooking",
            "Resources/Tech",
            "Resources/Tech/AI",
        ]

    def test_empty_string_ignored(self) -> None:
        assert enumerate_paths("") == []

    def test_dict_missing_name_and_folder(self) -> None:
        assert enumerate_paths({}) == []

    def test_subfolder_uses_name_key(self) -> None:
        assert enumerate_paths({"name": "Reference"}, "Resources") == ["Resources/Reference"]


class TestPathDepth:
    def test_single_component(self) -> None:
        assert path_depth("Resources") == 1

    def test_two_components(self) -> None:
        assert path_depth("Resources/Tech") == 2

    def test_three_components(self) -> None:
        assert path_depth("Resources/Tech/Python") == 3

    def test_empty_string(self) -> None:
        assert path_depth("") == 0


class TestPathComponents:
    def test_single(self) -> None:
        assert path_components("Resources") == ["Resources"]

    def test_two(self) -> None:
        assert path_components("Resources/Tech") == ["Resources", "Tech"]

    def test_three(self) -> None:
        assert path_components("Resources/Tech/Python") == ["Resources", "Tech", "Python"]

    def test_empty(self) -> None:
        assert path_components("") == []


class TestMaxTaxonomyDepth:
    def test_flat_taxonomy(self) -> None:
        taxonomy = {
            "forever_notes": {"inbox": {"folder": "Inbox"}, "archive": {"folder": "Archive"}}
        }
        assert max_taxonomy_depth(taxonomy) == 1

    def test_two_level_taxonomy(self) -> None:
        taxonomy = {
            "forever_notes": {"resources": {"folder": "Resources", "subfolders": ["Cooking"]}}
        }
        assert max_taxonomy_depth(taxonomy) == 2

    def test_three_level_taxonomy(self) -> None:
        taxonomy = {
            "forever_notes": {
                "resources": {
                    "folder": "Resources",
                    "subfolders": [{"name": "Tech", "subfolders": ["Python"]}],
                }
            }
        }
        assert max_taxonomy_depth(taxonomy) == 3

    def test_empty_taxonomy(self) -> None:
        assert max_taxonomy_depth({}) == 1

    def test_mixed_depths_returns_max(self) -> None:
        taxonomy = {
            "forever_notes": {
                "inbox": {"folder": "Inbox"},
                "resources": {
                    "folder": "Resources",
                    "subfolders": [{"name": "Tech", "subfolders": ["AI"]}],
                },
            }
        }
        assert max_taxonomy_depth(taxonomy) == 3


class TestClampPath:
    def test_within_limit(self) -> None:
        assert clamp_path("Resources/Tech", 3) == "Resources/Tech"

    def test_at_limit(self) -> None:
        assert clamp_path("Resources/Tech/Python", 3) == "Resources/Tech/Python"

    def test_exceeds_limit(self) -> None:
        assert clamp_path("A/B/C/D", 3) == "A/B/C"

    def test_empty_path(self) -> None:
        assert clamp_path("", 3) == ""

    def test_single_component(self) -> None:
        assert clamp_path("Resources", 3) == "Resources"

    def test_depth_one_limit(self) -> None:
        assert clamp_path("Resources/Tech/Python", 1) == "Resources"


class TestEffectiveMaxDepth:
    def test_default_no_settings(self) -> None:
        assert effective_max_depth(None) == 3

    def test_default_empty_settings(self) -> None:
        assert effective_max_depth({}) == 3

    def test_reads_from_settings(self) -> None:
        assert effective_max_depth({"thresholds": {"max_folder_depth": 4}}) == 4

    def test_clamped_to_apple_notes_max(self) -> None:
        assert (
            effective_max_depth({"thresholds": {"max_folder_depth": 99}}) == APPLE_NOTES_MAX_DEPTH
        )

    def test_depth_of_one(self) -> None:
        assert effective_max_depth({"thresholds": {"max_folder_depth": 1}}) == 1

    def test_missing_thresholds_key(self) -> None:
        assert effective_max_depth({"llm": {"provider": "anthropic"}}) == 3


class TestNestingMode:
    def test_default_no_settings(self) -> None:
        assert nesting_mode(None) == "natural"

    def test_default_empty_settings(self) -> None:
        assert nesting_mode({}) == "natural"

    def test_flat_mode(self) -> None:
        assert nesting_mode({"folder_nesting": "flat"}) == "flat"

    def test_deep_mode(self) -> None:
        assert nesting_mode({"folder_nesting": "deep"}) == "deep"

    def test_natural_explicit(self) -> None:
        assert nesting_mode({"folder_nesting": "natural"}) == "natural"
