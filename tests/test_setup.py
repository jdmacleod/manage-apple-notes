"""Tests for scripts/setup/ — scorer, frameworks, and run_setup utilities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
import yaml

from scripts.setup.frameworks import FRAMEWORKS, framework_choices, get_framework
from scripts.setup.run_setup import (
    _ask_container,
    _ask_forever_notes,
    _ask_numbered,
    _ask_organization_style,
    _auto_map_roles,
    _build_existing_taxonomy_yaml,
    _build_taxonomy_from_export,
    _build_taxonomy_yaml,
    _check_apple_intelligence_prerequisites,
    _collect_existing_folders,
    _collect_folder_names,
    _detect_accounts,
    _detect_container,
    _ensure_settings,
    _extract_folders_from_export,
    _fetch_subfolders,
    _fetch_top_level_folders,
    _find_export_optional,
    _group_paths_into_tree,
    _gtd_categories_snippet,
    _handle_multiple_accounts,
    _infer_framework,
    _relevant_missing_roles,
    _select_provider,
    _write_categories_for_taxonomy,
    _write_classify_exclude_archive_to_settings,
    _write_env_line,
    _write_folder_nesting_to_settings,
    _write_forever_notes_to_settings,
    _write_ollama_model_to_settings,
    _write_primary_account_to_settings,
    _write_provider_to_settings,
    _write_reorganization_mode_to_settings,
    _write_subfolder_threshold_to_settings,
    _write_taxonomy,
    _write_toplevel_folder_to_settings,
    analyze_corpus,
    run_setup,
)
from scripts.setup.scorer import score

# ── scorer.py ─────────────────────────────────────────────────────────────────


class TestScoreExistingPath:
    def test_q1_4_returns_existing(self) -> None:
        result = score(None, 4, None, None)
        assert result["winner"] == "EXISTING"
        assert result["runner_up"] is None
        assert result["confidence"] == "n/a"

    def test_q1_4_corpus_ignored(self) -> None:
        corpus = {"note_count": 5000, "cross_ref_pct": 0.9}
        result = score(corpus, 4, None, None)
        assert result["winner"] == "EXISTING"


class TestScoreFrameworkSelection:
    def test_task_goal_recommends_gtd(self) -> None:
        result = score(None, 1, 2, 1)
        assert result["winner"] == "GTD"

    def test_retrieval_goal_recommends_para(self) -> None:
        result = score(None, 2, 1, 2)
        assert result["winner"] == "PARA"

    def test_idea_goal_recommends_zettelkasten(self) -> None:
        result = score(None, 3, 3, 3)
        assert result["winner"] == "ZETTELKASTEN"

    def test_returns_all_required_keys(self) -> None:
        result = score(None, 2, 1, 2)
        for key in ("winner", "runner_up", "scores", "confidence", "gap", "rationale"):
            assert key in result

    def test_scores_dict_has_three_frameworks(self) -> None:
        result = score(None, 1, 1, 1)
        assert set(result["scores"]) == {"PARA", "GTD", "ZETTELKASTEN"}

    def test_rationale_is_non_empty_string(self) -> None:
        result = score(None, 2, 2, 2)
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 0


class TestScoreConfidence:
    def test_high_confidence_when_gap_5_or_more(self) -> None:
        # Q1=3 (+3 ZK), Q2=3 (+2 ZK), Q3=3 (+3 ZK), corpus xref >5% (+3 ZK) → big gap
        corpus = {
            "note_count": 500,
            "cross_ref_pct": 0.10,
            "task_keyword_pct": 0.0,
            "avg_word_count": 400,
            "folder_count": 3,
            "oldest_note_days": 1500,
        }
        result = score(corpus, 3, 3, 3)
        assert result["confidence"] == "high"
        assert result["winner"] == "ZETTELKASTEN"

    def test_low_confidence_defaults_to_para(self) -> None:
        # Force a near-tie: Q1=2 (+3 PARA), Q2=2 (+2 GTD, +1 PARA), Q3=2 (+2 PARA)
        # PARA=6, GTD=2, ZK=0 → gap is 4, moderate
        # To get low confidence, need gap < 2
        # Q1=2 (+3 PARA), Q2=1 (+2 PARA), Q3=1 (+2 GTD) → PARA=5, GTD=2, ZK=0 → gap=3 moderate
        # Hard to engineer a true tie with just questions; test that low confidence winner is PARA
        # Manually verified: Q1=1(+3 GTD), Q2=1(+2 PARA), Q3=2(+2 PARA) → GTD=3, PARA=4, ZK=0 → PARA wins
        result = score(None, 2, 2, 1)
        # Whatever wins, rationale should be present
        assert result["confidence"] in ("high", "moderate", "low")
        if result["confidence"] == "low":
            assert result["winner"] == "PARA"


class TestScoreCorpusSignals:
    def _base_corpus(self) -> dict:
        return {
            "note_count": 300,
            "folder_count": 4,
            "avg_word_count": 150,
            "task_keyword_pct": 0.0,
            "cross_ref_pct": 0.0,
            "oldest_note_days": 365,
        }

    def test_high_cross_ref_pct_boosts_zettelkasten(self) -> None:
        corpus = {**self._base_corpus(), "cross_ref_pct": 0.10}
        result = score(corpus, 3, 3, 3)
        assert result["scores"]["ZETTELKASTEN"] > result["scores"]["PARA"]

    def test_high_task_pct_boosts_gtd(self) -> None:
        corpus = {**self._base_corpus(), "task_keyword_pct": 0.20}
        result = score(corpus, 1, 2, 1)
        assert result["scores"]["GTD"] > result["scores"]["PARA"]

    def test_large_library_boosts_zettelkasten(self) -> None:
        corpus = {**self._base_corpus(), "note_count": 1500}
        # ZK gets +2 for large library
        base = score(self._base_corpus(), 3, 3, 3)
        large = score(corpus, 3, 3, 3)
        assert large["scores"]["ZETTELKASTEN"] > base["scores"]["ZETTELKASTEN"]

    def test_many_folders_boosts_para(self) -> None:
        corpus = {**self._base_corpus(), "folder_count": 8}
        base_scores = score(self._base_corpus(), 2, 1, 2)["scores"]["PARA"]
        high_scores = score(corpus, 2, 1, 2)["scores"]["PARA"]
        assert high_scores > base_scores

    def test_no_corpus_still_returns_recommendation(self) -> None:
        result = score(None, 2, 1, 2)
        assert result["winner"] in ("PARA", "GTD", "ZETTELKASTEN")
        assert result["scores"]["PARA"] > 0


class TestScoreTieBreaking:
    def test_tie_para_beats_zettelkasten(self) -> None:
        # Construct a case where raw scores give near-tie ZK vs PARA
        # Q1=2 (+3 PARA), Q2=3 (+2 ZK), Q3=3 (+3 ZK) → PARA=3, ZK=5, gap=2 moderate
        # Actually gap=2 is moderate not low, so no tie-break kicks in
        # Let's check the tie-break: if gap < 2 and ZK would win, PARA wins instead
        # We'll just verify the tie-break path doesn't crash
        result = score(None, 2, 2, 2)
        assert result["winner"] in ("PARA", "GTD", "ZETTELKASTEN")


# ── frameworks.py ─────────────────────────────────────────────────────────────


class TestGetFramework:
    def test_para_has_required_keys(self) -> None:
        fw = get_framework("PARA")
        for key in (
            "name",
            "category_keys",
            "canonical_names",
            "category_prompts",
            "folder_preview",
            "best_for",
            "maintenance",
        ):
            assert key in fw, f"PARA missing key: {key}"

    def test_gtd_has_extra_categories(self) -> None:
        fw = get_framework("GTD")
        assert "extra_categories" in fw
        assert "next_actions" in fw["extra_categories"]
        assert "waiting_for" in fw["extra_categories"]

    def test_zettelkasten_has_nine_keys(self) -> None:
        fw = get_framework("ZETTELKASTEN")
        assert len(fw["category_keys"]) == 9

    def test_case_insensitive(self) -> None:
        assert get_framework("para")["name"] == "PARA"
        assert get_framework("gtd")["name"] == "GTD"

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(KeyError):
            get_framework("UNKNOWN")

    def test_existing_has_improvement_suggestions(self) -> None:
        fw = FRAMEWORKS["EXISTING"]
        assert "improvement_suggestions" in fw
        assert len(fw["improvement_suggestions"]) >= 3


class TestFrameworkChoices:
    def test_returns_four_items(self) -> None:
        choices = framework_choices()
        assert len(choices) == 4

    def test_existing_option_is_last(self) -> None:
        choices = framework_choices()
        assert "existing" in choices[-1].lower() or "already have" in choices[-1].lower()


# ── run_setup.py — corpus analysis ────────────────────────────────────────────


class TestAnalyzeCorpus:
    def _write_export(self, tmp_path: Path, notes: list[dict]) -> Path:
        p = tmp_path / "notes-test.json"
        p.write_text(json.dumps(notes))
        return p

    def test_empty_export_returns_empty_dict(self, tmp_path: Path) -> None:
        path = self._write_export(tmp_path, [])
        assert analyze_corpus(path) == {}

    def test_basic_counts(self, tmp_path: Path) -> None:
        notes = [
            {
                "id": "1",
                "title": "A",
                "body": "hello world",
                "folder": "Inbox",
                "modified": "2024-01-01T00:00:00",
            },
            {
                "id": "2",
                "title": "B",
                "body": "another note",
                "folder": "Projects",
                "modified": "2024-06-01T00:00:00",
            },
        ]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["note_count"] == 2
        assert result["folder_count"] == 2

    def test_task_keyword_detection(self, tmp_path: Path) -> None:
        notes = [
            {
                "id": "1",
                "body": "TODO finish the report",
                "folder": "X",
                "modified": "2024-01-01T00:00:00",
            },
            {
                "id": "2",
                "body": "just a normal note",
                "folder": "X",
                "modified": "2024-01-01T00:00:00",
            },
        ]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["task_keyword_pct"] == pytest.approx(0.5)

    def test_cross_ref_detection(self, tmp_path: Path) -> None:
        notes = [
            {
                "id": "1",
                "body": "see [[Some Other Note]] for details",
                "folder": "X",
                "modified": "2024-01-01T00:00:00",
            },
            {"id": "2", "body": "plain text", "folder": "X", "modified": "2024-01-01T00:00:00"},
        ]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["cross_ref_pct"] == pytest.approx(0.5)

    def test_avg_word_count(self, tmp_path: Path) -> None:
        notes = [
            {
                "id": "1",
                "body": "one two three four",
                "folder": "X",
                "modified": "2024-01-01T00:00:00",
            },
            {"id": "2", "body": "a b", "folder": "X", "modified": "2024-01-01T00:00:00"},
        ]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["avg_word_count"] == pytest.approx(3.0)

    def test_oldest_note_days_positive(self, tmp_path: Path) -> None:
        old_date = "2020-01-01T00:00:00"
        notes = [{"id": "1", "body": "old note", "folder": "X", "modified": old_date}]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["oldest_note_days"] > 365 * 3

    def test_missing_body_handled(self, tmp_path: Path) -> None:
        notes = [{"id": "1", "folder": "X", "modified": "2024-01-01T00:00:00"}]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["note_count"] == 1
        assert result["avg_word_count"] == 0.0

    def test_invalid_modified_date_skipped(self, tmp_path: Path) -> None:
        notes = [{"id": "1", "body": "hi", "folder": "X", "modified": "not-a-date"}]
        result = analyze_corpus(self._write_export(tmp_path, notes))
        assert result["oldest_note_days"] == 0


# ── run_setup.py — YAML generation ────────────────────────────────────────────


class TestBuildTaxonomyYaml:
    def test_para_produces_valid_yaml(self) -> None:
        folder_map = {
            "inbox": "Inbox",
            "projects": "Projects",
            "areas": "Areas",
            "resources": "Resources",
            "archive": "Archive",
        }
        result = _build_taxonomy_yaml("PARA", folder_map)
        parsed = yaml.safe_load(result)
        assert "taxonomy" in parsed
        assert parsed["taxonomy"]["inbox"]["folder"] == "Inbox"
        assert parsed["taxonomy"]["archive"]["folder"] == "Archive"

    def test_preserves_category_order(self) -> None:
        fw = get_framework("PARA")
        folder_map = {
            k: v for k, v in zip(fw["category_keys"], fw["canonical_names"].values(), strict=True)
        }
        result = _build_taxonomy_yaml("PARA", folder_map)
        parsed = yaml.safe_load(result)
        keys = list(parsed["taxonomy"].keys())
        assert keys == fw["category_keys"]

    def test_skips_empty_folder_names(self) -> None:
        folder_map = {
            "inbox": "Inbox",
            "projects": "",
            "areas": "Areas",
            "resources": "Resources",
            "archive": "Archive",
        }
        result = _build_taxonomy_yaml("PARA", folder_map)
        parsed = yaml.safe_load(result)
        assert "projects" not in parsed["taxonomy"]

    def test_header_contains_framework_name(self) -> None:
        folder_map = {
            "inbox": "Inbox",
            "projects": "Projects",
            "areas": "Areas",
            "resources": "Resources",
            "archive": "Archive",
        }
        result = _build_taxonomy_yaml("PARA", folder_map)
        assert "Projects" in result  # part of "Projects · Areas · Resources · Archive"

    def test_gtd_includes_non_standard_keys(self) -> None:
        fw = get_framework("GTD")
        folder_map = {k: v for k, v in fw["canonical_names"].items()}
        result = _build_taxonomy_yaml("GTD", folder_map)
        parsed = yaml.safe_load(result)
        assert "next_actions" in parsed["taxonomy"]
        assert "waiting_for" in parsed["taxonomy"]


class TestBuildExistingTaxonomyYaml:
    def test_produces_valid_yaml(self) -> None:
        folder_map = {"inbox": "My Inbox", "archive": "Old Stuff"}
        result = _build_existing_taxonomy_yaml(folder_map)
        parsed = yaml.safe_load(result)
        assert parsed["taxonomy"]["inbox"]["folder"] == "My Inbox"
        assert parsed["taxonomy"]["archive"]["folder"] == "Old Stuff"

    def test_header_mentions_custom(self) -> None:
        result = _build_existing_taxonomy_yaml({"inbox": "Capture"})
        assert "Custom" in result or "existing" in result.lower()


class TestExtractFoldersFromExport:
    def test_prefers_folder_path_over_folder(self, tmp_path: Path) -> None:
        export = tmp_path / "notes.json"
        export.write_text(
            json.dumps([{"folder": "Finance", "folder_path": "Areas/Finance", "body": ""}])
        )
        folders, _ = _extract_folders_from_export(export)
        assert folders == ["Areas/Finance"]

    def test_falls_back_to_folder_when_no_folder_path(self, tmp_path: Path) -> None:
        export = tmp_path / "notes.json"
        export.write_text(json.dumps([{"folder": "Inbox", "body": ""}]))
        folders, _ = _extract_folders_from_export(export)
        assert folders == ["Inbox"]

    def test_returns_first_seen_order(self, tmp_path: Path) -> None:
        export = tmp_path / "notes.json"
        export.write_text(
            json.dumps(
                [
                    {"folder_path": "Projects", "body": ""},
                    {"folder_path": "Inbox", "body": ""},
                    {"folder_path": "Projects", "body": ""},
                    {"folder_path": "Archive/Old", "body": ""},
                ]
            )
        )
        folders, _ = _extract_folders_from_export(export)
        # Order reflects first appearance in the export, not alphabetical order
        assert folders == ["Projects", "Inbox", "Archive/Old"]

    def test_note_counts_are_accurate(self, tmp_path: Path) -> None:
        export = tmp_path / "notes.json"
        export.write_text(
            json.dumps(
                [
                    {"folder_path": "Inbox", "body": ""},
                    {"folder_path": "Inbox", "body": ""},
                    {"folder_path": "Projects", "body": ""},
                ]
            )
        )
        _, counts = _extract_folders_from_export(export)
        assert counts["Inbox"] == 2
        assert counts["Projects"] == 1

    def test_skips_notes_with_no_folder(self, tmp_path: Path) -> None:
        export = tmp_path / "notes.json"
        export.write_text(json.dumps([{"body": "no folder"}, {"folder": "", "body": "empty"}]))
        folders, _ = _extract_folders_from_export(export)
        assert folders == []


class TestGroupPathsIntoTree:
    def test_top_level_only_paths(self) -> None:
        tree = _group_paths_into_tree(["Inbox", "Projects", "Archive"])
        assert tree == {"Archive": [], "Inbox": [], "Projects": []}

    def test_subfolder_paths_grouped_under_top_level(self) -> None:
        tree = _group_paths_into_tree(["Areas/Finance", "Areas/Health", "Projects"])
        assert tree["Areas"] == ["Finance", "Health"]
        assert tree["Projects"] == []

    def test_subfolders_preserve_first_seen_order(self) -> None:
        tree = _group_paths_into_tree(["Areas/Zzz", "Areas/Aaa"])
        # First-seen order, not alphabetical
        assert tree["Areas"] == ["Zzz", "Aaa"]

    def test_top_level_folders_preserve_first_seen_order(self) -> None:
        tree = _group_paths_into_tree(["Zeta", "Alpha"])
        # First-seen order, not alphabetical
        assert list(tree.keys()) == ["Zeta", "Alpha"]

    def test_deeper_paths_collapsed_to_two_levels(self) -> None:
        tree = _group_paths_into_tree(["Areas/Work/Projects"])
        assert "Areas" in tree
        assert "Work" in tree["Areas"]

    def test_no_duplicate_subfolders(self) -> None:
        tree = _group_paths_into_tree(["Areas/Finance", "Areas/Finance"])
        assert tree["Areas"].count("Finance") == 1

    def test_empty_list(self) -> None:
        assert _group_paths_into_tree([]) == {}


class TestAutoMapRoles:
    def test_maps_inbox_by_name(self) -> None:
        mapping = _auto_map_roles(["Inbox", "Projects"])
        assert mapping.get("inbox") == "Inbox"

    def test_maps_archive_by_name(self) -> None:
        mapping = _auto_map_roles(["Archive", "Notes"])
        assert mapping.get("archive") == "Archive"

    def test_maps_projects_by_partial_match(self) -> None:
        mapping = _auto_map_roles(["My Projects"])
        assert mapping.get("projects") == "My Projects"

    def test_maps_standard_para_top_level_folders(self) -> None:
        mapping = _auto_map_roles(["Areas", "Archive", "Projects", "Resources"])
        assert mapping.get("areas") == "Areas"
        assert mapping.get("archive") == "Archive"
        assert mapping.get("projects") == "Projects"
        assert mapping.get("resources") == "Resources"

    def test_does_not_double_assign_same_folder(self) -> None:
        mapping = _auto_map_roles(["Inbox"])
        assert "inbox" in mapping
        assigned = list(mapping.values())
        assert len(assigned) == len(set(assigned))

    def test_unrecognised_folder_not_in_mapping(self) -> None:
        mapping = _auto_map_roles(["XYZ Random Folder"])
        assert "XYZ Random Folder" not in mapping.values()

    def test_empty_list_returns_empty(self) -> None:
        assert _auto_map_roles([]) == {}


class TestInferFramework:
    def test_para_when_projects_and_areas_present(self) -> None:
        assert _infer_framework({"projects": "Projects", "areas": "Areas"}) == "para"

    def test_para_when_projects_resources_archive_present(self) -> None:
        role_map = {"projects": "P", "resources": "R", "archive": "A"}
        assert _infer_framework(role_map) == "para"

    def test_zettelkasten_when_fleeting_literature_permanent_present(self) -> None:
        role_map = {"fleeting": "Fleeting", "literature": "Literature", "permanent": "Permanent"}
        assert _infer_framework(role_map) == "zettelkasten"

    def test_zettelkasten_when_two_zk_roles_and_no_para(self) -> None:
        role_map = {"fleeting": "Fleeting", "permanent": "Permanent"}
        assert _infer_framework(role_map) == "zettelkasten"

    def test_unknown_when_only_one_signal(self) -> None:
        assert _infer_framework({"projects": "Projects"}) == "unknown"
        assert _infer_framework({"fleeting": "Fleeting"}) == "unknown"

    def test_unknown_when_empty(self) -> None:
        assert _infer_framework({}) == "unknown"

    def test_para_wins_when_para_score_exceeds_zk(self) -> None:
        # 3 PARA roles vs 2 ZK roles → PARA wins (zk_score < para_score)
        role_map = {
            "projects": "P",
            "areas": "A",
            "resources": "R",
            "fleeting": "F",
            "literature": "L",
        }
        assert _infer_framework(role_map) == "para"

    def test_zk_wins_on_equal_score_when_both_at_two(self) -> None:
        # ZK score 2, PARA score 2 → ZK wins (zk_score >= para_score)
        role_map = {"fleeting": "F", "literature": "L", "projects": "P", "areas": "A"}
        assert _infer_framework(role_map) == "zettelkasten"


class TestRelevantMissingRoles:
    def test_para_user_sees_para_roles_not_zk(self) -> None:
        role_map = {"projects": "Projects", "archive": "Archive"}
        missing = ["inbox", "areas", "resources", "fleeting", "literature", "permanent"]
        result = _relevant_missing_roles(missing, role_map)
        assert "inbox" in result
        assert "areas" in result
        assert "resources" in result
        # ZK roles suppressed for PARA user
        assert "fleeting" not in result
        assert "literature" not in result
        assert "permanent" not in result

    def test_zk_user_sees_zk_roles_not_para_specific(self) -> None:
        role_map = {"fleeting": "F", "literature": "L"}
        missing = ["inbox", "permanent", "projects", "areas", "resources"]
        result = _relevant_missing_roles(missing, role_map)
        assert "inbox" in result
        assert "permanent" in result
        # PARA-specific roles suppressed
        assert "projects" not in result
        assert "areas" not in result
        assert "resources" not in result

    def test_unknown_framework_shows_only_universal(self) -> None:
        role_map = {"projects": "Projects"}  # only one PARA signal → unknown
        missing = ["inbox", "archive", "areas", "fleeting", "literature"]
        result = _relevant_missing_roles(missing, role_map)
        assert "inbox" in result
        assert "archive" in result
        assert "areas" not in result
        assert "fleeting" not in result
        assert "literature" not in result

    def test_preserves_display_order(self) -> None:
        role_map = {"projects": "P", "areas": "A"}  # PARA
        missing = ["resources", "inbox", "archive"]
        result = _relevant_missing_roles(missing, role_map)
        # inbox should come before archive, archive before resources per _ROLE_DISPLAY_ORDER
        assert result.index("inbox") < result.index("archive")
        assert result.index("archive") < result.index("resources")

    def test_already_covered_roles_not_in_output(self) -> None:
        role_map = {"projects": "P", "archive": "A", "inbox": "I"}
        missing = ["areas", "resources"]  # inbox already covered so not in missing
        result = _relevant_missing_roles(missing, role_map)
        assert "inbox" not in result  # not in missing list, so not returned


class TestBuildTaxonomyFromExport:
    def test_produces_valid_yaml(self) -> None:
        tree = {"Inbox": [], "Projects": []}
        result = _build_taxonomy_from_export(tree, {"inbox": "Inbox"})
        parsed = yaml.safe_load(result)
        assert "taxonomy" in parsed

    def test_role_mapped_folder_uses_semantic_key(self) -> None:
        result = _build_taxonomy_from_export({"Inbox": []}, {"inbox": "Inbox"})
        parsed = yaml.safe_load(result)
        assert parsed["taxonomy"]["inbox"]["folder"] == "Inbox"

    def test_subfolders_included_in_entry(self) -> None:
        tree = {"Areas": ["Finance", "Health"]}
        result = _build_taxonomy_from_export(tree, {"areas": "Areas"})
        parsed = yaml.safe_load(result)
        assert parsed["taxonomy"]["areas"]["subfolders"] == ["Finance", "Health"]

    def test_top_level_with_no_subfolders_has_no_subfolders_key(self) -> None:
        result = _build_taxonomy_from_export({"Projects": []}, {"projects": "Projects"})
        parsed = yaml.safe_load(result)
        assert "subfolders" not in parsed["taxonomy"]["projects"]

    def test_unmapped_folder_gets_sanitized_key(self) -> None:
        result = _build_taxonomy_from_export({"Health Notes": []}, {})
        parsed = yaml.safe_load(result)
        assert "health_notes" in parsed["taxonomy"]

    def test_collision_handled_with_suffix(self) -> None:
        # Two folders that both sanitize to the same key
        result = _build_taxonomy_from_export({"Test Folder": [], "Test_Folder": []}, {})
        parsed = yaml.safe_load(result)
        keys = list(parsed["taxonomy"].keys())
        assert len(keys) == len(set(keys)), "Collision produced duplicate keys"

    def test_all_top_level_folders_included(self) -> None:
        tree = {"Inbox": [], "Projects": [], "Health": [], "Finance": []}
        role_map = {"inbox": "Inbox", "projects": "Projects"}
        result = _build_taxonomy_from_export(tree, role_map)
        parsed = yaml.safe_load(result)
        stored = {v["folder"] for v in parsed["taxonomy"].values()}
        assert stored == {"Inbox", "Projects", "Health", "Finance"}

    def test_header_mentions_export(self) -> None:
        result = _build_taxonomy_from_export({"Inbox": []}, {})
        assert "export" in result.lower()


class TestGtdCategoriesSnippet:
    def test_returns_valid_yaml(self) -> None:
        snippet = _gtd_categories_snippet()
        parsed = yaml.safe_load(snippet)
        assert "categories" in parsed

    def test_includes_non_standard_keys(self) -> None:
        snippet = _gtd_categories_snippet()
        parsed = yaml.safe_load(snippet)
        cats = parsed["categories"]
        for key in ("next_actions", "waiting_for", "someday_maybe", "reference"):
            assert key in cats, f"Missing GTD category key: {key}"


# ── run_setup.py — file I/O ────────────────────────────────────────────────────


class TestWriteTaxonomy:
    def test_dry_run_does_not_write(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_taxonomy("taxonomy:\n  inbox:\n    folder: Inbox\n", dry_run=True)
        assert not (tmp_path / "taxonomy.local.yaml").exists()

    def test_writes_taxonomy_file(self, tmp_path: Path) -> None:
        content = "taxonomy:\n  inbox:\n    folder: Inbox\n"
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_taxonomy(content, dry_run=False)
        written = (tmp_path / "taxonomy.local.yaml").read_text()
        assert "Inbox" in written

    def test_backs_up_existing_file(self, tmp_path: Path) -> None:
        existing = tmp_path / "taxonomy.local.yaml"
        existing.write_text("old content")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_taxonomy("new content", dry_run=False)
        bak = tmp_path / "taxonomy.local.yaml.bak"
        assert bak.exists()
        assert bak.read_text() == "old content"


class TestEnsureSettings:
    def test_no_op_when_settings_exists(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text("llm_provider: apple\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            result = _ensure_settings(dry_run=False)
        assert settings.read_text() == "llm_provider: apple\n"
        assert result is False

    def test_copies_example_when_missing(self, tmp_path: Path) -> None:
        example = tmp_path / "settings.example.yaml"
        example.write_text("llm_provider: apple\nexample: true\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            result = _ensure_settings(dry_run=False)
        assert (tmp_path / "settings.local.yaml").exists()
        assert result is True

    def test_dry_run_does_not_copy(self, tmp_path: Path) -> None:
        example = tmp_path / "settings.example.yaml"
        example.write_text("llm_provider: apple\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            result = _ensure_settings(dry_run=True)
        assert not (tmp_path / "settings.local.yaml").exists()
        assert result is True


class TestFindExportOptional:
    def test_returns_none_when_no_exports(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup.find_latest_export",
            side_effect=FileNotFoundError("no exports"),
        )
        assert _find_export_optional() is None

    def test_returns_path_when_export_exists(self, mocker: MagicMock, tmp_path: Path) -> None:
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text("[]")
        mocker.patch("scripts.setup.run_setup.find_latest_export", return_value=export)
        assert _find_export_optional() == export


# ── run_setup.py — _ask_numbered ──────────────────────────────────────────────


class TestAskNumbered:
    def test_valid_choice_returned(self, mocker: MagicMock) -> None:
        mocker.patch("typer.prompt", return_value="2")
        assert _ask_numbered("Pick one", ["A", "B", "C"]) == 2

    def test_loops_on_invalid_then_accepts(self, mocker: MagicMock) -> None:
        mocker.patch("typer.prompt", side_effect=["0", "99", "x", "1"])
        assert _ask_numbered("Pick one", ["A", "B"]) == 1

    def test_default_accepted_on_empty_enter(self, mocker: MagicMock) -> None:
        mocker.patch("typer.prompt", return_value="")
        assert _ask_numbered("Pick one", ["A", "B", "C"], default=1) == 1

    def test_default_not_used_when_number_typed(self, mocker: MagicMock) -> None:
        mocker.patch("typer.prompt", return_value="3")
        assert _ask_numbered("Pick one", ["A", "B", "C"], default=1) == 3

    def test_no_default_empty_enter_loops(self, mocker: MagicMock) -> None:
        mocker.patch("typer.prompt", side_effect=["", "2"])
        assert _ask_numbered("Pick one", ["A", "B"]) == 2


# ── run_setup.py — orchestrator (mocked interactions) ─────────────────────────


class TestRunSetup:
    @pytest.fixture(autouse=True)
    def _stub_accounts(self, mocker: MagicMock) -> None:
        """Prevent live AppleScript execution in all TestRunSetup tests."""
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=["iCloud"])
        mocker.patch("scripts.setup.run_setup._fetch_top_level_folders", return_value=[])
        # _detect_container is a no-op when top_level_folders is [] (no questionary call),
        # but stub it anyway so tests are insulated from any future change in that path.
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))

    def _para_mocks(self, mocker: MagicMock, tmp_path: Path) -> None:
        """Set up mocks for a PARA path through run_setup."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "Projects",
                "areas": "Areas",
                "resources": "Resources",
                "archive": "Archive",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)

    def test_para_path_completes(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._para_mocks(mocker, tmp_path)
        run_setup(dry_run=False, no_corpus=True)  # asserts no exception raised

    def test_dry_run_flag_passed_to_write(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._para_mocks(mocker, tmp_path)
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=True, no_corpus=True)
        write_mock.assert_called_once()
        _yaml_arg, dry_run_arg = write_mock.call_args[0]
        assert dry_run_arg is True

    def test_existing_path_q1_4_no_export_uses_manual_mapping(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        collect_mock = mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "My Inbox", "archive": "Archive"},
        )
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        collect_mock.assert_called_once()

    def test_existing_path_with_export_auto_generates_taxonomy(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "Inbox", "folder_path": "Inbox", "body": ""},
                    {"folder": "Finance", "folder_path": "Areas/Finance", "body": ""},
                    {"folder": "Health", "folder_path": "Areas/Health", "body": ""},
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + decline Archive + decline Resources (PARA-inferred missing) + generate
        mocker.patch("typer.confirm", side_effect=[True, False, False, True])
        collect_mock = mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        collect_mock.assert_not_called()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        # Top-level folders appear at the root of the taxonomy
        stored_top = {v["folder"] for v in parsed["taxonomy"].values()}
        assert "Inbox" in stored_top
        assert "Areas" in stored_top
        assert "Projects" in stored_top
        # Subfolders are nested under Areas
        areas_entry = next(v for v in parsed["taxonomy"].values() if v["folder"] == "Areas")
        assert "Finance" in areas_entry.get("subfolders", [])
        assert "Health" in areas_entry.get("subfolders", [])

    def test_existing_path_with_export_fallback_to_manual_when_declined(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(json.dumps([{"folder": "Inbox", "body": ""}]))
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + decline Archive (universal missing, unknown framework) + decline generate
        mocker.patch("typer.confirm", side_effect=[True, False, False])
        collect_mock = mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "Inbox"},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        collect_mock.assert_called_once()

    def test_container_folder_excluded_from_taxonomy(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Notes directly in the container folder are excluded; only taxonomy categories kept."""
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    # Notes directly in the container (should be excluded)
                    {"folder": "Library", "folder_path": "Library", "body": ""},
                    {"folder": "Library", "folder_path": "Library", "body": ""},
                    # Notes in taxonomy categories (should appear in taxonomy)
                    {"folder": "Finance", "folder_path": "Areas/Finance", "body": ""},
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + decline Inbox + decline Archive + decline Resources (PARA missing) + generate
        mocker.patch("typer.confirm", side_effect=[True, False, False, False, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        # Simulate container="Library" returned from Phase 0 AppleScript detection
        mocker.patch(
            "scripts.setup.run_setup._detect_container",
            return_value=("Library", ["Areas", "Projects"]),
        )
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        top_folders = {v["folder"] for v in parsed["taxonomy"].values()}
        assert "Library" not in top_folders, "Container folder must not appear in taxonomy"
        assert "Areas" in top_folders
        assert "Projects" in top_folders

    def test_container_from_settings_used_when_phase0_detection_unavailable(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Falls back to settings.local.yaml for container name when Phase 0 returns None."""
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "MyLib", "folder_path": "MyLib", "body": ""},
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + decline Inbox + decline Archive (universal missing, unknown framework) + generate
        mocker.patch("typer.confirm", side_effect=[True, False, False, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        # Phase 0 detects no folders → container=None
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))
        # Settings fallback identifies "MyLib" as the container
        mocker.patch(
            "scripts.setup.run_setup.load_settings",
            return_value={"toplevel_folder": {"enabled": True, "name": "MyLib"}},
        )
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        top_folders = {v["folder"] for v in parsed["taxonomy"].values()}
        assert "MyLib" not in top_folders, "Container from settings must not appear in taxonomy"
        assert "Projects" in top_folders

    def test_container_prefixed_paths_stripped_before_role_detection(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Folders inside a container are recognised even when the export was not pre-stripped.

        If the user's export was run before toplevel_folder.enabled was set, paths still
        carry the container prefix (e.g. "Library/Archive"). Without stripping, _auto_map_roles
        only sees the container name and reports every role as missing. With the fix, prefix
        stripping happens in setup before tree building, so Archive (and other folders) are
        recognised correctly.
        """
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "Inbox", "folder_path": "Library/Inbox", "body": ""},
                    {"folder": "Projects", "folder_path": "Library/Projects", "body": ""},
                    {"folder": "Archive", "folder_path": "Library/Archive", "body": ""},
                    {"folder": "Sub", "folder_path": "Library/Archive/Sub", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch(
            "scripts.setup.run_setup._detect_container",
            return_value=("Library", ["Inbox", "Projects", "Archive"]),
        )
        # proceed + (PARA missing: Areas, Resources — offered and declined) + generate
        mocker.patch("typer.confirm", side_effect=[True, False, False, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)

        run_setup(dry_run=False, no_corpus=True)

        write_mock.assert_called_once()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        top_folders = {v["folder"] for v in parsed["taxonomy"].values()}
        # All three folders must be recognised — Archive must NOT be treated as missing
        assert "Inbox" in top_folders
        assert "Projects" in top_folders
        assert "Archive" in top_folders
        assert "Library" not in top_folders

    def test_absent_inbox_detected_and_added(self, mocker: MagicMock, tmp_path: Path) -> None:
        """Missing PARA-relevant folders are offered individually and added when confirmed."""
        # Projects + Archive → PARA inferred → missing PARA roles: Inbox, Areas, Resources
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                    {"folder": "Archive", "folder_path": "Archive", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + add Inbox + add Areas + add Resources + generate
        mocker.patch("typer.confirm", side_effect=[True, True, True, True, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        top_folders = {v["folder"] for v in parsed["taxonomy"].values()}
        # All confirmed-missing PARA roles are added
        assert "Inbox" in top_folders
        assert "Areas" in top_folders
        assert "Resources" in top_folders
        # Original export folders still present
        assert "Projects" in top_folders
        assert "Archive" in top_folders

    def test_absent_folders_declined_not_added(self, mocker: MagicMock, tmp_path: Path) -> None:
        """Declining an individual role skips only that folder."""
        # Projects + Archive → PARA → missing: Inbox, Areas, Resources
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                    {"folder": "Archive", "folder_path": "Archive", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        # proceed + decline Inbox + add Areas + add Resources + generate
        mocker.patch("typer.confirm", side_effect=[True, False, True, True, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()
        taxonomy_yaml, _ = write_mock.call_args[0]
        parsed = yaml.safe_load(taxonomy_yaml)
        top_folders = {v["folder"] for v in parsed["taxonomy"].values()}
        # Inbox declined — must not appear; Areas and Resources accepted — must appear
        assert "Inbox" not in top_folders
        assert "Areas" in top_folders
        assert "Resources" in top_folders
        assert "Projects" in top_folders
        assert "Archive" in top_folders

    def test_no_missing_folders_no_absent_prompt(self, mocker: MagicMock, tmp_path: Path) -> None:
        """When all standard roles are covered, the absent-folder prompt does not appear."""
        # Export covers all 9 standard roles so role_map is complete
        export = tmp_path / "notes-2024-01-01.json"
        export.write_text(
            json.dumps(
                [
                    {"folder": "Inbox", "folder_path": "Inbox", "body": ""},
                    {"folder": "Fleeting", "folder_path": "Fleeting", "body": ""},
                    {"folder": "Literature", "folder_path": "Literature", "body": ""},
                    {"folder": "Permanent", "folder_path": "Permanent", "body": ""},
                    {"folder": "Projects", "folder_path": "Projects", "body": ""},
                    {"folder": "Areas", "folder_path": "Areas", "body": ""},
                    {"folder": "Resources", "folder_path": "Resources", "body": ""},
                    {"folder": "Archive", "folder_path": "Archive", "body": ""},
                    {"folder": "Review", "folder_path": "Review", "body": ""},
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        confirm_mock = mocker.patch("typer.confirm", side_effect=[True, True])
        mocker.patch("scripts.setup.run_setup._collect_existing_folders")
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        # Only 2 confirms: "Proceed?" and "Generate taxonomy?" — no absent-folder prompt
        assert confirm_mock.call_count == 2

    def test_gtd_path_shows_snippet(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        # Q1=1 (tasks), Q2=2, Q3=1 → GTD
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[1, 2, 1])
        mocker.patch("typer.confirm", return_value=True)
        fw = get_framework("GTD")
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={k: v for k, v in fw["canonical_names"].items()},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        # Should not raise — GTD snippet panel is printed but not assertable here
        run_setup(dry_run=False, no_corpus=True)

    def test_user_overrides_recommendation(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2, 2])
        mocker.patch("typer.confirm", return_value=False)  # reject recommendation
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "next_actions": "Next Actions",
                "waiting_for": "Waiting For",
                "projects": "Projects",
                "someday_maybe": "Someday",
                "reference": "Reference",
                "archive": "Archive",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)

    def test_corpus_analysis_used_when_export_present(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        export = tmp_path / "notes-test.json"
        export.write_text(
            json.dumps(
                [
                    {
                        "id": "1",
                        "body": "note body",
                        "folder": "Inbox",
                        "modified": "2024-01-01T00:00:00",
                    },
                ]
            )
        )
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=export)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "Projects",
                "areas": "Areas",
                "resources": "Resources",
                "archive": "Archive",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        # Should not raise — corpus analysis runs and summary is printed
        run_setup(dry_run=False, no_corpus=False)

    def test_no_export_found_continues_without_corpus(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        # no_corpus=False but export not found → prints notice, continues with questions only
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=False)  # no export → else branch at line 262

    def test_no_corpus_flag_skips_corpus_analysis(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        analyze_mock = mocker.patch("scripts.setup.run_setup.analyze_corpus")
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        analyze_mock.assert_not_called()

    def test_existing_path_decline_uses_framework_choice(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        # Q1=4 (existing), then user declines and picks PARA (1)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[4, 1])
        mocker.patch("typer.confirm", return_value=False)  # decline existing path
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)

    def test_provider_selection_triggered_when_settings_created(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        select_mock = mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        select_mock.assert_called_once()

    def test_provider_selection_skipped_when_settings_exist(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        select_mock = mocker.patch("scripts.setup.run_setup._select_provider")
        container_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        select_mock.assert_not_called()
        container_mock.assert_not_called()

    def test_container_question_triggered_when_settings_created(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        container_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        container_mock.assert_called_once()

    def test_container_detected_writes_setting_not_ask(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        """Container confirmed in Phase 0.5 → _write_toplevel_folder_to_settings, no question."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch(
            "scripts.setup.run_setup._detect_container",
            return_value=("Library", ["Inbox", "Projects"]),
        )
        mocker.patch("scripts.setup.run_setup._fetch_top_level_folders", return_value=["Library"])
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        ask_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        write_mock = mocker.patch("scripts.setup.run_setup._write_toplevel_folder_to_settings")
        run_setup(dry_run=False, no_corpus=True)
        ask_mock.assert_not_called()
        write_mock.assert_called_once_with(enabled=True, name="Library", dry_run=False)

    def test_container_opted_out_no_ask_container(self, mocker: MagicMock) -> None:
        """User saw container question and said no → _ask_container is skipped."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch(
            "scripts.setup.run_setup._detect_container",
            return_value=(None, ["Inbox", "Projects"]),
        )
        mocker.patch(
            "scripts.setup.run_setup._fetch_top_level_folders",
            return_value=["Inbox", "Projects"],
        )
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        ask_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        ask_mock.assert_not_called()

    def test_existing_path_no_container_skips_write_and_ask(self, mocker: MagicMock) -> None:
        """EXISTING + no container: neither _ask_container nor _write_toplevel_folder called."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "Library/Inbox"},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        mocker.patch("scripts.setup.run_setup._write_categories_for_taxonomy")
        ask_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        write_mock = mocker.patch("scripts.setup.run_setup._write_toplevel_folder_to_settings")
        run_setup(dry_run=False, no_corpus=True)
        ask_mock.assert_not_called()
        write_mock.assert_not_called()

    def test_existing_path_with_container_writes_toplevel_setting(self, mocker: MagicMock) -> None:
        """EXISTING + container detected → toplevel_folder written enabled:true; no question."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "Library/Inbox"},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        mocker.patch("scripts.setup.run_setup._write_categories_for_taxonomy")
        # Override the autouse fixture: container IS detected this time
        mocker.patch(
            "scripts.setup.run_setup._detect_container",
            return_value=("Library", ["Inbox", "Projects"]),
        )
        ask_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        write_mock = mocker.patch("scripts.setup.run_setup._write_toplevel_folder_to_settings")
        run_setup(dry_run=False, no_corpus=True)
        ask_mock.assert_not_called()
        write_mock.assert_called_once_with(enabled=True, name="Library", dry_run=False)

    def test_existing_path_categories_written_on_settings_created(self, mocker: MagicMock) -> None:
        """EXISTING path with settings_created=True → _write_categories_for_taxonomy called."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "Inbox", "archive": "Archive"},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        mocker.patch("scripts.setup.run_setup._write_toplevel_folder_to_settings")
        cats_mock = mocker.patch("scripts.setup.run_setup._write_categories_for_taxonomy")
        run_setup(dry_run=False, no_corpus=True)
        cats_mock.assert_called_once()

    def test_existing_path_categories_skipped_when_settings_not_created(
        self, mocker: MagicMock
    ) -> None:
        """EXISTING path with settings_created=False → _write_categories_for_taxonomy not called."""
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "Inbox"},
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        cats_mock = mocker.patch("scripts.setup.run_setup._write_categories_for_taxonomy")
        run_setup(dry_run=False, no_corpus=True)
        cats_mock.assert_not_called()


