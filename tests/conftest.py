"""Shared pytest fixtures for manage-apple-notes tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--real-providers",
        action="store_true",
        default=False,
        help="Run integration tests that call live Apple Intelligence or Ollama.",
    )

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESPONSES_DIR = FIXTURES_DIR / "responses"
NOTES_DIR = FIXTURES_DIR / "notes"


# ---------------------------------------------------------------------------
# Synthetic note data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_notes() -> list[dict]:
    return json.loads((NOTES_DIR / "sample_notes.json").read_text())


@pytest.fixture
def minimal_settings() -> dict:
    return {
        "notes_root_folder": "Library",
        "capture_inbox_folder": "Notes",
        "notes_account": "iCloud",
        "anthropic_api_key_env": "ANTHROPIC_API_KEY",
        "llm_provider": "anthropic",
        "llm_providers": {
            "anthropic": {"model": "claude-sonnet-4-6", "context_size": 8192, "batch_size": 20},
        },
        "export": {"max_body_chars": 2000, "skip_empty": True},
        "folder_nesting": "natural",
        "thresholds": {
            "inactive_project_days": 90,
            "stub_words": 5,
            "inbox_stale_days": 7,
            "fleeting_stale_days": 30,
            "min_notes_for_subfolder": 8,
            "min_notes_for_hub": 3,
            "max_folder_depth": 3,
        },
        "deduplication": {
            "fuzzy_title_threshold": 85,
            "jaccard_content_threshold": 80,
            "content_preview_chars": 300,
        },
    }


@pytest.fixture
def deep_taxonomy() -> dict:
    return {
        "taxonomy": {
            "inbox": {"folder": "Inbox"},
            "resources": {
                "folder": "Resources",
                "subfolders": [
                    "Cooking",
                    {
                        "name": "Programming",
                        "subfolders": [
                            "Python",
                            {"name": "Systems", "subfolders": ["Networking"]},
                        ],
                    },
                ],
            },
            "archive": {"folder": "Archive"},
        }
    }


@pytest.fixture
def minimal_taxonomy() -> dict:
    return {
        "taxonomy": {
            "inbox": {"folder": "Inbox"},
            "projects": {"folder": "Projects"},
            "resources": {
                "folder": "Resources",
                "subfolders": ["Reference"],
            },
            "archive": {"folder": "Archive"},
        }
    }


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    provider = MagicMock()
    provider.name = "mock"
    provider.model = "mock-model"
    provider.classify_messages.return_value = json.dumps(
        [
            {
                "id": "x-coredata://test-uuid/ICNote/p1",
                "proposed_folder": "Resources",
                "proposed_subfolder": "Reference",
                "confidence": "high",
                "reason": "Technical reference material",
            }
        ]
    )
    return provider


# ---------------------------------------------------------------------------
# Anthropic API mocks
# ---------------------------------------------------------------------------


def _load_response_fixture(filename: str) -> MagicMock:
    import anthropic

    data = json.loads((RESPONSES_DIR / filename).read_text())
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(spec=anthropic.types.TextBlock, text=data["content"][0]["text"])
    ]
    mock_response.model = data["model"]
    mock_response.stop_reason = data["stop_reason"]
    return mock_response


@pytest.fixture
def mock_anthropic_success(mocker: MagicMock) -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _load_response_fixture("classify_success.json")
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_anthropic_malformed(mocker: MagicMock) -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _load_response_fixture("classify_malformed.json")
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_anthropic_rate_limit(mocker: MagicMock) -> MagicMock:
    import anthropic as anthropic_module

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = anthropic_module.RateLimitError(
        message="Rate limit exceeded",
        response=MagicMock(status_code=429),
        body={},
    )
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_anthropic_connection_error(mocker: MagicMock) -> MagicMock:
    import anthropic as anthropic_module

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = anthropic_module.APIConnectionError(
        request=MagicMock()
    )
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# subprocess / osascript mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_subprocess_success(mocker: MagicMock) -> MagicMock:
    mock = mocker.patch("subprocess.run")
    result = MagicMock()
    result.returncode = 0
    result.stdout = "created:p42"
    result.stderr = ""
    mock.return_value = result
    return mock


@pytest.fixture
def mock_subprocess_error(mocker: MagicMock) -> MagicMock:
    mock = mocker.patch("subprocess.run")
    mock.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["osascript", "-e", "..."],
        stderr="Notes got an error: -1728",
    )
    return mock


@pytest.fixture
def mock_popen_success(mocker: MagicMock) -> MagicMock:
    mock_popen = mocker.patch("subprocess.Popen")
    mock_proc = MagicMock()
    mock_proc.stdout.readline.side_effect = ["[MOVED] Note 1\n", "[SKIP] Note 2\n", ""]
    mock_proc.returncode = 0
    mock_proc.wait.return_value = 0
    mock_popen.return_value = mock_proc
    return mock_popen


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_data_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect CWD to tmp_path so relative 'data/' writes never reach the real data/ dir."""
    monkeypatch.chdir(tmp_path)
