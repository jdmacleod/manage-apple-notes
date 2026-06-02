"""Tests for scripts/classify/discover_themes.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.classify.discover_themes import (
    _build_discover_payload,
    _discover_batch,
    _export_folder_tree,
    _sanitize_batch_for_locale,
    inject_discover_taxonomy,
    run_discover,
)
from scripts.json_utils import extract_json_object, is_context_overflow


class TestInjectDiscoverTaxonomy:
    def test_replaces_categories_placeholder(self, minimal_taxonomy: dict) -> None:
        template = "Analyze notes. Categories: {CATEGORIES}. Find themes."
        result = inject_discover_taxonomy(template, minimal_taxonomy)
        assert "{CATEGORIES}" not in result
        assert "Inbox" in result
        assert "Resources" in result

    def test_empty_taxonomy(self) -> None:
        result = inject_discover_taxonomy("Categories: {CATEGORIES}", {"taxonomy": {}})
        assert result == "Categories: "

    def test_flat_mode_nesting_guidance(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CATEGORIES} {NESTING_GUIDANCE}", minimal_taxonomy, {"folder_nesting": "flat"}
        )
        assert "top-level categories only" in result

    def test_natural_mode_nesting_guidance(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CATEGORIES} {NESTING_GUIDANCE}", minimal_taxonomy, {"folder_nesting": "natural"}
        )
        assert "level" in result
        assert "{NESTING_GUIDANCE}" not in result

    def test_deep_mode_nesting_guidance(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CATEGORIES} {NESTING_GUIDANCE}",
            minimal_taxonomy,
            {"folder_nesting": "deep", "thresholds": {"max_folder_depth": 4}},
        )
        assert "4" in result
        assert "{NESTING_GUIDANCE}" not in result

    def test_conservatism_guidance_standard_is_empty(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CONSERVATISM_GUIDANCE}",
            minimal_taxonomy,
            {"reorganization_mode": "standard"},
        )
        assert result.strip() == ""

    def test_conservatism_guidance_conservative_has_content(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CONSERVATISM_GUIDANCE}",
            minimal_taxonomy,
            {"reorganization_mode": "conservative"},
        )
        assert "deliberately organized" in result
        assert "{CONSERVATISM_GUIDANCE}" not in result

    def test_conservatism_guidance_full_has_content(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy(
            "{CONSERVATISM_GUIDANCE}",
            minimal_taxonomy,
            {"reorganization_mode": "full"},
        )
        assert "no established structure" in result
        assert "{CONSERVATISM_GUIDANCE}" not in result

    def test_conservatism_guidance_default_is_standard(self, minimal_taxonomy: dict) -> None:
        result = inject_discover_taxonomy("{CONSERVATISM_GUIDANCE}", minimal_taxonomy)
        assert result.strip() == ""

    # Export folder tree injection tests
    def test_notes_none_falls_back_to_taxonomy_paths(self, minimal_taxonomy: dict) -> None:
        # minimal_taxonomy has Resources/Reference as a subfolder; with notes=None,
        # the established block should show that taxonomy path as the fallback.
        result = inject_discover_taxonomy("{ESTABLISHED_PATHS}", minimal_taxonomy, notes=None)
        assert "Resources/Reference" in result
        assert "currently exist in your Apple Notes library" in result

    def test_notes_provided_standard_shows_folder_list(self, minimal_taxonomy: dict) -> None:
        notes = [
            {"folder_path": "Areas/Finance"},
            {"folder_path": "Resources/Cooking"},
            {"folder_path": "Areas/Finance"},  # duplicate — should appear once
        ]
        result = inject_discover_taxonomy(
            "{ESTABLISHED_PATHS}",
            minimal_taxonomy,
            {"reorganization_mode": "standard"},
            notes=notes,
        )
        assert "Areas/Finance" in result
        assert "Resources/Cooking" in result
        assert result.count("Areas/Finance") == 1
        assert "Prefer existing names" in result

    def test_notes_provided_conservative_uses_strong_framing(self, minimal_taxonomy: dict) -> None:
        notes = [{"folder_path": "Areas/Finance"}, {"folder_path": "Resources/Cooking"}]
        result = inject_discover_taxonomy(
            "{ESTABLISHED_PATHS}",
            minimal_taxonomy,
            {"reorganization_mode": "conservative"},
            notes=notes,
        )
        assert "deliberate organizational structure" in result
        assert "Areas/Finance" in result

    def test_notes_provided_full_mode_ignores_notes(self, minimal_taxonomy: dict) -> None:
        notes = [{"folder_path": "Areas/Finance"}, {"folder_path": "Resources/Cooking"}]
        result = inject_discover_taxonomy(
            "{ESTABLISHED_PATHS}",
            minimal_taxonomy,
            {"reorganization_mode": "full"},
            notes=notes,
        )
        assert "No subfolder paths are established yet" in result
        assert "Areas/Finance" not in result

    def test_notes_empty_folder_paths_falls_back_to_taxonomy(self, minimal_taxonomy: dict) -> None:
        # When all notes have empty/missing folder_path, export_paths is empty and the
        # taxonomy fallback kicks in — minimal_taxonomy has Resources/Reference as a subfolder.
        notes = [{"folder_path": ""}, {"folder_path": None}, {"title": "no folder"}]
        result = inject_discover_taxonomy(
            "{ESTABLISHED_PATHS}",
            minimal_taxonomy,
            {"reorganization_mode": "standard"},
            notes=notes,
        )
        assert "Resources/Reference" in result


class TestExportFolderTree:
    def test_returns_unique_paths_in_first_appearance_order(self) -> None:
        notes = [
            {"folder_path": "Resources/Cooking"},
            {"folder_path": "Areas/Finance"},
            {"folder_path": "Resources/Cooking"},  # duplicate — should appear once
        ]
        # First-appearance order matches Apple Notes native arrangement, not alphabetical.
        assert _export_folder_tree(notes) == ["Resources/Cooking", "Areas/Finance"]

    def test_filters_empty_strings(self) -> None:
        notes = [{"folder_path": ""}, {"folder_path": "Areas/Finance"}, {"folder": ""}]
        assert _export_folder_tree(notes) == ["Areas/Finance"]

    def test_falls_back_to_folder_key(self) -> None:
        notes = [{"folder": "Inbox"}, {"folder_path": "Areas/Finance"}]
        result = _export_folder_tree(notes)
        assert "Inbox" in result
        assert "Areas/Finance" in result

    def test_empty_notes_returns_empty(self) -> None:
        assert _export_folder_tree([]) == []


class TestExtractJsonObject:
    def test_plain_object(self) -> None:
        result = extract_json_object('{"themes": [{"name": "Tech"}]}')
        assert result == {"themes": [{"name": "Tech"}]}

    def test_object_in_prose(self) -> None:
        text = 'Here is the result:\n{"themes": []}\nDone.'
        result = extract_json_object(text)
        assert result == {"themes": []}

    def test_object_in_code_fence(self) -> None:
        text = '```json\n{"themes": [{"name": "Health"}]}\n```'
        result = extract_json_object(text)
        assert result == {"themes": [{"name": "Health"}]}

    def test_no_object_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON object"):
            extract_json_object("No JSON here at all.")

    def test_trailing_braces_in_prose_ignored(self) -> None:
        # LLM synthesis responses often add prose like "I merged {N} themes" after the JSON.
        # rfind("}") would have grabbed that brace; raw_decode stops at the correct boundary.
        text = '{"themes": []}\nI merged {15} themes from {3} batches.'
        result = extract_json_object(text)
        assert result == {"themes": []}


class TestIsContextOverflow:
    def test_context_window_message(self) -> None:
        assert is_context_overflow(Exception("context window exceeded")) is True

    def test_unrelated_message(self) -> None:
        assert is_context_overflow(Exception("network error")) is False


class TestDiscoverBatch:
    def test_happy_path_returns_themes(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = json.dumps(
            {"themes": [{"name": "Technology", "estimated_count": 10}]}
        )
        result = _discover_batch(mock_llm_provider, "system", [{"id": "1", "title": "A"}])
        assert result == [{"name": "Technology", "estimated_count": 10}]

    def test_parse_error_returns_empty(self, mock_llm_provider: MagicMock) -> None:
        mock_llm_provider.classify_messages.return_value = "This is not JSON at all."
        result = _discover_batch(mock_llm_provider, "system", [{"id": "1"}])
        assert result == []

    def test_context_overflow_splits_and_merges(self, mock_llm_provider: MagicMock) -> None:
        call_count = 0

        def side_effect(system: str, user: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            # user is "Notes sample:\n\n[...]" — parse only the JSON part
            batch = json.loads(user.split("\n\n", 1)[-1])
            if call_count == 1 and len(batch) > 1:
                raise Exception("context_length exceeded")
            return json.dumps({"themes": [{"name": f"Theme{len(batch)}"}]})

        mock_llm_provider.classify_messages.side_effect = side_effect
        batch = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
        result = _discover_batch(mock_llm_provider, "system", batch)
        assert len(result) == 2

    def test_locale_error_all_cjk_skips_retry_returns_empty(
        self, mock_llm_provider: MagicMock
    ) -> None:
        # title strips to "" → has_content is False → no retry
        mock_llm_provider.classify_messages.side_effect = RuntimeError("apple_unsupported_locale")
        result = _discover_batch(mock_llm_provider, "system", [{"id": "1", "title": "日本語"}])
        assert result == []
        mock_llm_provider.classify_messages.assert_called_once()

    def test_locale_error_retries_with_sanitized_content(
        self, mock_llm_provider: MagicMock
    ) -> None:
        # First call raises locale error (mixed content); retry with sanitized succeeds.
        call_count = 0

        def side_effect(system: str, user: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("apple_unsupported_locale")
            return json.dumps({"themes": [{"name": "Technology", "estimated_count": 5}]})

        mock_llm_provider.classify_messages.side_effect = side_effect
        batch = [{"id": "1", "title": "Tech note 日本語", "excerpt": "Hello world"}]
        result = _discover_batch(mock_llm_provider, "system", batch)
        assert result == [{"name": "Technology", "estimated_count": 5}]
        assert call_count == 2

    def test_locale_error_retry_sanitizes_system_prompt(self, mock_llm_provider: MagicMock) -> None:
        # Root cause: system prompt contains non-Latin folder paths from {ESTABLISHED_PATHS}.
        # The retry must sanitize the system prompt too, not just the batch content.
        received_prompts: list[str] = []

        def side_effect(system: str, user: str, **kwargs: object) -> str:
            received_prompts.append(system)
            if len(received_prompts) == 1:
                raise RuntimeError("apple_unsupported_locale")
            return json.dumps({"themes": [{"name": "Work", "estimated_count": 3}]})

        mock_llm_provider.classify_messages.side_effect = side_effect
        non_latin_prompt = "Categories: Inbox. Existing paths: 仕事/Projects, 日記."
        batch = [{"id": "1", "title": "Work item", "excerpt": "Budget review"}]
        result = _discover_batch(mock_llm_provider, non_latin_prompt, batch)
        assert result == [{"name": "Work", "estimated_count": 3}]
        # First call used the original (non-Latin) prompt
        assert "仕事" in received_prompts[0]
        # Retry used a sanitized prompt — non-Latin chars stripped
        assert "仕事" not in received_prompts[1]
        assert "Categories: Inbox" in received_prompts[1]

    def test_locale_error_retry_also_fails_returns_empty(
        self, mock_llm_provider: MagicMock
    ) -> None:
        # Both the original and sanitized retry fail; batch is skipped.
        mock_llm_provider.classify_messages.side_effect = RuntimeError("apple_unsupported_locale")
        batch = [{"id": "1", "title": "Tech note 日本語", "excerpt": "Hello world"}]
        result = _discover_batch(mock_llm_provider, "system", batch)
        assert result == []
        assert mock_llm_provider.classify_messages.call_count == 2

    def test_locale_error_splits_on_persistent_retry_failure(
        self, mock_llm_provider: MagicMock
    ) -> None:
        # Multi-note batch: first call locale error, sanitized retry also locale error.
        # The batch should be split and each half processed independently so that
        # individual notes with ASCII content are not silently discarded.
        call_count = 0

        def side_effect(system: str, user: str, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            # user is "Notes sample:\n\n[...]" — parse only the JSON part
            batch = json.loads(user.split("\n\n", 1)[-1])
            if len(batch) > 1:
                raise RuntimeError("apple_unsupported_locale")
            return json.dumps({"themes": [{"name": f"Theme{call_count}"}]})

        mock_llm_provider.classify_messages.side_effect = side_effect
        batch = [
            {"id": "1", "title": "English note", "excerpt": "Budget review"},
            {"id": "2", "title": "Another note", "excerpt": "Project work"},
        ]
        result = _discover_batch(mock_llm_provider, "system", batch)
        # Both individual notes succeed after the batch is split
        assert len(result) == 2

    def test_unrecognised_error_returns_empty_not_raises(
        self, mock_llm_provider: MagicMock
    ) -> None:
        mock_llm_provider.classify_messages.side_effect = RuntimeError("connection reset")
        result = _discover_batch(mock_llm_provider, "system", [{"id": "1", "title": "A"}])
        assert result == []


class TestSanitizeBatchForLocale:
    def test_strips_cjk_from_title_and_excerpt(self) -> None:
        batch = [
            {"id": "1", "title": "Note 日本語", "excerpt": "Content 中文", "folder_path": "Inbox"}
        ]
        result = _sanitize_batch_for_locale(batch)
        assert result[0]["title"] == "Note"
        assert result[0]["excerpt"] == "Content"
        assert result[0]["folder_path"] == "Inbox"
        assert result[0]["id"] == "1"

    def test_preserves_ascii_fields_unchanged(self) -> None:
        batch = [{"id": "1", "title": "Hello", "excerpt": "World", "folder_path": "Resources"}]
        result = _sanitize_batch_for_locale(batch)
        assert result[0] == {
            "id": "1",
            "title": "Hello",
            "excerpt": "World",
            "folder_path": "Resources",
        }

    def test_handles_missing_fields_gracefully(self) -> None:
        batch = [{"id": "1"}]
        result = _sanitize_batch_for_locale(batch)
        assert result[0]["title"] == ""
        assert result[0]["excerpt"] == ""
        assert result[0]["folder_path"] == ""

    def test_preserves_non_text_fields(self) -> None:
        batch = [
            {
                "id": "abc-123",
                "title": "Note",
                "excerpt": "body",
                "folder_path": "Inbox",
                "extra": 42,
            }
        ]
        result = _sanitize_batch_for_locale(batch)
        assert result[0]["id"] == "abc-123"
        assert result[0]["extra"] == 42


class TestBuildDiscoverPayload:
    def test_excludes_id_field(self) -> None:
        batch = [{"id": "x-coredata://ABC/p1", "title": "Budget", "excerpt": "Q4", "folder_path": "Work"}]
        payload = _build_discover_payload(batch)
        assert "x-coredata" not in payload
        assert "id" not in payload

    def test_includes_english_preamble(self) -> None:
        batch = [{"id": "1", "title": "Note", "excerpt": "Text", "folder_path": "Inbox"}]
        payload = _build_discover_payload(batch)
        assert payload.startswith("Notes sample:\n\n")

    def test_json_part_is_valid(self) -> None:
        batch = [{"id": "1", "title": "Note", "excerpt": "Text", "folder_path": "Inbox"}]
        payload = _build_discover_payload(batch)
        json_part = payload.split("\n\n", 1)[-1]
        items = json.loads(json_part)
        assert items[0]["title"] == "Note"
        assert "id" not in items[0]

    def test_preserves_title_excerpt_folder_path(self) -> None:
        batch = [{"id": "x", "title": "Meeting", "excerpt": "Budget", "folder_path": "Work/Finance"}]
        payload = _build_discover_payload(batch)
        items = json.loads(payload.split("\n\n", 1)[-1])
        assert items[0] == {"title": "Meeting", "excerpt": "Budget", "folder_path": "Work/Finance"}


class TestRunDiscover:
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

        mocker.patch(
            "scripts.classify.discover_themes.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_taxonomy", return_value=minimal_taxonomy
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_discover_prompt", return_value="{CATEGORIES}"
        )
        mocker.patch(
            "scripts.classify.discover_themes.get_provider", return_value=mock_llm_provider
        )

        run_discover(export_file=str(export_file), dry_run=True)

        mock_llm_provider.classify_messages.assert_not_called()

    def test_real_run_writes_theme_map(
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
            {"themes": [{"name": "Technology", "estimated_count": 10}]}
        )

        mocker.patch(
            "scripts.classify.discover_themes.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_taxonomy", return_value=minimal_taxonomy
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_discover_prompt", return_value="{CATEGORIES}"
        )
        mocker.patch(
            "scripts.classify.discover_themes.get_provider", return_value=mock_llm_provider
        )
        mocker.patch("scripts.classify.discover_themes.THEME_MAPS_DIR", tmp_path)

        run_discover(export_file=str(export_file), dry_run=False)

        theme_files = list(tmp_path.glob("themes-*.json"))
        assert len(theme_files) == 1
        data = json.loads(theme_files[0].read_text())
        assert "themes" in data

    def test_missing_export_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
        mock_llm_provider: MagicMock,
    ) -> None:
        mocker.patch(
            "scripts.classify.discover_themes.load_settings", return_value=minimal_settings
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_taxonomy", return_value=minimal_taxonomy
        )
        mocker.patch(
            "scripts.classify.discover_themes.load_discover_prompt", return_value="{CATEGORIES}"
        )
        mocker.patch(
            "scripts.classify.discover_themes.get_provider", return_value=mock_llm_provider
        )

        with pytest.raises(SystemExit):
            run_discover(export_file=str(tmp_path / "nonexistent.json"), dry_run=True)