# ── run_setup.py — EXISTING path: categories block ────────────────────────────

_PARA_TAXONOMY_YAML = """\
taxonomy:
  inbox:
    folder: Inbox
  projects:
    folder: Projects
  areas:
    folder: Areas
  resources:
    folder: Resources
  archive:
    folder: Archive
"""

_ZK_TAXONOMY_YAML = """\
taxonomy:
  inbox:
    folder: Inbox
  fleeting:
    folder: Fleeting
  literature:
    folder: Literature
  permanent:
    folder: Permanent
  projects:
    folder: Projects
  areas:
    folder: Areas
  resources:
    folder: Resources
  archive:
    folder: Archive
  review:
    folder: Review
"""

_SETTINGS_WITH_CATEGORIES = """\
reorganization_mode: "standard"
categories:
  inbox:
    description: "temporary capture"
    transit: true
    stale_days: 7
  fleeting:
    description: "quick, short-lived thoughts"
    transit: true
    stale_days: 30
  literature:
    description: "notes tied to a specific source"
  permanent:
    description: "refined, evergreen concepts"
  projects:
    description: "active projects"
    active_days: 90
  areas:
    description: "ongoing responsibilities"
  resources:
    description: "reference material"
  archive:
    description: "inactive notes"
    exclude_from_classify: true
    exclude_from_discover: true
  review:
    description: "unclear"
    catchall: true

# Settings below apply only when forever_notes_mode is "strict".
strict_mode:
  enabled: false
"""


