<div align="center">

<a href="https://github.com/OEvortex/llm4free">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/OEvortex/llm4free/blob/main/logo.svg" style="background-color: #f8f9fa; padding: 12px; border-radius: 6px; display: inline-block;">
    <img src="https://github.com/OEvortex/llm4free/blob/main/logo.svg" alt="LLM4Free Logo" width="320">
  </picture>
</a>

<h1>LLM4Free</h1>

<p><strong>One Python toolkit for 40+ free &amp; paid AI models, web search, image &amp; voice generation, and a drop-in OpenAI-compatible server — all behind a single, consistent interface.</strong></p>

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

## ✨ Why LLM4Free?

Most AI libraries lock you into **one provider** and **one way of doing things**. LLM4Free gives you *everything* behind the interface you already know — the OpenAI SDK:

- 🔌 **One interface, 40+ providers.** Every chat provider implements `client.chat.completions.create(...)` — identical to the OpenAI Python SDK. Switch providers by changing one line.
- 💸 **Free tier built in.** Use Gemini, Toolbaz, ChatGPT, Pollinations, and more with **zero API key** — then graduate to Groq, DeepInfra, or your own key when you need scale.
- 🔄 **Auto-failover client.** The unified `Client` retries across providers and resolves models for you. No more 3am outages from a dead endpoint.
- 🔍 **Multi-engine search.** DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Wikipedia — one API.
- 🖼️🗣️ **Images & voice.** Text-to-image (Pollinations, Together, Stable Horde…) and text-to-speech (ElevenLabs, OpenAI FM, Qwen, Murf…) out of the box.
- 🚀 **OpenAI-compatible server.** Serve any provider through standard `/v1` endpoints — point the official OpenAI SDK at your laptop.
- 🧰 **Developer toolbox.** Web crawler (Scout), GitHub data toolkit, temp-mail, user-agent rotation, and more.
- 📚 **Fully typed & documented.** 100% type-annotated public API with auto-generated MkDocs reference.

> [!NOTE]
> LLM4Free is **Apache-2.0 licensed** — free for personal and commercial use.

<hr/>

## 📦 Installation

```bash
# pip
pip install -U llm4free

# With the OpenAI-compatible API server
pip install -U "llm4free[api]"

# With development tools
pip install -U "llm4free[dev]"
```

```bash
# uv (recommended)
uv add llm4free

# Run without installing
uv run llm4free --help

# Install as a global CLI tool
uv tool install llm4free
```

```bash
# Build and run with Docker (see docs/DOCKER.md)
docker build -t llm4free-api .
docker run -p 8000:8000 llm4free-api
```

> [!NOTE]
> LLM4Free does **not** ship a pre-built Docker image. The `Dockerfile` in this repo
> builds the image from source (it installs `llm4free[api]` from PyPI/git at build time).
> You can also serve LLM4Free without Docker:

```bash
# Install and run the OpenAI-compatible server directly
pip install "llm4free[api]"
llm4free-server --port 8000

# Or with uv (recommended)
uv pip install "llm4free[api]"
uv run llm4free-server
```

See [docs/DOCKER.md](docs/DOCKER.md) for full Docker deployment options including compose profiles.

<hr/>

## 🚀 Quick Start

### Unified Client — one client for everything

The fastest way to use LLM4Free is the unified `Client`. It behaves just like the OpenAI SDK you already know, but it picks a working provider for you and auto-fails over when one is down. Use `model="auto"` to let it choose, or `model="Provider/Model"` to force a specific one.

```python
from llm4free.client import Client

# Let the client pick any working provider/model
client = Client(print_provider_info=True)
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms"}],
)
print(response.choices[0].message.content)

# Or force a specific provider/model explicitly
client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

> [!TIP]
> `model="auto"` resolves a working provider and model for you — no need to memorize provider names. Use `model="Provider/Model"` (for example `"Gemini/gemini-3.6-flash"`) to force a specific backend. `client.chat.completions.last_provider` tells you which provider was used, and `print_provider_info=True` prints it live. This gives you auto-failover and model resolution for free.

### AI Chat — no API key required (raw provider)

Prefer to use a provider directly? Every provider implements the OpenAI-compatible interface. The `Client` above is the recommended path because it adds auto-failover and model resolution automatically.

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms"}],
)
print(response.choices[0].message.content)
```

### Web Search

```python
from llm4free import DuckDuckGoSearch

search = DuckDuckGoSearch()
results = search.text("best practices for API design", max_results=5)
for result in results:
    print(f"{result['title']}: {result['href']}")
```

### Image Generation

The same unified `Client` does images OpenAI-style — `client.images.generate(...)` (alias `client.images.create(...)`). Use `model="auto"` for automatic provider selection and failover, or pin a backend with `model="Provider/Model"`.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)

