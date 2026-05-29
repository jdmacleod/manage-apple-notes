# Python Conventions Reference

Annotated snippets for the `python-review` skill.

---

## Anthropic API Call Pattern

### Bare except — flag this

```python
def classify_note(client, note_content: str) -> dict:
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": note_content}],
        )
        return json.loads(response.content[0].text)
    except Exception:
        return {}  # silently returns empty on any failure
```

**Problems:** Swallows rate limit signals, network errors, and parse
failures identically. Caller has no way to distinguish a transient error
from a permanent one.

### Correct pattern — separate call from parse, handle each error type

```python
def call_api(client: anthropic.Anthropic, prompt: str) -> str:
    """Call the Anthropic API and return the raw text response."""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except anthropic.RateLimitError:
        # Caller should retry with exponential backoff
        raise
    except anthropic.APIStatusError as e:
        raise RuntimeError(
            f"Anthropic API error {e.status_code}: {e.message}"
        ) from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError(
            f"Could not reach Anthropic API: {e}"
        ) from e


def parse_classification(raw: str) -> dict:
    """Parse the model's JSON response. Raises ValueError on bad output."""
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model returned invalid JSON: {e}\nRaw: {raw[:200]}") from e
    # Validate required keys
    required = {"folder_path", "confidence"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Model response missing keys: {missing}")
    return result
```

---

## subprocess / osascript Pattern

### Missing check=True — flag this

```python
def run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
    )
    return result.stdout.decode("utf-8").strip()
    # If osascript exits non-zero, stdout is empty and no error is raised
```

### shell=True with variable — flag this

```python
# DANGEROUS: note_title could contain shell metacharacters
cmd = f"osascript -e 'tell application \"Notes\" to get note \"{note_title}\"'"
result = subprocess.run(cmd, shell=True, capture_output=True)
```

### Correct pattern

```python
def run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout. Raises on non-zero exit."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=True,   # raises CalledProcessError on non-zero exit
    )
    return result.stdout.strip()
```

For cases where failure should be handled gracefully rather than raising:

```python
def run_applescript_safe(script: str) -> tuple[bool, str]:
    """Returns (success, output_or_error)."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, result.stdout.strip()
```

---

## YAML Config Loading

### Unvalidated access — flag this

```python
def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

# Later, in another function:
config = load_config(settings_path)
root = config["notes_root_folder"]  # KeyError if key missing — opaque error
```

### Correct pattern — validate at load time

```python
REQUIRED_SETTINGS = {
    "notes_root_folder",
    "capture_inbox_folder",
    "anthropic_api_key_env",
}

def load_settings(path: Path) -> dict:
    """Load and validate settings.local.yaml. Raises on missing keys."""
    if not path.exists():
        raise FileNotFoundError(
            f"Settings file not found: {path}\n"
            f"Copy config/settings.example.yaml to {path} and fill it in."
        )
    with open(path) as f:
        config = yaml.safe_load(f)
    missing = REQUIRED_SETTINGS - config.keys()
    if missing:
        raise ValueError(
            f"Missing required settings keys: {missing}\n"
            f"See config/settings.example.yaml for reference."
        )
    return config
```

---

## Proposal File I/O

### Non-atomic write — flag on data/ files

```python
# RISKY: a crash between open() and close() leaves a corrupt/partial file
with open(proposals_path, "w") as f:
    json.dump(proposals, f, indent=2)
```

### Atomic write pattern

```python
import os
import tempfile
from pathlib import Path

def write_proposals(proposals: list[dict], output_path: Path) -> None:
    """Write proposals atomically — no partial file on crash."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=output_path.parent,
        delete=False,
        suffix=".tmp",
        encoding="utf-8",
    ) as tmp:
        json.dump(proposals, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name
    os.replace(tmp_path, output_path)  # atomic on POSIX
```

---

## Dry-Run Guard

### Missing guard — flag on any write script

```python
def apply_proposals(proposals_path: Path, notes_account: str) -> None:
    proposals = json.loads(proposals_path.read_text())
    for group in proposals["groups"]:
        if group["resolution"] == "delete":
            for note_id in group["delete_ids"]:
                delete_note(note_id)  # no dry-run check anywhere
```

### Correct guard pattern

```python
def apply_proposals(
    proposals_path: Path,
    notes_account: str,
    dry_run: bool = False,
) -> None:
    proposals = json.loads(proposals_path.read_text())
    for group in proposals["groups"]:
        if group["resolution"] == "delete":
            for note_id in group["delete_ids"]:
                if dry_run:
                    print(f"[dry-run] would delete note {note_id}")
                else:
                    delete_note(note_id)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("proposals", type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without applying them")
    args = parser.parse_args()
    apply_proposals(args.proposals, dry_run=args.dry_run)
```

---

## pathlib vs os.path

All of these `os.path` patterns should be replaced with `pathlib`:

| os.path (flag) | pathlib (correct) |
|---|---|
| `os.path.join(a, b)` | `Path(a) / b` |
| `os.path.exists(p)` | `Path(p).exists()` |
| `os.path.dirname(p)` | `Path(p).parent` |
| `os.path.basename(p)` | `Path(p).name` |
| `os.path.splitext(p)` | `Path(p).stem`, `Path(p).suffix` |
| `open(os.path.join(...))` | `open(Path(...) / ...)` |

---

## Type Annotation Completeness

### Missing annotations — flag on public functions

```python
# No annotations — intent unclear, untestable without runtime introspection
def classify_notes(notes, config, client):
    ...
```

### Correct — annotate all public function signatures

```python
from pathlib import Path
import anthropic

def classify_notes(
    notes: list[dict],
    config: dict,
    client: anthropic.Anthropic,
    dry_run: bool = False,
) -> list[dict]:
    ...
```

Private helpers (prefixed `_`) are lower priority but should still be
annotated on non-trivial functions.
