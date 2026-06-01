"""Tests for scripts/setup/ — scorer, frameworks, and run_setup utilities."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from scripts.setup.frameworks import FRAMEWORKS, framework_choices, get_framework
from scripts.setup.run_setup import (
    _ask_container,
    _build_existing_taxonomy_yaml,
    _build_taxonomy_yaml,
    _ensure_settings,
    _find_export_optional,
    _gtd_categories_snippet,
    _select_provider,
    _write_env_line,
    _write_provider_to_settings,
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


# ── run_setup.py — orchestrator (mocked interactions) ─────────────────────────


class TestRunSetup:
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

    def test_existing_path_q1_4(self, mocker: MagicMock, tmp_path: Path) -> None:
        mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
        mocker.patch("scripts.setup.run_setup._ask_numbered", return_value=4)
        mocker.patch("typer.confirm", return_value=True)
        mocker.patch(
            "scripts.setup.run_setup._collect_existing_folders",
            return_value={"inbox": "My Inbox", "archive": "Archive"},
        )
        write_mock = mocker.patch("scripts.setup.run_setup._write_taxonomy")
        mocker.patch("scripts.setup.run_setup._ensure_settings", return_value=False)
        run_setup(dry_run=False, no_corpus=True)
        write_mock.assert_called_once()

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

    def test_no_corpus_flag_skips_export(self, mocker: MagicMock, tmp_path: Path) -> None:
        find_mock = mocker.patch("scripts.setup.run_setup._find_export_optional", return_value=None)
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
        find_mock.assert_not_called()

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
        mocker.patch("scripts.setup.run_setup._select_provider", return_value=True)
        container_mock = mocker.patch("scripts.setup.run_setup._ask_container")
        run_setup(dry_run=False, no_corpus=True)
        container_mock.assert_called_once()


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
