<div align="center">

<a href="https://github.com/OEvortex/llm4free">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/OEvortex/llm4free/blob/main/logo.svg" style="background-color: #f8f9fa; padding: 12px; border-radius: 6px; display: inline-block;">
    <img src="https://github.com/OEvortex/llm4free/blob/main/logo.svg" alt="LLM4Free Logo" width="320">
  </picture>
</a>

<h1>LLM4Free</h1>

<p><strong>A collection of reverse-engineered website AIs — 40+ free LLM chat, image, speech, and search backends exposed through one OpenAI-compatible interface.</strong></p>

<p>
  <a href="https://pypi.org/project/llm4free/"><img src="https://img.shields.io/pypi/v/llm4free.svg?style=flat-square&logo=pypi&label=PyPI" alt="PyPI Version"></a>
  <a href="https://pepy.tech/project/llm4free"><img src="https://static.pepy.tech/badge/llm4free/month?style=flat-square" alt="Monthly Downloads"></a>
  <a href="https://pepy.tech/project/llm4free"><img src="https://static.pepy.tech/badge/llm4free?style=flat-square" alt="Total Downloads"></a>
  <a href="https://github.com/OEvortex/llm4free/stargazers"><img src="https://img.shields.io/github/stars/OEvortex/llm4free?style=flat-square" alt="GitHub Stars"></a>
  <a href="https://github.com/OEvortex/llm4free/network/members"><img src="https://img.shields.io/github/forks/OEvortex/llm4free?style=flat-square" alt="GitHub Forks"></a>
  <a href="#"><img src="https://img.shields.io/pypi/pyversions/llm4free?style=flat-square&logo=python" alt="Python Version"></a>
  <a href="https://github.com/OEvortex/llm4free/blob/main/LICENSE.md"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="License"></a>
  <a href="https://deepwiki.com/OEvortex/llm4free"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</p>

<p>
  <a href="https://t.me/OEvortexAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
  <a href="https://youtube.com/@OEvortex"><img alt="YouTube" src="https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  <a href="https://buymeacoffee.com/oevortex"><img alt="Buy Me A Coffee" src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black"></a>
</p>

</div>

<hr/>

## Overview

LLM4Free is a Python package that collects **reverse-engineered backends for third-party AI websites** and exposes them through a single, consistent interface modeled on the OpenAI SDK. Instead of integrating each site's private front-end yourself, you import one package and call `client.chat.completions.create(...)`, `client.images.generate(...)`, or `client.audio.speech.create(...)`.

Every backend is adapted to the same response shapes, so you can switch providers by changing one argument. The unified `Client` adds automatic provider selection, model resolution, instance caching, and failover.

- **Chat:** 31 LLM providers, most usable without an API key
- **Images:** 13 text-to-image providers
- **Speech:** 14 text-to-speech and 2 speech-to-text providers
- **Search:** DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Parallel, SerpBase, Wikipedia
- **Serving:** a FastAPI server exposing OpenAI- and Anthropic-compatible endpoints
- **Utilities:** HTML parsing, crawling, GitHub data, temporary mail, user-agent rotation, and more

## Scope and disclaimer

> [!WARNING]
> **This package is a collection, not a reverse-engineering tool.**
>
> The providers in LLM4Free wrap the public web interfaces of third-party AI services that were reverse-engineered into API-style backends. LLM4Free collects those backends and adapts them to an OpenAI-compatible interface; it does not itself perform reverse engineering.
>
> - LLM4Free is **not affiliated with or endorsed by** any provider it wraps.
> - Third-party endpoints may change, rate-limit, or block access at any time. Availability is best-effort.
> - You are responsible for complying with each provider's terms of service and all applicable laws.
> - The software is provided **as is**, without warranty of any kind.

See [LEGAL_NOTICE.md](LEGAL_NOTICE.md) for the full terms.

## Key features

| Capability | What you get |
|---|---|
| OpenAI-compatible chat | `chat.completions.create(...)` with streaming and tool calling |
| OpenAI-compatible images | `images.generate(...)` / `images.create(...)` |
| OpenAI-compatible speech | `audio.speech.create(...)` and `audio.transcriptions.create(...)` |
| Unified client | Automatic provider selection, model resolution, caching, failover |
| Free-first defaults | Auth-required providers are excluded unless explicitly enabled |
| Model registry | Enumerate providers, models, and voices programmatically |
| API server | OpenAI `/v1` routes plus Anthropic `/v1/messages` compatibility |
| CLI | Rich-powered search, weather, translation, maps, and more |
| Built-in HTTP client | Zero-dependency, httpx-style client (`llm4free.browser_requests._http`) with optional browser TLS impersonation |
| Typed public API | Type hints and consistent response objects throughout |