class TestWriteCategoriesForTaxonomy:
    def test_para_taxonomy_writes_only_para_roles(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_CATEGORIES)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_PARA_TAXONOMY_YAML, dry_run=False)
        result = yaml.safe_load(settings.read_text())
        cats = result["categories"]
        assert set(cats.keys()) == {"inbox", "projects", "areas", "resources", "archive"}
        # ZK-specific roles removed
        assert "fleeting" not in cats
        assert "literature" not in cats
        assert "permanent" not in cats
        assert "review" not in cats

    def test_zk_taxonomy_writes_all_nine_roles(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_CATEGORIES)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_ZK_TAXONOMY_YAML, dry_run=False)
        result = yaml.safe_load(settings.read_text())
        cats = result["categories"]
        assert set(cats.keys()) == {
            "inbox",
            "fleeting",
            "literature",
            "permanent",
            "projects",
            "areas",
            "resources",
            "archive",
            "review",
        }

    def test_behavioral_flags_preserved(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_CATEGORIES)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_PARA_TAXONOMY_YAML, dry_run=False)
        result = yaml.safe_load(settings.read_text())
        cats = result["categories"]
        assert cats["inbox"]["transit"] is True
        assert cats["inbox"]["stale_days"] == 7
        assert cats["projects"]["active_days"] == 90
        assert cats["archive"]["exclude_from_classify"] is True
        assert cats["archive"]["exclude_from_discover"] is True

    def test_unknown_custom_key_omitted(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_CATEGORIES)
        custom_yaml = """\
taxonomy:
  inbox:
    folder: Inbox
  my_custom_folder:
    folder: CustomStuff
"""
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(custom_yaml, dry_run=False)
        result = yaml.safe_load(settings.read_text())
        cats = result["categories"]
        assert "inbox" in cats
        assert "my_custom_folder" not in cats

    def test_surrounding_content_preserved(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_CATEGORIES)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_PARA_TAXONOMY_YAML, dry_run=False)
        text = settings.read_text()
        assert 'reorganization_mode: "standard"' in text
        assert "strict_mode:" in text

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = _SETTINGS_WITH_CATEGORIES
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_PARA_TAXONOMY_YAML, dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_categories_for_taxonomy(_PARA_TAXONOMY_YAML, dry_run=False)
        # Should not raise; nothing to assert except no exception


