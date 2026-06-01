"""Tests for scripts/review/run_review.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.review.run_review import (
    build_folder_choices,
    filter_by_confidence,
    find_latest_dedup_proposal,
    find_latest_proposal,
    review_classify_proposal,
    review_dedup_proposal,
    run_review,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_proposal(
    moves: list[dict] | None = None,
    needs_review: list[dict] | None = None,
    no_change: list[dict] | None = None,
) -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "source_export": "data/exports/notes-2026-01-01.json",
        "moves": moves or [],
        "needs_review": needs_review or [],
        "no_change": no_change or [],
    }


def _make_dedup_proposal(groups: list[dict] | None = None) -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "source_export": "data/exports/notes-2026-01-01.json",
        "groups": groups or [],
    }


# ── build_folder_choices ───────────────────────────────────────────────────────


class TestBuildFolderChoices:
    def test_flat_taxonomy_returns_top_level_folders(self) -> None:
        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "projects": {"folder": "Projects"},
            }
        }
        choices = build_folder_choices(taxonomy)
        paths = [c["path"] for c in choices]
        assert "Inbox" in paths
        assert "Projects" in paths

    def test_includes_subfolders(self) -> None:
        taxonomy = {
            "taxonomy": {
                "permanent": {
                    "folder": "Permanent",
                    "subfolders": [{"name": "Health"}, {"name": "Tech"}],
                }
            }
        }
        choices = build_folder_choices(taxonomy)
        paths = [c["path"] for c in choices]
        assert "Permanent" in paths
        assert "Permanent/Health" in paths
        assert "Permanent/Tech" in paths

    def test_subfolder_entry_has_correct_fields(self) -> None:
        taxonomy = {
            "taxonomy": {
                "permanent": {
                    "folder": "Permanent",
                    "subfolders": [{"name": "Health"}],
                }
            }
        }
        choices = build_folder_choices(taxonomy)
        sub = next(c for c in choices if c["path"] == "Permanent/Health")
        assert sub["folder"] == "Permanent"
        assert sub["subfolder"] == "Health"

    def test_empty_taxonomy_returns_empty(self) -> None:
        assert build_folder_choices({}) == []
        assert build_folder_choices({"taxonomy": {}}) == []

    def test_skips_categories_without_folder(self) -> None:
        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": ""},
                "projects": {"folder": "Projects"},
            }
        }
        choices = build_folder_choices(taxonomy)
        assert len(choices) == 1
        assert choices[0]["path"] == "Projects"


# ── filter_by_confidence ───────────────────────────────────────────────────────


class TestFilterByConfidence:
    def _moves(self) -> list[dict]:
        return [
            {"id": "1", "confidence": "high"},
            {"id": "2", "confidence": "medium"},
            {"id": "3", "confidence": "low"},
        ]

    def test_high_keeps_only_high(self) -> None:
        kept, dropped = filter_by_confidence(self._moves(), "high")
        assert len(kept) == 1
        assert kept[0]["confidence"] == "high"
        assert dropped == 2

    def test_medium_keeps_high_and_medium(self) -> None:
        kept, dropped = filter_by_confidence(self._moves(), "medium")
        assert len(kept) == 2
        assert all(m["confidence"] in ("high", "medium") for m in kept)
        assert dropped == 1

    def test_unknown_threshold_keeps_all(self) -> None:
        kept, dropped = filter_by_confidence(self._moves(), "unknown")
        assert len(kept) == 3
        assert dropped == 0

    def test_empty_input(self) -> None:
        kept, dropped = filter_by_confidence([], "high")
        assert kept == []
        assert dropped == 0


# ── find_latest_proposal ──────────────────────────────────────────────────────


class TestFindLatestProposal:
    def test_returns_most_recent(self, tmp_path: Path) -> None:
        (tmp_path / "proposal-2026-01-01.json").write_text("{}")
        newer = tmp_path / "proposal-2026-06-01.json"
        newer.write_text("{}")
        with patch("scripts.review.run_review.PROPOSALS_DIR", tmp_path):
            result = find_latest_proposal()
        assert result == newer

    def test_raises_when_empty(self, tmp_path: Path) -> None:
        with (
            patch("scripts.review.run_review.PROPOSALS_DIR", tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            find_latest_proposal()


class TestFindLatestDedupProposal:
    def test_returns_most_recent(self, tmp_path: Path) -> None:
        (tmp_path / "dedup-2026-01-01.json").write_text("{}")
        newer = tmp_path / "dedup-2026-06-01.json"
        newer.write_text("{}")
        with patch("scripts.review.run_review.DEDUP_PROPOSALS_DIR", tmp_path):
            result = find_latest_dedup_proposal()
        assert result == newer

    def test_raises_when_empty(self, tmp_path: Path) -> None:
        with (
            patch("scripts.review.run_review.DEDUP_PROPOSALS_DIR", tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            find_latest_dedup_proposal()


# ── review_classify_proposal ───────────────────────────────────────────────────


class TestReviewClassifyProposal:
    def test_no_needs_review_returns_unchanged_moves(self, tmp_path: Path) -> None:
        proposal = _make_proposal(
            moves=[{"id": "1", "confidence": "high", "title": "A"}],
        )
        path = tmp_path / "proposal.json"
        result = review_classify_proposal(proposal, path, confidence=None)
        assert len(result["moves"]) == 1

    def test_confidence_filter_drops_low(self, tmp_path: Path) -> None:
        proposal = _make_proposal(
            moves=[
                {"id": "1", "confidence": "high", "title": "A"},
                {"id": "2", "confidence": "low", "title": "B"},
            ],
        )
        path = tmp_path / "proposal.json"
        result = review_classify_proposal(proposal, path, confidence="medium")
        assert len(result["moves"]) == 1
        assert result["moves"][0]["id"] == "1"

    def test_needs_review_placed_when_user_selects_folder(
        self, mocker: MagicMock, tmp_path: Path
    ) -> None:
        proposal = _make_proposal(
            needs_review=[
                {"id": "nr1", "title": "My Note", "current_folder": "Inbox", "reason": "unclear"}
            ]
        )
        path = tmp_path / "proposal.json"
        taxonomy = {
            "taxonomy": {
                "permanent": {"folder": "Permanent"},
                "projects": {"folder": "Projects"},
            }
        }
        mocker.patch("scripts.review.run_review.load_taxonomy", return_value=taxonomy)
        mocker.patch("typer.prompt", return_value="1")  # select "Permanent"
        result = review_classify_proposal(proposal, path, confidence=None)
        assert len(result["moves"]) == 1
        assert result["moves"][0]["id"] == "nr1"
        assert result["moves"][0]["proposed_folder"] == "Permanent"
        assert result["needs_review"] == []

    def test_needs_review_skipped_on_last_option(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal = _make_proposal(
            needs_review=[
                {"id": "nr1", "title": "My Note", "current_folder": "Inbox", "reason": "unclear"}
            ]
        )
        path = tmp_path / "proposal.json"
        taxonomy = {"taxonomy": {"permanent": {"folder": "Permanent"}}}
        mocker.patch("scripts.review.run_review.load_taxonomy", return_value=taxonomy)
        # Last option is always "Skip — leave in needs_review" (index = len(choices) + 1)
        mocker.patch("typer.prompt", return_value="2")  # "2" = Skip (1 folder + 1 skip option)
        result = review_classify_proposal(proposal, path, confidence=None)
        assert result["moves"] == []
        assert len(result["needs_review"]) == 1

    def test_no_taxonomy_skips_placement(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal = _make_proposal(
            needs_review=[{"id": "nr1", "title": "Note", "current_folder": "Inbox"}]
        )
        path = tmp_path / "proposal.json"
        mocker.patch("scripts.review.run_review.load_taxonomy", return_value={})
        result = review_classify_proposal(proposal, path, confidence=None)
        assert result["moves"] == []


# ── review_dedup_proposal ──────────────────────────────────────────────────────


class TestReviewDedupProposal:
    def test_no_delete_groups_returns_unchanged(self, tmp_path: Path) -> None:
        proposal = _make_dedup_proposal(
            groups=[{"group_id": 1, "resolution": "review", "notes": [], "keep_id": ""}]
        )
        path = tmp_path / "dedup.json"
        result = review_dedup_proposal(proposal, path)
        assert len(result["groups"]) == 1
        assert result["groups"][0]["resolution"] == "review"

    def test_confirmed_group_stays_in_proposal(self, mocker: MagicMock, tmp_path: Path) -> None:
        group = {
            "group_id": 1,
            "resolution": "delete",
            "duplicate_type": "exact",
            "notes": [
                {"id": "a", "title": "Note A", "content_preview": "..."},
                {"id": "b", "title": "Note B", "content_preview": "..."},
            ],
            "keep_id": "a",
        }
        proposal = _make_dedup_proposal(groups=[group])
        path = tmp_path / "dedup.json"
        mocker.patch("typer.confirm", return_value=True)
        result = review_dedup_proposal(proposal, path)
        assert len(result["groups"]) == 1
        assert result["groups"][0]["resolution"] == "delete"

    def test_declined_group_removed_from_proposal(self, mocker: MagicMock, tmp_path: Path) -> None:
        group = {
            "group_id": 1,
            "resolution": "delete",
            "duplicate_type": "near_duplicate",
            "notes": [
                {"id": "a", "title": "Note A", "content_preview": ""},
                {"id": "b", "title": "Note B", "content_preview": ""},
            ],
            "keep_id": "a",
        }
        proposal = _make_dedup_proposal(groups=[group])
        path = tmp_path / "dedup.json"
        mocker.patch("typer.confirm", return_value=False)
        result = review_dedup_proposal(proposal, path)
        assert result["groups"] == []

    def test_review_groups_always_kept(self, mocker: MagicMock, tmp_path: Path) -> None:
        delete_group = {
            "group_id": 1,
            "resolution": "delete",
            "duplicate_type": "exact",
            "notes": [
                {"id": "a", "title": "A", "content_preview": ""},
                {"id": "b", "title": "B", "content_preview": ""},
            ],
            "keep_id": "a",
        }
        review_group = {
            "group_id": 2,
            "resolution": "review",
            "notes": [{"id": "c", "title": "C"}, {"id": "d", "title": "D"}],
            "keep_id": "",
        }
        proposal = _make_dedup_proposal(groups=[delete_group, review_group])
        path = tmp_path / "dedup.json"
        mocker.patch("typer.confirm", return_value=False)  # decline delete group
        result = review_dedup_proposal(proposal, path)
        remaining = [g["resolution"] for g in result["groups"]]
        assert "review" in remaining
        assert "delete" not in remaining


# ── run_review ─────────────────────────────────────────────────────────────────


class TestRunReview:
    def _write_proposal(self, path: Path, proposal: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proposal, indent=2))

    def test_writes_updated_proposal(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal_dir = tmp_path / "proposals"
        proposal_dir.mkdir()
        path = proposal_dir / "proposal-2026-01-01.json"
        proposal = _make_proposal(moves=[{"id": "1", "confidence": "high", "title": "A"}])
        self._write_proposal(path, proposal)

        mocker.patch("scripts.review.run_review.PROPOSALS_DIR", proposal_dir)
        mocker.patch("scripts.review.run_review.review_classify_proposal", return_value=proposal)

        run_review(proposal_file=str(path), dedup=False, confidence=None)

        assert path.exists()
        bak = path.with_suffix(".json.pre-review.bak")
        assert bak.exists()

    def test_exits_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            run_review(proposal_file=str(tmp_path / "missing.json"), dedup=False, confidence=None)

    def test_exits_when_no_proposals_found(self, tmp_path: Path) -> None:
        with patch("scripts.review.run_review.PROPOSALS_DIR", tmp_path), pytest.raises(SystemExit):
            run_review(proposal_file=None, dedup=False, confidence=None)

    def test_dedup_path_calls_dedup_review(self, mocker: MagicMock, tmp_path: Path) -> None:
        dedup_dir = tmp_path / "dedup"
        dedup_dir.mkdir()
        path = dedup_dir / "dedup-2026-01-01.json"
        proposal = _make_dedup_proposal()
        self._write_proposal(path, proposal)

        mocker.patch("scripts.review.run_review.DEDUP_PROPOSALS_DIR", dedup_dir)
        dedup_mock = mocker.patch(
            "scripts.review.run_review.review_dedup_proposal", return_value=proposal
        )

        run_review(proposal_file=str(path), dedup=True, confidence=None)
        dedup_mock.assert_called_once()

    def test_confidence_passed_to_review_function(self, mocker: MagicMock, tmp_path: Path) -> None:
        proposal_dir = tmp_path / "proposals"
        proposal_dir.mkdir()
        path = proposal_dir / "proposal-2026-01-01.json"
        proposal = _make_proposal()
        self._write_proposal(path, proposal)

        mocker.patch("scripts.review.run_review.PROPOSALS_DIR", proposal_dir)
        review_mock = mocker.patch(
            "scripts.review.run_review.review_classify_proposal", return_value=proposal
        )

        run_review(proposal_file=str(path), dedup=False, confidence="high")
        _, _, confidence_arg = review_mock.call_args[0]
        assert confidence_arg == "high"