## How it works

1. A third-party AI website exposes a public front-end used by its own web UI.
2. Each provider in this package reproduces the requests that front-end makes and normalizes the response.
3. The provider is adapted to the OpenAI-compatible shape: `chat.completions.create(...)`, `images.create(...)`, `tts(...)`, or `audio.transcriptions.create(...)`.
4. The unified `Client` selects a working provider, resolves the requested model, caches instances, and fails over on error.

The result: services that were only usable in a browser become ordinary Python objects and standard HTTP endpoints.

## Requirements

- Python **3.10+**
- No API keys required for free providers
- No HTTP libraries required for the built-in client — it runs on the standard library
- Optional: `fastapi` and `uvicorn` for the API server (`[api]` extra)
- Optional: `primp` for browser TLS/JA3 + HTTP/2 fingerprinting (`[impersonate]` extra)

## Installation

```bash
# Core package
pip install -U llm4free

# With the OpenAI-compatible API server
pip install -U "llm4free[api]"

# With browser TLS/JA3 + HTTP/2 fingerprinting for the built-in HTTP client
pip install -U "llm4free[impersonate]"

# With development tools
pip install -U "llm4free[dev]"
```

With [uv](https://github.com/astral-sh/uv) (recommended):

```bash
uv add llm4free
uv add "llm4free[impersonate]"   # optional browser-fingerprinting backend
uv run llm4free --help
uv tool install llm4free
```

Docker:

```bash
docker build -t llm4free-api .
docker run -p 8000:8000 llm4free-api
```

> [!NOTE]
> No pre-built Docker image is published. The `Dockerfile` builds the image from source at build time. See [docs/DOCKER.md](docs/DOCKER.md) for Compose profiles and deployment options.

## Quick start

```python
from llm4free import Client

client = Client(print_provider_info=True)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms."}],
)

print(response.choices[0].message.content)
print(client.chat.completions.last_provider)
```

`model="auto"` lets the client choose a working provider and model. To pin a backend, use `"Provider/Model"`:

```python
client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

Fuzzy model names are also resolved across providers, so `model="gpt-4o"` will match a provider that serves an equivalent model.

## Chat completions

### Basic usage

```python
from llm4free import Client

client = Client()
response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Summarize the plot of Hamlet in three sentences."},
    ],
)
print(response.choices[0].message.content)
```

### Streaming

```python
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a short poem about the sea."}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

### Tool calling

```python
weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is the weather in London?"}],
    tools=[weather_tool],
)
print(response.choices[0].message.tool_calls)
```

### Direct provider usage

Every provider implements the same interface and can be instantiated directly:

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

Authenticated providers accept an `api_key`:

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-key")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a Python function to sort a list."}],
)
```

## Image generation

```python
from llm4free import Client

client = Client(print_provider_info=True)

image = client.images.generate(
    prompt="A serene mountain landscape at sunset",
    model="auto",
    size="1024x1024",
)
print(image.data[0].url)
```

`images.create(...)` is an alias. To force a backend:

```python
image = client.images.generate(
    prompt="A cyberpunk city at night",
    model="PollinationsAI/flux",
)
```

Direct provider usage:

```python
from llm4free.TTI import PollinationsAI

generator = PollinationsAI()
image = generator.images.create(model="flux", prompt="A cyberpunk city at night")
print(image.data[0].url)
```

## Text-to-speech

```python
from llm4free import Client

client = Client(print_provider_info=True)

audio = client.audio.speech.create(
    input_text="Welcome to the weekly product update.",
    model="auto",
    response_format="mp3",
)
print(audio)  # path to the generated audio file
```

With `stream=True`, the call returns a byte-chunk generator:

```python
chunks = client.audio.speech.create(
    input_text="Streaming speech synthesis.",
    model="auto",
    stream=True,
)
with open("speech.mp3", "wb") as handle:
    for chunk in chunks:
        handle.write(chunk)
```

Direct provider usage:

```python
from llm4free.TTS import ParlerTTS

tts = ParlerTTS()
audio_path = tts.tts("Hello, world!")
print(audio_path)
```

## Speech-to-text

STT providers follow the OpenAI Whisper API shape:

```python
from llm4free.STT import ElevenLabsSTT

