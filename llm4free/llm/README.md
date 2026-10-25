<div align="center">
  <a href="https://github.com/OEvortex/llm4free">
    <img src="https://img.shields.io/badge/LLM4Free-OpenAI%20Compatible%20Providers-4285F4?style=for-the-badge&logo=openai&logoColor=white" alt="LLM4Free OpenAI Compatible Providers">
  </a>
  <br/>
  <h1>LLM4Free OpenAI-Compatible Providers</h1>
  <p><strong>Seamlessly integrate with various AI providers using OpenAI-compatible interfaces</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/License-Apache--2.0-blue?style=flat-square" alt="License: Apache-2.0">
    <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome">
  </p>

  <p>
    Access multiple AI providers through a standardized OpenAI-compatible interface, making it easy to switch between providers without changing your code.
  </p>
</div>

## 🚀 Overview

The LLM4Free OpenAI-Compatible Providers module offers a standardized way to interact with various AI providers using the familiar OpenAI API structure. This makes it easy to:

- Use the same code structure across different AI providers
- Switch between providers without major code changes
- Leverage the OpenAI ecosystem of tools and libraries with alternative AI providers

All providers live in `llm4free.llm` and implement the same
`client.chat.completions.create(...)` interface. Providers that need an API key
live in `llm4free.llm.Auth` and are also re-exported from `llm4free.llm`.

## ⚙️ Available Providers

### No API key required

| Provider | Class | Example models |
|----------|-------|----------------|
| AkashGPT | `AkashGPT` | `openai-gpt-oss-120b`, `Meta-Llama-3-3-70B-Instruct` |
| ChatGPT | `ChatGPT`, `ChatGPTReversed` | `GPT-6-free` |
| ChatJimmy | `ChatJimmy` | `llama3.1-8B` |
| Gemini | `Gemini` | `gemini-3.6-flash`, `gemini-3.1-pro`, `gemini-3.5-flash-lite` |
| GptFree | `GptFree` | `gpt-4o` |
| IBM | `IBM` | `granite-reasoning-deep`, `granite-reasoning-light` |
| K2Think | `K2Think` | `IFM/K2-Horizon-375B-A23B` |
| Miklium | `Miklium` | `miklium`, `personalityless`, `male`, `female`, `all` |
| Netwrck | `Netwrck` | `thedrummer/skyfall-36b-v2`, `inclusionai/ling-3.0-flash` |
| OllamaSwarm | `OllamaSwarm` | models discovered from public Ollama endpoints |
| PiAI | `PiAI` | `inflection_3_pi` |
| RewindAI | `RewindAI` | `qwen/qwen-2.5-7b-instruct`, `qwen/qwen3-coder`, ... |
| Toolbaz | `Toolbaz` | `toolbaz-v5`, `gpt-5`, `gemini-3.6-flash`, `deepseek-v3` |
| TypliAI | `TypliAI` | `openai/gpt-4o-mini`, `anthropic/claude-sonnet-5-pro` |
| WiseCat | `WiseCat` | `chat-model-small` (also accepted as `WiseCat/chat-model-small`) |

### API key required (`llm4free.llm.Auth`)

| Provider | Class | Constructor |
|----------|-------|-------------|
| AI4Chat | `AI4Chat` | `AI4Chat(api_key=..., model="gpt-5.2")` |
| Cerebras | `Cerebras` | `Cerebras(api_key=...)` |
| DeepAI | `DeepAI` | `DeepAI(api_key=...)` |
| DeepInfra | `DeepInfra` | `DeepInfra(api_key=...)` |
| Groq | `Groq` | `Groq(api_key=...)` |
| HuggingFace | `HuggingFace` | `HuggingFace(api_key=...)` |
| NVIDIA | `Nvidia` | `Nvidia(api_key=...)` |
| OpenRouter | `OpenRouter` | `OpenRouter(api_key=...)` |
| Sambanova | `Sambanova` | `Sambanova(api_key=...)` |
| TextPollinations | `TextPollinations` | `TextPollinations(api_key=...)` |
| TogetherAI | `TogetherAI` | `TogetherAI(api_key=...)` |
| TwoAI | `TwoAI` | `TwoAI(api_key=...)` |
| UncensoredChat | `UncensoredChat` | `UncensoredChat(api_key=...)` |
| Upstage | `Upstage` | `Upstage(api_key=...)` |
| Zenmux | `Zenmux` | `Zenmux(api_key=...)` |

Keyed providers accept common options such as `timeout`, `browser`, and
`proxies`; check each class signature for the exact set. Some providers
(`Cerebras`, `HuggingFace`, `Nvidia`, `OpenRouter`, `TogetherAI`) fetch their
model list from the upstream API when an `api_key` is supplied.

