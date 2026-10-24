"""Generate images and save the results to disk.

Run:
    uv run python examples/images.py
"""

from __future__ import annotations

import base64
import urllib.request
from pathlib import Path

from llm4free import Client

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


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


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = Client()

    response = client.images.generate(
        prompt=(
            "Editorial cover illustration of a quiet city street at dawn, "
            "soft light, minimal color palette, high detail"
        ),
        model="auto",
        n=2,
        size="1024x1024",
        response_format="b64_json",
    )

    for index, image in enumerate(response.data, start=1):
        destination = OUTPUT_DIR / f"cover_{index}.png"
        save_image(image.url, image.b64_json, destination)
        print(f"saved {destination}")

    print(f"provider: {client.images.last_provider}")


if __name__ == "__main__":
    main()
