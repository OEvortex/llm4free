"""Multi-turn conversation with retained message history.

Run:
    uv run python examples/conversation.py
"""

from __future__ import annotations

from typing import Any

from llm4free import Client

SYSTEM_PROMPT = "You are a senior Python engineer. Be direct and practical."


class Conversation:
    def __init__(self, client: Client, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._client = client
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    def ask(self, message: str) -> str:
        self._messages.append({"role": "user", "content": message})

        response = self._client.chat.completions.create(
            model="auto",
            messages=self._messages,
            max_tokens=600,
            temperature=0.3,
        )
        reply_message = response.choices[0].message
        reply = (reply_message.content if reply_message else None) or ""

        self._messages.append({"role": "assistant", "content": reply})
        return reply


def main() -> None:
    conversation = Conversation(Client())

    questions = [
        "I have a list of dicts. How do I sort it by the 'score' key?",
        "Show the same sort with reverse=True.",
        "What is the time complexity of that sort?",
    ]

    for question in questions:
        print(f"\nUser: {question}")
        print(f"Assistant: {conversation.ask(question)}")


if __name__ == "__main__":
    main()
