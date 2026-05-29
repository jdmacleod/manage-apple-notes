# Mock Patterns Reference

Exact code patterns for the `test-author` skill.

---

## Anthropic API Response Fixture Schema

Save as `tests/fixtures/responses/classify_success.json`:

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "{\"folder_path\": \"Resources/Reference\", \"confidence\": 0.92}"
    }
  ],
  "model": "claude-sonnet-4-6",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 312, "output_tokens": 18}
}
```

Save as `tests/fixtures/responses/classify_malformed_json.json`:

```json
{
  "id": "msg_02ABC",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "I think this note belongs in Resources/Reference (high confidence)."
    }
  ],
  "model": "claude-sonnet-4-6",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 312, "output_tokens": 24}
}
```

---

## conftest.py — Full Shared Fixtures

```python
"""conftest.py — shared pytest fixtures for manage-apple-notes tests."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESPONSES_DIR = FIXTURES_DIR / "responses"
NOTES_DIR = FIXTURES_DIR / "notes"


# ---------------------------------------------------------------------------
# Synthetic note data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_notes() -> list[dict]:
    """A small set of synthetic notes safe to use in any test."""
    return [
        {
            "id": "x-coredata://test-uuid/ICNote/p1",
            "title": "Router reset procedure",
            "body": "Hold reset button 10s. Default login: admin/admin.",
            "folder": "Inbox",
            "folder_path": "Inbox",
        },
        {
            "id": "x-coredata://test-uuid/ICNote/p2",
            "title": "Website redesign kickoff",
            "body": "Meeting notes from 2026-03-01. Action items: wireframes by Friday.",
            "folder": "Inbox",
            "folder_path": "Inbox",
        },
        {
            "id": "x-coredata://test-uuid/ICNote/p3",
            "title": "",
            "body": "",
            "folder": "Inbox",
            "folder_path": "Inbox",
        },
    ]


@pytest.fixture
def minimal_settings() -> dict:
    """A minimal valid settings dict — avoids loading settings.local.yaml."""
    return {
        "notes_root_folder": "Library",
        "capture_inbox_folder": "Notes",
        "notes_account": "iCloud",
        "anthropic_api_key_env": "ANTHROPIC_API_KEY",
    }


# ---------------------------------------------------------------------------
# Anthropic API mocks
# ---------------------------------------------------------------------------

def _load_response(filename: str) -> MagicMock:
    """Load a response fixture JSON and wrap it in a MagicMock."""
    data = json.loads((RESPONSES_DIR / filename).read_text())
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=data["content"][0]["text"])]
    mock_response.model = data["model"]
    mock_response.stop_reason = data["stop_reason"]
    return mock_response


@pytest.fixture
def mock_anthropic_success(mocker):
    """Mock Anthropic client returning a valid classification response."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _load_response("classify_success.json")
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_anthropic_malformed(mocker):
    """Mock Anthropic client returning non-JSON prose (model hallucination)."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _load_response(
        "classify_malformed_json.json"
    )
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


@pytest.fixture
def mock_anthropic_rate_limit(mocker):
    """Mock Anthropic client raising RateLimitError on first call."""
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
def mock_anthropic_connection_error(mocker):
    """Mock Anthropic client raising APIConnectionError."""
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
def mock_subprocess_success(mocker):
    """Mock subprocess.run returning success with sample folder list."""
    mock = mocker.patch("subprocess.run")
    result = MagicMock()
    result.returncode = 0
    result.stdout = "Library, Inbox"
    result.stderr = ""
    mock.return_value = result
    return mock


@pytest.fixture
def mock_subprocess_notes_error(mocker):
    """Mock subprocess.run raising CalledProcessError (Notes object not found)."""
    mock = mocker.patch("subprocess.run")
    mock.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["osascript", "-e", "..."],
        stderr="Notes got an error: -1728",
    )
    return mock


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_data_directory_writes(tmp_path, monkeypatch):
    """Redirect any accidental data/ writes to tmp_path during tests."""
    # This is a soft guard — it won't catch reads, but prevents test pollution
    data_dir = Path("data")
    if not data_dir.exists():
        monkeypatch.chdir(tmp_path)
```

---

## Example Test File — test_classify_notes.py

```python
"""Tests for scripts/classify_notes.py"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import call

# Import only the functions under test
from scripts.classify_notes import call_api, parse_classification, classify_all


class TestCallApi:
    def test_happy_path(self, mock_anthropic_success):
        """call_api returns raw text from the model response."""
        import anthropic
        client = anthropic.Anthropic()
        result = call_api(client, "Test prompt")
        assert isinstance(result, str)
        assert "folder_path" in result

    def test_rate_limit_raises(self, mock_anthropic_rate_limit):
        """call_api re-raises RateLimitError so caller can apply backoff."""
        import anthropic
        client = anthropic.Anthropic()
        with pytest.raises(anthropic.RateLimitError):
            call_api(client, "Test prompt")

    def test_connection_error_raises(self, mock_anthropic_connection_error):
        """call_api re-raises APIConnectionError."""
        import anthropic
        client = anthropic.Anthropic()
        with pytest.raises(anthropic.APIConnectionError):
            call_api(client, "Test prompt")


class TestParseClassification:
    def test_valid_json(self):
        raw = '{"folder_path": "Resources/Reference", "confidence": 0.9}'
        result = parse_classification(raw)
        assert result["folder_path"] == "Resources/Reference"
        assert result["confidence"] == pytest.approx(0.9)

    def test_malformed_json_raises(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_classification("This is prose, not JSON.")

    def test_missing_required_key_raises(self):
        with pytest.raises(ValueError, match="missing keys"):
            parse_classification('{"folder_path": "Inbox"}')  # missing confidence


class TestDryRun:
    def test_dry_run_makes_no_api_calls(
        self, mock_anthropic_success, sample_notes, minimal_settings, tmp_path
    ):
        """With --dry-run, classify_all should not call the Anthropic API."""
        import anthropic
        client = anthropic.Anthropic()
        output = tmp_path / "classifications.json"
        classify_all(
            notes=sample_notes,
            settings=minimal_settings,
            client=client,
            output_path=output,
            dry_run=True,
        )
        mock_anthropic_success.messages.create.assert_not_called()
        assert not output.exists()
```