## 💻 Usage Examples

Import provider classes from `llm4free.llm` (or `llm4free.llm.Auth` for keyed
providers). Provider classes are **not** exported from `llm4free.client`; that
module exports the unified `Client`.

### Basic usage (Gemini, no key)

```python
from llm4free.llm import Gemini

client = Gemini(timeout=60)

response = client.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."},
    ],
)

print(response.choices[0].message.content)
```

### Streaming (Toolbaz, no key)

```python
from llm4free.llm import Toolbaz

client = Toolbaz(timeout=30)

stream = client.chat.completions.create(
    model="toolbaz-v5",
    messages=[{"role": "user", "content": "Write a short poem about programming."}],
    stream=True,
)

for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

### Keyed provider (Groq)

```python
from llm4free.llm.Auth import Groq

client = Groq(api_key="gsk_...")

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### Keyed provider (DeepInfra)

```python
from llm4free.llm.Auth import DeepInfra

client = DeepInfra(api_key="...")

response = client.chat.completions.create(
    model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me about Python programming."},
    ],
    temperature=0.7,
    max_tokens=500,
)

print(response.choices[0].message.content)
```

### Listing models

Every provider exposes `models.list()`:

```python
from llm4free.llm import Gemini

client = Gemini()
for model in client.models.list():
    print(model.id)
```

Static model lists are available at `Provider.AVAILABLE_MODELS`:

```python
from llm4free.llm import Toolbaz

print(Toolbaz.AVAILABLE_MODELS)
```

### Unified client with failover

For automatic failover across providers, use the unified `Client` instead of a
single provider class:

```python
from llm4free import Client

client = Client()
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
print("Served by:", client.last_provider)
```

You can also pin a provider with the `"Provider/Model"` form:

```python
response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello"}],
)
```

## 🔄 Response Format

All providers return responses that mimic the OpenAI API structure, ensuring compatibility with tools built for OpenAI. The data classes live in `llm4free.llm.utils`.

### 📝 Non-streaming Response

```json
{
  "id": "chatcmpl-123abc",
  "object": "chat.completion",
  "created": 1677858242,
  "model": "gemini-3.6-flash",
  "usage": {
    "prompt_tokens": 13,
    "completion_tokens": 7,
    "total_tokens": 20
  },
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "This is a response from the model."
      },
      "finish_reason": "stop",
      "index": 0
    }
  ]
}
```

### 📱 Streaming Response Chunks

```json
{
  "id": "chatcmpl-123abc",
  "object": "chat.completion.chunk",
  "created": 1677858242,
  "model": "gemini-3.6-flash",
  "choices": [
    {
      "delta": {
        "content": "This "
      },
      "finish_reason": null,
      "index": 0
    }
  ]
}
```

## 🧩 Architecture

The OpenAI-compatible providers are built on a modular architecture:

- `base.py` — `OpenAICompatibleProvider`, `BaseChat`, `BaseCompletions`, `SimpleModelList`
- `utils.py` — response data classes (`ChatCompletion`, `ChatCompletionChunk`, `Choice`, `ChoiceDelta`, `CompletionUsage`, ...)
- `Auth/` — providers that require an API key
- One module per provider (e.g. `gemini.py`, `toolbaz.py`) implementing the shared interface

This architecture makes it easy to add new providers while maintaining a consistent interface.

## 📝 Notes

- Providers that need credentials set `required_auth = True`; check the class attribute before use.
- Not all OpenAI features (e.g. tools, JSON mode) are supported by every provider.
- Response formats are standardized, but the underlying content and reliability depend on the specific provider and model.
- Upstream free endpoints change frequently; a provider may be temporarily unavailable.

## 🤝 Contributing

Want to add a new OpenAI-compatible provider? Follow these steps:

1. Create a new module in `llm4free/llm/` (or `llm4free/llm/Auth/` if it needs a key)
2. Subclass `OpenAICompatibleProvider` and implement `chat.completions.create(...)`
3. Add the class to `llm4free/llm/__init__.py` (and `Auth/__init__.py` when applicable)
4. Add tests and update this README

## 📚 Related Documentation

- [Providers reference](../../docs/api/providers.md)
- [Client documentation](../../docs/client.md)
- [Tool calling](../../docs/tool-calling.md)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)

<div align="center">
  <a href="https://t.me/OEvortexAI"><img alt="Telegram Group" src="https://img.shields.io/badge/Telegram%20Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white"></a>
  <a href="https://buymeacoffee.com/oevortex"><img alt="Buy Me A Coffee" src="https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black"></a>
</div>
