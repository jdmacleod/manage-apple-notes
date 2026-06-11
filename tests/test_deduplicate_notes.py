"""Tests for scripts/classify/deduplicate_notes.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.classify.deduplicate_notes import (
    _build_entries,
    _choose_keep,
    _md5,
    _normalize_body,
    _note_summary,
    _word_count,
    pass1_exact,
    pass2_fuzzy,
    pass3_llm,
    run_dedup,
)


class TestNormalizeBody:
    def test_lowercases_and_strips_punctuation(self) -> None:
        result = _normalize_body("Hello, World!")
        assert result == "hello world"

    def test_collapses_whitespace(self) -> None:
        result = _normalize_body("  too   many   spaces  ")
        assert result == "too many spaces"

    def test_empty_string(self) -> None:
        assert _normalize_body("") == ""


class TestMd5:
    def test_stable_hash(self) -> None:
        assert _md5("hello") == _md5("hello")

    def test_different_inputs_differ(self) -> None:
        assert _md5("hello") != _md5("world")

    def test_returns_hex_string(self) -> None:
        result = _md5("test")
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)


class TestWordCount:
    def test_normal_text(self) -> None:
        assert _word_count("hello world foo") == 3

    def test_empty_string(self) -> None:
        assert _word_count("") == 0

    def test_single_word(self) -> None:
        assert _word_count("hello") == 1


class TestBuildEntries:
    def test_adds_hash_and_word_count(self) -> None:
        notes = [
            {
                "id": "1",
                "title": "A",
                "folder": "Inbox",
                "body": "Hello world",
                "modified": "2026-01-01",
            }
        ]
        entries = _build_entries(notes, {})
        assert len(entries) == 1
        assert entries[0]["_hash"] is not None
        assert entries[0]["word_count"] == 2

    def test_uses_proposal_folder_path(self) -> None:
        notes = [{"id": "1", "title": "A", "folder": "Inbox", "body": "test"}]
        proposal_index = {"1": {"proposed_folder_path": "Resources/Reference"}}
        entries = _build_entries(notes, proposal_index)
        assert entries[0]["proposed_folder_path"] == "Resources/Reference"

    def test_empty_body_has_none_hash(self) -> None:
        notes = [{"id": "1", "title": "A", "folder": "Inbox", "body": ""}]
        entries = _build_entries(notes, {})
        assert entries[0]["_hash"] is None


class TestChooseKeep:
    def test_longer_note_wins(self) -> None:
        notes = [
            {
                "id": "1",
                "word_count": 10,
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "title": "A",
            },
            {
                "id": "2",
                "word_count": 5,
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "title": "A",
            },
        ]
        keep_id, reason = _choose_keep(notes)
        assert keep_id == "1"
        assert "content" in reason.lower()

    def test_already_in_correct_folder_preferred(self) -> None:
        notes = [
            {
                "id": "1",
                "word_count": 5,
                "folder_path": "Inbox",
                "proposed_folder_path": "Resources",
                "modified": "2026-01-01",
                "title": "A",
            },
            {
                "id": "2",
                "word_count": 5,
                "folder_path": "Resources",
                "proposed_folder_path": "Resources",
                "modified": "2026-01-01",
                "title": "A",
            },
        ]
        keep_id, _ = _choose_keep(notes)
        assert keep_id == "2"


class TestNoteSummary:
    def test_creates_summary_dict(self) -> None:
        note = {
            "id": "1",
            "title": "Test Note",
            "folder": "Inbox",
            "proposed_folder_path": "Resources",
            "modified": "2026-01-01",
            "word_count": 10,
            "body": "Hello world this is a body",
        }
        summary = _note_summary(note, preview_chars=5)
        assert summary["id"] == "1"
        assert summary["content_preview"] == "Hello"


class TestPass1Exact:
    def test_finds_exact_duplicates(self) -> None:
        entries = [
            {
                "id": "1",
                "title": "A",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-02",
                "word_count": 3,
                "body": "same body",
                "_hash": _md5(_normalize_body("same body")),
                "_normalized": _normalize_body("same body"),
            },
            {
                "id": "2",
                "title": "A",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "word_count": 3,
                "body": "same body",
                "_hash": _md5(_normalize_body("same body")),
                "_normalized": _normalize_body("same body"),
            },
            {
                "id": "3",
                "title": "B",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "word_count": 2,
                "body": "different",
                "_hash": _md5(_normalize_body("different")),
                "_normalized": _normalize_body("different"),
            },
        ]
        groups, consumed = pass1_exact(entries, preview_chars=50)
        assert len(groups) == 1
        assert len(consumed) == 2
        assert groups[0]["duplicate_type"] == "exact"

    def test_no_duplicates_returns_empty(self) -> None:
        entries = [
            {
                "id": "1",
                "_hash": "aaa",
                "_normalized": "note one",
                "title": "A",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "word_count": 2,
                "body": "note one",
            },
            {
                "id": "2",
                "_hash": "bbb",
                "_normalized": "note two",
                "title": "B",
                "folder": "Inbox",
                "folder_path": "Inbox",
                "proposed_folder_path": "Inbox",
                "modified": "2026-01-01",
                "word_count": 2,
                "body": "note two",
            },
        ]
        groups, consumed = pass1_exact(entries, preview_chars=50)
        assert groups == []
        assert consumed == set()


class TestPass2Fuzzy:
    def test_similar_titles_above_threshold(self, minimal_settings: dict) -> None:
        body = "Use type hints on all Python functions to catch bugs early and improve readability."
        entries = [
            {
                "id": "1",
                "title": "Python typing guide",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": body,
                "word_count": 14,
                "_hash": "aaa",
                "_normalized": body,
            },
            {
                "id": "2",
                "title": "Python typing guide",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": body,
                "word_count": 14,
                "_hash": "bbb",
                "_normalized": body,
            },
        ]
        candidates = pass2_fuzzy(entries, set(), minimal_settings)
        assert len(candidates) >= 1

    def test_dissimilar_notes_below_threshold(self, minimal_settings: dict) -> None:
        entries = [
            {
                "id": "1",
                "title": "Router setup",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": "Configure the router admin page.",
                "word_count": 5,
                "_hash": "aaa",
                "_normalized": "configure the router",
            },
            {
                "id": "2",
                "title": "Cake recipe",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": "Mix flour eggs butter sugar.",
                "word_count": 5,
                "_hash": "bbb",
                "_normalized": "mix flour eggs",
            },
        ]
        candidates = pass2_fuzzy(entries, set(), minimal_settings)
        assert candidates == []

    def test_consumed_notes_skipped(self, minimal_settings: dict) -> None:
        entries = [
            {
                "id": "1",
                "title": "Python guide",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": "same content",
                "word_count": 3,
                "_hash": "aaa",
                "_normalized": "same content",
            },
            {
                "id": "2",
                "title": "Python guide",
                "folder": "Resources",
                "proposed_folder_path": "Resources",
                "body": "same content",
                "word_count": 3,
                "_hash": "bbb",
                "_normalized": "same content",
            },
        ]
        candidates = pass2_fuzzy(entries, {"1", "2"}, minimal_settings)
        assert candidates == []


class TestPass3Llm:
    def test_returns_llm_decisions(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = json.dumps(
            [
                {
                    "group_id": 1,
                    "is_duplicate": True,
                    "resolution": "delete",
                    "keep_id": "1",
                    "delete_ids": ["2"],
                    "keep_reason": "More complete",
                }
            ]
        )
        note_a = {
            "id": "1",
            "title": "A",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 5,
            "body": "test body",
        }
        note_b = {
            "id": "2",
            "title": "A",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 5,
            "body": "test body",
        }
        candidates = [(note_a, note_b, 90.0)]
        result = pass3_llm(candidates, "system", mock_llm_provider, 100)
        assert len(result) == 1
        assert result[0]["is_duplicate"] is True

    def test_malformed_llm_response_raises(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = "Not JSON"
        note_a = {
            "id": "1",
            "title": "A",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 5,
            "body": "test",
        }
        note_b = {
            "id": "2",
            "title": "A",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 5,
            "body": "test",
        }
        with pytest.raises(ValueError):
            pass3_llm([(note_a, note_b, 90.0)], "system", mock_llm_provider, 100)

    def test_locale_error_retries_with_title_only(self, mock_llm_provider: MagicMock) -> None:
        llm_result = json.dumps(
            [
                {
                    "group_id": 1,
                    "is_duplicate": False,
                    "resolution": "keep",
                    "keep_id": "1",
                    "delete_ids": [],
                }
            ]
        )
        mock_llm_provider.classify_messages.side_effect = [
            RuntimeError("apple_unsupported_locale"),
            llm_result,
        ]
        note_a = {
            "id": "1",
            "title": "日本語タイトル",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 3,
            "body": "CJK body content",
        }
        note_b = {
            "id": "2",
            "title": "別のタイトル",
            "folder": "Inbox",
            "proposed_folder_path": "Inbox",
            "modified": "2026-01-01",
            "word_count": 3,
            "body": "Other CJK body",
        }
        result = pass3_llm([(note_a, note_b, 85.0)], "system", mock_llm_provider, 100)
        # Second call succeeds with title-only payload (no "body" key)
        assert mock_llm_provider.classify_messages.call_count == 2
        title_only_payload = json.loads(mock_llm_provider.classify_messages.call_args[0][1])
        assert all("body" not in n for group in title_only_payload for n in group["notes"])
        assert len(result) == 1
        assert result[0]["is_duplicate"] is False


class TestRunDedup:
    def test_dry_run_does_not_write_proposal(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        sample_notes: list[dict],
        minimal_settings: dict,
    ) -> None:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(sample_notes))

        mocker.patch(
            "scripts.classify.deduplicate_notes.load_settings", return_value=minimal_settings
        )

        run_dedup(export_file=str(export_file), proposal_file=None, dry_run=True)

        assert not list(tmp_path.glob("dedup-*.json"))

    def test_real_run_writes_proposal(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        sample_notes: list[dict],
        minimal_settings: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(sample_notes))

        mock_llm_provider.classify_messages.return_value = json.dumps([])

        mocker.patch(
            "scripts.classify.deduplicate_notes.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.classify.deduplicate_notes.load_prompt_template", return_value="system prompt"
        )
        mocker.patch(
            "scripts.classify.deduplicate_notes.get_provider", return_value=mock_llm_provider
        )
        mocker.patch("scripts.classify.deduplicate_notes.DEDUP_PROPOSALS_DIR", tmp_path)
        mocker.patch("scripts.classify.deduplicate_notes.find_latest_proposal", return_value=None)

        run_dedup(export_file=str(export_file), proposal_file=None, dry_run=False)

        proposals = list(tmp_path.glob("dedup-*.json"))
        assert len(proposals) == 1
