"""Tests for scripts/classify/classify_notes.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.classify.classify_notes import (
    _build_folder_path,
    _subfolder_str,
    _subfolders,
    classify_batch,
    classify_batch_resilient,
    inject_taxonomy,
    price_per_million,
    run_classify,
)
from scripts.folder_utils import folder_name
from scripts.json_utils import extract_json_array, is_context_overflow


class TestExtractJsonArray:
    def test_plain_array(self) -> None:
        result = extract_json_array('[{"id": "1", "folder": "Inbox"}]')
        assert result == [{"id": "1", "folder": "Inbox"}]

    def test_array_in_prose(self) -> None:
        text = 'Here are the results:\n[{"id": "1"}]\nEnd.'
        result = extract_json_array(text)
        assert result == [{"id": "1"}]

    def test_array_in_code_fence(self) -> None:
        text = '```json\n[{"id": "1"}]\n```'
        result = extract_json_array(text)
        assert result == [{"id": "1"}]

    def test_empty_array(self) -> None:
        result = extract_json_array("[]")
        assert result == []

    def test_no_array_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON array"):
            extract_json_array("This is just prose with no JSON.")


class TestIsContextOverflow:
    def test_detects_context_length(self) -> None:
        exc = Exception("context_length exceeded")
        assert is_context_overflow(exc) is True

    def test_detects_context_window(self) -> None:
        exc = Exception("maximum context window reached")
        assert is_context_overflow(exc) is True

    def test_unrelated_exception(self) -> None:
        exc = Exception("Rate limit exceeded")
        assert is_context_overflow(exc) is False


class TestInjectTaxonomy:
    def test_replaces_category_list(self, minimal_taxonomy: dict) -> None:
        template = "Categories:\n{CATEGORY_LIST}\nCatchall: {CATCHALL}"
        result = inject_taxonomy(template, minimal_taxonomy)
        assert "Inbox" in result
        assert "Resources" in result
        assert "{CATEGORY_LIST}" not in result

    def test_uses_review_as_catchall(self) -> None:
        taxonomy = {
            "taxonomy": {
                "review": {"folder": "Review"},
                "inbox": {"folder": "Inbox"},
            }
        }
        result = inject_taxonomy("Catchall: {CATCHALL}", taxonomy)
        assert "Review" in result

    def test_falls_back_to_inbox_catchall(self) -> None:
        taxonomy = {"taxonomy": {"inbox": {"folder": "Inbox"}}}
        result = inject_taxonomy("Catchall: {CATCHALL}", taxonomy)
        assert "Inbox" in result

    def test_subfolders_listed(self) -> None:
        taxonomy = {
            "taxonomy": {"resources": {"folder": "Resources", "subfolders": ["Reference", "Tools"]}}
        }
        result = inject_taxonomy("{CATEGORY_LIST}", taxonomy)
        assert "Reference" in result
        assert "Tools" in result
        assert "[Resources/Reference]" in result

    def test_flat_mode_no_subfolders(self) -> None:
        taxonomy = {
            "taxonomy": {"resources": {"folder": "Resources", "subfolders": ["Reference", "Tools"]}}
        }
        result = inject_taxonomy("{CATEGORY_LIST}", taxonomy, {"folder_nesting": "flat"})
        assert "Resources" in result
        assert "[Resources/Reference]" not in result
        assert "Reference" not in result

    def test_deep_taxonomy_shows_nested_paths(self, deep_taxonomy: dict) -> None:
        result = inject_taxonomy("{CATEGORY_LIST}", deep_taxonomy)
        assert "[Resources/Programming]" in result
        assert "[Resources/Programming/Python]" in result
        assert "[Resources/Programming/Systems/Networking]" not in result  # exceeds default depth 3

    def test_deep_taxonomy_with_depth_5(self, deep_taxonomy: dict) -> None:
        settings = {"folder_nesting": "natural", "thresholds": {"max_folder_depth": 5}}
        result = inject_taxonomy("{CATEGORY_LIST}", deep_taxonomy, settings)
        assert "[Resources/Programming/Systems/Networking]" in result

    def test_relocation_guidance_standard_is_empty(self, minimal_taxonomy: dict) -> None:
        result = inject_taxonomy(
            "{RELOCATION_GUIDANCE}", minimal_taxonomy, {"reorganization_mode": "standard"}
        )
        assert result.strip() == ""

    def test_relocation_guidance_conservative_has_content(self, minimal_taxonomy: dict) -> None:
        result = inject_taxonomy(
            "{RELOCATION_GUIDANCE}", minimal_taxonomy, {"reorganization_mode": "conservative"}
        )
        assert "Inbox or Fleeting" in result
        assert "{RELOCATION_GUIDANCE}" not in result

    def test_relocation_guidance_full_has_content(self, minimal_taxonomy: dict) -> None:
        result = inject_taxonomy(
            "{RELOCATION_GUIDANCE}", minimal_taxonomy, {"reorganization_mode": "full"}
        )
        assert "purely on its content" in result
        assert "{RELOCATION_GUIDANCE}" not in result

    def test_relocation_guidance_default_is_standard(self, minimal_taxonomy: dict) -> None:
        result = inject_taxonomy("{RELOCATION_GUIDANCE}", minimal_taxonomy)
        assert result.strip() == ""


class TestConservativeModePostProcessing:
    """Tests for the conservative-mode safety net in run_classify()."""

    def _make_note(self, note_id: str, folder_path: str) -> dict:
        return {
            "id": note_id,
            "title": f"Note {note_id}",
            "folder": folder_path,
            "folder_path": folder_path,
            "body": "content",
        }

    def _run_conservative_classify(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        notes: list[dict],
        llm_results: list[dict],
        taxonomy: dict,
    ) -> dict:
        from scripts.classify.classify_notes import run_classify

        export_file = tmp_path / "notes-test.json"
        export_file.write_text(__import__("json").dumps(notes))

        settings = {
            "reorganization_mode": "conservative",
            "llm": {"batch_size": 50},
            "export": {"skip_empty": False},
            "classify": {"exclude_archive": False},
        }

        mocker.patch("scripts.classify.classify_notes.load_settings", return_value=settings)
        mocker.patch("scripts.classify.classify_notes.load_taxonomy", return_value=taxonomy)
        mocker.patch("scripts.classify.classify_notes.local_taxonomy_exists", return_value=True)
        mocker.patch("scripts.classify.classify_notes.PROPOSALS_DIR", tmp_path / "proposals")

        mock_provider = mocker.MagicMock()
        mock_provider.name = "mock"
        mock_provider.model = "mock-model"
        mock_provider.classify_messages.return_value = __import__("json").dumps(llm_results)
        mocker.patch("scripts.classify.classify_notes.get_provider", return_value=mock_provider)
        mocker.patch("scripts.classify.classify_notes.RunLogger")

        run_classify(export_file=str(export_file), dry_run=False)

        proposals = list((tmp_path / "proposals").glob("proposal-*.json"))
        assert len(proposals) == 1
        return __import__("json").loads(proposals[0].read_text())

    def test_medium_confidence_non_transit_goes_to_needs_review(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:

        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "fleeting": {"folder": "Fleeting"},
                "resources": {"folder": "Resources", "subfolders": ["Programming"]},
            }
        }
        notes = [self._make_note("p1", "Resources/Programming")]
        llm_results = [
            {
                "id": "p1",
                "proposed_folder_path": "Resources/Other",
                "proposed_folder": "Resources",
                "proposed_subfolder": "Other",
                "confidence": "medium",
                "reason": "fits better here",
            }
        ]
        proposal = self._run_conservative_classify(mocker, tmp_path, notes, llm_results, taxonomy)
        assert len(proposal["moves"]) == 0
        assert any(n["id"] == "p1" for n in proposal["needs_review"])
        assert any("[conservative]" in n.get("reason", "") for n in proposal["needs_review"])

    def test_high_confidence_non_transit_still_moves(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "fleeting": {"folder": "Fleeting"},
                "resources": {"folder": "Resources"},
                "permanent": {"folder": "Notes"},
            }
        }
        notes = [self._make_note("p1", "Resources")]
        llm_results = [
            {
                "id": "p1",
                "proposed_folder_path": "Notes",
                "proposed_folder": "Notes",
                "proposed_subfolder": None,
                "confidence": "high",
                "reason": "clearly a permanent note",
            }
        ]
        proposal = self._run_conservative_classify(mocker, tmp_path, notes, llm_results, taxonomy)
        assert any(n["id"] == "p1" for n in proposal["moves"])
        assert len(proposal["needs_review"]) == 0

    def test_transit_note_medium_confidence_still_moves(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "fleeting": {"folder": "Fleeting"},
                "resources": {"folder": "Resources"},
            }
        }
        notes = [self._make_note("p1", "Inbox")]
        llm_results = [
            {
                "id": "p1",
                "proposed_folder_path": "Resources",
                "proposed_folder": "Resources",
                "proposed_subfolder": None,
                "confidence": "medium",
                "reason": "reference material",
            }
        ]
        proposal = self._run_conservative_classify(mocker, tmp_path, notes, llm_results, taxonomy)
        assert any(n["id"] == "p1" for n in proposal["moves"])
        assert len(proposal["needs_review"]) == 0


class TestProposalPathDerivation:
    def test_proposed_folder_path_primary(self) -> None:
        result = {
            "proposed_folder_path": "Resources/Programming/Python",
            "confidence": "high",
            "reason": "x",
        }
        from scripts.folder_utils import clamp_path, effective_max_depth

        path = clamp_path(result.get("proposed_folder_path", ""), effective_max_depth(None))
        parts = path.split("/", 1)
        assert parts[0] == "Resources"
        assert parts[1] == "Programming/Python"

    def test_fallback_to_old_fields(self) -> None:
        result = {"proposed_folder": "Resources", "proposed_subfolder": "Reference"}
        fp = result.get("proposed_folder_path") or ""
        if not fp:
            pf = result.get("proposed_folder", "")
            ps = result.get("proposed_subfolder") or ""
            fp = f"{pf}/{ps}" if ps else pf
        assert fp == "Resources/Reference"


class TestPricePerMillion:
    def test_known_opus_prefix(self) -> None:
        assert price_per_million("claude-opus-4-7") == 15.0

    def test_known_sonnet_prefix(self) -> None:
        assert price_per_million("claude-sonnet-4-6") == 3.0

    def test_known_haiku_prefix(self) -> None:
        assert price_per_million("claude-haiku-4-5") == 0.25

    def test_unknown_model_returns_none(self) -> None:
        assert price_per_million("llama3") is None


class TestBuildFolderPath:
    def test_folder_only(self) -> None:
        assert _build_folder_path("Resources", None) == "Resources"

    def test_folder_with_subfolder(self) -> None:
        assert _build_folder_path("Resources", "Reference") == "Resources/Reference"


class TestFolderNameAndSubfolders:
    def testfolder_name_dict(self) -> None:
        assert folder_name({"folder": "Inbox"}) == "Inbox"

    def testfolder_name_string(self) -> None:
        assert folder_name("Inbox") == "Inbox"

    def test_subfolders_from_dict(self) -> None:
        entry = {"folder": "Resources", "subfolders": ["Reference", "Tools"]}
        assert _subfolders(entry) == ["Reference", "Tools"]

    def test_subfolders_empty(self) -> None:
        assert _subfolders({"folder": "Inbox"}) == []

    def test_subfolders_from_string_entry(self) -> None:
        assert _subfolders("Inbox") == []

    def test_subfolder_str_with_items(self) -> None:
        assert _subfolder_str(["Reference", "Tools"]) == "Reference, Tools"

    def test_subfolder_str_empty(self) -> None:
        assert _subfolder_str([]) == "none"


class TestClassifyBatch:
    def test_happy_path(self, mock_llm_provider: MagicMock) -> None:
        notes = [
            {
                "id": "x-coredata://test/p1",
                "title": "Router setup",
                "body": "Admin page at 192.168.1.1",
                "folder": "Inbox",
            }
        ]
        mock_llm_provider.classify_messages.return_value = json.dumps(
            [{"id": "x-coredata://test/p1", "proposed_folder": "Resources", "confidence": "high"}]
        )
        result = classify_batch(mock_llm_provider, notes, "system prompt", {})
        assert len(result) == 1
        assert result[0]["proposed_folder"] == "Resources"

    def test_provider_error_propagates(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.side_effect = RuntimeError("API error")
        with pytest.raises(RuntimeError):
            classify_batch(mock_llm_provider, [{"id": "1"}], "prompt", {})

    def test_malformed_response_raises(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = "This is not JSON."
        with pytest.raises(ValueError):
            classify_batch(mock_llm_provider, [{"id": "1"}], "prompt", {})


class TestClassifyBatchResilient:
    def test_happy_path(self, mock_llm_provider: MagicMock) -> None:
        notes = [{"id": "1", "title": "A", "body": "B", "folder": "Inbox"}]
        mock_llm_provider.classify_messages.return_value = json.dumps(
            [{"id": "1", "proposed_folder": "Resources"}]
        )
        result = classify_batch_resilient(mock_llm_provider, notes, "prompt", {})
        assert len(result) == 1

    def test_empty_batch_returns_empty(self, mock_llm_provider: MagicMock) -> None:
        result = classify_batch_resilient(mock_llm_provider, [], "prompt", {})
        assert result == []

    def test_splits_on_context_overflow(self, mock_llm_provider: MagicMock) -> None:
        notes = [
            {"id": "1", "title": "A", "body": "B", "folder": "Inbox"},
            {"id": "2", "title": "C", "body": "D", "folder": "Inbox"},
        ]
        call_count = 0

        def side_effect(system: str, user: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("context_length exceeded")
            note_id = json.loads(user)[0]["id"]
            return json.dumps([{"id": note_id, "proposed_folder": "Resources"}])

        mock_llm_provider.classify_messages.side_effect = side_effect
        result = classify_batch_resilient(mock_llm_provider, notes, "prompt", {})
        assert len(result) == 2

    def test_single_note_failure_returns_empty(self, mock_llm_provider: MagicMock) -> None:
        notes = [{"id": "1", "title": "A", "body": "B", "folder": "Inbox"}]
        mock_llm_provider.classify_messages.side_effect = ValueError("bad JSON")
        result = classify_batch_resilient(mock_llm_provider, notes, "prompt", {})
        assert result == []


class TestRunClassify:
    def test_dry_run_makes_no_api_calls(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        sample_notes: list[dict],
        minimal_settings: dict,
        minimal_taxonomy: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(sample_notes))

        mocker.patch("scripts.classify.classify_notes.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.classify_notes.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch(
            "scripts.classify.classify_notes.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch("scripts.classify.classify_notes.get_provider", return_value=mock_llm_provider)

        run_classify(export_file=str(export_file), dry_run=True)

        mock_llm_provider.classify_messages.assert_not_called()

    def test_real_run_writes_proposal(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        sample_notes: list[dict],
        minimal_settings: dict,
        minimal_taxonomy: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(sample_notes))

        mock_llm_provider.classify_messages.return_value = json.dumps(
            [
                {
                    "id": "x-coredata://test-uuid/ICNote/p1",
                    "proposed_folder": "Resources",
                    "proposed_subfolder": "Reference",
                    "confidence": "high",
                    "reason": "Technical",
                }
            ]
        )

        mocker.patch("scripts.classify.classify_notes.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.classify_notes.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch(
            "scripts.classify.classify_notes.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch("scripts.classify.classify_notes.get_provider", return_value=mock_llm_provider)
        mocker.patch("scripts.classify.classify_notes.PROPOSALS_DIR", tmp_path)

        run_classify(export_file=str(export_file), dry_run=False)

        proposals = list(tmp_path.glob("proposal-*.json"))
        assert len(proposals) == 1
        data = json.loads(proposals[0].read_text())
        assert "moves" in data
        assert "needs_review" in data

    def test_missing_export_file_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        mocker.patch("scripts.classify.classify_notes.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.classify.classify_notes.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch(
            "scripts.classify.classify_notes.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch("scripts.classify.classify_notes.get_provider", return_value=mock_llm_provider)

        with pytest.raises(SystemExit):
            run_classify(export_file=str(tmp_path / "nonexistent.json"), dry_run=True)

    def _run_classify_with_notes(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        notes: list[dict],
        settings: dict,
        taxonomy: dict,
        llm_response: list[dict],
    ) -> dict:
        """Helper: run classify and return the written proposal as a dict."""
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.model = "mock-model"
        mock_provider.classify_messages.return_value = json.dumps(llm_response)

        mocker.patch("scripts.classify.classify_notes.load_settings", return_value=settings)
        mocker.patch("scripts.classify.classify_notes.load_taxonomy", return_value=taxonomy)
        mocker.patch(
            "scripts.classify.classify_notes.load_prompt_template",
            return_value="{CATEGORY_LIST} {CATCHALL}",
        )
        mocker.patch("scripts.classify.classify_notes.get_provider", return_value=mock_provider)
        mocker.patch("scripts.classify.classify_notes.PROPOSALS_DIR", tmp_path)

        run_classify(export_file=str(export_file), dry_run=False)

        proposals = list(tmp_path.glob("proposal-*.json"))
        return json.loads(proposals[0].read_text())

    def test_archive_notes_excluded_from_moves_by_default(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "arch-1",
                "title": "Old project",
                "body": "Done.",
                "folder": "Archive",
                "folder_path": "Archive",
            }
        ]
        llm_response: list[dict] = []  # LLM should never be called for this note
        data = self._run_classify_with_notes(
            mocker, tmp_path, notes, minimal_settings, minimal_taxonomy, llm_response
        )
        assert all(m["id"] != "arch-1" for m in data["moves"])
        assert any(n["id"] == "arch-1" for n in data["no_change"])

    def test_archive_notes_included_when_exclude_false(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        settings = {**minimal_settings, "classify": {"exclude_archive": False}}
        notes = [
            {
                "id": "arch-1",
                "title": "Old project",
                "body": "Done.",
                "folder": "Archive",
                "folder_path": "Archive",
            }
        ]
        llm_response = [
            {
                "id": "arch-1",
                "proposed_folder_path": "Resources/Reference",
                "proposed_folder": "Resources",
                "proposed_subfolder": "Reference",
                "confidence": "high",
                "reason": "Reference material",
            }
        ]
        data = self._run_classify_with_notes(
            mocker, tmp_path, notes, settings, minimal_taxonomy, llm_response
        )
        assert any(m["id"] == "arch-1" for m in data["moves"])

    def test_subfolder_note_detected_as_no_change(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "ref-1",
                "title": "Python guide",
                "body": "Use type hints.",
                "folder": "Reference",
                "folder_path": "Resources/Reference",
            }
        ]
        llm_response = [
            {
                "id": "ref-1",
                "proposed_folder_path": "Resources/Reference",
                "proposed_folder": "Resources",
                "proposed_subfolder": "Reference",
                "confidence": "high",
                "reason": "Already in correct folder",
            }
        ]
        data = self._run_classify_with_notes(
            mocker, tmp_path, notes, minimal_settings, minimal_taxonomy, llm_response
        )
        assert all(m["id"] != "ref-1" for m in data["moves"])
        assert any(n["id"] == "ref-1" for n in data["no_change"])