# Auto-select a working image provider
image = client.images.generate(
    prompt="A serene mountain landscape at sunset",
    model="auto",
    size="1024x1024",
)
print(image.data[0].url)

# Or force a specific backend
image = client.images.generate(
    prompt="A cyberpunk city at night",
    model="PollinationsAI/flux",
)
print(image.data[0].url)
```

Prefer a provider directly? Every TTI provider implements the OpenAI-style `images.create(...)` method too:

```python
from llm4free.TTI import PollinationsAI

gen = PollinationsAI()
image = gen.images.create(model="flux", prompt="A serene mountain landscape at sunset")
print(image.data[0].url)
```

### Unified Client — recall the hero example

The unified `Client` shown at the top of [Quick Start](#unified-client--one-client-for-everything) is the recommended way to use LLM4Free: `model="auto"` picks a working provider, `model="Provider/Model"` forces a specific one, and it auto-fails over between providers.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarize LLM4Free."}],
)
print(resp.choices[0].message.content)
```

See [docs/getting-started.md](docs/getting-started.md) for the full quick-start guide.

<hr/>

## 💻 Command Line Interface

A rich CLI powered by [Rich](https://github.com/Textualize/rich) — search, chat, and generate straight from your terminal.

```bash
llm4free --help                       # List all commands
llm4free version                      # Show version
llm4free text -k "python programming" # DuckDuckGo search (default)
llm4free images -k "mountains"        # Image search
llm4free news -k "AI breakthrough"      # News search
llm4free weather -l "New York"        # Weather info
llm4free translate -k "Hola" --to en  # Translation
```

### Supported Engines

| Category     | Engines                                                        |
| ------------ | -------------------------------------------------------------- |
| `text`       | `ddg`, `bing`, `brave`, `yahoo`, `mojeek`, `parallel`, `wikipedia`, `serpbase` |
| `images`     | `ddg`, `bing`, `brave`, `yahoo`                               |
| `videos`     | `ddg`, `bing`, `brave`, `yahoo`                               |
| `news`       | `ddg`, `bing`, `brave`, `yahoo`                               |
| `suggestions`| `ddg`, `bing`, `brave`, `yahoo`                               |
| `weather`    | `ddg`, `yahoo`                                                |
| `answers`    | `ddg`, `bing`, `brave`, `yahoo`                               |
| `translate`  | `ddg`, `bing`, `brave`, `yahoo`                               |
| `maps`       | `ddg`, `bing`, `brave`, `yahoo`                               |

```bash
# Use a specific engine
llm4free text -k "climate change" -e bing
llm4free text -k "quantum physics" -e wikipedia
```

Full CLI reference: [docs/cli.md](docs/cli.md)

<hr/>

## 🤖 AI Chat Providers

All providers use the **OpenAI-compatible interface** (`client.chat.completions.create(...)`).

### Free Providers (No Auth Required)

```python
from llm4free.llm.gemini import Gemini
from llm4free.llm.gptfree import GptFree

# Gemini - multiple models
client = Gemini()
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)

# GptFree
client = GptFree()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### Authenticated Providers

```python
from llm4free.llm.Auth.groq import Groq
from llm4free.llm.Auth.deepinfra import DeepInfra

groq = Groq(api_key="your-key")
response = groq.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a Python function to sort a list"}],
)
print(response.choices[0].message.content)
```

### Streaming

```python
from llm4free.llm.gemini import Gemini

client = Gemini()
stream = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Tell me a joke"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

See [llm4free/llm/](llm4free/llm/) for all available provider implementations.

<hr/>

## 🔍 Search Engines

```python
from llm4free import DuckDuckGoSearch, BingSearch, YahooSearch, BraveSearch

# DuckDuckGo
ddg = DuckDuckGoSearch()
results = ddg.text("python frameworks", max_results=5)

# Bing
bing = BingSearch()
results = bing.text("climate change solutions")

# Brave
brave = BraveSearch()
results = brave.text("machine learning tutorials")
```

Search docs: [docs/search.md](docs/search.md)

<hr/>

## 🖼️ Text-to-Image

```python
from llm4free.TTI import PollinationsAI, TogetherImage

# PollinationsAI
poll = PollinationsAI()
poll.images.create(model="flux", prompt="A cyberpunk city at night")

# Together AI
together = TogetherImage()
together.images.create(model="auto", prompt="A robot playing chess")
```

