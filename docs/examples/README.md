# Examples Hub

> Last updated: 2026-07-16
> Type: Code Examples
> Audience: Developers

This page is an index of the runnable examples shipped in this `docs/examples/` folder. Each example uses **verified** import paths (every provider is imported from `llm4free.llm.*` or `llm4free.client`).

> [!TIP]
> **Recommended entry point: the unified `Client`.** For most use cases, start with `from llm4free.client import Client` and `client.chat.completions.create(model="auto", messages=[...])`. The `Client` picks a working provider/model automatically and fails over if one is down — no need to import individual provider classes. The examples below show both the unified `Client` and raw provider classes so you can choose the level of control you need. See [docs/client.md](../client.md) for the full reference.

> [!NOTE]
> All chat providers implement the OpenAI-compatible `chat.completions.create(...)` interface, so the code shape is identical across vendors. Free providers (`Gemini`, `Toolbaz`, `ChatJimmy`, `GptFree`) need no API key; auth-required providers (e.g. `Groq`, `DeepInfra`) take an `api_key`.

## Table of Contents

- [Available Examples](#available-examples)
- [Quick Start](#quick-start)
- [Provider Import Paths](#provider-import-paths)
- [Related Resources](#related-resources)

---

## Available Examples

This folder currently contains two example guides:

| Example | File | Description |
| ------- | ---- | ----------- |
| Basic Chat | [basic-chat.md](basic-chat.md) | Simplest ways to chat: free and keyed providers, customizing responses, conversation reuse, and the unified `Client`. |
| Streaming Responses | [streaming-responses.md](streaming-responses.md) | Token-by-token streaming, processing and saving streamed output, and error handling. |

> [!TIP]
> For web search examples, see the standalone [Search guide](../search.md), which covers `DuckDuckGoSearch`, `BingSearch`, `BraveSearch`, `YahooSearch`, `Mojeek`, `Wikipedia`, and `SerpBase`.

---

## Quick Start

### Simplest chat example (no API key)

```python
from llm4free.llm.gemini import Gemini

# Initialize (no API key needed)
client = Gemini()

# Ask a question
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "What is Python?"}],
)
print(response.choices[0].message.content)
```

### With API key

```python
from llm4free.llm.Auth.groq import Groq

# Initialize with your API key
client = Groq(api_key="your-groq-api-key")

# Get a response
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
)
print(response.choices[0].message.content)
```

### With streaming

```python
from llm4free.llm.Auth.groq import Groq

client = Groq(api_key="your-groq-api-key")

# Stream response in chunks
stream = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Write a haiku"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
```

### With the unified Client

```python
from llm4free.client import Client

client = Client()

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

---

## Provider Import Paths

Use these verified paths (the legacy `llm4free.Provider.Openai_comp.*` and top-level names like `Meta`/`GROQ`/`OpenAI` do **not** exist in this version):

| Provider | Import |
| -------- | ------ |
| `Gemini` (free) | `from llm4free.llm.gemini import Gemini` |
| `Toolbaz` (free) | `from llm4free.llm.toolbaz import Toolbaz` |
| `ChatJimmy` (free) | `from llm4free.llm.chatjimmy import ChatJimmy` |
| `Groq` (key) | `from llm4free.llm.Auth.groq import Groq` |
| `DeepInfra` (key) | `from llm4free.llm.Auth.deepinfra import DeepInfra` |
| Unified client | `from llm4free.client import Client` |

---

## Related Resources

- [API Reference](../api-reference.md) — Complete API documentation
- [Getting Started](../getting-started.md) — Quick start guide
- [Troubleshooting](../troubleshooting.md) — Solutions to problems
- [Search Guide](../search.md) — Web search engines and usage
