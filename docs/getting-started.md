# Getting Started with LLM4Free

> **Last updated:** 2026-07-16
> **Audience:** New users and developers who want to install `llm4free` and run their first chat, search, and image generation in minutes.

LLM4Free is a single Python toolkit that gives you 40+ AI providers, multi-engine web search, image & voice generation, and an OpenAI-compatible API server — all behind one consistent, OpenAI-style interface. This guide takes you from install to your first chat, search, and image in a few minutes.

## Table of Contents

- [Installation](#installation)
- [The unified Client](#the-unified-client)
- [Your first chat (raw provider, no API key)](#your-first-chat-raw-provider-no-api-key)
- [Streaming responses](#streaming-responses)
- [Web search](#web-search)
- [Image generation](#image-generation)
- [Using an authenticated provider](#using-an-authenticated-provider)
- [Common issues](#common-issues)
- [Next steps](#next-steps)

---

## Installation

### pip

```bash
# Basic install
pip install -U llm4free

# With the OpenAI-compatible API server
pip install -U "llm4free[api]"

# With development tooling
pip install -U "llm4free[dev]"
```

### uv (recommended)

```bash
uv add llm4free                 # add to a project
uv tool install llm4free        # or install as a global CLI tool
uv run llm4free --help          # run without installing
```

### Docker (build from source)

```bash
docker build -t llm4free-api .
docker run -p 8000:8000 llm4free-api
```

> [!NOTE]
> LLM4Free does **not** publish a pre-built Docker image. Build it yourself with the
> `Dockerfile` in this repo, or serve the server without Docker:
> `pip install "llm4free[api]"` then `llm4free-server`. See [docs/DOCKER.md](DOCKER.md).

### Verify

```bash
llm4free version      # prints the installed version
llm4free --help       # lists all CLI commands
```

> [!NOTE]
> Many providers work with **no API key**. Authenticated providers (Groq, DeepInfra, etc.) unlock when you pass a key.

---

## The unified Client

Start here. The unified `Client` is the recommended entry point: it mirrors the OpenAI SDK you already know, resolves the best provider for a model, auto-fails over when one is down, and unifies chat, image, and audio behind one object. Use `model="auto"` to let it choose, or `model="Provider/Model"` to force a specific backend.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)

# Auto provider + model selection
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarize LLM4Free in one sentence."}],
)
print(resp.choices[0].message.content)

# Force a specific provider/model
resp = client.chat.completions.create(
    model="HeckAI/google/gemini-2.5-flash-preview",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(client.chat.completions.last_provider)  # which provider was used

# Image generation
img = client.images.generate(prompt="A neon owl", model="auto", size="1024x1024")
print(img.data[0].url)

# Audio (text-to-speech)
audio_path = client.audio.speech.create(input_text="Hello from LLM4Free", model="auto")
print(audio_path)
```

> [!TIP]
> `model="auto"` picks a working provider/model for you; `model="HeckAI/google/gemini-2.5-flash-preview"` forces a specific one. `print_provider_info=True` prints the chosen provider/model live, and `client.chat.completions.last_provider` exposes it after the call. The raw-provider examples below are still valid, but the `Client` gives you auto-failover and model resolution for free.

See [client.md](client.md) for the full client reference.

---

## Your first chat (raw provider, no API key)

Prefer to use a provider directly? `HeckAI` is a free provider that needs no authentication. Every provider uses the OpenAI-compatible `chat.completions.create(...)` interface. The unified `Client` [above](#the-unified-client) is the recommended path because it adds auto-failover and model resolution automatically.

```python
from llm4free.llm.heckai import HeckAI

client = HeckAI()
response = client.chat.completions.create(
    model="google/gemini-2.5-flash-preview",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms"}],
)
print(response.choices[0].message.content)
```

**Output:**

```
Quantum computing uses qubits, which can be 0, 1, or both at once (superposition)...
```

---

## Streaming responses

Pass `stream=True` to receive tokens as they are generated. The call returns a generator of `ChatCompletionChunk` objects.

```python
from llm4free.llm.heckai import HeckAI

client = HeckAI()
stream = client.chat.completions.create(
    model="google/gemini-2.5-flash-preview",
    messages=[{"role": "user", "content": "Write a short poem about Python"}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

See [Streaming Responses](examples/streaming-responses.md) for a dedicated guide.

---

## Web search

LLM4Free ships multi-engine search (DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Wikipedia). Results are mapping-like objects you can read by `title`, `href`, and `body` keys.

```python
from llm4free import DuckDuckGoSearch

search = DuckDuckGoSearch()
results = search.text("best practices for API design", max_results=5)

for r in results:
    print(f"Title:  {r['title']}")
    print(f"URL:    {r['href']}")
    print(f"Snippet:{r['body']}\n")
```

Use a different engine:

```python
from llm4free import BingSearch, YahooSearch

bing = BingSearch()
print(bing.text("climate change solutions", max_results=5))

yahoo = YahooSearch()
print(yahoo.text("python frameworks", max_results=5))
```

Search from the CLI:

```bash
llm4free text -k "python programming"
llm4free text -k "quantum physics" -e wikipedia
llm4free news -k "AI breakthrough" -e yahoo
```

---

## Image generation

Text-to-image providers include `PollinationsAI`, `TogetherImage`, `StableHordeAI`, `Lexica`, `MiragicAI`, and more. Each exposes an OpenAI-style `images.create(prompt=...)` method that returns an `ImageResponse`.

```python
from llm4free.Provider.TTI import PollinationsAI

gen = PollinationsAI()
response = gen.images.create(prompt="A serene mountain landscape at sunset", response_format="url")
print(response.data[0].url)
```

> [!NOTE]
> `response_format="url"` returns hosted image URLs in `response.data[i].url`. Omit it (or use `b64_json`) to get local file paths via `response.data[i].image_path` instead.

```python
from llm4free.Provider.TTI import TogetherImage

together = TogetherImage()
response = together.images.create(prompt="A robot playing chess")
print(response.data[0].image_path)
```

---

## Using an authenticated provider

Authenticate by passing `api_key`. Authenticated providers become available to the unified `Client` automatically.

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-groq-key")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a Python function to sort a list"}],
)
print(response.choices[0].message.content)
```

DeepInfra works the same way:

```python
from llm4free.llm.Auth.deepinfra import DeepInfra

client = DeepInfra(api_key="your-deepinfra-key")
response = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "What is Python?"}],
)
print(response.choices[0].message.content)
```

> [!TIP]
> Keep keys out of source control. Set them via environment variables or a secrets file and read them at runtime.

---

## Common issues

### `ModuleNotFoundError: No module named 'llm4free'`

```bash
pip install -U llm4free
# or
uv add llm4free
```

### `curl_cffi` or other optional dependency missing

Install the relevant extra or the full set:

```bash
pip install -U "llm4free[all]"
```

### A provider returns an error or empty response

Free providers change frequently. Exclude the troublesome one:

```python
from llm4free.client import Client

client = Client(exclude=["FlakyProvider"])
```

Or pick a specific provider directly (see [provider-development.md](provider-development.md) for the full list).

### Rate limited / connection errors

Increase the timeout and add small delays between calls:

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-key", timeout=60)
try:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "Hello"}],
    )
except Exception as e:
    print(f"Error: {e}")
```

---

## Next steps

- **[API Reference](api-reference.md)** — core classes and methods
- **[Python Client](client.md)** — unified client with auto-failover
- **[Search](search.md)** — multi-engine search API
- **[Tool Calling](tool-calling.md)** — function calling with any provider
- **[OpenAI API Server](openai-api-server.md)** — serve providers via `/v1`
- **[Examples](examples/README.md)** — copy-paste code examples
- **[Troubleshooting](troubleshooting.md)** — deeper fixes

**You're ready to build.** Every provider shares the OpenAI `chat.completions.create(...)` shape, so you can switch models and vendors by changing a single line.
