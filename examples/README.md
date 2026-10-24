# Examples

Standalone, runnable examples for the `llm4free` client. Each script uses the
same client shape as the OpenAI Python SDK:

```python
client.chat.completions.create(...)
client.images.generate(...)
client.audio.speech.create(...)
```

## Setup

From a checkout of this repository:

```bash
uv sync
```

Or install the package:

```bash
uv add llm4free
```

Examples that generate files write them to `examples/output/`.

## API keys

Free providers work without a key. To enable providers that require
authentication, set `LLM4FREE_API_KEY` and construct the client with
`drop_auth_providers=False`:

```python
client = Client(api_key=os.getenv("LLM4FREE_API_KEY"), drop_auth_providers=False)
```

## Examples

| File | What it shows |
| --- | --- |
| [`quickstart.py`](quickstart.py) | One chat request and one image request |
| [`conversation.py`](conversation.py) | Multi-turn chat with retained history |
| [`streaming.py`](streaming.py) | Token-by-token streaming responses |
| [`tool_calling.py`](tool_calling.py) | Tool/function calling with a support agent |
| [`images.py`](images.py) | Generating and saving images |
| [`text_to_speech.py`](text_to_speech.py) | Generating and saving speech audio |
| [`content_pipeline.py`](content_pipeline.py) | Chaining article, cover image, and narration |

Run any example directly:

```bash
uv run python examples/quickstart.py
uv run python examples/tool_calling.py
```

## How provider selection works

- `model="auto"` picks an available provider and model.
- `model="ProviderName/model-name"` pins a provider by name.
- `provider=SomeProviderClass` pins a provider class for one request.
- `print_provider_info=True` reports the provider and model used for each call.
- The client automatically falls back to other providers when a request fails.

```python
from llm4free import Client
from llm4free.TTI.pollinations import PollinationsAI

client = Client(print_provider_info=True)

client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello"}],
)

client.images.generate(
    prompt="A geometric fox, flat vector style",
    model="auto",
    provider=PollinationsAI,
)
```
