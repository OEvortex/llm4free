import re

import requests

from llm4free.litagent import LitAgent
from llm4free.sanitize import sanitize_stream


def remove_stats(content: str) -> str:
    """Remove ChatJimmy's statistics trailer from the assistant response."""
    return re.split(r"<\|stats\|>", content, maxsplit=1)[0].rstrip()


resp = requests.post(
    "https://chatjimmy.ai/api/chat",
    headers=LitAgent().generate_fingerprint(),
    json={
        "messages": [{"role": "user", "content": input(">>> ")}],
        "chatOptions": {
            "selectedModel": "llama3.1-8B",
            "systemPrompt": "",
            "topK": 8,
        },
        "attachment": None,
    },
    timeout=60,
)
resp.raise_for_status()

for chunk in sanitize_stream(
    resp,
    to_json=False,
    intro_value=None,
    content_extractor=remove_stats,
    raw=False,
): # type: ignore
    print(chunk, end="", flush=True)
