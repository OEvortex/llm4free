import base64
import urllib.request
from pathlib import Path

from llm4free import Client

client = Client()
output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)

resp = client.images.generate(
    prompt="A quiet city street at dawn, soft light, minimal color palette",
    model="auto",
    n=2,
)

for index, image in enumerate(resp.data, start=1):
    path = output_dir / f"image_{index}.png"
    if image.url:
        request = urllib.request.Request(
            image.url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    elif image.b64_json:
        path.write_bytes(base64.b64decode(image.b64_json))
    print(path)