TTI docs: [docs/getting-started.md#image-generation](docs/getting-started.md#image-generation)

<hr/>

## 🗣️ Text-to-Speech

```python
from llm4free.TTS import ParlerTTS

tts = ParlerTTS()
audio_path = tts.tts("Hello, world!")
print(audio_path)
```

TTS model registry: [docs/models.md](docs/models.md)

<hr/>

## 🌐 OpenAI-Compatible API Server

Run a local FastAPI server that serves **any** LLM4Free provider through standard OpenAI endpoints.

```bash
# Start the server
llm4free-server

# Custom config
llm4free-server --port 8080 --host 0.0.0.0 --debug
```

### Use with the official OpenAI Python client

```python
from openai import OpenAI

client = OpenAI(api_key="dummy", base_url="http://localhost:8000/v1")

response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

### Docker Deployment

Build and run with Docker Compose:

```bash
docker compose up llm4free-api
docker compose -f docker-compose.yml -f docker-compose.no-auth.yml up llm4free-api
```

> [!NOTE]
> LLM4Free does **not** publish a pre-built Docker image. The `Dockerfile` in this repo
> builds the image from source at `docker build` time. If you don't want to use Docker,
> serve the OpenAI-compatible server directly with `pip install "llm4free[api]"` and
> `llm4free-server`, or via `uv run llm4free-server`.

Full server docs: [docs/openai-api-server.md](docs/openai-api-server.md) | Docker: [docs/DOCKER.md](docs/DOCKER.md)

<hr/>

## 🧩 Tool Calling

Built-in function calling that works with any provider.

```python
from llm4free import Client

client = Client()

weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name."}},
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

Tool calling docs: [docs/tool-calling.md](docs/tool-calling.md)

<hr/>

## 📊 Model Registry

Enumerate available models across all providers.

```python
from llm4free import model

# All LLM models
all_models = model.llm.list()
print(f"Total: {len(all_models)}")

# Models by provider
summary = model.llm.summary()
print(f"Providers: {summary['providers']}, models: {summary['models']}")
for provider, count in summary["provider_model_counts"].items():
    print(f"  {provider}: {count}")

# TTS voices
voices = model.tts.list()
print(f"Total voices: {len(voices)}")
```

Model registry docs: [docs/models.md](docs/models.md)

<hr/>

## 🛠️ Developer Tools

| Tool | Description | Docs |
|------|-------------|------|
| [Scout](docs/scout.md) | HTML parser & web crawler | [docs/scout.md](docs/scout.md) |
| [LitPrinter](docs/litprinter.md) | Styled debug printing | [docs/litprinter.md](docs/litprinter.md) |
| [LitAgent](docs/litagent.md) | User-agent rotation | [docs/litagent.md](docs/litagent.md) |
| [GitAPI](docs/gitapi.md) | GitHub data extraction | [docs/gitapi.md](docs/gitapi.md) |
| [Decorators](docs/decorators.md) | `@timeIt` and `@retry` | [docs/decorators.md](docs/decorators.md) |
| [Sanitize](docs/sanitize.md) | Stream sanitization | [docs/sanitize.md](docs/sanitize.md) |
| [Prompts](docs/awesome-prompts.md) | System prompt manager | [docs/awesome-prompts.md](docs/awesome-prompts.md) |

<hr/>

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, first chat, web search, image generation |
| [Architecture](docs/architecture.md) | System design, layers, and data flows |
| [CLI Reference](docs/cli.md) | All CLI commands and options |
| [Python Client](docs/client.md) | Unified client with auto-failover |
| [API Server](docs/openai-api-server.md) | OpenAI-compatible FastAPI server |
| [Model Registry](docs/models.md) | Enumerate LLM, TTS, TTI models |
| [Tool Calling](docs/tool-calling.md) | Function calling with any provider |
| [Search Docs](docs/search.md) | Multi-engine search API |
| [Scout](docs/scout.md) | HTML parser and crawler |
| [Provider Development](docs/provider-development.md) | Create custom providers |
| [Deployment](docs/deployment.md) | Production deployment guide |
| [Docker](docs/DOCKER.md) | Docker setup and compose profiles |
| [Inferno](docs/inferno.md) | Local LLM server |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [Contributing](docs/contributing.md) | How to contribute |
| [Provider Modules](llm4free/llm/) | All provider implementations |
| [Docs Hub](docs/README.md) | Full documentation index |

<hr/>

## 🤝 Contributing

We welcome contributions — new providers, search engines, bug fixes, and docs. With 40+ providers and counting, there's always room to help.

1. Fork the repository
2. Create a feature branch
3. Make changes with descriptive commits
4. Submit a pull request

See [docs/contributing.md](docs/contributing.md) for full guidelines, and [docs/provider-development.md](docs/provider-development.md) to add a provider.

<hr/>

## 📄 License

Released under **Apache-2.0**. See [LICENSE.md](LICENSE.md). Free for personal and commercial use.

<hr/>

<div align="center">
  <p>Made with ❤️ by the LLM4Free team · <a href="https://github.com/OEvortex/llm4free">GitHub</a> · <a href="https://pypi.org/project/llm4free">PyPI</a> · <a href="https://t.me/OEvortexAI">Telegram</a></p>
</div>
