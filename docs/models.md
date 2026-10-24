# Model Registry (`llm4free/models.py`)

> **Last updated:** 2026-07-16
> **Maintained by:** LLM4Free Core Team

`llm4free/models.py` exposes a lightweight discovery layer so you can inspect the Large Language Model (LLM), Text-to-Speech (TTS), and Text-to-Image (TTI) offerings that ship with LLM4Free. The registry powers documentation examples (README, docs/search.md, etc.) and is useful when building UI selectors or performing health checks across providers.

## Table of Contents

- [Public API](#public-api)
- [How It Works](#how-it-works)
- [Example Usage](#example-usage)
- [Returned Structures](#returned-structures)
- [Extending the Registry](#extending-the-registry)
- [Related Docs](#related-docs)

---

## Public API

```python
from llm4free import model

model.llm.list()       # Dict[str, List[str]] mapping provider -> models
model.llm.get("Groq")  # List[str] of Groq models
model.llm.summary()    # Counts per provider
model.llm.providers()  # Detailed metadata per LLM provider

model.tts.list()       # Dict[str, voices]
model.tts.get("ElevenlabsTTS")
model.tts.summary()

model.tti.list()       # Dict[str, List[str]] for image providers
model.tti.get("PollinationsAI")
model.tti.providers()  # Detailed metadata per TTI provider
model.tti.summary()
```

The object exported from `llm4free/__init__.py` is a singleton (`model`) that contains `llm`, `tts`, and `tti` namespaces.

> [!NOTE]
> The `model` registry is rebuilt on each call by importing provider modules. Some providers implement `get_models()` by calling their API, so results and counts can change between calls. For the **live, runtime-discovered** lists of providers currently importable (and their auth status), use the `Client` helper class methods — see [Live runtime discovery via the Client](#live-runtime-discovery-via-the-client). These two views complement each other: the registry documents the full catalog, while the `Client` helpers reflect what is actually loadable in your environment.
> - `llm` supports `list()`, `get()`, `summary()`, `providers()`, and `provider(name)`.
> - `tti` supports `list()`, `get()`, `summary()`, `providers()`, and `provider(name)`.
> - `tts` supports `list()`, `get()`, and `summary()` only (no `providers()` method).

---

## How It Works

- The LLM registry walks `llm4free.llm`, `llm4free.AISEARCH`, and `llm4free.STT`, collecting any class that exposes `get_models()` or a list-like `AVAILABLE_MODELS`.
- The TTS registry walks `llm4free.TTS`, collecting subclasses of `llm4free.AIbase.TTSProvider` that expose `all_voices` or `SUPPORTED_VOICES`.
- The TTI registry walks `llm4free.TTI`, collecting classes with list-like `AVAILABLE_MODELS` or `get_models()`, excluding `TTICompatibleProvider` and `Base*` classes.
- Sets are converted to lists for JSON friendliness. Docstring first lines become `metadata["description"]` in the detail views.

---

## Example Usage

```python
from llm4free import model
from rich import print

summary = model.llm.summary()
print(f"Providers: {summary['providers']}, models: {summary['models']}")
print("Per-provider counts:")
for provider, count in summary['provider_model_counts'].items():
    print(f"  {provider}: {count}")

# Enumerate voices
voices = model.tts.list()
print(f"TTS providers: {len(voices)}")
print(f"Elevenlabs voices (first 5): {voices.get('ElevenlabsTTS', [])[:5]}")

# Discover TTI metadata
print(f"TTI providers: {list(model.tti.list().keys())}")
```

---

## Returned Structures

### `llm.list()`
```python
{
  "Groq": ["distil-whisper-large-v3-en", "gemma2-9b-it", "llama-3.3-70b-versatile", ...],
  "DeepInfra": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", ...],
  ...
}
```

### `llm.summary()`
```python
{
  "providers": 30,
  "models": 1503,
  "provider_model_counts": {
    "Groq": 25,
    "DeepInfra": 5,
    ...
  }
}
```

Counts depend on the providers installed and on any live `get_models()` calls.

### `tts.list()`
Values are either `list[str]` (voice names) or `dict[str, str]` (voice name -> voice ID), depending on the provider.

### `tti.providers()`
```python
{
  "PollinationsAI": {
      "name": "PollinationsAI",
      "class": "PollinationsAI",
      "module": "pollinations",
      "models": ["any-dark", "flux", "flux-3d", "flux-anime", "flux-pro", ...],
      "parameters": ["prompt", "model", "n", "size", "response_format", ...],
      "model_count": 16,
      "metadata": {"description": "PollinationsAI TTI Provider - ..."}
  },
  ...
}
```

---

## Extending the Registry

1. **New provider class** – inherit from `OpenAICompatibleProvider` (chat), `BaseTTSProvider` (speech), or `TTICompatibleProvider` (images).
2. **Expose models/voices** – implement `get_models()` or set `AVAILABLE_MODELS` / `all_voices` (`SUPPORTED_VOICES` also works for TTS).
3. **Docstrings** – the first line becomes `metadata['description']`, so keep it meaningful.
4. **Verify** – call `model.llm.list()` (or `tts.list()`, `tti.list()`) after adding a provider to confirm it appears.

---

## Live runtime discovery via the Client

The static `model` registry above enumerates every provider LLM4Free *ships with*. The `Client` class exposes complementary **runtime-discovered** lists that reflect exactly what is importable in the current environment at call time (after dynamic loading of `llm4free.llm`, `llm4free.TTI`, and `llm4free.TTS`):

- `Client.get_chat_providers()` – all chat (OpenAI-compatible) provider names.
- `Client.get_free_chat_providers()` – chat providers that need no API key.
- `Client.get_image_providers()` – all text-to-image provider names.
- `Client.get_tts_providers()` – all text-to-speech provider names.

These mirror `model.llm.providers()`, `model.tti.providers()`, and `model.tts.list()` but are subtype-checked and available as plain class methods, so they pair naturally with the unified `Client` entry point.

```python
from llm4free.client import Client

# Live, runtime-discovered provider lists (no instance needed — these are staticmethods)
chat_providers = Client.get_chat_providers()
free_chat = Client.get_free_chat_providers()
image_providers = Client.get_image_providers()
tts_providers = Client.get_tts_providers()

print(f"{len(chat_providers)} chat providers, {len(free_chat)} free")
print(f"Image providers: {image_providers}")
print(f"TTS providers: {tts_providers}")

# Use the discovery to drive the Client itself:
client = Client()
response = client.chat.completions.create(
    model="auto",  # "auto" picks from the same providers listed above
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

> [!TIP]
> The same provider names returned here are what you pass to the `Client` and the server via the `Provider/Model` syntax, e.g. `client.chat.completions.create(model="Gemini/gemini-3.6-flash")`.

---

## Related Docs

- [docs/client.md](client.md) – the unified client uses `_get_models_safely()` to enhance model resolution.
- [Provider.md](../Provider.md) – cross-reference provider locations and normal vs OpenAI-compatible implementations.
- [docs/architecture.md](architecture.md) – where the registry fits within the overall system.
