"""Generate speech audio and write it to a file.

Run:
    uv run python examples/text_to_speech.py
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

from llm4free import Client

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def save_audio(
    audio: str | Generator[bytes, None, None], destination: Path
) -> None:
    if isinstance(audio, str):
        shutil.copyfile(audio, destination)
        return

    with destination.open("wb") as handle:
        for chunk in audio:
            handle.write(chunk)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = Client()

    audio = client.audio.speech.create(
        input_text=(
            "Welcome to the weekly product update. "
            "This week we shipped faster search, improved caching, "
            "and a new command palette."
        ),
        model="auto",
        response_format="mp3",
        stream=True,
    )

    destination = OUTPUT_DIR / "update.mp3"
    save_audio(audio, destination)
    print(f"saved {destination}")
    print(f"provider: {client.audio.speech.last_provider}")


if __name__ == "__main__":
    main()
