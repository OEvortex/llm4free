# Client API Reference

## Unified Client

`llm4free.Client` is a single entry point for chat completions, image generation,
and text-to-speech. It resolves model names across providers, caches provider
instances, and fails over to another provider when the first one fails.

### Quick Start

```python
from llm4free import Client

client = Client()
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

`model="auto"` lets the client pick an available provider and model. You can
also pass `provider/model` (for example `"Gemini/gemini-3.6-flash"`) to pin a
specific provider.

### Client Initialization

```python
from llm4free import Client

# Default: free providers only, automatic failover
client = Client()

# Show which provider answered each request
client = Client(print_provider_info=True)

# Use one API key, but keep auth-required providers excluded
client = Client(api_key="your-key")

# Allow auth-required providers as well
client = Client(api_key="your-key", drop_auth_providers=False)

# Skip providers that are unreliable for you
client = Client(
    exclude=["Toolbaz"],
    exclude_images=["PollinationsAI"],
    exclude_tts=["ParlerTTS"],
)

# Route all provider requests through a proxy
client = Client(proxies={"http": "http://localhost:8080", "https": "http://localhost:8080"})
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `provider` | provider class | `None` | Default chat provider class. |
| `image_provider` | provider class | `None` | Default image provider class. |
| `api_key` | `str` | `None` | Key passed to providers that need auth. |
| `proxies` | `dict` | `{}` | Proxy settings applied to every provider. |
| `exclude` | `list[str]` | `[]` | Chat provider names to skip (case-insensitive). |
| `exclude_images` | `list[str]` | `[]` | Image provider names to skip. |
| `exclude_tts` | `list[str]` | `[]` | TTS provider names to skip. |
| `print_provider_info` | `bool` | `False` | Print the selected provider/model per request. |
| `drop_auth_providers` | `bool` | `True` | Exclude `required_auth=True` providers entirely. |

> [!IMPORTANT]
> `drop_auth_providers` defaults to `True`, so providers with `required_auth = True`
> are skipped even when you pass `api_key`. Set `drop_auth_providers=False` to
> include them.

### Discovering Providers

These are static methods on `Client`:

```python
from llm4free import Client

print(Client.get_chat_providers())         # all chat providers
print(Client.get_free_chat_providers())    # chat providers without auth
print(Client.get_image_providers())        # all image providers
print(Client.get_free_image_providers())
print(Client.get_tts_providers())          # all TTS providers
print(Client.get_free_tts_providers())
print(Client.get_audio_providers())        # alias of get_tts_providers()
print(Client.get_free_audio_providers())   # alias of get_free_tts_providers()
```

### Chat Completions

```python
# Basic completion
response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
    ],
)

# Streaming
for chunk in client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Write a poem"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="")

# Tool calling
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "What is the weather in Paris?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }],
)
```

`client.chat.completions.last_provider` holds the name of the provider that
served the most recent request.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | `"auto"` | `"auto"`, `provider/model`, or a model name. |
| `messages` | `list[dict]` | required | OpenAI-style messages. |
| `max_tokens` | `int` | `None` | Maximum tokens to generate. |
| `stream` | `bool` | `False` | Return a generator of chunks. |
| `temperature` | `float` | `None` | Sampling temperature. |
| `top_p` | `float` | `None` | Nucleus sampling. |
| `tools` | `list` | `None` | OpenAI tool definitions or `Tool` objects. |
| `tool_choice` | `str` / `dict` | `None` | Tool selection hint (native-tool providers only). |
| `timeout` | `int` | `None` | Per-request timeout in seconds. |
| `proxies` | `dict` | `None` | Per-request proxy override. |
| `provider` | provider class | `None` | Pin a provider for this call. |

### Image Generation

```python
response = client.images.generate(
    prompt="A sunset over mountains",
    model="auto",
    n=1,
    size="1024x1024",
)
print(response.data[0].url)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | `str` | required | Image description. |
| `model` | `str` | `"auto"` | `"auto"`, `provider/model`, or a model name. |
| `n` | `int` | `1` | Number of images. |
| `size` | `str` | `"1024x1024"` | Image dimensions. |
| `response_format` | `str` | `"url"` | `"url"` or `"b64_json"`. |
| `provider` | provider class | `None` | Pin an image provider for this call. |

`client.images.last_provider` holds the provider that served the last request.

### Text-to-Speech

```python
audio_file = client.audio.speech.create(
    input_text="Hello, world!",
    model="auto",
)
print(audio_file)  # path to the generated audio file
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_text` | `str` | required | Text to synthesize (`input` is also accepted). |
| `model` | `str` | `"auto"` | `"auto"`, `provider/model`, or a model name. |
| `voice` | `str` | `None` | Voice name, if the provider supports voices. |
| `response_format` | `str` | `"mp3"` | Audio format. |
| `instructions` | `str` | `None` | Style instructions for supporting providers. |
| `stream` | `bool` | `False` | Return a byte generator instead of a file path. |
| `chunk_size` | `int` | `1024` | Chunk size used when `stream=True`. |
| `provider` | provider class | `None` | Pin a TTS provider for this call. |

`client.audio.speech.last_provider` holds the provider that served the last request.

## Direct Provider Usage

Providers use the same `chat.completions.create()` interface as the unified
client, so code written against one provider works with another.

```python
from llm4free.llm.gemini import Gemini

ai = Gemini()
response = ai.chat.completions.create(
    model="gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

Choose a model name from that provider's `AVAILABLE_MODELS`:

```python
from llm4free.llm.gemini import Gemini

print(Gemini.AVAILABLE_MODELS)
```

## Error Handling

Provider failures are normally handled by automatic failover: if one provider
raises, the client tries the next candidate. If every candidate fails, the last
error is raised.

```python
from llm4free import Client

client = Client()

try:
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Hello!"}],
    )
except RuntimeError as exc:
    print(f"All providers failed: {exc}")
```
