# Providers API Reference

## Base Class

Every chat provider derives from `OpenAICompatibleProvider` and exposes the
same OpenAI-style surface: `provider.chat.completions.create(...)`.

```python
from llm4free.llm.base import OpenAICompatibleProvider

class MyProvider(OpenAICompatibleProvider):
    AVAILABLE_MODELS = ["my-model"]
    required_auth = False        # True if an API key is mandatory
    supports_tools = False       # True for native tool calling

    def __init__(self, api_key=None, proxies=None):
        super().__init__(proxies=proxies)
        self.chat = MyChat(self)

    @property
    def models(self):
        from llm4free.llm.base import SimpleModelList
        return SimpleModelList(self.AVAILABLE_MODELS)
```

The `models` property must return an object with a `.list()` method
(`SimpleModelList` is the built-in helper). `AVAILABLE_MODELS` is the static
fallback that the client and server use for model resolution.

When `supports_tools = False`, `OpenAICompatibleProvider` transparently wraps
`chat.completions.create()` and runs a prompt-based tool loop for you, so the
provider does not need to understand OpenAI `tools` payloads.

## Discovering Providers

```python
from llm4free import Client

Client.get_chat_providers()        # all chat providers
Client.get_free_chat_providers()   # chat providers with required_auth = False
Client.get_image_providers()       # all text-to-image providers
Client.get_free_image_providers()
Client.get_tts_providers()         # all text-to-speech providers
Client.get_free_tts_providers()
```

### Free Chat Providers (no API key)

`AkashGPT`, `ChatGPT`, `ChatJimmy`, `Gemini`, `GptFree`, `IBM`, `K2Think`,
`Miklium`, `Netwrck`, `OllamaSwarm`, `PiAI`, `Toolbaz`, `TypliAI`, `WiseCat`.

### Authenticated Chat Providers

`AI4Chat`, `Cerebras`, `DeepAI`, `DeepInfra`, `Groq`, `HuggingFace`, `Nvidia`,
`OpenRouter`, `Sambanova`, `TextPollinations`, `TogetherAI`, `TwoAI`, `Upstage`,
`Zenmux`.

> [!NOTE]
> These providers set `required_auth = True`. The unified `Client` excludes them
> by default (`drop_auth_providers=True`), even when `api_key` is supplied. Pass
> `drop_auth_providers=False` to include them.

### Image Providers (TTI)

`BingImageAI`, `Lexica`, `MagicHourAI`, `MagicStudioAI`, `MiragicAI`,
`NoLoginTool`, `OneFreeAI`, `PerchanceAI`, `PollinationsAI`, `RaphaelAI`,
`StableHordeAI`, `TogetherImage`, `VisualGPT`.

### Speech Providers (TTS)

`DeepgramTTS`, `ElevenlabsTTS`, `KittenTTS`, `KyutaiTTS`, `LuxTTS`, `MurfAITTS`,
`OpenAIFMTTS`, `ParlerTTS`, `PocketTTS`, `QwenTTS`, `SherpaTTS`, `StreamElements`,
`TTSAI`, `TTSOpenTTS`, `XLNKTTS`.

## Provider Selection

### Automatic Selection

```python
from llm4free import Client

client = Client()
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

The client tries the best-matching provider first and falls back to others if
it fails.

### Pinning a Provider

Use a `provider/model` identifier or pass the provider class directly:

```python
from llm4free import Client
from llm4free.llm.gemini import Gemini

client = Client()

# Via model identifier
response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)

# Via provider class
response = client.chat.completions.create(
    model="gemini-3.6-flash",
    provider=Gemini,
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### Direct Provider Usage

```python
from llm4free.llm.gemini import Gemini

ai = Gemini()
response = ai.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## Server Provider Map

The API server uses a separate registry built at startup.

### Initialize Providers

```python
from llm4free.server.providers import initialize_provider_map

initialize_provider_map()  # registers free chat providers and their models
```

Only providers with `required_auth = False` are registered. Equivalent helpers
exist for the other modalities: `initialize_tti_provider_map()` and
`initialize_tts_provider_map()`.

### Resolve Provider

```python
from llm4free.server.providers import resolve_provider_and_model

provider_class, model_name = resolve_provider_and_model("Gemini/gemini-3.6-flash")
```

The server resolver is strict: use `Provider/Model` explicitly, or a bare model
name, which is resolved against `AppConfig.default_provider`. It does not support
`"auto"`, fuzzy matching, or failover. Image and speech identifiers are resolved
by `resolve_tti_provider_and_model()` and `resolve_tts_provider_and_model()`.

### Get Provider Instance

```python
from llm4free.server.providers import get_provider_instance

provider = get_provider_instance(provider_class)  # cached per provider class
```

## Registering a Custom Provider

Implement the class, then expose it from `llm4free/llm/__init__.py` so that the
client registries and the server provider map can discover it.

```python
# llm4free/llm/myprovider.py
from llm4free.llm.base import BaseChat, BaseCompletions, OpenAICompatibleProvider, SimpleModelList


class Completions(BaseCompletions):
    def __init__(self, client):
        self._client = client

    def create(self, *, model, messages, stream=False, **kwargs):
        ...  # return a ChatCompletion or a generator of ChatCompletionChunk


class Chat(BaseChat):
    def __init__(self, client):
        self.completions = Completions(client)


class MyProvider(OpenAICompatibleProvider):
    AVAILABLE_MODELS = ["my-model"]
    required_auth = False

    def __init__(self, api_key=None, proxies=None):
        super().__init__(proxies=proxies)
        self.chat = Chat(self)

    @property
    def models(self):
        return SimpleModelList(self.AVAILABLE_MODELS)
```

## Provider Configuration

### API Keys

```python
from llm4free import Client

# Pass one key to auth-required providers
client = Client(api_key="sk-...", drop_auth_providers=False)

# Or pass credentials straight to a provider class
from llm4free.llm.Auth.groq import Groq
ai = Groq(api_key="gsk-...")
```