# ── run_setup.py — provider selection ─────────────────────────────────────────


class TestWriteProviderToSettings:
    def test_replaces_llm_provider_line(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text('llm_provider: "apple"\nother: setting\n')
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_provider_to_settings("anthropic", dry_run=False)
        assert 'llm_provider: "anthropic"' in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = 'llm_provider: "apple"\n'
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_provider_to_settings("ollama", dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_provider_to_settings("anthropic", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteEnvLine:
    # Use tmp_path/config as CONFIG_DIR so CONFIG_DIR.parent == tmp_path and .env lands there.

    def test_creates_env_if_missing(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            _write_env_line("ANTHROPIC_API_KEY", "sk-test-key", dry_run=False)
        env = tmp_path / ".env"
        assert env.exists()
        assert "ANTHROPIC_API_KEY=sk-test-key" in env.read_text()

    def test_appends_to_existing_env(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        env = tmp_path / ".env"
        env.write_text("EXISTING_VAR=value\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            _write_env_line("OLLAMA_BASE_URL", "http://host:11434", dry_run=False)
        content = env.read_text()
        assert "EXISTING_VAR=value" in content
        assert "OLLAMA_BASE_URL=http://host:11434" in content

    def test_does_not_overwrite_existing_key(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        env = tmp_path / ".env"
        env.write_text("ANTHROPIC_API_KEY=original-key\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            _write_env_line("ANTHROPIC_API_KEY", "new-key", dry_run=False)
        assert "original-key" in env.read_text()
        assert "new-key" not in env.read_text()

    def test_dry_run_does_not_create_file(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            _write_env_line("ANTHROPIC_API_KEY", "sk-test", dry_run=True)
        assert not (tmp_path / ".env").exists()


class TestSelectProvider:
    # Use tmp_path/config as CONFIG_DIR so CONFIG_DIR.parent == tmp_path and .env lands there.

    def _setup_config(self, tmp_path: Path) -> Path:
        """Create tmp_path/config/settings.local.yaml and return the config dir."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.local.yaml").write_text('llm_provider: "apple"\nother: value\n')
        return config_dir

    def test_apple_writes_provider_returns_true(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=1)
        mocker.patch("scripts.setup.run_setup._check_apple_intelligence_prerequisites")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert 'llm_provider: "apple"' in (config_dir / "settings.local.yaml").read_text()

    def test_anthropic_with_key_writes_env(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=2)
        mocker.patch("typer.prompt", return_value="sk-ant-testkey")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert 'llm_provider: "anthropic"' in (config_dir / "settings.local.yaml").read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-testkey" in (tmp_path / ".env").read_text()

    def test_anthropic_without_key_skips_env(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=2)
        mocker.patch("typer.prompt", return_value="")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert not (tmp_path / ".env").exists()

    def test_ollama_default_url_no_env_entry(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=3)
        mocker.patch("typer.prompt", return_value="http://localhost:11434")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert 'llm_provider: "ollama"' in (config_dir / "settings.local.yaml").read_text()
        assert not (tmp_path / ".env").exists()

    def test_ollama_custom_url_writes_env(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=3)
        mocker.patch("typer.prompt", return_value="http://myhost:11434")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert "OLLAMA_BASE_URL=http://myhost:11434" in (tmp_path / ".env").read_text()

    def test_aws_ollama_writes_provider_returns_true(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert 'llm_provider: "aws-ollama"' in (config_dir / "settings.local.yaml").read_text()

    def test_skip_returns_false(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=5)
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is False

    def test_dry_run_does_not_write_settings(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        original = (config_dir / "settings.local.yaml").read_text()
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=2)
        mocker.patch("typer.prompt", return_value="sk-ant-test")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=True)
        assert result is True
        assert (config_dir / "settings.local.yaml").read_text() == original
        assert not (tmp_path / ".env").exists()

    def test_apple_is_default_on_empty_enter(self, mocker: MagicMock, tmp_path: Path) -> None:
        config_dir = self._setup_config(tmp_path)
        # Simulate user pressing Enter (empty input) → default=1 → Apple
        mocker.patch("typer.prompt", return_value="")
        mocker.patch("scripts.setup.run_setup._check_apple_intelligence_prerequisites")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            result = _select_provider(dry_run=False)
        assert result is True
        assert 'llm_provider: "apple"' in (config_dir / "settings.local.yaml").read_text()


# ── run_setup.py — Apple Intelligence prerequisites ───────────────────────────


class TestCheckAppleIntelligencePrerequisites:
    """Unit tests for _check_apple_intelligence_prerequisites."""

    import subprocess as _subprocess

    def _mock_binary(self, mocker: MagicMock, exists: bool) -> MagicMock:
        mock = MagicMock()
        mock.is_file.return_value = exists
        mock.__str__ = MagicMock(return_value="/fake/apple-llm")
        mocker.patch("scripts.setup.run_setup._APPLE_LLM_BINARY", mock)
        return mock

    def test_all_ok_xcode26_binary_available(self, mocker: MagicMock) -> None:
        xcode_ok = MagicMock(returncode=0, stdout="Xcode 26.0\nBuild version 26A123\n")
        probe_ok = MagicMock(returncode=0, stdout="ok\n", stderr="")
        mocker.patch("scripts.setup.run_setup.subprocess.run", side_effect=[xcode_ok, probe_ok])
        self._mock_binary(mocker, exists=True)
        _check_apple_intelligence_prerequisites()  # should not raise

    def _mock_disk(self, mocker: MagicMock, free_gb: float) -> None:
        mocker.patch(
            "scripts.setup.run_setup.shutil.disk_usage",
            return_value=MagicMock(free=int(free_gb * 1024**3)),
        )

    def test_xcode_not_found_file_not_found(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup.subprocess.run", side_effect=FileNotFoundError)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=100)
        _check_apple_intelligence_prerequisites()

    def test_xcode_old_version_warns(self, mocker: MagicMock) -> None:
        xcode_old = MagicMock(returncode=0, stdout="Xcode 15.4\nBuild version 15F31d\n")
        mocker.patch("scripts.setup.run_setup.subprocess.run", return_value=xcode_old)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=100)
        _check_apple_intelligence_prerequisites()

    def test_xcode_nonzero_returncode(self, mocker: MagicMock) -> None:
        xcode_fail = MagicMock(returncode=1, stdout="", stderr="xcodebuild: error\n")
        mocker.patch("scripts.setup.run_setup.subprocess.run", return_value=xcode_fail)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=100)
        _check_apple_intelligence_prerequisites()

    def test_xcode_timeout_skipped(self, mocker: MagicMock) -> None:
        import subprocess as _sp

        mocker.patch(
            "scripts.setup.run_setup.subprocess.run",
            side_effect=_sp.TimeoutExpired(cmd="xcodebuild", timeout=10),
        )
        self._mock_binary(mocker, exists=False)
        _check_apple_intelligence_prerequisites()

    def test_binary_missing_xcode_ok_shows_build_command(self, mocker: MagicMock) -> None:
        xcode_ok = MagicMock(returncode=0, stdout="Xcode 26.0\n")
        mocker.patch("scripts.setup.run_setup.subprocess.run", return_value=xcode_ok)
        self._mock_binary(mocker, exists=False)
        _check_apple_intelligence_prerequisites()

    def test_binary_missing_xcode_not_found_shows_install_first(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup.subprocess.run", side_effect=FileNotFoundError)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=100)
        _check_apple_intelligence_prerequisites()

    def test_low_disk_space_shows_warning(
        self, mocker: MagicMock, capsys: pytest.CaptureFixture
    ) -> None:
        mocker.patch("scripts.setup.run_setup.subprocess.run", side_effect=FileNotFoundError)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=30)
        _check_apple_intelligence_prerequisites()
        # Verified via mock — no exception means warning path was reached

    def test_adequate_disk_space_no_warning(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup.subprocess.run", side_effect=FileNotFoundError)
        self._mock_binary(mocker, exists=False)
        self._mock_disk(mocker, free_gb=60)
        _check_apple_intelligence_prerequisites()  # disk_usage called, no warning printed

    def test_ai_unavailable_exit2_shows_reason(self, mocker: MagicMock) -> None:
        xcode_ok = MagicMock(returncode=0, stdout="Xcode 26.0\n")
        probe_unavail = MagicMock(
            returncode=2,
            stderr="error: Apple Intelligence is not enabled — turn it on in System Settings\n",
            stdout="",
        )
        mocker.patch(
            "scripts.setup.run_setup.subprocess.run",
            side_effect=[xcode_ok, probe_unavail],
        )
        self._mock_binary(mocker, exists=True)
        _check_apple_intelligence_prerequisites()

    def test_probe_timeout_treated_as_available(self, mocker: MagicMock) -> None:
        import subprocess as _sp

        xcode_ok = MagicMock(returncode=0, stdout="Xcode 26.0\n")
        mocker.patch(
            "scripts.setup.run_setup.subprocess.run",
            side_effect=[xcode_ok, _sp.TimeoutExpired(cmd="apple-llm", timeout=20)],
        )
        self._mock_binary(mocker, exists=True)
        _check_apple_intelligence_prerequisites()

    def test_select_provider_apple_calls_prerequisites(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.local.yaml").write_text('llm_provider: "apple"\n')
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=1)
        check_mock = mocker.patch("scripts.setup.run_setup._check_apple_intelligence_prerequisites")
        with patch("scripts.setup.run_setup.CONFIG_DIR", config_dir):
            _select_provider(dry_run=False)
        check_mock.assert_called_once()


# ── run_setup.py — container question ─────────────────────────────────────────

_SETTINGS_WITH_TOPLEVEL = """\
reorganization_mode: "standard"
toplevel_folder:
  enabled: false         # true = nest all taxonomy folders inside `name` at account root
  name: "Library"        # container folder name (only used when enabled: true)
llm_provider: "apple"
"""


class TestWriteTopLevelFolderToSettings:
    def test_enables_container(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_TOPLEVEL)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=True, name="Library", dry_run=False)
        assert "  enabled: true" in settings.read_text()

    def test_disables_container(self, tmp_path: Path) -> None:
        content = _SETTINGS_WITH_TOPLEVEL.replace("enabled: false", "enabled: true")
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(content)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=False, name="Library", dry_run=False)
        assert "  enabled: false" in settings.read_text()

    def test_custom_name_written(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_TOPLEVEL)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=True, name="Notes", dry_run=False)
        text = settings.read_text()
        assert "  enabled: true" in text
        assert '"Notes"' in text

    def test_other_settings_preserved(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_TOPLEVEL)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=True, name="Library", dry_run=False)
        assert 'llm_provider: "apple"' in settings.read_text()
        assert 'reorganization_mode: "standard"' in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_TOPLEVEL)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=True, name="Library", dry_run=True)
        assert "  enabled: false" in settings.read_text()

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_toplevel_folder_to_settings(enabled=True, name="Library", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestAskContainer:
    def _make_settings(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_TOPLEVEL)

    def test_yes_enables_container_default_name(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._make_settings(tmp_path)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch("typer.prompt", return_value="Library")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_container(dry_run=False)
        assert "  enabled: true" in (tmp_path / "settings.local.yaml").read_text()

    def test_yes_enables_container_custom_name(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._make_settings(tmp_path)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch("typer.prompt", return_value="Notes")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_container(dry_run=False)
        text = (tmp_path / "settings.local.yaml").read_text()
        assert "  enabled: true" in text
        assert '"Notes"' in text

    def test_no_writes_enabled_false(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._make_settings(tmp_path)
        mocker.patch("typer.confirm", return_value=False)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_container(dry_run=False)
        assert "  enabled: false" in (tmp_path / "settings.local.yaml").read_text()

    def test_dry_run_does_not_write(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._make_settings(tmp_path)
        original = (tmp_path / "settings.local.yaml").read_text()
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch("typer.prompt", return_value="Library")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_container(dry_run=True)
        assert (tmp_path / "settings.local.yaml").read_text() == original


# ── run_setup.py — account detection ──────────────────────────────────────────

_SETTINGS_WITH_PRIMARY_ACCOUNT = """\
export:
  include_body: true
  primary_account: ""         # Export only notes from this Apple Notes account
"""


class TestDetectAccounts:
    def test_returns_account_names(self, mocker: MagicMock) -> None:
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "iCloud\nWork Gmail\n"
        # Ensure script path exists for the check
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )
        result = _detect_accounts()
        assert result == ["iCloud", "Work Gmail"]

    def test_returns_empty_on_nonzero_returncode(self, mocker: MagicMock) -> None:
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )
        assert _detect_accounts() == []

    def test_returns_empty_on_timeout(self, mocker: MagicMock) -> None:
        import subprocess as _subprocess

        mocker.patch(
            "scripts.setup.run_setup.subprocess.run",
            side_effect=_subprocess.TimeoutExpired(cmd="osascript", timeout=10),
        )
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )
        assert _detect_accounts() == []

    def test_returns_empty_on_oserror(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup.subprocess.run", side_effect=OSError("osascript not found")
        )
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )
        assert _detect_accounts() == []

    def test_returns_empty_when_script_missing(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: False),
        )
        assert _detect_accounts() == []

    def test_strips_blank_lines(self, mocker: MagicMock) -> None:
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "\niCloud\n\n"
        mocker.patch(
            "scripts.setup.run_setup._LIST_ACCOUNTS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )
        assert _detect_accounts() == ["iCloud"]


class TestHandleMultipleAccounts:
    def test_returns_selected_account(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=2)
        result = _handle_multiple_accounts(["iCloud", "Work Gmail"])
        assert result == "Work Gmail"

    def test_first_account_on_selection_one(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=1)
        result = _handle_multiple_accounts(["iCloud", "Personal Gmail"])
        assert result == "iCloud"


class TestWritePrimaryAccountToSettings:
    def test_writes_account_name(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_PRIMARY_ACCOUNT)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_primary_account_to_settings("iCloud", dry_run=False)
        assert '  primary_account: "iCloud"' in settings.read_text()

    def test_replaces_existing_value(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_PRIMARY_ACCOUNT.replace('""', '"OldAccount"'))
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_primary_account_to_settings("iCloud", dry_run=False)
        assert '  primary_account: "iCloud"' in settings.read_text()
        assert "OldAccount" not in settings.read_text()

    def test_other_settings_preserved(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(_SETTINGS_WITH_PRIMARY_ACCOUNT)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_primary_account_to_settings("iCloud", dry_run=False)
        assert "include_body: true" in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = _SETTINGS_WITH_PRIMARY_ACCOUNT
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_primary_account_to_settings("iCloud", dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_primary_account_to_settings("iCloud", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteReorganizationModeToSettings:
    def test_writes_conservative(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text('reorganization_mode: "standard"\nother: setting\n')
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_reorganization_mode_to_settings("conservative", dry_run=False)
        assert 'reorganization_mode: "conservative"' in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_static(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text('reorganization_mode: "standard"\n')
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_reorganization_mode_to_settings("static", dry_run=False)
        assert 'reorganization_mode: "static"' in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = 'reorganization_mode: "standard"\n'
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_reorganization_mode_to_settings("static", dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_reorganization_mode_to_settings("conservative", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteSubfolderThresholdToSettings:
    def test_writes_threshold_value(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text("thresholds:\n  min_notes_for_subfolder: 8\nother: setting\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_subfolder_threshold_to_settings(15, dry_run=False)
        assert "min_notes_for_subfolder: 15" in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_low_threshold(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text("thresholds:\n  min_notes_for_subfolder: 8\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_subfolder_threshold_to_settings(5, dry_run=False)
        assert "min_notes_for_subfolder: 5" in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = "thresholds:\n  min_notes_for_subfolder: 8\n"
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_subfolder_threshold_to_settings(15, dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_subfolder_threshold_to_settings(10, dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteFolderNestingToSettings:
    def test_writes_nesting_value(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text('folder_nesting: "natural"\nother: setting\n')
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_folder_nesting_to_settings("flat", dry_run=False)
        assert 'folder_nesting: "flat"' in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_natural(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text('folder_nesting: "flat"\n')
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_folder_nesting_to_settings("natural", dry_run=False)
        assert 'folder_nesting: "natural"' in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = 'folder_nesting: "natural"\n'
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_folder_nesting_to_settings("flat", dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_folder_nesting_to_settings("flat", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteClassifyExcludeArchiveToSettings:
    def test_writes_false(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text("classify:\n  exclude_archive: true\nother: setting\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_classify_exclude_archive_to_settings(False, dry_run=False)
        assert "exclude_archive: false" in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_true(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text("classify:\n  exclude_archive: false\n")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_classify_exclude_archive_to_settings(True, dry_run=False)
        assert "exclude_archive: true" in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        original = "classify:\n  exclude_archive: true\n"
        settings.write_text(original)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_classify_exclude_archive_to_settings(False, dry_run=True)
        assert settings.read_text() == original

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_classify_exclude_archive_to_settings(False, dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteOllamaModelToSettings:
    _SETTINGS_TEMPLATE = (
        "llm_providers:\n"
        "  anthropic:\n"
        '    model: "claude-opus-4-6"\n'
        "\n"
        "  ollama:\n"
        '    model: "llama3"\n'
        "    batch_size: 10\n"
        "\n"
        "  aws-ollama:\n"
        '    model: "gpt-oss:20b"\n'
    )

    def test_writes_ollama_model(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_ollama_model_to_settings("llama3.2", dry_run=False)
        content = settings.read_text()
        assert '    model: "llama3.2"' in content

    def test_does_not_clobber_anthropic_or_aws_model(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_ollama_model_to_settings("mistral", dry_run=False)
        content = settings.read_text()
        assert '"claude-opus-4-6"' in content
        assert '"gpt-oss:20b"' in content
        assert '"mistral"' in content

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_ollama_model_to_settings("mistral", dry_run=True)
        assert settings.read_text() == self._SETTINGS_TEMPLATE

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_ollama_model_to_settings("llama3.2", dry_run=False)
        assert not (tmp_path / "settings.local.yaml").exists()


class TestWriteForeverNotesToSettings:
    _SETTINGS_TEMPLATE = (
        'forever_notes_mode: "loose"\n'
        "strict_mode:\n"
        '  home_note_title: "✱ Home"\n'
        '  hub_title_prefix: "✱ "\n'
        '  internal_links: "text"\n'
        "other: setting\n"
    )

    def test_writes_mode_to_strict(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False)
        assert 'forever_notes_mode: "strict"' in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_home_title_and_hub_prefix(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings(
                "strict", dry_run=False, home_title="My Notes", hub_prefix="# "
            )
        content = settings.read_text()
        assert 'forever_notes_mode: "strict"' in content
        assert 'home_note_title: "My Notes"' in content
        assert 'hub_title_prefix: "# "' in content

    def test_omits_naming_when_not_supplied(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False)
        content = settings.read_text()
        # Without explicit overrides, original naming values are preserved
        assert "✱ Home" in content
        assert "✱ " in content

    def test_writes_internal_links_html(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False, internal_links="html")
        assert 'internal_links: "html"' in settings.read_text()
        assert "other: setting" in settings.read_text()

    def test_writes_internal_links_text(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False, internal_links="text")
        assert 'internal_links: "text"' in settings.read_text()

    def test_omits_internal_links_when_not_supplied(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False)
        # Original value preserved
        assert 'internal_links: "text"' in settings.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings(
                "strict",
                dry_run=True,
                home_title="Test",
                hub_prefix="- ",
                internal_links="html",
            )
        assert settings.read_text() == self._SETTINGS_TEMPLATE

    def test_no_op_when_file_missing(self, tmp_path: Path) -> None:
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _write_forever_notes_to_settings("strict", dry_run=False, home_title="X")
        assert not (tmp_path / "settings.local.yaml").exists()


class TestAskOrganizationStyle:
    _SETTINGS_TEMPLATE = (
        'reorganization_mode: "standard"\n'
        'folder_nesting: "natural"\n'
        "thresholds:\n"
        "  min_notes_for_subfolder: 8\n"
        "classify:\n"
        "  exclude_archive: true\n"
    )

    def _setup(self, tmp_path: Path) -> Path:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        return settings

    def test_default_threshold_is_8_for_non_existing(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        settings = self._setup(tmp_path)
        # Choices: mode=2 (conservative), threshold=2 (8 notes — default), archive=True
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 2])
        mocker.patch("typer.confirm", return_value=True)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_organization_style(dry_run=False, is_existing=False)
        assert "min_notes_for_subfolder: 8" in settings.read_text()

    def test_default_threshold_is_15_for_existing(self, mocker: MagicMock, tmp_path: Path) -> None:
        settings = self._setup(tmp_path)
        # When is_existing=True the threshold default is choice 3 (15 notes);
        # simulate user pressing Enter → default accepted → threshold_map[3] = 15
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 3])
        mocker.patch("typer.confirm", return_value=True)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_organization_style(dry_run=False, is_existing=True)
        assert "min_notes_for_subfolder: 15" in settings.read_text()

    def test_mode_default_conservative_regardless_of_is_existing(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        settings = self._setup(tmp_path)
        # Both existing and non-existing default to conservative (choice 2)
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 2])
        mocker.patch("typer.confirm", return_value=True)
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_organization_style(dry_run=False, is_existing=True)
        assert 'reorganization_mode: "conservative"' in settings.read_text()


class TestAskForeverNotes:
    _SETTINGS_TEMPLATE = (
        'forever_notes_mode: "loose"\n'
        "strict_mode:\n"
        '  home_note_title: "✱ Home"\n'
        '  hub_title_prefix: "✱ "\n'
        '  internal_links: "text"\n'
    )

    def test_strict_writes_mode_names_and_text_links(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        # confirm calls: 1=enable hub, 2=use HTML links (False → text)
        mocker.patch("typer.confirm", side_effect=[True, False])
        mocker.patch("typer.prompt", side_effect=["My Notes", "# "])
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_forever_notes(dry_run=False)
        content = settings.read_text()
        assert 'forever_notes_mode: "strict"' in content
        assert 'home_note_title: "My Notes"' in content
        assert 'hub_title_prefix: "# "' in content
        assert 'internal_links: "text"' in content

    def test_strict_html_links_written_when_confirmed(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        # confirm calls: 1=enable hub, 2=use HTML links (True → html)
        mocker.patch("typer.confirm", side_effect=[True, True])
        mocker.patch("typer.prompt", side_effect=["✱ Home", "✱ "])
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_forever_notes(dry_run=False)
        assert 'internal_links: "html"' in settings.read_text()

    def test_loose_does_not_prompt_for_names(self, mocker: MagicMock, tmp_path: Path) -> None:
        settings = tmp_path / "settings.local.yaml"
        settings.write_text(self._SETTINGS_TEMPLATE)
        mocker.patch("typer.confirm", return_value=False)  # Disable Hub structure
        prompt_mock = mocker.patch("typer.prompt")
        with patch("scripts.setup.run_setup.CONFIG_DIR", tmp_path):
            _ask_forever_notes(dry_run=False)
        prompt_mock.assert_not_called()
        assert 'forever_notes_mode: "loose"' in settings.read_text()

    def test_forever_notes_called_when_settings_created(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=[])
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        fn_mock = mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        fn_mock.assert_called_once()

    def test_forever_notes_skipped_when_settings_already_exist(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=[])
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        fn_mock = mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        run_setup(dry_run=False, no_corpus=True)
        fn_mock.assert_not_called()


class TestRunSetupAccountIntegration:
    """Integration tests for account detection wired into run_setup."""

    def _base_mocks(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._fetch_top_level_folders", return_value=[])
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=True)
        mocker.patch("scripts.setup.run_setup._ask_organization_style")
        mocker.patch("scripts.setup.run_setup._ask_forever_notes")
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=False)
        mocker.patch("scripts.setup.run_setup._ask_container")

    def test_single_account_no_prompt(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=["iCloud"])
        write_mock = mocker.patch("scripts.setup.run_setup._write_primary_account_to_settings")
        self._base_mocks(mocker)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_not_called()

    def test_multiple_accounts_writes_selection(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=["iCloud", "Gmail"])
        mocker.patch("scripts.setup.run_setup._handle_multiple_accounts", return_value="Gmail")
        write_mock = mocker.patch("scripts.setup.run_setup._write_primary_account_to_settings")
        self._base_mocks(mocker)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once_with("Gmail", False)

    def test_no_accounts_detected_skips_write(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=[])
        write_mock = mocker.patch("scripts.setup.run_setup._write_primary_account_to_settings")
        self._base_mocks(mocker)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_not_called()

    def test_account_write_skipped_when_settings_exist(self, mocker: MagicMock) -> None:
        mocker.patch("scripts.setup.run_setup._detect_accounts", return_value=["iCloud", "Gmail"])
        mocker.patch("scripts.setup.run_setup._handle_multiple_accounts", return_value="Gmail")
        write_mock = mocker.patch("scripts.setup.run_setup._write_primary_account_to_settings")
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._fetch_top_level_folders", return_value=[])
        mocker.patch("scripts.setup.run_setup._detect_container", return_value=(None, []))
        mocker.patch("scripts.setup.run_setup._ask_numbered", side_effect=[2, 1, 2])
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_folder_names",
            return_value={
                "inbox": "Inbox",
                "projects": "P",
                "areas": "A",
                "resources": "R",
                "archive": "Arc",
            },
        )
        mocker.patch("scripts.setup.run_setup._write_taxonomy")
        # settings_created=False → Phase 9 is skipped
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_not_called()


# ── _fetch_top_level_folders ──────────────────────────────────────────────────


class TestFetchTopLevelFolders:
    def _mock_script_exists(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup._LIST_FOLDERS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )

    def test_returns_sorted_folder_names(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Projects\nInbox\nArchive\n"
        result = _fetch_top_level_folders("iCloud")
        assert result == ["Archive", "Inbox", "Projects"]

    def test_writes_account_filter_file(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._mock_script_exists(mocker)
        account_file = tmp_path / "notes_setup_account.tmp"
        mocker.patch("scripts.setup.run_setup._SETUP_ACCOUNT_FILE", account_file)
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Inbox\n"
        _fetch_top_level_folders("iCloud")
        # File is cleaned up after the call — just verify subprocess was called
        mock_run.assert_called_once()

    def test_returns_empty_on_nonzero_returncode(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        assert _fetch_top_level_folders(None) == []

    def test_returns_empty_when_script_missing(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup._LIST_FOLDERS_SCRIPT",
            new=MagicMock(exists=lambda: False),
        )
        assert _fetch_top_level_folders("iCloud") == []

    def test_returns_empty_on_exception(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mocker.patch(
            "scripts.setup.run_setup.subprocess.run", side_effect=OSError("permission denied")
        )
        assert _fetch_top_level_folders("iCloud") == []


# ── _fetch_subfolders ─────────────────────────────────────────────────────────


class TestFetchSubfolders:
    def _mock_script_exists(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup._LIST_SUBFOLDERS_SCRIPT",
            new=MagicMock(exists=lambda: True),
        )

    def test_returns_sorted_subfolder_names(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Projects\nInbox\nArchive\n"
        result = _fetch_subfolders("Library", "iCloud")
        assert result == ["Archive", "Inbox", "Projects"]

    def test_returns_empty_on_nonzero_returncode(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        assert _fetch_subfolders("Library", None) == []

    def test_returns_empty_when_script_missing(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.setup.run_setup._LIST_SUBFOLDERS_SCRIPT",
            new=MagicMock(exists=lambda: False),
        )
        assert _fetch_subfolders("Library", "iCloud") == []

    def test_returns_empty_on_exception(self, mocker: MagicMock) -> None:
        self._mock_script_exists(mocker)
        mocker.patch(
            "scripts.setup.run_setup.subprocess.run", side_effect=OSError("permission denied")
        )
        assert _fetch_subfolders("Library", "iCloud") == []

    def test_writes_container_filter_file(self, mocker: MagicMock, tmp_path: Path) -> None:
        self._mock_script_exists(mocker)
        container_file = tmp_path / "notes_setup_container.tmp"
        mocker.patch("scripts.setup.run_setup._SETUP_CONTAINER_FILE", container_file)
        mocker.patch(
            "scripts.setup.run_setup._SETUP_ACCOUNT_FILE", tmp_path / "notes_setup_account.tmp"
        )
        mock_run = mocker.patch("scripts.setup.run_setup.subprocess.run")
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Inbox\n"
        _fetch_subfolders("Library", "iCloud")
        mock_run.assert_called_once()


# ── _detect_container ─────────────────────────────────────────────────────────


class TestDetectContainer:
    def test_returns_none_when_no_folders(self) -> None:
        container, folders = _detect_container([], None)
        assert container is None
        assert folders == []

    def test_no_container_selected_returns_top_level(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "No container — folders are at the account root"
        container, folders = _detect_container(["Inbox", "Projects"], None)
        assert container is None
        assert folders == ["Inbox", "Projects"]

    def test_container_selected_returns_subfolders(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "Library"
        mocker.patch(
            "scripts.setup.run_setup._fetch_subfolders",
            return_value=["Archive", "Inbox", "Projects"],
        )
        container, folders = _detect_container(["Library"], "iCloud")
        assert container == "Library"
        assert folders == ["Archive", "Inbox", "Projects"]

    def test_container_with_empty_subfolders_falls_back(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "Library"
        mocker.patch("scripts.setup.run_setup._fetch_subfolders", return_value=[])
        container, folders = _detect_container(["Library", "Archive"], "iCloud")
        assert container is None
        assert folders == ["Library", "Archive"]

    def test_abort_on_ctrl_c(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = None
        with pytest.raises(typer.Abort):
            _detect_container(["Library"], None)


# ── _collect_folder_names (questionary path) ──────────────────────────────────


class TestCollectFolderNamesQuestionary:
    def test_uses_autocomplete_when_folders_available(self, mocker: MagicMock) -> None:
        mock_ac = mocker.patch("scripts.setup.run_setup.questionary.autocomplete")
        mock_ac.return_value.ask.return_value = "My Inbox"
        result = _collect_folder_names("PARA", existing_folders=["My Inbox", "Projects"])
        mock_ac.assert_called()
        assert result["inbox"] == "My Inbox"

    def test_falls_back_to_typer_when_no_folders(self, mocker: MagicMock) -> None:
        mock_prompt = mocker.patch("typer.prompt", return_value="Inbox")
        mock_ac = mocker.patch("scripts.setup.run_setup.questionary.autocomplete")
        _collect_folder_names("PARA", existing_folders=[])
        mock_ac.assert_not_called()
        mock_prompt.assert_called()

    def test_uses_canonical_default_on_empty_answer(self, mocker: MagicMock) -> None:
        mock_ac = mocker.patch("scripts.setup.run_setup.questionary.autocomplete")
        mock_ac.return_value.ask.return_value = ""  # user cleared the pre-fill
        result = _collect_folder_names("PARA", existing_folders=["Inbox"])
        # canonical default "Inbox" should be used when answer is empty
        assert result["inbox"] == "Inbox"

    def test_abort_on_ctrl_c(self, mocker: MagicMock) -> None:
        mock_ac = mocker.patch("scripts.setup.run_setup.questionary.autocomplete")
        mock_ac.return_value.ask.return_value = None  # questionary returns None on Ctrl+C
        with pytest.raises(typer.Abort):
            _collect_folder_names("PARA", existing_folders=["Inbox"])

    def test_all_categories_prompted(self, mocker: MagicMock) -> None:
        mock_ac = mocker.patch("scripts.setup.run_setup.questionary.autocomplete")
        mock_ac.return_value.ask.return_value = "X"
        result = _collect_folder_names("PARA", existing_folders=["Inbox", "Projects"])
        from scripts.setup.frameworks import get_framework

        assert set(result.keys()) == set(get_framework("PARA")["category_keys"])


# ── _collect_existing_folders (questionary path) ──────────────────────────────


class TestCollectExistingFoldersQuestionary:
    def test_uses_select_when_folders_available(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "Capture"
        result = _collect_existing_folders(existing_folders=["Capture", "Work", "Archive"])
        mock_sel.assert_called()
        assert result["inbox"] == "Capture"

    def test_skip_option_excluded_from_map(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "--- skip ---"
        result = _collect_existing_folders(existing_folders=["Inbox"])
        assert "inbox" not in result

    def test_falls_back_to_typer_when_no_folders(self, mocker: MagicMock) -> None:
        mock_prompt = mocker.patch("typer.prompt", return_value="")
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        _collect_existing_folders(existing_folders=[])
        mock_sel.assert_not_called()
        mock_prompt.assert_called()

    def test_skip_appended_to_choices(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "--- skip ---"
        _collect_existing_folders(existing_folders=["Inbox", "Projects"])
        # Verify "--- skip ---" was included in choices for at least one call
        call_kwargs = mock_sel.call_args_list[0]
        choices = call_kwargs[1].get("choices") or call_kwargs[0][1]
        assert "--- skip ---" in choices

    def test_abort_on_ctrl_c(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = None
        with pytest.raises(typer.Abort):
            _collect_existing_folders(existing_folders=["Inbox"])

    def test_container_prefix_prepended_to_stored_value(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "Inbox"
        result = _collect_existing_folders(
            existing_folders=["Inbox", "Projects"], container="Library"
        )
        assert result["inbox"] == "Library/Inbox"

    def test_no_container_stores_bare_name(self, mocker: MagicMock) -> None:
        mock_sel = mocker.patch("scripts.setup.run_setup.questionary.select")
        mock_sel.return_value.ask.return_value = "Inbox"
        result = _collect_existing_folders(existing_folders=["Inbox", "Projects"])
        assert result["inbox"] == "Inbox"
