# 🖼️ LLM4Free Text-to-Image (TTI)

LLM4Free ships a set of text-to-image providers behind one OpenAI-style interface. Every provider exposes `images.create(...)` and returns an `ImageResponse` (a pydantic model) containing a `created` timestamp and a `data` list of `ImageData` objects with either a `url` or a `b64_json` string.

## ✨ Features

- **Unified API** – the same keyword-only `images.create()` call works across all providers
- **URL or Base64 output** – choose `response_format="url"` or `"b64_json"`
- **Format conversion** – optional in-memory PNG/JPEG conversion via Pillow (`convert_format=True`)
- **Model listing** – `provider.models.list()` returns the provider's model/style names
- **Fallback image hosting** – URL output is uploaded through catbox.moe → 0x0.st → anonfiles.com → transfer.sh, retrying each service before moving on
- **No API keys for most providers** – 9 of the 13 providers work anonymously

## 📦 Providers

All names below are importable from `llm4free.TTI`.

| Provider | Auth required | Default `model` | Models / styles |
|---|---|---|---|
| `BingImageAI` | Yes – `cookies.json` (Bing session) | `dalle3` | `dalle3`, `mai-image-1`, `gpt4o` |
| `Lexica` | No | `lexica` | `lexica` |
| `MagicHourAI` | No | `general` | 16 styles (`photorealistic`, `cinematic`, `anime`, `cartoon`, `watercolor`, `digital-art`, `fantasy`, `vector`, `minimalist`, `illustration`, `3d-render`, `oil-painting`, `sketch`, `retro`, `surreal`, ...) |
| `MagicStudioAI` | No | `magicstudio` | `magicstudio` |
| `MiragicAI` | No | `flux` | `flux`, `turbo`, `gptimage` |
| `NoLoginTool` | No | `@cf/black-forest-labs/flux-1-schnell` | 7 Cloudflare/Horde models (see `AVAILABLE_MODELS`) |
| `OneFreeAI` | No | `qwen_image_plus` | `qwen_image_plus`, `flux_1_1_pro`, `flux_1_1_pro_ultra`, `nano_banana`, `nano_banana_pro` |
| `PerchanceAI` | No (optional `user_key`) | `painted-anime` | 38 styles |
| `PollinationsAI` | No | **required** (no default) | 16 models (`flux`, `flux-pro`, `flux-realism`, `flux-anime`, `flux-3d`, `any-dark`, `turbo`, `gptimage`, `gptimage-large`, `kontext`, `nanobanana`, `nanobanana-pro`, `seedream`, `seedream-pro`, `qwen-image`, `grok-imagine`) |
| `RaphaelAI` | Yes – signed-in cookies (2 anonymous generations/day otherwise) | `raphael-basic` | `raphael-basic`, `raphael-2`, `gpt-image-2`, `nano-banana-2`, `nano-banana-pro`, `seedream-5` |
| `StableHordeAI` | No (optional API key for queue priority) | `auto` | Fetched dynamically from the AI Horde status endpoint (`154+` models at time of writing, falls back to `Deliberate`) |
| `TogetherImage` | Yes – Together API key | **required** (no default) | Fetched from the Together models endpoint; 13 FLUX models are used as a fallback list |
| `VisualGPT` | Yes – `cookies.json` (VisualGPT session) | **required** (no default) | `nano-banana` |

`provider.required_auth` and `provider.working` are class attributes that report these capabilities.

## 🚀 Quick Start

```python
from llm4free.TTI import PollinationsAI

client = PollinationsAI()

response = client.images.create(
    model="flux",
    prompt="A futuristic city skyline at sunset",
    n=2,
    response_format="url",
)

for image in response.data:
    print(image.url)
```

### Base64 output

```python
response = client.images.create(
    model="flux",
    prompt="Crystal mountain landscape",
    response_format="b64_json",
)
print(response.data[0].b64_json[:64])
```

### Listing models

```python
from llm4free.TTI import MagicHourAI

client = MagicHourAI()
print(client.models.list())
```

### Converting the output format

```python
from llm4free.TTI import MiragicAI

client = MiragicAI()
response = client.images.create(
    model="turbo",
    prompt="A paper-cut landscape",
    image_format="jpeg",
    convert_format=True,   # requires Pillow
    response_format="b64_json",
)
```

### Save an image to disk

