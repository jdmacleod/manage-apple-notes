"""Smoke test: verifies end-to-end LLM inference with the configured provider.

Uses Ollama if OLLAMA_BASE_URL is set in .env (or the environment), otherwise
falls back to Anthropic via ANTHROPIC_API_KEY.

Usage:
    uv run python scripts/test_inference.py
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()

from scripts.classify.classify_notes import inject_taxonomy, load_prompt_template
from scripts.config import load_settings, load_taxonomy
from scripts.json_utils import extract_json_array
from scripts.providers import LLMProvider, OllamaProvider, get_provider

TEST_NOTE = [
    {
        "id": "test-note-1",
        "title": "Trip to Japan notes",
        "body": (
            "Visited Tokyo, Kyoto, and Osaka. Cherry blossoms were stunning. "
            "Bookmarked restaurants and temples to revisit."
        ),
        "current_folder": "Inbox",
    }
]


def main() -> None:
    settings = load_settings()
    taxonomy = load_taxonomy()
    system_prompt = inject_taxonomy(load_prompt_template(), taxonomy)

    provider: LLMProvider
    if os.environ.get("OLLAMA_BASE_URL"):
        provider = OllamaProvider("llama3")  # OLLAMA_MODEL env var overrides in __init__
    else:
        provider = get_provider(settings)

    print(f"Provider: {provider.name}  Model: {provider.model}")
    print("Sending one test note...")

    response = provider.classify_messages(
        system_prompt,
        json.dumps(TEST_NOTE, indent=2, ensure_ascii=False),
    )
    results = extract_json_array(response)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
