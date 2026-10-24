# LLM4Free — Documentation Hub

> A unified Python toolkit for 40+ AI providers, web search, image & voice generation, and an OpenAI-compatible server — all behind a single, consistent interface.

Welcome to the LLM4Free documentation hub. Whether you want to chat with a free model in 30 seconds, build a search-powered app, deploy a local OpenAI-compatible API, or write your own provider, you are in the right place.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Documentation Index](#documentation-index)
- [Supported Providers](#supported-providers)
- [Key Features](#key-features)
- [Quick Links](#quick-links)
- [License](#license)

---

## Quick Start

### Installation

```bash
# pip (recommended for beginners)
pip install -U llm4free

# uv (recommended for developers)
uv add llm4free

# Docker
docker pull OEvortex/llm4free:latest
```

### The unified Client — one client for everything

The fastest way into LLM4Free is the unified `Client`. It mirrors the OpenAI SDK you already know, but picks a working provider for you and auto-fails over when one is down. Use `model="auto"` to let it choose, or `model="ProviderName/ModelName"` to force a specific one.

```python
from llm4free.client import Client

# Let the client pick any working provider/model
client = Client(print_provider_info=True)
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is Python?"}],
)
print(response.choices[0].message.content)

# Or force a specific provider/model
client.chat.completions.create(
    model="HeckAI/google/gemini-3-flash-preview",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

> [!NOTE]
> `model="auto"` resolves a working provider and model for you — no need to memorize provider names. Use `model="HeckAI/google/gemini-3-flash-preview"` to force a specific backend. `client.chat.completions.last_provider` tells you which provider was used, and `print_provider_info=True` prints it live.

> [!TIP]
> **Why the unified Client?** Because it gives you three things for free that raw provider imports do not: (1) **auto-failover** — if one provider is down or rate-limited, the client retries across others; (2) **`model="auto"`** — you never have to hard-code a working provider/model; and (3) **`model="ProviderName/ModelName"`** — one consistent syntax to force any backend. It also unifies chat, image, and audio behind a single object. The raw provider examples below are still valid, but the `Client` is the recommended path for most apps.

### Chat with a free provider (no API key, raw provider)

Prefer a direct provider import? Every provider implements the OpenAI-compatible interface. The `Client` above is recommended because it adds auto-failover and model resolution automatically.

```python
from llm4free.llm.heckai import HeckAI

client = HeckAI()
response = client.chat.completions.create(
    model="google/gemini-3-flash-preview",
    messages=[{"role": "user", "content": "What is Python?"}],
)
print(response.choices[0].message.content)
```

> [!NOTE]
> `HeckAI` is a no-auth provider. Import it from `llm4free.llm.heckai` — the older `llm4free.Provider.Openai_comp.heckai` path no longer exists.

### Web search

```python
from llm4free import DuckDuckGoSearch

engine = DuckDuckGoSearch()
results = engine.text("AI trends 2025", max_results=5)
for r in results:
    print(r.title, r.url)
```

### Image generation

```python
from llm4free.TTI import PollinationsAI

generator = PollinationsAI()
image = generator.generate_image("Beautiful sunset over mountains")
```

**[→ Full Getting Started Guide](getting-started.md)**

---

## Documentation Index

### Start Here

- **[Getting Started](getting-started.md)** — Installation, first examples, IDE setup
- **[Examples](examples/README.md)** — Copy-paste code examples
- **[API Reference](api-reference.md)** — Entry point to the API docs
  - [Client API](api/client.md)
  - [Providers](api/providers.md)
  - [Search](api/search.md)
  - [Server](api/server.md)

### By Your Goal

| I want to… | Start here |
|---|---|
| **Try it out (5 min)** | [Quick Start](#quick-start) |
| **Build an app (1 hour)** | [Getting Started](getting-started.md) → [API Reference](api-reference.md) → [Examples](examples/README.md) |
| **Understand the design** | [Architecture](architecture.md) |
| **Deploy to production** | [Deployment Guide](deployment.md) |
| **Create a provider** | [Provider Development](provider-development.md) |
| **Contribute code** | [Contributing Guide](contributing.md) |
| **Troubleshoot issues** | [Troubleshooting](troubleshooting.md) |

### Development & Reference

- **[Provider Development](provider-development.md)** — Create custom AI providers
- **[Contributing Guide](contributing.md)** — Contribution process and standards
- **[CLI Reference](cli.md)** — Command-line interface reference
- **[Decorators](decorators.md)** — Utility decorators for error handling and optimization
- **[Client API](client.md)** — Unified client with auto-failover

### Deployment & Operations

- **[Deployment](deployment.md)** — Docker, production setup
- **[OpenAI API Server](openai-api-server.md)** — Deploy an OpenAI-compatible REST API
- **[Docker Guide](DOCKER.md)** — Containerization and Docker Compose
- **[Search Engines](search.md)** — Multi-engine web search
- **[Troubleshooting](troubleshooting.md)** — Common issues and solutions

### Tools & Extensions

- **[LitAgent](litagent.md)** — User-agent & IP rotation
- **[LitPrinter](litprinter.md)** — Advanced debug output
- **[ZeroArt](zeroart.md)** — ASCII art generation
- **[GGUF Converter](gguf.md)** — Model format conversion
- **[Weather Utils](weather.md)** — Weather data retrieval
- **[Git API](gitapi.md)** — GitHub integration helpers
- **[Scout](scout.md)** — HTML parser & web crawler
- **[Awesome Prompts](awesome-prompts.md)** — Curated system prompts
- **[Models](models.md)** — Using the model registry
- **[Tool Calling](tool-calling.md)** — Structured tool/function calling

---

## Supported Providers

LLM4Free supports **40+ AI providers** plus multiple search engines and media models:

| Category | Examples |
|----------|----------|
| **Free (no auth)** | HeckAI, ArtingAI, FreeAI, WiseCat, ExaAI, Netwrck, and 30+ more |
| **Authenticated** | Groq, DeepInfra, IBM, OpenRouter, HuggingFace, Sambanova, TogetherAI, AI4Chat (free key at ai4chat.co/api) |
| **Search** | DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Wikipedia, SerpBase |
| **Images (TTI)** | PollinationsAI, TogetherImage, StableHordeAI, Lexica, MagicStudioAI, PerchanceAI |
| **Voice (TTS)** | ElevenLabs, OpenAI FM, Qwen, Murf, Parler, Kitten, Lux, Sherpa |

> [!TIP]
> The full, current provider list lives in [`llm4free/llm/`](../llm4free/llm/) and the authenticated providers in [`llm4free/llm/Auth/`](../llm4free/llm/Auth/).

---

## Key Features

- Multi-provider AI chat — OpenAI-compatible, no key required for free providers
- Unified `Client` with automatic failover across providers
- Multi-engine web search (DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Wikipedia, SerpBase)
- Text-to-image and text-to-speech generation
- OpenAI-compatible API server (FastAPI)
- `Scout` HTML parser & web crawler with a BeautifulSoup-compatible API
- 100% type-annotated public API

---

## Quick Links

| Resource | Link |
|----------|------|
| PyPI Package | https://pypi.org/project/llm4free |
| GitHub Repository | https://github.com/OEvortex/LLM4Free |
| Issue Tracker | https://github.com/OEvortex/LLM4Free/issues |
| Telegram Community | https://t.me/OEvortexAI |
| YouTube Channel | https://youtube.com/@OEvortex |

---

## License

LLM4Free is released under the **Apache-2.0 License**.

*GitHub · PyPI · Telegram*