stt = ElevenLabsSTT()
with open("audio.mp3", "rb") as audio_file:
    transcription = stt.audio.transcriptions.create(
        model="scribe_v1",
        file=audio_file,
        response_format="text",
    )
print(transcription.text)
```

Available providers: `ElevenLabsSTT`, `CohereSTT`.

## Web search

`client.search` gives every engine an OpenAI-style entry point:

```python
from llm4free import Client

client = Client()
response = client.search.create(
    query="best practices for API design",
    engine="auto",       # or "duckduckgo", "bing", "brave", ...
    max_results=5,
)

print(response.engine)   # e.g. "duckduckgo"
for result in response.data:
    print(result.title, result.href)
```

Pin an engine, query another category, or serialize the response:

```python
client.search.create(query="climate change", engine="bing", max_results=5)
client.search.images("mount everest", max_results=5)
client.search.news("ai regulation", engine="yahoo")
client.search.weather("Tokyo", engine="yahoo")
client.search.text("fastapi").to_dict()
```

Engines: `duckduckgo`, `bing`, `brave`, `yahoo`, `mojeek`, `wikipedia`, `parallel`, and `serpbase` (requires `SERPBASE_API_KEY`). Auto mode fails over across engines; inspect support with `client.search.list_engines()` and `client.search.capabilities()`.

The engine classes are still available for direct use:

```python
from llm4free import DuckDuckGoSearch

search = DuckDuckGoSearch()
results = search.text("best practices for API design", max_results=5)

for result in results:
    print(result["title"], result["href"])
```

## Provider catalog

All chat providers implement `chat.completions.create(...)`. Auth-required providers are excluded by the unified client by default; pass `drop_auth_providers=False` and an `api_key` to enable them.

### Chat — free (no key required)

| Provider | Class | Notes |
|---|---|---|
| Gemini | `Gemini` | Multiple Gemini models |
| GptFree | `GptFree` | GPT-4o-compatible endpoint |
| ChatGPT | `ChatGPT` | Public ChatGPT front-end |
| Toolbaz | `Toolbaz` | Multiple models |
| IBM | `IBM` | IBM Granite Playground |
| PiAI | `PiAI` | Inflection Pi front-end |
| AkashGPT | `AkashGPT` | — |
| ChatJimmy | `ChatJimmy` | — |
| ChatBotChatApp | `ChatBotChatApp` | Multiple hosted models, SSE streaming |
| AskMeAI | `AskMeAI` | Agentic chat front-end, SSE streaming |
| K2Think | `K2Think` | — |
| Miklium | `Miklium` | — |
| Netwrck | `Netwrck` | — |
| OllamaSwarm | `OllamaSwarm` | Ollama-style swarm endpoint |
| TypliAI | `TypliAI` | — |
| WiseCat | `WiseCat` | — |

### Chat — authenticated

| Provider | Class | Module |
|---|---|---|
| AI4Chat | `AI4Chat` | `llm.ai4chat` |
| Cerebras | `Cerebras` | `llm.Auth.cerebras` |
| DeepAI | `DeepAI` | `llm.Auth.deep_ai` |
| DeepInfra | `DeepInfra` | `llm.Auth.deepinfra` |
| Groq | `Groq` | `llm.Auth.groq` |
| HuggingFace | `HuggingFace` | `llm.Auth.huggingface` |
| Nvidia | `Nvidia` | `llm.Auth.nvidia` |
| OpenRouter | `OpenRouter` | `llm.Auth.openrouter` |
| Sambanova | `Sambanova` | `llm.Auth.sambanova` |
| TextPollinations | `TextPollinations` | `llm.Auth.textpollinations` |
| TogetherAI | `TogetherAI` | `llm.Auth.together_ai` |
| TwoAI | `TwoAI` | `llm.Auth.two_ai` |
| UncensoredChat | `UncensoredChat` | `llm.Auth.uncensoredchat` |
| Upstage | `Upstage` | `llm.Auth.upstage` |
| Zenmux | `Zenmux` | `llm.Auth.zenmux` |

### Text-to-image

`BingImageAI`, `Lexica`, `MagicHourAI`, `MagicStudioAI`, `MiragicAI`, `NoLoginTool`, `OneFreeAI`, `PerchanceAI`, `PollinationsAI`, `RaphaelAI`, `StableHordeAI`, `TogetherImage`, `VisualGPT`

### Text-to-speech

`DeepgramTTS`, `ElevenlabsTTS` (key required), `KittenTTS`, `LuxTTS`, `MurfAITTS`, `OpenAIFMTTS`, `ParlerTTS`, `KyutaiTTS`, `QwenTTS`, `SherpaTTS`, `StreamElements`, `TTSAI`, `TTSOpenTTS`, `XLNKTTS`

### Speech-to-text

`ElevenLabsSTT`, `CohereSTT`

### Search engines

| Module | Classes |
|---|---|
| `llm4free.search` | `DuckDuckGoSearch`, `BingSearch`, `BraveSearch`, `YahooSearch`, `Search`, `SearchResponse` |
| `llm4free.search.engines` | `Mojeek`, `Parallel`, `SerpBase`, `Wikipedia` |

## Model registry

```python
from llm4free import model

