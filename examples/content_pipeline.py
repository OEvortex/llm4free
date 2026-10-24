"""Build a small content package from a topic.

This example chains chat, image, and speech generation, and shows how to
supply an API key for authenticated providers.

Run:
    uv run python examples/content_pipeline.py

Set LLM4FREE_API_KEY to enable providers that require authentication.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import urllib.request
from pathlib import Path

from llm4free import Client
from llm4free.TTI.pollinations import PollinationsAI

OUTPUT_ROOT = Path(__file__).resolve().parent / "output"


def build_client() -> Client:
    api_key = os.getenv("LLM4FREE_API_KEY")
    return Client(
        api_key=api_key,
        drop_auth_providers=api_key is None,
        print_provider_info=True,
    )


def ask(client: Client, prompt: str, max_tokens: int = 900) -> str:
    response = client.chat.completions.create(
        model="auto",
        messages=[
            {"role": "system", "content": "You are a careful technical writer."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.4,
    )
    message = response.choices[0].message
    return (message.content if message else None) or ""


def write_article(client: Client, topic: str) -> str:
    return ask(
        client,
        f"Write a concise 400-word Markdown article about {topic}. "
        "Use one H1 heading and two H2 sections.",
    )


def save_image(
    url: str | None, b64_json: str | None, destination: Path
) -> None:
    if url:
        with urllib.request.urlopen(url, timeout=60) as response:
            destination.write_bytes(response.read())
        return
    if b64_json:
        destination.write_bytes(base64.b64decode(b64_json))
        return
    raise ValueError("Image response contains neither url nor b64_json")


def create_cover(client: Client, topic: str, destination: Path) -> None:
    image_prompt = ask(
        client,
        f"Write one vivid image-generation prompt for an article cover about "
        f"{topic}. Return only the prompt.",
        max_tokens=120,
    ).strip()

    response = client.images.generate(
        prompt=image_prompt,
        model="auto",
        n=1,
        size="1024x1024",
        provider=PollinationsAI,
    )
    image = response.data[0]
    save_image(image.url, image.b64_json, destination)


def create_narration(
    client: Client, article: str, destination: Path
) -> None:
    script = ask(
        client,
        "Turn this article into a 60-second narration script.\n\n" + article,
        max_tokens=300,
    )
    audio = client.audio.speech.create(
        input_text=script,
        model="auto",
        response_format="mp3",
        stream=True,
    )

    if isinstance(audio, str):
        shutil.copyfile(audio, destination)
        return

    with destination.open("wb") as handle:
        for chunk in audio:
            handle.write(chunk)


def main() -> None:
    topic = "why local-first software is making a comeback"
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60]
    output_dir = OUTPUT_ROOT / slug
    output_dir.mkdir(parents=True, exist_ok=True)

    client = build_client()

    article = write_article(client, topic)
    article_path = output_dir / "article.md"
    article_path.write_text(article, encoding="utf-8")

    cover_path = output_dir / "cover.png"
    create_cover(client, topic, cover_path)

    narration_path = output_dir / "narration.mp3"
    create_narration(client, article, narration_path)

    print("\nGenerated:")
    print(article_path)
    print(cover_path)
    print(narration_path)


if __name__ == "__main__":
    main()
