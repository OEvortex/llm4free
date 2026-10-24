# 🔍 LLM4Free AI Search

Five AI-powered search providers that return synthesized answers with web/source context instead of raw result lists. All of them share the same entry point:

```python
provider.search(prompt, stream=False, raw=False, **kwargs)
```

- `stream=False` returns a `SearchResponse` (or a provider-specific structure for some providers)
- `stream=True` returns a generator of chunks; when the answer is complete, the full text is also stored on `provider.last_response`
- `raw=True` returns the unmodified provider payload/stream for custom processing

The providers are importable from `llm4free` (re-exported via `llm4free.AISEARCH`):

```python
from llm4free import Perplexity, IAsk, Monica, webpilotai

# BraveSearch is also a web-search engine at top level, so import the AI
# search version explicitly to avoid the name collision:
from llm4free.AISEARCH import BraveSearch
```

## 📦 Providers

| Provider | Class | Constructor | Notes |
|---|---|---|---|
| Perplexity | `Perplexity` | `cookies=None, timeout=60, proxies=None` | Modes, source selection, model preference, follow-up context |
| IAsk | `IAsk` | `timeout=30, proxies=None, mode="question", detail_level=None` | `question`/`academic`/`forums`/`wiki`/`thinking` modes |
| Monica | `Monica` | `timeout=60, proxies=None` | Streamed Monica search API |
| WebPilot | `webpilotai` | `timeout=90, proxies=None` | Lowercase class name is intentional |
| Brave Search | `BraveSearch` | `cookies=None, timeout=60, proxies=None` | Standard answers and Deep Research |

There is no `PERPLEXED`, `Stellar`, or `WebPilotAI` (capitalized) provider in the package.

## 🚀 Installation

```bash
pip install -U llm4free
```

## 💻 Quick start

```python
from llm4free import Perplexity

ai = Perplexity()
response = ai.search("What is the weather in London?")
print(response)
print(ai.last_response)
```

### Streaming

```python
for chunk in ai.search("Explain black holes", stream=True):
    print(chunk, end="", flush=True)
```

### Perplexity options

```python
ai = Perplexity(timeout=90)

response = ai.search(
    "Recent developments in battery technology",
    sources=["web"],          # default
    incognito=True,           # default
    language="en-US",         # default
    mode="auto",              # "auto" (default) or "copilot"
    model="turbo",            # sets model_preference
    max_retries=3,            # default
)
```

`follow_up` can carry a previous turn:
`{"attachments": [...], "backend_uuid": "..."}`.

### IAsk

```python
from llm4free import IAsk

ai = IAsk(mode="academic", detail_level="detailed")
response = ai.search("Recent developments in mRNA vaccines")
print(response)

# Override per request
response = ai.search("CRISPR ethics", mode="thinking", detail_level="comprehensive")
```

- Modes: `question`, `academic`, `forums`, `wiki`, `thinking`
- Detail levels: `concise`, `detailed`, `comprehensive`
- `IAsk.create_url(prompt, mode=..., detail_level=...)` builds the underlying IAsk URL without making a request.

### Monica

```python
from llm4free import Monica

ai = Monica(timeout=60)
print(ai.search("Summarize the latest climate report"))
```

### webpilotai

```python
from llm4free import webpilotai

ai = webpilotai(timeout=90)
print(ai.search("Compare vector database options"))
```

### Brave Search

```python
from llm4free.AISEARCH import BraveSearch

ai = BraveSearch(timeout=60)

# Standard Brave answer
print(ai.search("What is Python?"))

# Formatted streaming: small upstream token deltas are grouped into readable chunks
for chunk in ai.search("Explain Python generators", stream=True):
    print(chunk, end="", flush=True)
print(ai.last_response)

# Deep Research (can take several minutes)
research = ai.search(
    "Compare the current state of web search engines",
    model="brave-deep-research",
    max_retries=3,
)
print(research)

# Raw provider stream for custom parsing/debugging
raw_stream = ai.search("What is Python?", stream=True, raw=True)
```

`BraveSearch` model values are `"brave"` (default) and `"brave-deep-research"`. With `stream=True` and `raw=False`, small upstream deltas are combined into chunks of at most 800 characters while keeping partial words intact.

## 🛡️ Error handling

```python
from llm4free import exceptions
from llm4free import Perplexity

ai = Perplexity()
try:
    response = ai.search("Your query")
except exceptions.APIConnectionError as exc:
    print(f"API error: {exc}")
except exceptions.FailedToGenerateResponseError as exc:
    print(f"Generation error: {exc}")
```

Provider/network failures use the shared exception types in `llm4free/exceptions.py` (`APIConnectionError`, `AuthenticationError`, `RatelimitE`, `TimeoutE`, `FailedToGenerateResponseError`, `InvalidResponseError`, ...).

## 🤝 Contributing

New providers should subclass `llm4free.AIbase.AISearch`, implement `search()`, keep `last_response` updated, and be exported from `llm4free/AISEARCH/__init__.py`.
