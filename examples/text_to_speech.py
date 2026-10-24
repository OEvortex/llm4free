import shutil
from pathlib import Path

from llm4free import Client

client = Client()
output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)

audio = client.audio.speech.create(
    input_text="Welcome to the weekly product update.",
    model="auto",
    response_format="mp3",
    stream=True,
)

path = output_dir / "speech.mp3"
if isinstance(audio, str):
    shutil.copyfile(audio, path)
else:
    with path.open("wb") as handle:
        for chunk in audio:
            handle.write(chunk)
print(path)
