"""Tests for scripts/classify/discover_themes.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.classify.discover_themes import (
    _discover_batch,
    _extract_json_object,
    _is_context_overflow,
    inject_discover_taxonomy,
    run_discover,
)


class TestInjectDiscoverTaxonomy:
    def test_replaces_categories_placeholder(self, minimal_taxonomy: dict) -> None:
        template = "Analyze notes. Categories: {CATEGORIES}. Find themes."
        result = inject_discover_taxonomy(template, minimal_taxonomy)
        assert "{CATEGORIES}" not in result
        assert "Inbox" in result
        assert "Resources" in result

    def test_empty_taxonomy(self) -> None:
        result = inject_discover_taxonomy("Categories: {CATEGORIES}", {"forever_notes": {}})
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


class TestExtractJsonObject:
    def test_plain_object(self) -> None:
        result = _extract_json_object('{"themes": [{"name": "Tech"}]}')
        assert result == {"themes": [{"name": "Tech"}]}

    def test_object_in_prose(self) -> None:
        text = 'Here is the result:\n{"themes": []}\nDone.'
        result = _extract_json_object(text)
        assert result == {"themes": []}

    def test_object_in_code_fence(self) -> None:
        text = '```json\n{"themes": [{"name": "Health"}]}\n```'
        result = _extract_json_object(text)
        assert result == {"themes": [{"name": "Health"}]}

    def test_no_object_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON object"):
            _extract_json_object("No JSON here at all.")


class TestIsContextOverflow:
    def test_context_window_message(self) -> None:
        assert _is_context_overflow(Exception("context window exceeded")) is True

    def test_unrelated_message(self) -> None:
        assert _is_context_overflow(Exception("network error")) is False


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
            batch = json.loads(user)
            if call_count == 1 and len(batch) > 1:
                raise Exception("context_length exceeded")
            return json.dumps({"themes": [{"name": f"Theme{len(batch)}"}]})

        mock_llm_provider.classify_messages.side_effect = side_effect
        batch = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
        result = _discover_batch(mock_llm_provider, "system", batch)
        assert len(result) == 2


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
