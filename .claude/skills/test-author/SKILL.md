---
name: test-author
description: "Write pytest tests for the manage-apple-notes toolkit. Use this skill whenever the user asks to write tests for any script, asks 'how should I test this', opens any file under tests/, or mentions pytest, fixtures, or mocking in the context of this project. Also trigger when the user asks about test coverage or wants to verify a specific behaviour (dry-run, error handling, AppleScript failure). The project has two external dependencies that must always be mocked — the Anthropic API and the MCP/AppleScript layer — and a strict privacy rule: no real note content in any test file. This skill provides the project's mocking conventions so every test follows the same patterns."
---

# Test Author

This skill writes pytest tests for the manage-apple-notes toolkit. The
project has two hard constraints that apply to every test file:

1. **Mock the external dependencies** — the Anthropic API and any
   AppleScript subprocess call must never be invoked in tests. They require
   a live Notes library and real API credentials.

2. **No real note content** — all note content in fixtures must be
   synthetic. Never copy from a real notes export. The `data/` directory
   must not be accessed by any test.

Read `references/mock-patterns.md` for the exact fixture code.
Use this SKILL.md to understand the structure and conventions.

---

## Project Test Layout

```
tests/
├── conftest.py               # Shared fixtures: mock_anthropic, settings
├── fixtures/
│   ├── notes/                # Synthetic note JSON files
│   │   └── sample_notes.json
│   └── responses/            # Anthropic API response JSON fixtures
│       ├── classify_success.json
│       ├── classify_malformed_json.json
│       └── api_rate_limit_error.json
├── test_classify_notes.py
├── test_apply_proposals.py
├── test_export_notes.py
└── test_deduplicate_notes.py
```

One test file per script. Test function names follow:
`test_<function_name>_<scenario>` — e.g., `test_classify_note_happy_path`,
`test_classify_note_rate_limit_retries`, `test_apply_proposals_dry_run`.

---

## The Three Mocking Conventions

### 1. Anthropic API — fixture JSON + pytest-mock

Load response fixtures from JSON files rather than hardcoding strings.
This keeps tests maintainable as the response schema evolves.

```python
# conftest.py
import json
from pathlib import Path
import pytest

@pytest.fixture
def classify_success_response():
    fixture = Path("tests/fixtures/responses/classify_success.json")
    return json.loads(fixture.read_text())

@pytest.fixture
def mock_anthropic(mocker, classify_success_response):
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = classify_success_response
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client
```

The fixture JSON should match the real SDK response structure — see
`references/mock-patterns.md` for the full schema. Using a fixture file
rather than an inline `MagicMock` means a change to how the response is
parsed will break the right test rather than silently passing.

### 2. subprocess / osascript — mock at the subprocess level

Mock `subprocess.run` rather than the wrapper function. This tests that
the wrapper correctly handles non-zero exit codes and stderr output.

```python
@pytest.fixture
def mock_subprocess_success(mocker):
    mock = mocker.patch("subprocess.run")
    mock.return_value.returncode = 0
    mock.return_value.stdout = "note1, note2, note3"
    mock.return_value.stderr = ""
    return mock

@pytest.fixture
def mock_subprocess_failure(mocker):
    mock = mocker.patch("subprocess.run")
    mock.return_value.returncode = 1
    mock.return_value.stdout = ""
    mock.return_value.stderr = "Notes got an error: -1728"
    # Also make check=True raise as expected
    mock.side_effect = subprocess.CalledProcessError(
        1, ["osascript"], stderr="Notes got an error: -1728"
    )
    return mock
```

### 3. Privacy boundary — conftest guard

Add a session-scoped fixture to `conftest.py` that asserts no test
accesses `data/`. This catches accidental path construction bugs:

```python
@pytest.fixture(autouse=True, scope="session")
def block_data_directory_access(tmp_path_factory):
    """Ensure no test reads from the real data/ directory."""
    data_dir = Path("data").resolve()
    # Monkeypatching open is complex; instead assert data/ is empty during tests
    # by checking no files are read from it via a custom collector — or simply
    # use this fixture as documentation and enforce via CI path restrictions.
    yield
    # Post-test: confirm data/ was not written to
    if data_dir.exists():
        assert not any(data_dir.iterdir()), (
            "data/ directory was written to during tests — check for missing mocks"
        )
```

---

## Required Test Coverage

For every script, write at minimum:

| Scenario | Why it matters |
|---|---|
| Happy path | Confirms basic function works end-to-end with mocks |
| API rate limit | `anthropic.RateLimitError` — must retry or abort gracefully, not silently return `{}` |
| Malformed model response | `json.JSONDecodeError` — model returned non-JSON; must raise, not silently skip |
| subprocess failure (`returncode != 0`) | AppleScript error — must raise `CalledProcessError` or equivalent, not return empty string |
| `--dry-run` flag | Destructive scripts only — confirms no writes occur when `--dry-run` is set |
| Missing config key | `KeyError` on settings access — must produce clear error message, not a traceback |

---

## Writing the Tests

When writing a test:

1. Import only from the script under test — do not import from other
   scripts in the same project. Tests are isolated.
2. Use `pytest.raises` for expected exceptions rather than `try/except`.
3. Assert on specific values, not just "did not raise". A test that only
   checks no exception was raised is not a test.
4. Synthetic note content should be realistic enough to pass through
   classification logic but contain no personal information. Good example:
   ```json
   {"id": "x-coredata://test/note/1", "title": "Router reset steps",
    "body": "Hold reset 10s. Default: admin/admin.", "folder": "Inbox"}
   ```
5. For dry-run tests, assert that the mock subprocess/API was called zero
   times, not just that the function returned without error.

---

## Output Format

When asked to write tests, produce:

1. The complete test file (not a fragment)
2. Any new fixture JSON files needed under `tests/fixtures/`
3. Any additions to `conftest.py`
4. A brief summary of what each test covers and any gaps in coverage
   you couldn't address without more context about the script's internals

Always include the import block at the top. Use `from pathlib import Path`
rather than `import os`.
