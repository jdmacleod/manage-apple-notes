import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

raw = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
base_url = raw if raw.endswith("/v1") else f"{raw}/v1"
model = os.environ.get("OLLAMA_MODEL", "llama3")

client = OpenAI(
    base_url=base_url,
    api_key="ollama",  # required by the SDK; ignored by Ollama and llama.cpp
)

response = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in one sentence."},
    ],
    stream=True,
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
