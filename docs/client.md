# LLM4Free Python Client (`llm4free/client.py`)

> **Last updated:** 2026-07-16
> **Maintained by:** OEvortex

`llm4free.client.Client` is the unified Python entry point for LLM4Free providers. It exposes an OpenAI-style surface for chat completions, image generation, and audio speech synthesis while handling dynamic provider discovery, intelligent model resolution, automatic failover, and per-process provider instance caching.

> [!TIP]
> **Start here.** The unified `Client` is the recommended way to use LLM4Free. Set `model="auto"` and the client picks any working provider/model and automatically fails over if one is down — no need to import individual provider classes. This is the smartest, lowest-friction path and the main differentiator versus libraries that require you to pick a provider by hand.

## Table of Contents

- [Why the Unified Client?](#why-the-unified-client)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Client Initialization](#client-initialization)
- [Chat Completions](#chat-completions)
- [Image Generation](#image-generation)
- [Audio Speech Synthesis](#audio-speech-synthesis)
- [Provider Resolution Engine](#provider-resolution-engine)
- [Fallback Tiers and Failover](#fallback-tiers-and-failover)
- [Provider Caching](#provider-caching)
- [Provider Helper Methods](#provider-helper-methods)
- [Error Handling](#error-handling)
- [Advanced Usage Patterns](#advanced-usage-patterns)
- [Debug Tips](#debug-tips)
- [Internal Functions](#internal-functions)
- [Related Docs](#related-docs)

---

## Why the Unified Client?

Most libraries that aggregate AI providers make you choose a provider class and a model up front, then handle failures yourself. The LLM4Free `Client` flips that around:

| Capability | Unified `Client` | Raw provider classes |
| ---------- | ---------------- | -------------------- |
| Pick a model | `model="auto"` picks any working provider/model | You pick the provider **and** model |
| Failover | Automatic, tiered (exact → fuzzy → any) | None — you must `try/except` and retry |
| Fuzzy model matching | Built in (`difflib`, 50% cutoff) | Not available |
| One interface for chat/images/audio | Yes (`client.chat`, `client.images`, `client.audio`) | Separate imports per provider type |
| Debugging | `print_provider_info=True` + `last_provider` | Manual |

> [!NOTE]
> You can still use raw provider classes (e.g. `from llm4free.llm.gemini import Gemini`) when you want full control. The `Client` is the recommended default; provider classes remain available for fine-grained use.

---

## Architecture

The client is built as a layered system that mirrors the OpenAI Python client shape while adding automatic provider management:

```
Client
├── chat (ClientChat)
│   └── completions (ClientCompletions)
│       ├── _resolve_provider_and_model()
│       ├── _fuzzy_resolve_provider_and_model()
│       ├── _get_available_providers()
│       └── create()  ← main entry point
├── images (ClientImages)
│   ├── _resolve_provider_and_model()
│   ├── _fuzzy_resolve_provider_and_model()
│   ├── _get_available_providers()
│   ├── generate()
│   └── create()  ← alias for generate()
└── audio (ClientAudio)
    └── speech (ClientAudioSpeech)
        ├── _resolve_provider_and_model()
        ├── _fuzzy_resolve_provider_and_model()
        ├── _get_available_providers()
        └── create()  ← main entry point
```

Each namespace (`chat`, `images`, `audio`) maintains its own provider registry, resolution logic, and fallback queue. The parent `Client` instance coordinates shared configuration (API keys, proxies, exclusions) and caches provider instances across all namespaces.

> [!NOTE]
> Provider discovery scans the `llm4free.llm` package for OpenAI-compatible providers, `llm4free.TTI` for image providers, and `llm4free.TTS` for audio providers. The legacy `llm4free.Provider.Openai_comp` path no longer exists — import providers from `llm4free.llm` (e.g. `from llm4free.llm.Auth.groq import Groq`).

---

## Quick Start

The fastest way to use LLM4Free is the unified `Client` with `model="auto"`. The client selects a working provider, and if it fails, transparently falls back to another.

```python
from llm4free.client import Client

client = Client(print_provider_info=True)

# Chat completion with AUTO provider/model selection (recommended default)
chat = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Summarize LLM4Free in one sentence."}],
)
print(chat.choices[0].message.content)

# Force a SPECIFIC provider/model with the "Provider/Model" syntax
chat = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Explain auto-failover in one sentence."}],
)
print(chat.choices[0].message.content)
```

### Three ways to specify a model

The `model` argument is the same across `chat`, `images`, and `audio`. There are three supported forms:

1. **`"auto"`** — Let the client pick any available provider and model. This is the recommended default and the one-line path to resilience: if the selected provider is down, the client fails over automatically.

   ```python
   client.chat.completions.create(model="auto", messages=[...])
   ```

2. **`"ProviderName/ModelName"`** — Pin an exact provider and model. Case-insensitive on the provider name. If the provider is unavailable, the client still falls back to others.

   ```python
   # Provider name (case-insensitive) + "/" + model name
   client.chat.completions.create(model="Gemini/gemini-3.6-flash", messages=[...])
   client.images.generate(model="PollinationsAI/flux", prompt="...")
   ```

3. **Bare model name** — Pass just a model string and the client resolves it across all providers. It tries an exact match, then a substring match, then fuzzy matching (`difflib`, 50% cutoff), and finally a random provider if nothing matches.

   ```python
   client.chat.completions.create(model="gpt-4o", messages=[...])  # fuzzy-matched provider
   ```

> [!TIP]
> The `Provider/Model` form is the most reproducible: it forces the exact provider and model while still keeping automatic failover as a safety net. Use `auto` for maximum resilience, and a bare name when you care about the model but not who serves it.

```python
# Image generation (auto)
image = client.images.generate(
    prompt="A neon owl in a futuristic city",
    model="auto",
)
print(image.data[0].url)

# Audio speech generation (auto)
audio_path = client.audio.speech.create(
    input_text="Hello from LLM4Free.",
    model="auto",
)
print(audio_path)
```

---

## Client Initialization

```python
Client(
    provider=None,           # Optional[Type[OpenAICompatibleProvider]]
    image_provider=None,     # Optional[Type[TTICompatibleProvider]]
    api_key=None,            # Optional[str]
    proxies=None,            # Optional[dict]
    exclude=None,            # Optional[List[str]]
    exclude_images=None,     # Optional[List[str]]
    exclude_tts=None,        # Optional[List[str]]
    print_provider_info=False,   # bool
    drop_auth_providers=True,    # bool
    **kwargs,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | `Type[OpenAICompatibleProvider]` | `None` | Default provider class for chat completions. When specified, this provider is prioritized during resolution. |
| `image_provider` | `Type[TTICompatibleProvider]` | `None` | Default provider class for image generation. Prioritized during image resolution. |
| `api_key` | `str` | `None` | API key passed to authenticated providers. Auth-required providers are still excluded unless `drop_auth_providers=False`. |
| `proxies` | `dict` | `None` | HTTP proxy configuration dictionary (e.g., `{"http": "http://proxy:8080", "https": "http://proxy:8080"}`). Applied to all provider requests. |
| `exclude` | `List[str]` | `None` | Case-insensitive list of provider names to exclude from chat completions. |
| `exclude_images` | `List[str]` | `None` | Case-insensitive list of provider names to exclude from image generation. |
| `exclude_tts` | `List[str]` | `None` | Case-insensitive list of provider names to exclude from audio/TTS generation. |
| `print_provider_info` | `bool` | `False` | When `True`, prints color-formatted provider name and model to stdout as requests succeed. Useful for debugging resolution and failover. |
| `drop_auth_providers` | `bool` | `True` | When `True`, providers with `required_auth = True` are excluded even if `api_key` is set. Set to `False` to allow them when a key is supplied. |
| `**kwargs` | `Any` | — | Additional keyword arguments stored for future use. |

### Examples

```python
# Minimal setup — uses all free providers
client = Client()

# With authentication and debugging
client = Client(
    api_key="sk-your-api-key",
    proxies={"http": "http://proxy.example.com:8080"},
    exclude=["UnreliableProvider"],
    print_provider_info=True,
)

# With specific default providers
from llm4free.llm.Auth.groq import Groq
from llm4free.TTI.stablehorde import StableHordeAI

client = Client(
    provider=Groq,
    image_provider=StableHordeAI,
)
```

---

## Chat Completions

Access via `client.chat.completions.create(...)`.

### Method Signature

```python
client.chat.completions.create(
    model="auto",              # str — required
    messages,                  # List[Dict[str, Any]] — required
    max_tokens=None,           # Optional[int]
    stream=False,              # bool
    temperature=None,          # Optional[float]
    top_p=None,                # Optional[float]
    tools=None,                # Optional[List[Union[Tool, Dict[str, Any]]]]
    tool_choice=None,          # Optional[Union[str, Dict[str, Any]]]
    timeout=None,              # Optional[int]
    proxies=None,              # Optional[dict]
    provider=None,             # Optional[Type[OpenAICompatibleProvider]]
    **kwargs,
) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | `"auto"` | Model identifier. Supports `"auto"`, `"ProviderName/model-name"`, or plain model name. |
| `messages` | `List[Dict[str, Any]]` | — | List of message dicts with `role` and `content` keys. Required. |
| `max_tokens` | `int` | `None` | Maximum tokens in the response. |
| `stream` | `bool` | `False` | Whether to stream the response as chunks. |
| `temperature` | `float` | `None` | Sampling temperature (0–2). Controls response randomness. |
| `top_p` | `float` | `None` | Nucleus sampling parameter (0–1). |
| `tools` | `List[Tool \| Dict]` | `None` | Tools or tool definitions for function calling. |
| `tool_choice` | `str \| Dict` | `None` | Which tool to use or how to select tools. |
| `timeout` | `int` | `None` | Request timeout in seconds. |
| `proxies` | `dict` | `None` | HTTP proxy configuration for this specific call. |
| `provider` | `Type[OpenAICompatibleProvider]` | `None` | Specific provider class to use, bypassing auto resolution. |

### Return Types

- **Non-streaming**: `ChatCompletion` object with `choices[0].message.content`
- **Streaming**: `Generator[ChatCompletionChunk, None, None]` yielding chunks with `choices[0].delta.content`

### Examples

```python
# Basic chat
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Streaming
for chunk in client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a poem about Python."}],
    stream=True,
):
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)

# With specific provider
from llm4free.llm.Auth.groq import Groq
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Explain recursion."}],
    provider=Groq,
)
```

### Tracking Last Provider

```python
completions = client.chat.completions
response = completions.create(model="auto", messages=[...])
print(f"Used provider: {completions.last_provider}")
```

---

## Image Generation

Access via `client.images.generate(...)` or `client.images.create(...)` (alias).

### Method Signature

```python
client.images.generate(
    prompt,                  # str — required
    model="auto",            # str
    n=1,                     # int
    size="1024x1024",        # str
    response_format="url",   # str — "url" or "b64_json"
    provider=None,           # Optional[Type[TTICompatibleProvider]]
    **kwargs,
) -> ImageResponse
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | — | Text description of the image(s) to generate. Required. |
| `model` | `str` | `"auto"` | Model identifier. Same resolution strategy as chat. |
| `n` | `int` | `1` | Number of images to generate. |
| `size` | `str` | `"1024x1024"` | Image size specification (e.g., `"1024x1024"`, `"512x512"`). |
| `response_format` | `str` | `"url"` | Response format: `"url"` for image URLs or `"b64_json"` for base64 data. |
| `provider` | `Type[TTICompatibleProvider]` | `None` | Specific TTI provider class to use. |

### Return Type

`ImageResponse` object containing generated images with:
- `data[0].url` — URL to the generated image (when `response_format="url"`)
- `data[0].b64_json` — Base64-encoded image data (when `response_format="b64_json"`)

### Examples

```python
# Basic image generation
response = client.images.generate(
    prompt="A beautiful sunset over mountains",
    model="auto",
    n=1,
    size="1024x1024",
)
print(response.data[0].url)

# Using specific provider
from llm4free.TTI.stablehorde import StableHordeAI
response = client.images.generate(
    prompt="A cat wearing sunglasses",
    provider=StableHordeAI,
)

# Using create() alias (OpenAI-style)
response = client.images.create(
    prompt="A robot painting a picture",
    model="auto",
)

# Pin a specific backend with the Provider/Model syntax
response = client.images.generate(
    prompt="A cyberpunk city at night",
    model="PollinationsAI/flux",
)
print(response.data[0].url)
```

### Tracking Last Provider

```python
images = client.images
response = images.generate(prompt="...", model="auto")
print(f"Used provider: {images.last_provider}")
```

---

## Audio Speech Synthesis

Access via `client.audio.speech.create(...)`.

### Method Signature

```python
client.audio.speech.create(
    input_text=None,           # str — required
    model="auto",              # str
    voice=None,                # Optional[str]
    response_format="mp3",     # str
    instructions=None,         # Optional[str]
    stream=False,              # bool
    chunk_size=1024,           # int
    provider=None,             # Optional[Type[BaseTTSProvider]]
    verbose=False,             # bool
    **kwargs,
) -> Union[str, Generator[bytes, None, None]]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_text` | `str` | — | Text to synthesize into speech. Required. Also accepts `input` as kwarg. |
| `model` | `str` | `"auto"` | TTS model identifier. Same resolution strategy as chat/images. |
| `voice` | `str` | `None` | Voice identifier for the TTS provider. |
| `response_format` | `str` | `"mp3"` | Audio format (e.g., `"mp3"`, `"wav"`, `"ogg"`). |
| `instructions` | `str` | `None` | Additional instructions for speech generation (provider-specific). |
| `stream` | `bool` | `False` | When `True`, returns a generator yielding audio bytes from the generated file. |
| `chunk_size` | `int` | `1024` | Size of audio chunks (bytes) when streaming. |
| `provider` | `Type[BaseTTSProvider]` | `None` | Specific TTS provider class to use. |
| `verbose` | `bool` | `False` | Provider-specific verbose output flag. |

### Return Types

- **Non-streaming**: `str` — Path to the generated audio file on disk
- **Streaming**: `Generator[bytes, None, None]` — Iterator yielding audio bytes

### Examples

```python
# Basic speech
audio_path = client.audio.speech.create(
    input_text="Hello from LLM4Free.",
    model="auto",
)
print(f"Audio saved to: {audio_path}")

# Streaming audio
for chunk in client.audio.speech.create(
    input_text="This is a streaming speech example.",
    model="auto",
    stream=True,
):
    # Process audio chunks (e.g., write to file or play)
    pass

# Using specific provider
from llm4free.TTS.elevenlabs import ElevenlabsTTS
audio_path = client.audio.speech.create(
    input_text="Hello world",
    provider=ElevenlabsTTS,
)
```

### Tracking Last Provider

```python
speech = client.audio.speech
audio_path = speech.create(input_text="Hello", model="auto")
print(f"Used provider: {speech.last_provider}")
```

---

## Provider Resolution Engine

The client uses a multi-stage resolution strategy to map model identifiers to concrete provider/model pairs. This engine is implemented independently for chat (`ClientCompletions`), images (`ClientImages`), and audio (`ClientAudioSpeech`).

### Input Formats

The `model` parameter accepts three formats:

1. **`"auto"`** — Randomly selects an available provider and model
2. **`"ProviderName/model-name"`** — Forces exact provider and model
3. **Plain model name** — Searches across all providers for exact or fuzzy match

### Resolution Strategy

The resolution follows this priority order:

1. **Provider/model format**: If the model string contains `/`, it is parsed as `provider/model`. The provider is looked up by name (case-insensitive) in the appropriate registry. If found, the exact provider and model are returned.

2. **Explicit provider**: If a `provider` class is passed directly, it is used. If `model="auto"`, a random model is selected from that provider's available models.

3. **Auto selection**: If `model="auto"` with no explicit provider, the client:
   - Filters available providers based on exclusions and API key availability
   - Collects all providers that have at least one model
   - Randomly selects one provider and one model from its available models

4. **Exact match**: For a plain model name, the client searches across all available providers for an exact case-insensitive match.

5. **Substring match**: If no exact match is found, the client looks for substring containment (either the query is contained in a model name or vice versa).

6. **Fuzzy match**: Uses `difflib.get_close_matches()` with a 50% cutoff to find the closest model name.

7. **Random fallback**: If all matching fails, a random available provider is selected with the original model string.

### Fuzzy Matching Details

```python
# Three levels of matching are attempted:
# 1. Exact case-insensitive match
for m_name in model_to_provider:
    if m_name.lower() == model.lower():
        return model_to_provider[m_name], m_name

# 2. Substring match
for m_name in model_to_provider:
    if model.lower() in m_name.lower() or m_name.lower() in model.lower():
        return model_to_provider[m_name], m_name

# 3. Fuzzy match with difflib (50% cutoff)
matches = difflib.get_close_matches(model, model_to_provider.keys(), n=1, cutoff=0.5)
if matches:
    return model_to_provider[matches[0]], matches[0]
```

When `print_provider_info=True`, substring and fuzzy matches are printed in yellow:

```
Substring match: 'gpt-4' -> 'gpt-4o-mini'
Fuzzy match: 'claude-3' -> 'claude-3-sonnet'
```

---

## Fallback Tiers and Failover

If the initially resolved provider fails, the client automatically falls back to other providers using a tiered priority queue:

### Tier Classification

Providers are classified into three tiers based on model compatibility:

- **Tier 1**: Providers with an **exact model match** for the requested model
- **Tier 2**: Providers with a **fuzzy model match** (via `difflib.get_close_matches()`)
- **Tier 3**: Providers with **any available model** (random model assigned)

### Failover Process

1. The initially resolved provider is attempted first
2. If it fails, the client builds a fallback queue:
   - All Tier 1 providers (shuffled randomly within the tier)
   - All Tier 2 providers (shuffled randomly within the tier)
   - All Tier 3 providers (shuffled randomly within the tier)
3. Providers are tried in order: Tier 1 → Tier 2 → Tier 3
4. The first provider to return a valid response with non-empty content succeeds
5. If all providers fail, a `RuntimeError` is raised with error summaries

### Streaming Failover

For streaming responses, the failover logic attempts to consume the first chunk:
- If the first chunk is received successfully, the provider is marked as successful
- A chained generator yields the first chunk followed by the rest of the stream
- If the first chunk fails, the next provider in the fallback queue is tried

### Error Reporting

When all providers fail, the error message includes up to 3 error summaries:

```python
RuntimeError: All chat providers failed. Errors: ProviderA: Connection timeout; ProviderB: Rate limit exceeded; ProviderC: Invalid response
```

---

## Provider Caching

The client maintains a per-process `_provider_cache` dictionary to avoid redundant provider instantiations:

```python
self._provider_cache = {}  # Dict[str, ProviderInstance]
```

### How Caching Works

1. When a provider is first requested, it is instantiated with the client's configuration (proxies, API key)
2. The instance is stored in `_provider_cache` keyed by provider class name
3. Subsequent requests for the same provider return the cached instance
4. Caching applies across all namespaces (chat, images, audio)

### Cache Initialization

Provider instances are initialized with client-level configuration:

```python
init_kwargs = {}
if self._client.proxies:
    init_kwargs["proxies"] = self._client.proxies
if self._client.api_key:
    init_kwargs["api_key"] = self._client.api_key
instance = provider_class(**init_kwargs)
self._client._provider_cache[p_name] = instance
```

For TTS providers, additional proxy handling attempts multiple proxy parameter names:

```python
# TTS providers may accept "proxies" or "proxy"
proxy_candidates = [
    {**init_kwargs, "proxies": self._client.proxies},
    {**init_kwargs, "proxy": proxy_value},
    init_kwargs,
]
for candidate in proxy_candidates:
    try:
        instance = provider_class(**candidate)
        # Cache and return
    except Exception:
        continue
```

---

## Provider Helper Methods

Static methods on `Client` for discovering available providers:

```python
# Chat providers
Client.get_chat_providers()       # List[str] — all chat providers
Client.get_free_chat_providers()  # List[str] — chat providers without auth

# Image providers
Client.get_image_providers()       # List[str] — all image providers
Client.get_free_image_providers()  # List[str] — image providers without auth

# TTS/Audio providers
Client.get_tts_providers()         # List[str] — all TTS providers
Client.get_free_tts_providers()    # List[str] — TTS providers without auth
Client.get_audio_providers()       # Alias for get_tts_providers()
Client.get_free_audio_providers()  # Alias for get_free_tts_providers()
```

### Examples

```python
# List all available chat providers
providers = Client.get_chat_providers()
print(f"Total chat providers: {len(providers)}")
print(providers)

# List free providers only
free = Client.get_free_chat_providers()
print(f"Free chat providers: {len(free)}")

# With an API key, authenticated providers can be included
client = Client(api_key="sk-your-key", drop_auth_providers=False)
# Now authenticated providers are included in resolution
```

---

## Error Handling

### Common Exceptions

| Exception | When Raised |
|-----------|-------------|
| `RuntimeError` | No providers available or all providers fail (chat/images/audio) |
| `ValueError` | `input_text` for speech is missing or not a string |
| `ImportError` | Server module not available (for `run_api`/`start_server`) |

### Validation

- `input_text` for speech must be a non-empty string; otherwise `ValueError` is raised
- Chat responses with empty content are treated as failures and trigger fallback
- TTS responses that don't produce a file are treated as failures and trigger fallback

### Graceful Degradation

The client is designed to be resilient:
- Provider loading failures are silently handled during module initialization
- Individual provider failures trigger automatic fallback to the next provider
- Only when all providers fail is an exception raised

---

## Advanced Usage Patterns

### Excluding Unstable Providers

```python
client = Client(
    exclude=["FlakyProvider", "SlowProvider"],
    exclude_images=["UnreliableImageProvider"],
    exclude_tts=["BadTTSProvider"],
)
```

### Using Proxies

```python
client = Client(
    proxies={
        "http": "http://proxy.example.com:8080",
        "https": "http://proxy.example.com:8080",
    }
)
```

### Per-Call Provider Override

```python
from llm4free.llm.Auth.groq import Groq

# Use Groq for this specific call regardless of auto resolution
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello"}],
    provider=Groq,
)
```

### Mixed Auth and Free Providers

```python
# Without API key — only free providers are used
client = Client()

# With API key and drop_auth_providers=False — both free and authenticated providers
client = Client(api_key="sk-your-key", drop_auth_providers=False)
```

### Server Functions

The client also exposes server startup functions (requires `llm4free[api]`):

```python
from llm4free.client import run_api, start_server

# Start the OpenAI-compatible API server
run_api(host="0.0.0.0", port=8000)

# Or use start_server for production deployment
start_server()
```

If the API dependencies are not installed, these functions raise `ImportError`.

---

## Debug Tips

1. **Enable provider info printing**:
   ```python
   client = Client(print_provider_info=True)
   ```
   This prints color-formatted provider:model pairs as requests succeed:
   ```
   Gemini:gemini-3.6-flash
   PollinationsAI:flux (Fallback)
   ```

2. **Check which provider was used**:
   ```python
   client.chat.completions.last_provider
   client.images.last_provider
   client.audio.speech.last_provider
   ```

3. **Exclude problematic providers**:
   ```python
   client = Client(exclude=["ProblematicProvider"])
   ```

4. **Test with specific provider first**:
   ```python
   from llm4free.llm.chatgpt import ChatGPT
   response = client.chat.completions.create(
       model="GPT-6-free",
       messages=[...],
       provider=ChatGPT,
   )
   ```

5. **List available providers**:
   ```python
   print(Client.get_chat_providers())
   print(Client.get_free_chat_providers())
   ```

---

## Internal Functions

These module-level functions support the client's provider discovery:

| Function | Description |
|----------|-------------|
| `load_openai_providers()` | Dynamically loads all OpenAI-compatible provider classes from `llm4free.llm`. Returns `(provider_map, auth_required_set)`. |
| `load_tti_providers()` | Dynamically loads all TTI provider classes from `llm4free.TTI`. Returns `(provider_map, auth_required_set)`. |
| `load_tts_providers()` | Dynamically loads all TTS provider classes from `llm4free.TTS`. Returns `(provider_map, auth_required_set)`. |
| `_get_models_safely(provider_cls, client)` | Safely retrieves models from a provider class, handling all exceptions. Uses client cache if available. |
| `_get_tts_models_safely(provider_cls)` | Retrieves TTS models from `SUPPORTED_MODELS` or `AVAILABLE_MODELS` class attributes. Defaults to `["gpt-4o-mini-tts"]`. |
| `_normalized_name_set(values)` | Converts a list of provider names to a case-normalized set for exclusion matching. |

### Global Registries

After module load, these global variables are populated:

```python
OPENAI_PROVIDERS, OPENAI_AUTH_REQUIRED = load_openai_providers()
TTI_PROVIDERS, TTI_AUTH_REQUIRED = load_tti_providers()
TTS_PROVIDERS, TTS_AUTH_REQUIRED = load_tts_providers()
```

These registries are used by the client's resolution and filtering logic.

---

## Related Docs

- [docs/models.md](models.md) — Model registry for LLM, TTS, and TTI discovery
- [docs/openai-api-server.md](openai-api-server.md) — OpenAI-compatible API server
- [docs/architecture.md](architecture.md) — System design and layer interactions
- [Provider.md](../Provider.md) — Complete provider matrix with file locations
- [docs/getting-started.md](getting-started.md) — Quick start guide
- [docs/tool-calling.md](tool-calling.md) — Function calling with tools
