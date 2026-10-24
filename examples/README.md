# Examples

Small, standalone scripts using the OpenAI-style `llm4free` client:

```python
client.chat.completions.create(...)
client.images.generate(...)
client.audio.speech.create(...)
```

## Setup

From the repository root:

```bash
uv sync
# or: pip install -e ".[dev]"
```

If you only want the library outside this repository:

```bash
pip install -U llm4free
```

Scripts that generate files write them to `examples/output/`.

## Examples

| File | What it shows |
| --- | --- |
| [`quickstart.py`](quickstart.py) | One chat request and one image request |
| [`conversation.py`](conversation.py) | Multi-turn chat with retained history |
| [`streaming.py`](streaming.py) | Token-by-token streaming responses |
| [`tool_calling.py`](tool_calling.py) | Tool/function calling with a weather tool |
| [`images.py`](images.py) | Generating and saving images |
| [`text_to_speech.py`](text_to_speech.py) | Generating and saving speech audio |
| [`content_pipeline.py`](content_pipeline.py) | Chaining article, cover image, and narration |

Run any example directly:

```bash
uv run python examples/quickstart.py
uv run python examples/tool_calling.py
```

## Provider selection

- `model="auto"` picks an available provider and model.
- `model="ProviderName/model-name"` pins a provider by name.
- `provider=SomeProviderClass` pins a provider class for one request.
- `print_provider_info=True` is a `Client(...)` constructor argument that reports the provider and model used for each call.
- The client automatically falls back to other providers when a request fails.