```python
import base64
from llm4free.TTI import PollinationsAI

client = PollinationsAI()
response = client.images.create(
    model="flux", prompt="A red panda", response_format="b64_json"
)
with open("red_panda.png", "wb") as f:
    f.write(base64.b64decode(response.data[0].b64_json))
```

## 🔧 API

```python
images.create(
    *,
    model: str,
    prompt: str,
    n: int = 1,
    size: str = "1024x1024",
    response_format: str = "url",      # "url" | "b64_json"
    user: str | None = None,
    style: str = "none",
    aspect_ratio: str = "1:1",
    timeout: int | None = None,
    image_format: str = "png",         # "png" | "jpeg" (MagicStudioAI defaults to "jpg")
    seed: int | None = None,
    convert_format: bool = False,
    **kwargs,                          # provider-specific extras
) -> ImageResponse
```

- `model` has a default on most providers; it is required for `PollinationsAI`, `TogetherImage`, and `VisualGPT`.
- `n` is honoured by loop-based providers; providers that generate one image per request may return fewer items.
- `response_format` must be `"url"` or `"b64_json"`; anything else raises `ValueError`.
- When `response_format="url"` and every hosting service fails, providers raise `RuntimeError`.
- `convert_format=True` requires Pillow; otherwise the original bytes are returned.

`ImageResponse`/`ImageData` are re-exported from `llm4free.TTI`:

```python
from llm4free.TTI import ImageData, ImageResponse

print(ImageResponse(created=0, data=[ImageData(url="https://example.com/a.png")]))
```

## 🔐 Authenticated providers

### BingImageAI

```python
from llm4free.TTI import BingImageAI

# cookies.json is loaded during __init__ and FileNotFoundError is raised if missing.
client = BingImageAI(cookies_file="cookies.json")
response = client.images.create(model="dalle3", prompt="A cute red cat")
print(response.data[0].url)
```

Export Bing cookies from your browser after signing in to Bing Image Creator. Microsoft Rewards limits the free tier (~15 images/day).

### VisualGPT

```python
from llm4free.TTI import VisualGPT

client = VisualGPT(cookies_file="visualgpt_cookies.json")
response = client.images.create(model="nano-banana", prompt="A neon-lit alley")
```

### RaphaelAI

`RaphaelAI` prefers a signed-in session. Anonymous use is limited to about two generations per day, after which the provider raises a `RuntimeError` describing `ANON_DAILY_LIMIT`.

```python
from llm4free.TTI import RaphaelAI

client = RaphaelAI.from_browser(headed=True)  # harvests cookies from raphael.app
response = client.images.create(model="raphael-basic", prompt="A mountain lake")
```

### TogetherImage

```python
from llm4free.TTI import TogetherImage

client = TogetherImage(api_key="YOUR_TOGETHER_KEY")
print(client.models.list())
response = client.images.create(
    model="black-forest-labs/FLUX.1-schnell",
    prompt="A surreal desert",
)
```

### StableHordeAI

```python
from llm4free.TTI import StableHordeAI

client = StableHordeAI()  # anonymous key is used by default
response = client.images.create(
    model="auto",
    prompt="A japanese waifu in a short kimono",
    steps=30,
    cfg_scale=7.0,
    sampler_name="k_euler_a",
    karras=True,
)
```

Stable Horde extras: `enhance`, `steps`, `cfg_scale`, `sampler_name`, `karras`, `trusted_workers`, `nsfw`, `censor_nsfw`.

## 🖥️ Image hosting

The `llm4free/TTI/image_hosting.py` module uploads generated bytes through a fallback chain. Each service is retried `max_retries=3` times before moving on, and the first successful URL is returned:

1. `catbox.moe` (JSON API)
2. `0x0.st` (plain-text URL response)
3. `anonfiles.com` (JSON API — the current endpoint may be unavailable)
4. `transfer.sh` (HTTP PUT)

All services are used without authentication. Availability and retention are controlled by each service, so URLs are best treated as temporary.

## 🧩 Adding a provider

1. Subclass `TTICompatibleProvider` and a `BaseImages` implementation, then set `images` in `__init__`.
2. Define `AVAILABLE_MODELS`, `required_auth`, and `working`.
3. Implement a `models` property returning `SimpleModelList(...)`.
4. Export the class from `llm4free/TTI/__init__.py`.

See `base.py` and `utils.py` for the contracts.

## 📄 License

Part of the LLM4Free project — Apache-2.0.
