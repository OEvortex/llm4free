"""Stream model output token by token.

Run:
    uv run python examples/streaming.py
"""

from __future__ import annotations

from typing import Any

from llm4free import Client


def stream_reply(client: Client, messages: list[dict[str, Any]]) -> None:
    stream = client.chat.completions.create(
        model="auto",
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)

    print()


def main() -> None:
    client = Client(print_provider_info=True)
    stream_reply(
        client,
        [
            {"role": "system", "content": "You are a concise technical writer."},
            {
                "role": "user",
                "content": "Explain how HTTP streaming responses work.",
            },
        ],
    )


if __name__ == "__main__":
    main()
