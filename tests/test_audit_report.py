"""Tests for run_audit report structure and basic output in scripts/maintenance/audit.py."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.maintenance.audit import run_audit


def _make_notes(count: int = 5) -> list[dict]:
    recent_date = datetime.now().isoformat()
    return [
        {
            "id": f"x-coredata://test/p{i}",
            "title": f"Note {i}",
            "body": "Some content here for testing purposes.",
            "folder": "Resources",
            "folder_path": "Resources",
            "modified": recent_date,
        }
        for i in range(count)
    ]


class TestRunAuditStructure:
    def test_dry_run_does_not_write_report(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = _make_notes()
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=None, dry_run=True)

        assert not list(tmp_path.glob("audit-*.md"))

    def test_real_run_writes_report(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = _make_notes()
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-test.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        assert report_path.exists()
        content = report_path.read_text()
        assert "Library Audit" in content
        assert "Library Statistics" in content
        assert "Duplicate Titles" in content

    def test_report_contains_all_sections(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = _make_notes()
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-test.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        for section in [
            "Library Statistics",
            "Inactive Projects",
            "Untitled Notes",
            "Stub Notes",
            "Duplicate Titles",
            "Stale Inbox",
            "Stale Fleeting",
            "Untracked Folders",
            "Uncategorized Notes",
            "Subfolder Candidates",
        ]:
            assert section in content, f"Missing section: {section}"

    def test_statistics_section_contains_category_counts(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        notes = [
            {
                "id": f"r{i}",
                "title": f"Resource {i}",
                "body": "reference material",
                "folder": "Resources",
                "folder_path": "Resources",
                "modified": datetime.now().isoformat(),
            }
            for i in range(3)
        ]
        export_file = tmp_path / "notes-test.json"
        export_file.write_text(json.dumps(notes))
        report_path = tmp_path / "audit-stats.md"

        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        run_audit(export_file=str(export_file), output_override=str(report_path), dry_run=False)

        content = report_path.read_text()
        stats_section = content.split("## Library Statistics")[1].split("\n---\n")[0]
        assert "Resources" in stats_section
        assert "Age Distribution" in stats_section

    def test_missing_export_exits(
        self,
        mocker: MagicMock,
        tmp_path: Path,
        minimal_settings: dict,
        minimal_taxonomy: dict,
    ) -> None:
        mocker.patch("scripts.maintenance.audit.load_settings", return_value=minimal_settings)
        mocker.patch("scripts.maintenance.audit.load_taxonomy", return_value=minimal_taxonomy)

        with pytest.raises(SystemExit):
            run_audit(
                export_file=str(tmp_path / "nonexistent.json"),
                output_override=None,
                dry_run=True,
            )
