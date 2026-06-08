"""Tests for scripts/forever_notes/sync_hubs.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scripts.folder_utils import folder_name
from scripts.forever_notes.sync_hubs import (
    HEAVY_ASTERISK,
    _build_home_body,
    _build_theme_index,
    _generate_hub_body,
    _hub_tag,
    _hub_title,
    _lookup_uuids,
    _note_link,
    _subfolders,
    _theme_order,
    _url_id,
    _write_note_applescript,
    run_sync_hubs,
)


class TestUrlId:
    def test_extracts_numeric_part(self) -> None:
        assert _url_id("x-coredata://uuid/ICNote/p123") == "123"

    def test_returns_empty_for_empty_string(self) -> None:
        assert _url_id("") == ""

    def test_handles_non_p_prefix(self) -> None:
        assert _url_id("x-coredata://uuid/ICNote/123") == "123"

    def test_handles_single_segment(self) -> None:
        assert _url_id("p42") == "42"


class TestHubTag:
    def test_explicit_tag_used(self) -> None:
        sf = {"name": "Reference", "hub_tag": "#custom-tag"}
        assert _hub_tag(sf) == "#custom-tag"

    def test_generates_from_name(self) -> None:
        sf = {"name": "Cooking & Recipes"}
        tag = _hub_tag(sf)
        assert tag.startswith("#")
        assert "cooking" in tag
        assert "&" not in tag

    def test_lowercases_and_hyphenates(self) -> None:
        sf = {"name": "Industry And Work"}
        assert _hub_tag(sf) == "#industry-and-work"


class TestHubTitle:
    def test_explicit_hub_title_used(self) -> None:
        sf = {"name": "Reference", "hub_title": "✱ Custom Title"}
        assert _hub_title(sf, "✱ ") == "✱ Custom Title"

    def test_generated_from_prefix_and_name(self) -> None:
        sf = {"name": "Reference"}
        assert _hub_title(sf, "✱ ") == "✱ Reference"


class TestNoteLink:
    def test_with_uuid_returns_href(self) -> None:
        link = _note_link("Test Note", "x-coredata://uuid/p1", "STABLE-UUID-123")
        assert 'href="applenotes://showNote?identifier=STABLE-UUID-123"' in link
        assert "Test Note" in link

    def test_with_nid_only_returns_href(self) -> None:
        link = _note_link("Test Note", "x-coredata://uuid/p42")
        assert 'href="applenotes://showNote?identifier=42"' in link

    def test_no_id_returns_escaped_text(self) -> None:
        link = _note_link("Test Note", "")
        assert link == "Test Note"
        assert "href" not in link

    def test_escapes_html_special_chars(self) -> None:
        link = _note_link("A & B", "")
        assert "&amp;" in link


class TestFolderNameAndSubfolders:
    def testfolder_name_from_dict(self) -> None:
        assert folder_name({"folder": "Resources"}) == "Resources"

    def testfolder_name_from_string(self) -> None:
        assert folder_name("Resources") == "Resources"

    def test_subfolders_dict_entries(self) -> None:
        entry = {"folder": "Resources", "subfolders": [{"name": "Reference"}, {"name": "Tools"}]}
        result = _subfolders(entry)
        assert len(result) == 2
        assert result[0]["name"] == "Reference"

    def test_subfolders_string_entries_wrapped(self) -> None:
        entry = {"folder": "Resources", "subfolders": ["Reference", "Tools"]}
        result = _subfolders(entry)
        assert result[0] == {"name": "Reference"}

    def test_subfolders_empty(self) -> None:
        assert _subfolders({"folder": "Inbox"}) == []


class TestBuildThemeIndex:
    def test_includes_themes_above_min_count(self) -> None:
        taxonomy = {
            "taxonomy": {
                "resources": {
                    "folder": "Resources",
                    "subfolders": [{"name": "Reference"}],
                }
            }
        }
        notes = [
            {"folder_path": "Resources/Reference", "title": f"Note {i}", "id": f"p{i}"}
            for i in range(5)
        ]
        index = _build_theme_index(taxonomy, notes, min_count=3)
        assert "Reference" in index
        assert index["Reference"]["total"] == 5

    def test_excludes_themes_below_min_count(self) -> None:
        taxonomy = {
            "taxonomy": {
                "resources": {
                    "folder": "Resources",
                    "subfolders": [{"name": "Reference"}],
                }
            }
        }
        notes = [
            {"folder_path": "Resources/Reference", "title": "Note 1", "id": "p1"},
        ]
        index = _build_theme_index(taxonomy, notes, min_count=5)
        assert "Reference" not in index

    def test_empty_taxonomy_returns_empty(self) -> None:
        index = _build_theme_index({}, [], min_count=1)
        assert index == {}

    def test_three_level_path_indexed_by_leaf(self) -> None:
        taxonomy = {
            "taxonomy": {
                "resources": {
                    "folder": "Resources",
                    "subfolders": [
                        {"name": "Programming", "subfolders": ["Python"]},
                    ],
                }
            }
        }
        notes = [
            {"folder_path": "Resources/Programming/Python", "title": f"Note {i}", "id": f"p{i}"}
            for i in range(5)
        ]
        index = _build_theme_index(taxonomy, notes, min_count=3)
        assert "Python" in index
        assert index["Python"]["total"] == 5


class TestGenerateHubBody:
    def test_text_mode_no_links(self) -> None:
        sf_def = {"name": "Reference", "hub_title": f"{HEAVY_ASTERISK} Reference"}
        categories = {"Resources": [("Router setup", "x-coredata://uuid/p1")]}
        body = _generate_hub_body(sf_def, categories, f"{HEAVY_ASTERISK} ", use_links=False)
        assert "Router setup" in body
        assert "href" not in body

    def test_html_mode_with_links(self) -> None:
        sf_def = {"name": "Reference", "hub_title": f"{HEAVY_ASTERISK} Reference"}
        categories = {"Resources": [("Router setup", "x-coredata://uuid/p1")]}
        uuid_map = {"1": "STABLE-UUID"}
        body = _generate_hub_body(
            sf_def, categories, f"{HEAVY_ASTERISK} ", uuid_map=uuid_map, use_links=True
        )
        assert "href" in body

    def test_multiple_categories_get_h2_headings(self) -> None:
        sf_def = {"name": "Reference"}
        categories = {
            "Areas": [("Note A", "p1")],
            "Resources": [("Note B", "p2")],
        }
        body = _generate_hub_body(sf_def, categories, "✱ ", use_links=False)
        assert "<h2>" in body

    def test_single_category_no_h2(self) -> None:
        sf_def = {"name": "Reference"}
        categories = {"Resources": [("Note B", "p2")]}
        body = _generate_hub_body(sf_def, categories, "✱ ", use_links=False)
        assert "<h2>" not in body

    def test_cat_order_overrides_alphabetical(self) -> None:
        """Categories appear in taxonomy key order, not alphabetically."""
        sf_def = {"name": "Health"}
        # Alphabetical order would be Areas before Inbox, but taxonomy has Inbox first.
        categories = {
            "Areas": [("Note A", "p1")],
            "Inbox": [("Note B", "p2")],
        }
        # Taxonomy: inbox (pos 0) before areas (pos 1)
        cat_order = {"Inbox": 0, "Areas": 1}
        body = _generate_hub_body(sf_def, categories, "✱ ", use_links=False, cat_order=cat_order)
        inbox_pos = body.index("Inbox")
        areas_pos = body.index("Areas")
        assert inbox_pos < areas_pos, "Inbox section must precede Areas when taxonomy so dictates"

    def test_no_cat_order_falls_back_to_alphabetical(self) -> None:
        """Without cat_order, categories fall back to alphabetical order."""
        sf_def = {"name": "Health"}
        categories = {
            "Inbox": [("Note B", "p2")],
            "Areas": [("Note A", "p1")],
        }
        body = _generate_hub_body(sf_def, categories, "✱ ", use_links=False)
        # No cat_order → alphabetical: Areas before Inbox
        areas_pos = body.index("Areas")
        inbox_pos = body.index("Inbox")
        assert areas_pos < inbox_pos


class TestBuildHomeBody:
    def test_includes_category_headings(self, minimal_taxonomy: dict) -> None:
        body = _build_home_body(minimal_taxonomy, {}, {}, "✱ ", "✱ Home")
        assert "Inbox" in body
        assert "Resources" in body

    def test_hub_eligible_subfolder_appears(self, minimal_taxonomy: dict) -> None:
        hub_index = {
            "Reference": {
                "_sf_def": {"name": "Reference", "hub_title": "✱ Reference"},
                "categories": {"Resources": [("Note", "p1")]},
                "total": 5,
            }
        }
        body = _build_home_body(minimal_taxonomy, hub_index, hub_index, "✱ ", "✱ Home")
        assert "✱ Reference" in body

    def test_non_hub_subfolder_appears_plain(self, minimal_taxonomy: dict) -> None:
        # "Reference" is in home_index but not hub_index → plain text leaf.
        home_index = {
            "Reference": {
                "_sf_def": {"name": "Reference"},
                "categories": {"Resources": [("Note", "p1")]},
                "total": 2,
            }
        }
        body = _build_home_body(minimal_taxonomy, {}, home_index, "✱ ", "✱ Home")
        assert "Reference" in body
        assert "✱ Reference" not in body

    def test_subfolder_below_home_threshold_suppressed(self, minimal_taxonomy: dict) -> None:
        # Empty home_index: "Reference" is in the taxonomy but has no notes → not rendered.
        body = _build_home_body(minimal_taxonomy, {}, {}, "✱ ", "✱ Home")
        assert "Reference" not in body

    def test_home_only_subfolder_appears_as_leaf(self, minimal_taxonomy: dict) -> None:
        # Subfolder meets min_notes_for_home_link but not min_notes_for_hub:
        # it appears in home_index but not hub_index, so renders as plain leaf name.
        home_index = {
            "Reference": {
                "_sf_def": {"name": "Reference"},
                "categories": {"Resources": [("Note", "p1")]},
                "total": 1,
            }
        }
        body = _build_home_body(minimal_taxonomy, {}, home_index, "✱ ", "✱ Home")
        assert "Reference" in body
        assert "✱ Reference" not in body
        assert "href" not in body

    def test_deep_subfolder_appears_in_home(self, deep_taxonomy: dict) -> None:
        hub_index = {
            "Python": {
                "_sf_def": {"name": "Python", "hub_title": "✱ Python"},
                "categories": {"Resources": [("Note", "p1")]},
                "total": 4,
            }
        }
        body = _build_home_body(deep_taxonomy, hub_index, hub_index, "✱ ", "✱ Home")
        assert "✱ Python" in body

    def test_deep_subfolder_indented_after_parent(self, deep_taxonomy: dict) -> None:
        hub_index = {
            "Programming": {
                "_sf_def": {"name": "Programming"},
                "categories": {"Resources": [("Note", "p1")]},
                "total": 4,
            },
            "Python": {
                "_sf_def": {"name": "Python"},
                "categories": {"Resources": [("Note", "p2")]},
                "total": 4,
            },
        }
        body = _build_home_body(deep_taxonomy, hub_index, hub_index, "✱ ", "✱ Home")
        prog_pos = body.index("Programming")
        python_pos = body.index("Python")
        assert python_pos > prog_pos
        assert "&nbsp;" in body

    def test_subfolders_sorted_by_export_order(self) -> None:
        # Taxonomy lists Finance before Health, but export has Health first.
        # The Home body should reflect the export order (Health before Finance).
        taxonomy = {
            "taxonomy": {
                "areas": {
                    "folder": "Areas",
                    "subfolders": ["Finance", "Health & Wellness"],
                }
            }
        }
        home_index = {
            "Finance": {"_sf_def": {"name": "Finance"}, "categories": {}, "total": 5},
            "Health & Wellness": {
                "_sf_def": {"name": "Health & Wellness"},
                "categories": {},
                "total": 5,
            },
        }
        export_sf_order = {"Areas/Health & Wellness": 0, "Areas/Finance": 1}
        body = _build_home_body(
            taxonomy,
            {},
            home_index,
            "✱ ",
            "✱ Home",
            export_sf_order=export_sf_order,
        )
        assert body.index("Health &amp; Wellness") < body.index("Finance")

    def test_subfolder_not_in_export_falls_to_end(self) -> None:
        # "NewFolder" is in taxonomy but not in export → appears after export-ordered entries.
        taxonomy = {
            "taxonomy": {
                "areas": {
                    "folder": "Areas",
                    "subfolders": ["NewFolder", "Finance"],
                }
            }
        }
        home_index = {
            "Finance": {"_sf_def": {"name": "Finance"}, "categories": {}, "total": 5},
            "NewFolder": {"_sf_def": {"name": "NewFolder"}, "categories": {}, "total": 5},
        }
        # Export only knows Finance (NewFolder not yet moved to Apple Notes)
        export_sf_order = {"Areas/Finance": 0}
        body = _build_home_body(
            taxonomy,
            {},
            home_index,
            "✱ ",
            "✱ Home",
            export_sf_order=export_sf_order,
        )
        # Finance (in export, pos 0) should appear before NewFolder (not in export)
        assert body.index("Finance") < body.index("NewFolder")

    def test_export_sf_order_none_preserves_taxonomy_order(self) -> None:
        # When export_sf_order is not provided, taxonomy list order is preserved.
        taxonomy = {
            "taxonomy": {
                "areas": {
                    "folder": "Areas",
                    "subfolders": ["Finance", "Health & Wellness"],
                }
            }
        }
        home_index = {
            "Finance": {"_sf_def": {"name": "Finance"}, "categories": {}, "total": 5},
            "Health & Wellness": {
                "_sf_def": {"name": "Health & Wellness"},
                "categories": {},
                "total": 5,
            },
        }
        body = _build_home_body(taxonomy, {}, home_index, "✱ ", "✱ Home")
        # No export_sf_order → taxonomy order (Finance first)
        assert body.index("Finance") < body.index("Health &amp; Wellness")


class TestLookupUuids:
    def test_empty_keys_returns_empty(self) -> None:
        result = _lookup_uuids([])
        assert result == {}

    def test_db_not_exists_returns_empty(self, mocker: MagicMock) -> None:
        mocker.patch(
            "scripts.forever_notes.sync_hubs.NOTESTORE_DB", Path("/nonexistent/NoteStore.sqlite")
        )
        result = _lookup_uuids(["123"])
        assert result == {}

    def test_permission_error_returns_empty(self, mocker: MagicMock, tmp_path: Path) -> None:
        fake_db = tmp_path / "NoteStore.sqlite"
        fake_db.write_bytes(b"fake db")
        mocker.patch("scripts.forever_notes.sync_hubs.NOTESTORE_DB", fake_db)
        mocker.patch("shutil.copy2", side_effect=PermissionError("no access"))
        result = _lookup_uuids(["123"])
        assert result == {}

    def test_sqlite_success_returns_mapping(self, mocker: MagicMock, tmp_path: Path) -> None:
        fake_db = tmp_path / "NoteStore.sqlite"
        fake_db.write_bytes(b"fake db")
        mocker.patch("scripts.forever_notes.sync_hubs.NOTESTORE_DB", fake_db)
        mocker.patch("shutil.copy2")

        mock_con = MagicMock()
        mock_con.execute.return_value.fetchall.return_value = [(123, "STABLE-UUID-123")]
        mocker.patch("sqlite3.connect", return_value=mock_con)

        result = _lookup_uuids(["123"])
        assert result == {"123": "STABLE-UUID-123"}


class TestWriteNoteApplescript:
    def test_dry_run_returns_dry_run_status(self) -> None:
        status, local_id = _write_note_applescript(
            "Test Note", "<p>body</p>", "Inbox", dry_run=True
        )
        assert status == "[DRY RUN]"
        assert local_id == ""

    def test_success_returns_status_and_id(self, mocker: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "created:p42"
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        status, local_id = _write_note_applescript(
            "Test Note", "<p>body</p>", "Inbox", dry_run=False
        )
        assert status == "created"
        assert local_id == "p42"

    def test_nonzero_exit_returns_error(self, mocker: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Notes error -1728"
        mocker.patch("subprocess.run", return_value=mock_result)

        status, local_id = _write_note_applescript(
            "Test Note", "<p>body</p>", "Inbox", dry_run=False
        )
        assert status == "error"
        assert local_id == ""

    def test_account_arg_passed_to_subprocess(self, mocker: MagicMock) -> None:
        mock_result = MagicMock(returncode=0, stdout="created:p1", stderr="")
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        _write_note_applescript(
            "✱ Hub", "<p>body</p>", None, dry_run=False, container="", account="iCloud"
        )

        called_cmd = mock_run.call_args[0][0]
        assert "iCloud" in called_cmd

    def test_empty_account_still_passes_arg(self, mocker: MagicMock) -> None:
        mock_result = MagicMock(returncode=0, stdout="updated:p2", stderr="")
        mock_run = mocker.patch("subprocess.run", return_value=mock_result)

        _write_note_applescript("✱ Hub", "<p>body</p>", None, dry_run=False)

        called_cmd = mock_run.call_args[0][0]
        # Empty string account arg is always appended (7 total args: osascript, script, 5 payload)
        assert len(called_cmd) == 7
        assert called_cmd[-1] == ""


class TestThemeOrder:
    def test_basic_order_matches_taxonomy(self) -> None:
        taxonomy = {
            "taxonomy": {
                "resources": {
                    "folder": "Resources",
                    "subfolders": ["Cooking", "Finance"],
                },
                "areas": {
                    "folder": "Areas",
                    "subfolders": ["Health"],
                },
            }
        }
        order = _theme_order(taxonomy)
        assert order["Cooking"] < order["Finance"] < order["Health"]

    def test_same_leaf_across_categories_uses_first_appearance(self) -> None:
        taxonomy = {
            "taxonomy": {
                "permanent": {
                    "folder": "Permanent",
                    "subfolders": ["Health"],
                },
                "areas": {
                    "folder": "Areas",
                    "subfolders": ["Health", "Finance"],
                },
            }
        }
        order = _theme_order(taxonomy)
        # "Health" first appears under permanent (position 0), Finance second (position 1)
        assert order["Health"] == 0
        assert order["Finance"] == 1

    def test_empty_taxonomy_returns_empty(self) -> None:
        assert _theme_order({}) == {}

    def test_flat_categories_excluded(self) -> None:
        # Flat categories (no subfolders / depth < 2) should not appear in the order map.
        taxonomy = {
            "taxonomy": {
                "inbox": {"folder": "Inbox"},
                "resources": {"folder": "Resources", "subfolders": ["Cooking"]},
            }
        }
        order = _theme_order(taxonomy)
        assert "Inbox" not in order
        assert "Cooking" in order


class TestRunSyncHubs:
    def test_non_strict_mode_exits_early(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        settings = {"forever_notes_mode": "loose"}
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)

        mock_write = mocker.patch("scripts.forever_notes.sync_hubs._write_note_applescript")
        run_sync_hubs(dry_run=True)
        mock_write.assert_not_called()

    def test_strict_mode_dry_run_no_subprocess(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": "x-coredata://test/p1",
                "title": "Python typing guide",
                "folder": "Resources",
                "folder_path": "Resources/Reference",
                "modified": "2026-01-01",
            }
        ] * 10  # 10 notes to meet min_count threshold
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {"hub_title_prefix": "✱ ", "home_note_title": "✱ Home"},
            "thresholds": {"min_notes_for_hub": 5},
            "toplevel_folder": {"enabled": False},
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)

        mock_subprocess = mocker.patch("subprocess.run")
        run_sync_hubs(export_file=str(export_file), dry_run=True)
        mock_subprocess.assert_not_called()

    def test_no_home_eligible_subfolders_exits_early(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        # Empty notes list → home_index is empty → exits before writing anything.
        notes: list[dict] = []
        export_file = tmp_path / "notes-empty.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {"hub_title_prefix": "✱ "},
            "thresholds": {"min_notes_for_hub": 5, "min_notes_for_home_link": 1},
            "toplevel_folder": {"enabled": False},
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)

        mock_write = mocker.patch("scripts.forever_notes.sync_hubs._write_note_applescript")
        run_sync_hubs(export_file=str(export_file), dry_run=True)
        mock_write.assert_not_called()

    def test_container_prefix_stripped_before_theme_index(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        # Export written before toplevel_folder.enabled was set: paths carry the
        # container prefix "Library/Resources/Reference".  Without stripping,
        # _build_theme_index matches nothing → empty home_index → early exit and
        # _write_note_applescript is never called.  With stripping it should be called.
        notes = [
            {
                "id": f"x-coredata://test/p{i}",
                "title": f"Note {i}",
                "folder": "Resources",
                "folder_path": "Library/Resources/Reference",
                "modified": "2026-01-01",
            }
            for i in range(5)
        ]
        export_file = tmp_path / "notes-prefixed.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {"hub_title_prefix": "✱ ", "home_note_title": "✱ Home"},
            "thresholds": {"min_notes_for_hub": 3, "min_notes_for_home_link": 1},
            "toplevel_folder": {"enabled": True, "name": "Library"},
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.forever_notes.sync_hubs.local_taxonomy_exists", return_value=True)

        write_mock = mocker.patch(
            "scripts.forever_notes.sync_hubs._write_note_applescript",
            return_value=("created", "p99"),
        )
        mocker.patch("scripts.forever_notes.sync_hubs.RunLogger")
        run_sync_hubs(export_file=str(export_file), dry_run=False)
        # After stripping "Library/" the notes match "Resources/Reference" in the
        # taxonomy → home_index non-empty → hub and home writes are attempted.
        assert write_mock.called

    def test_primary_account_passed_to_write(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": f"x-coredata://test/p{i}",
                "title": f"Note {i}",
                "folder": "Resources",
                "folder_path": "Resources/Reference",
                "modified": "2026-01-01",
            }
            for i in range(5)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        settings = {
            "forever_notes_mode": "strict",
            "strict_mode": {"hub_title_prefix": "✱ ", "home_note_title": "✱ Home"},
            "thresholds": {"min_notes_for_hub": 1, "min_notes_for_home_link": 1},
            "toplevel_folder": {"enabled": False},
            "primary_account": "iCloud",
        }
        mocker.patch("scripts.forever_notes.sync_hubs.load_settings", return_value=settings)
        mocker.patch("scripts.forever_notes.sync_hubs.load_taxonomy", return_value=minimal_taxonomy)
        mocker.patch("scripts.forever_notes.sync_hubs.local_taxonomy_exists", return_value=True)

        mock_write = mocker.patch(
            "scripts.forever_notes.sync_hubs._write_note_applescript",
            return_value=("created", "p99"),
        )
        mocker.patch("scripts.forever_notes.sync_hubs.RunLogger")

        run_sync_hubs(export_file=str(export_file), dry_run=False)

        # Every call to _write_note_applescript must carry account="iCloud"
        for call in mock_write.call_args_list:
            assert call.kwargs.get("account") == "iCloud"