# Provider -> models mapping
llm_models = model.llm.list()
print(f"Providers: {len(llm_models)}")

summary = model.llm.summary()
print(f"Total models: {summary['models']}")

for provider, count in summary["provider_model_counts"].items():
    print(f"  {provider}: {count} models")

# Provider -> voices mapping
tts_voices = model.tts.list()

# Provider -> models mapping
tti_models = model.tti.list()
```

Detailed metadata is available through `model.llm.providers()` and `model.llm.provider("Gemini")`.

## OpenAI-compatible server

Start a local FastAPI server that exposes every wrapped backend through standard routes:

```bash
llm4free-server
llm4free-server --port 8080 --host 0.0.0.0 --debug
```

Or from Python:

```python
from llm4free.client import run_api

run_api(host="0.0.0.0", port=8000)
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/v1/models` | List models |
| `GET` | `/v1/models/{model}` | Retrieve a model |
| `GET` | `/v1/providers` | List chat providers |
| `POST` | `/v1/chat/completions` | Chat completions (streaming supported) |
| `POST` | `/v1/messages` | Anthropic-compatible messages |
| `POST` | `/v1/images/generations` | Image generation |
| `POST` | `/v1/audio/speech` | Text-to-speech |
| `GET` | `/v1/TTI/models` | List image models |
| `GET` | `/v1/TTS/models` | List speech models |
| `GET` | `/search` | Unified web search |

### OpenAI client

```python
from openai import OpenAI

client = OpenAI(api_key="dummy", base_url="http://localhost:8000/v1")

response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### Docker Compose

```bash
docker compose up llm4free-api
docker compose -f docker-compose.yml -f docker-compose.no-auth.yml up llm4free-api
```

> [!NOTE]
> The server has authentication and rate limiting disabled by default. Do not expose it to untrusted networks without adding your own controls.

Full reference: [docs/openai-api-server.md](docs/openai-api-server.md) | Deployment: [docs/DOCKER.md](docs/DOCKER.md)

## Command-line interface

```bash
llm4free --help
llm4free version

llm4free text -k "python programming"
llm4free images -k "mountains"
llm4free videos -k "documentary"
llm4free news -k "AI breakthrough"
llm4free weather -l "New York"
llm4free answers -k "what is quantum entanglement"
llm4free suggestions -q "python"
llm4free translate -k "Hola" --to en
llm4free maps -k "coffee shops" -p "London"
llm4free search -k "climate change" -e bing
```

### Engines

| Command | Engines |
|---|---|
| `text` | `ddg`, `bing`, `yahoo`, `brave`, `mojeek`, `parallel`, `wikipedia`, `serpbase` |
| `images` | `ddg`, `bing`, `yahoo`, `brave` |
| `videos` | `ddg`, `brave`, `yahoo` |
| `news` | `ddg`, `bing`, `yahoo`, `brave` |
| `suggestions` | `ddg`, `bing`, `yahoo`, `brave` |
| `answers` | `ddg` |
| `maps` | `ddg` |
| `translate` | `ddg` |
| `weather` | `ddg` |

```bash
llm4free text -k "climate change" -e bing
llm4free text -k "quantum physics" -e wikipedia
```

Full CLI reference: [docs/cli.md](docs/cli.md)

## Developer tools

| Tool | Description | Docs |
|---|---|---|
| Scout | HTML parser and web crawler | [docs/scout.md](docs/scout.md) |
| LitPrinter | Styled debug printing | [docs/litprinter.md](docs/litprinter.md) |
| LitAgent | User-agent rotation | [docs/litagent.md](docs/litagent.md) |
| GitAPI | GitHub data extraction | [docs/gitapi.md](docs/gitapi.md) |
| Decorators | `@timeIt` and `@retry` | [docs/decorators.md](docs/decorators.md) |
| Sanitize | Stream sanitization | [docs/sanitize.md](docs/sanitize.md) |
| Prompts | System prompt manager | [docs/awesome-prompts.md](docs/awesome-prompts.md) |

