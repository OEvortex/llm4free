import base64
import shutil
import urllib.request
from pathlib import Path

from llm4free import Client

client = Client()
output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)
topic = "why local-first software is making a comeback"

# 1. Article
resp = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a careful technical writer."},
        {"role": "user", "content": f"Write a 400-word Markdown article about {topic}."},
    ],
)
message = resp.choices[0].message
article = (message.content if message else "") or ""
article_path = output_dir / "article.md"
article_path.write_text(article, encoding="utf-8")

# 2. Cover image
resp = client.chat.completions.create(
    model="auto",
    messages=[
        {
            "role": "user",
            "content": f"Write one vivid image prompt for a cover about {topic}. "
            "Return only the prompt.",
        }
    ],
)
message = resp.choices[0].message
image_prompt = (message.content if message else "") or topic
cover = client.images.generate(prompt=image_prompt, model="auto").data[0]
cover_path = output_dir / "cover.png"
if cover.url:
    request = urllib.request.Request(cover.url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        cover_path.write_bytes(response.read())
elif cover.b64_json:
    cover_path.write_bytes(base64.b64decode(cover.b64_json))

# 3. Narration
resp = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "Turn this into a 60-second script:\n\n" + article}
    ],
)
message = resp.choices[0].message
script = (message.content if message else "") or article

audio = client.audio.speech.create(
    input_text=script,
    model="auto",
    response_format="mp3",
    stream=True,
)
narration_path = output_dir / "narration.mp3"
if isinstance(audio, str):
    shutil.copyfile(audio, narration_path)
else:
    with narration_path.open("wb") as handle:
        for chunk in audio:
            handle.write(chunk)

print("\nGenerated:")
print(article_path)
print(cover_path)
print(narration_path)
