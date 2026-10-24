"""Minimal chat and image generation with llm4free.

Run:
    uv run python examples/quickstart.py
"""

from llm4free import Client


def main() -> None:
    client = Client()

    response = client.chat.completions.create(
        model="auto",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Give me three ideas for a weekend Python project.",
            },
        ],
    )
    message = response.choices[0].message
    print("Chat response:")
    print((message.content if message else None) or "(empty response)")

    image = client.images.generate(
        prompt="A cozy desk with a laptop, warm morning light, photorealistic",
        model="auto",
        n=1,
        size="1024x1024",
    )
    print("\nImage URL:")
    print(image.data[0].url)


if __name__ == "__main__":
    main()