## Configuration

### Client options

| Option | Type | Description |
|---|---|---|
| `provider` | `type` | Default chat provider class |
| `image_provider` | `type` | Default image provider class |
| `api_key` | `str` | Key for authenticated providers |
| `proxies` | `dict` | Proxy configuration applied to all requests |
| `exclude` | `list[str]` | Provider names to exclude from chat |
| `exclude_images` | `list[str]` | Provider names to exclude from images |
| `exclude_tts` | `list[str]` | Provider names to exclude from speech |
| `exclude_search` | `list[str]` | Engine ids to exclude from search auto-selection |
| `print_provider_info` | `bool` | Print the selected provider and model |
| `drop_auth_providers` | `bool` | Exclude auth-required providers (default `True`) |

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `LLM4FREE_HOST` | `0.0.0.0` | Server bind address |
| `LLM4FREE_PORT` | `8000` | Server port |
| `LLM4FREE_WORKERS` | `1` | Server worker processes |
| `LLM4FREE_LOG_LEVEL` | `info` | Server log level |
| `LLM4FREE_DEFAULT_PROVIDER` | — | Default provider for the server |
| `LLM4FREE_BASE_URL` | — | Base URL prefix for routes |
| `LLM4FREE_DEBUG` | `false` | Enable debug mode |
| `LLM4FREE_NO_UPDATE` | — | Set to `1` to disable the update check |

## Project structure

```
llm4free/
├── client.py          # Unified Client with failover and model resolution
├── cli.py             # Rich-powered command-line interface
├── models.py          # Model, voice, and provider registry
├── llm/               # Chat providers (free and authenticated)
├── TTI/               # Text-to-image providers
├── TTS/               # Text-to-speech providers
├── STT/               # Speech-to-text providers
├── search/            # Search engines and result models
├── AISEARCH/          # AI-powered search backends
├── browser_requests/  # Browser automation + the built-in HTTP client (_http)
├── server/            # FastAPI OpenAI/Anthropic-compatible server
├── Extra/             # GitAPI, temp-mail, YouTube toolkit, utilities
├── scout/             # HTML parser and crawler
└── litagent/          # User-agent rotation
```

## Documentation

| Resource | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation and first chat |
| [Architecture](docs/architecture.md) | System design and data flows |
| [Client](docs/client.md) | Unified client and failover behavior |
| [CLI Reference](docs/cli.md) | Commands and options |
| [API Server](docs/openai-api-server.md) | OpenAI-compatible server |
| [Model Registry](docs/models.md) | Enumerating models and voices |
| [Tool Calling](docs/tool-calling.md) | Function calling across providers |
| [Search](docs/search.md) | Multi-engine search API |
| [HTTP Client](docs/http.md) | Built-in zero-dependency HTTP client and impersonation |
| [Provider Development](docs/provider-development.md) | Writing custom providers |
| [Deployment](docs/deployment.md) | Production deployment |
| [Docker](docs/DOCKER.md) | Images and Compose profiles |
| [Troubleshooting](docs/troubleshooting.md) | Common issues |
| [Docs Hub](docs/README.md) | Full documentation index |

## Contributing

Contributions are welcome: new providers, search engines, bug fixes, tests, and documentation.

1. Fork the repository.
2. Create a feature branch.
3. Make focused changes with descriptive commits.
4. Open a pull request.

See [docs/contributing.md](docs/contributing.md) and [docs/provider-development.md](docs/provider-development.md).

Please verify that any new backend complies with the target service's terms of use before submitting.

## License and legal

Released under **Apache-2.0**. See [LICENSE.md](LICENSE.md).

- [LEGAL_NOTICE.md](LEGAL_NOTICE.md) — affiliation, liability, third-party services, and user responsibilities
- [CHANGELOG.md](CHANGELOG.md) — release history

<hr/>

<div align="center">
  <p>Made with ❤️ by the LLM4Free team · <a href="https://github.com/OEvortex/llm4free">GitHub</a> · <a href="https://pypi.org/project/llm4free">PyPI</a> · <a href="https://t.me/OEvortexAI">Telegram</a></p>
</div>
