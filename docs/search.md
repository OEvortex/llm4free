# LLM4Free Search Module

> Last updated: 2026-09-24
> Audience: Developers integrating web search into Python applications

LLM4Free's search module provides unified access to multiple search engines through a consistent Python API and CLI. All engines return typed result dataclasses that support both attribute and dict-style access.

> [!TIP]
> Prefer chat, image, or audio generation instead of search? Use the unified `Client`, which automatically picks any working provider/model (no provider wiring needed):
> ```python
> from llm4free.client import Client
> client = Client()
> client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hello"}])
> ```

## Table of Contents

- [Quick Start](#quick-start)
- [Engine Capabilities](#engine-capabilities)
- [Imports](#imports)
- [Result Types](#result-types)
- [DuckDuckGo](#duckduckgo)
- [Bing](#bing)
- [Brave](#brave)
- [Yahoo](#yahoo)
- [Low-Level Engines](#low-level-engines)
- [CLI](#cli)
- [Parallel](#parallel)
- [Processing Results](#processing-results)
- [Multi-Engine Search](#multi-engine-search)
- [Combining Search with AI](#combining-search-with-ai)
- [Error Handling](#error-handling)
- [Custom Search Engine](#custom-search-engine)
- [API Reference](#api-reference)
- [Related Docs](#related-docs)

---

## Quick Start

```python
from llm4free import DuckDuckGoSearch

search = DuckDuckGoSearch()
results = search.text("python programming", max_results=5)
for r in results:
    print(f"{r['title']}: {r['href']}")
```

> [!NOTE]
> All results support both attribute access (`result.title`) and dict-style access (`result['title']`). URL aliases `link` and `url` both map to `href`.

---

## Engine Capabilities

| Category      | Engines                                                             |
| ------------- | ------------------------------------------------------------------- |
| `text`        | DuckDuckGo, Bing, Brave, Yahoo, Mojeek, Wikipedia, SerpBase, Parallel |
| `images`      | DuckDuckGo, Bing, Brave, Yahoo, SerpBase                            |
| `videos`      | DuckDuckGo, Brave, Yahoo                                            |
| `news`        | DuckDuckGo, Bing, Brave, Yahoo                                      |
| `suggestions` | DuckDuckGo, Bing, Brave, Yahoo                                      |
| `weather`     | DuckDuckGo, Yahoo                                                   |
| `answers`     | DuckDuckGo                                                          |
| `translate`   | DuckDuckGo                                                          |
| `maps`        | DuckDuckGo                                                          |

> [!WARNING]
> `SerpBase` requires an API key (`required_auth = True`). Parallel uses a public MCP endpoint and does not require an API key, but public access is subject to Parallel's free-tier rate limits and terms. All other engines work without authentication. The engine registry is defined in [`llm4free/search/__init__.py`](../../llm4free/search/__init__.py).

---

## Imports

The search engines are exported from the top-level package:

```python
from llm4free import (
    DuckDuckGoSearch,  # Full-featured: text, images, videos, news, maps, translate, weather, answers, suggestions
    BingSearch,        # Text, images, news, suggestions
    BraveSearch,       # Text, images, videos, news, suggestions
    YahooSearch,       # Text, images, videos, news, suggestions, weather
    Parallel,          # LLM-friendly text search through Parallel's public MCP endpoint
    Mojeek,            # Text only (independent European engine)
    Wikipedia,         # Text only (encyclopedia)
    SerpBase,          # Text, images (requires API key)
)
```

---

## Result Types

The main interfaces (`DuckDuckGoSearch`, `BingSearch`, `BraveSearch`, `YahooSearch`, `SerpBase`) return typed dataclasses. Low-level engines (`Mojeek`, `Parallel`, `Wikipedia`) return `TextResult`.

```python
from llm4free.search.results import TextResult, ImagesResult, VideosResult, NewsResult

# Both access styles work:
result.title      # attribute
result['title']   # dict-style
result['href']    # URL
result['link']    # alias for href
result['url']     # alias for href
```

### TextResult

| Field    | Type | Aliases for dict access   |
| -------- | ---- | ------------------------- |
| `title`  | str  |                           |
| `href`   | str  | `link`, `url`             |
| `body`   | str  | `snippet`                 |

### ImagesResult

| Field       | Type |
| ----------- | ---- |
| `title`     | str  |
| `image`     | str  |
| `thumbnail` | str  |
| `url`       | str  |
| `height`    | int  |
| `width`     | int  |
| `source`    | str  |

### VideosResult

| Field        | Type |
| ------------ | ---- |
| `title`      | str  |
| `url`        | str  |
| `thumbnail`  | str  |
| `content`    | str  |
| `description`| str  |
| `duration`   | str  |
| `embed_html` | str  |
| `embed_url`  | str  |
| `publisher`  | str  |
| `uploader`   | str  |

### NewsResult

| Field    | Type |
| -------- | ---- |
| `title`  | str  |
| `body`   | str  |
| `url`    | str  |
| `date`   | str  |
| `image`  | str  |
| `source` | str  |

---

## DuckDuckGo

The most feature-complete engine. Privacy-focused, no tracking.

```python
from llm4free import DuckDuckGoSearch

ddg = DuckDuckGoSearch()
```

### Text Search

```python
results = ddg.text(
    keywords="artificial intelligence",
    region="wt-wt",          # Region code
    safesearch="moderate",   # "on", "moderate", "off"
    timelimit="y",           # "d"=day, "w"=week, "m"=month, "y"=year
    backend="api",           # "api" or "html"
    max_results=10,
)
```

### Image Search

```python
results = ddg.images(
    keywords="nature photography",
    size="large",            # "small", "medium", "large", "wallpaper"
    color="green",           # Color filter
    type_image="photo",      # "photo", "clipart", "line", "animated", "face"
    layout="square",         # "square", "tall", "wide"
    license_image="commercial",
    max_results=50,
)
```

### Video Search

```python
results = ddg.videos(
    keywords="python tutorials",
    resolution="hd",          # "sd", "hd"
    duration="medium",        # "short", "medium", "long"
    license_videos="creativeCommon",
    max_results=30,
)
```

### News Search

```python
results = ddg.news(
    keywords="technology trends",
    timelimit="w",  # Last week
    max_results=20,
)
for item in results:
    print(f"{item['title']} - {item['date']}")
```

### Maps Search

```python
results = ddg.maps(
    keywords="coffee shops",
    place="new york",
    city="New York",
    radius=5,
    max_results=30,
)
```

### Translate

```python
results = ddg.translate(
    keywords="Hola mundo",
    from_lang="es",
    to_lang="en",
)
```

### Weather

```python
weather = ddg.weather("New York")
print(f"Temperature: {weather['current']['temperature_c']}C")
```

### Answers

```python
results = ddg.answers("python programming language")
```

### Suggestions

```python
results = ddg.suggestions("python prog", region="wt-wt")
```

---

## Bing

```python
from llm4free import BingSearch

bing = BingSearch()
```

### Text Search

```python
results = bing.text(
    keywords="machine learning",
    region="us",
    safesearch="moderate",
    unique=True,              # Deduplicate results
    max_results=10,
)
```

### Image Search

```python
results = bing.images(
    keywords="landscape photography",
    region="us",
    max_results=20,
)
```

### News Search

```python
results = bing.news(
    keywords="AI breakthroughs",
    max_results=15,
)
```

### Suggestions

```python
results = bing.suggestions(
    query="how to learn python",
    region="en-US",
)
```

---

## Brave

Privacy-focused modern search engine.

```python
from llm4free import BraveSearch

brave = BraveSearch()
```

### Text Search

```python
results = brave.text(
    keywords="cybersecurity",
    region="us-en",
    safesearch="moderate",
    max_results=10,
)
```

### Image Search

```python
results = brave.images(
    keywords="cyberpunk art",
    max_results=15,
)
```

### Video Search

```python
results = brave.videos(
    keywords="python tutorial",
    max_results=10,
)
```

### News Search

```python
results = brave.news(
    keywords="space exploration",
    max_results=10,
)
```

### Suggestions

```python
results = brave.suggestions(
    query="artificial i",
    rich=True,
    country="US",
)
```

---

## Yahoo

```python
from llm4free import YahooSearch

yahoo = YahooSearch()
```

### Text Search

```python
results = yahoo.text(
    keywords="web development",
    region="us",
    max_results=10,
)
```

### Image Search

```python
results = yahoo.images(
    keywords="landscapes",
    region="us",
    max_results=20,
)
```

### Video Search

```python
results = yahoo.videos(
    keywords="python tutorials",
    max_results=10,
)
```

### News Search

```python
results = yahoo.news(
    keywords="AI news",
    max_results=15,
)
```

### Weather

```python
weather = yahoo.weather("London")
```

### Suggestions

```python
results = yahoo.suggestions("web dev", region="us")
```

---

## Low-Level Engines

These engines only support text search and are accessed via their `run()` method.

### Mojeek

Independent European search engine, privacy-first.

```python
from llm4free import Mojeek

mojeek = Mojeek()
results = mojeek.run("privacy tools", region="us-en", max_results=5)
```

### Wikipedia

Encyclopedia search returning article summaries.

```python
from llm4free import Wikipedia

wiki = Wikipedia()
results = wiki.run("Quantum Computing", region="us-en", max_results=3)
for r in results:
    print(f"{r['title']}: {r['body'][:200]}")
```

### SerpBase

SerpBase proxies a third-party search API and requires authentication.

```python
from llm4free import SerpBase

serpbase = SerpBase(api_key="your-serpbase-key")
results = serpbase.text("machine learning papers", max_results=5)
```

---

## CLI

The CLI uses `--engine` (`-e`) to select the backend. DuckDuckGo is the default.

```bash
# Text search
llm4free text -k "python programming"
llm4free text -k "python programming" -e brave
llm4free text -k "quantum physics" -e wikipedia
llm4free text -k "latest Python release" -e parallel

# Image search
llm4free images -k "cyberpunk art" -e bing

# News
llm4free news -k "space exploration" -e yahoo

# Weather
llm4free weather -l "London"

# Suggestions
llm4free suggestions -q "artificial i"

# Translate
llm4free translate -k "Hola mundo" --to en
```

See [cli.md](cli.md) for the full CLI reference.

---

## Parallel

Parallel provides LLM-friendly text search through its public MCP endpoint. It returns the same `TextResult` objects as LLM4Free's other text engines and does not require an API key.

### Typed Results

```python
from llm4free import Parallel

parallel = Parallel(timeout=60)
results = parallel.search(
    "current Python release features",
    max_results=5,
)

for result in results:
    print(f"{result.title}: {result.href}")
    print(result.body)
```

Use `objective` to describe what the answer should accomplish and `search_queries` to provide one or more related query variants:

```python
results = parallel.search(
    "python release",
    objective="Find the latest stable Python release and its new features",
    search_queries=[
        "latest stable Python release",
        "what's new in the latest Python",
    ],
    max_results=5,
)
```

The same options are available through `search_text()`, which returns Parallel's concatenated MCP text content instead of typed results:

```python
text = parallel.search_text(
    "python release",
    objective="Summarize the latest Python release",
)
print(text)
```

`model_name`, `session_id`, and a per-request `timeout` can also be supplied when supported by the endpoint. A provider instance automatically initializes and reuses its MCP session.

> [!NOTE]
> Parallel determines relevance independently. The `region`, `safesearch`, `timelimit`, and `page` parameters are accepted for compatibility with `BaseSearchEngine` but are not forwarded to Parallel. `max_results` limits the returned results locally.

---

## Processing Results

### Extract URLs

```python
from llm4free import DuckDuckGoSearch

search = DuckDuckGoSearch()
results = search.text("api design", max_results=5)

urls = [r['href'] for r in results]
for url in urls:
    print(url)
```

### Filter by Keyword

```python
results = search.text("python", max_results=20)
official = [r for r in results if "python.org" in r['href']]
```

### Group by Domain

```python
from urllib.parse import urlparse

results = search.text("web development", max_results=15)
grouped = {}
for r in results:
    domain = urlparse(r['href']).netloc
    grouped.setdefault(domain, []).append(r)

for domain, items in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"{domain} ({len(items)} results)")
```

### Convert to Dict

```python
results = search.text("python", max_results=5)
dicts = [r.to_dict() for r in results]
```

### Save to JSON

```python
import json

results = search.text("python programming", max_results=10)
with open("results.json", "w") as f:
    json.dump([r.to_dict() for r in results], f, indent=2)
```

---

## Multi-Engine Search

```python
from llm4free import DuckDuckGoSearch, BingSearch, BraveSearch

def search_all(query, max_results=5):
    engines = [DuckDuckGoSearch(), BingSearch(), BraveSearch()]
    seen = set()
    combined = []

    for engine in engines:
        results = engine.text(query, max_results=max_results)
        for r in results:
            url = r['href']
            if url not in seen:
                seen.add(url)
                combined.append(r)
    return combined

results = search_all("python programming", max_results=5)
for r in results:
    print(f"{r['title']}: {r['href']}")
```

Low-level engines use a different call signature. For example, Parallel exposes `search()` directly:

```python
from llm4free import Parallel

results = Parallel().search("python programming", max_results=5)
```

---

## Combining Search with AI

> [!TIP]
> The unified `Client` exposes OpenAI-compatible chat completions. Use a free provider such as `HeckAI` to summarize results — no API key required.

### Summarize Results

```python
from llm4free import DuckDuckGoSearch
from llm4free.llm.heckai import HeckAI

search = DuckDuckGoSearch()
results = search.text("quantum computing", max_results=3)

context = "\n".join(f"{r['title']}: {r['body']}" for r in results)
ai = HeckAI()
response = ai.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": f"Summarize these search results:\n{context}"}],
)
print(response.choices[0].message.content)
```

### Research Assistant

```python
from llm4free import DuckDuckGoSearch
from llm4free.llm.heckai import HeckAI

def research(query: str):
    search = DuckDuckGoSearch()
    results = search.text(query, max_results=5)

    context = "Search Results:\n"
    for i, r in enumerate(results, 1):
        context += f"{i}. {r['title']}: {r['body'][:100]}...\n"

    ai = HeckAI()
    answer = ai.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": f"{context}\nBased on these results, explain: {query}"}],
    )

    print(f"Answer: {answer.choices[0].message.content}\n")
    print("Sources:")
    for r in results:
        print(f"  {r['href']}")

research("how does photosynthesis work")
```

### News Analysis

```python
from llm4free import DuckDuckGoSearch
from llm4free.llm.heckai import HeckAI

search = DuckDuckGoSearch()
news = search.news("artificial intelligence", max_results=3)

news_text = "\n".join(f"{item['title']}: {item['body']}" for item in news)
ai = HeckAI()
response = ai.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": f"Key takeaways from this news:\n{news_text}"}],
)
print(response.choices[0].message.content)
```

---

## Error Handling

```python
from llm4free import DuckDuckGoSearch

try:
    search = DuckDuckGoSearch()
    results = search.text("python programming", max_results=5)
    print(f"Found {len(results)} results")
except Exception as e:
    print(f"Search failed: {e}")
```

For rate-limited scenarios, add delays between requests:

```python
import time

for query in ["python", "javascript", "rust"]:
    results = search.text(query, max_results=5)
    print(f"{query}: {len(results)} results")
    time.sleep(1)
```

---

## Custom Search Engine

Extend `BaseSearchEngine` to add a new engine. The base class is generic over the result type (e.g. `TextResult`) and exposes class attributes for the request configuration.

```python
from llm4free.search.base import BaseSearchEngine
from llm4free.search.results import TextResult

class MyEngine(BaseSearchEngine[TextResult]):
    name = "myengine"
    category = "text"
    provider = "myengine"
    search_url = "https://example.com/search"
    search_method = "GET"
    items_xpath = "//div[@class='result']"
    elements_xpath = {
        "title": ".//h3/a/text()",
        "href": ".//h3/a/@href",
        "body": ".//p/text()",
    }

    def build_payload(self, query, region, safesearch, timelimit, page=1, **kwargs):
        return {"q": query, "p": page}

# Use it
engine = MyEngine()
results = engine.run("test query", max_results=5)
```

---

## API Reference

### DuckDuckGoSearch

| Method        | Signature                                                                   | Returns               |
| ------------- | --------------------------------------------------------------------------- | --------------------- |
| `text`        | `(keywords, region="wt-wt", safesearch="moderate", timelimit=None, backend="api", max_results=None)` | `List[TextResult]`   |
| `images`      | `(keywords, region="wt-wt", safesearch="moderate", timelimit=None, size=None, color=None, type_image=None, layout=None, license_image=None, max_results=None)` | `List[ImagesResult]` |
| `videos`      | `(keywords, region="wt-wt", safesearch="moderate", timelimit=None, resolution=None, duration=None, license_videos=None, max_results=None)` | `List[VideosResult]` |
| `news`        | `(keywords, region="wt-wt", safesearch="moderate", timelimit=None, max_results=None)` | `List[NewsResult]`   |
| `answers`     | `(keywords)`                                                                | `List[Dict]`          |
| `suggestions` | `(keywords, region="wt-wt")`                                                | `List[Dict]`          |
| `maps`        | `(keywords, place=None, street=None, city=None, county=None, state=None, country=None, postalcode=None, latitude=None, longitude=None, radius=0, max_results=None)` | `List[Dict]`          |
| `translate`   | `(keywords, from_lang=None, to_lang="en")`                                  | `List[Dict]`          |
| `weather`     | `(keywords)`                                                                | `WeatherData`         |

### BingSearch

| Method        | Signature                                            | Returns               |
| ------------- | ---------------------------------------------------- | --------------------- |
| `text`        | `(keywords, region="us", safesearch="moderate", max_results=None, unique=True)` | `List[TextResult]`   |
| `images`      | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[ImagesResult]` |
| `news`        | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[NewsResult]`   |
| `suggestions` | `(query, region="en-US")`                            | `List[Dict]`          |

### BraveSearch

| Method        | Signature                                            | Returns               |
| ------------- | ---------------------------------------------------- | --------------------- |
| `text`        | `(keywords, region="us-en", safesearch="moderate", max_results=None)` | `List[TextResult]`   |
| `images`      | `(keywords, region="us-en", safesearch="moderate", max_results=None)` | `List[ImagesResult]` |
| `videos`      | `(keywords, region="us-en", safesearch="moderate", max_results=None)` | `List[VideosResult]` |
| `news`        | `(keywords, region="us-en", safesearch="moderate", max_results=None)` | `List[NewsResult]`   |
| `suggestions` | `(query, rich=True, country=None, max_results=None)` | `List[Dict]`          |

### YahooSearch

| Method        | Signature                                            | Returns               |
| ------------- | ---------------------------------------------------- | --------------------- |
| `text`        | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[TextResult]`   |
| `images`      | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[ImagesResult]` |
| `videos`      | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[VideosResult]` |
| `news`        | `(keywords, region="us", safesearch="moderate", max_results=None)` | `List[NewsResult]`   |
| `suggestions` | `(keywords, region="us")`                            | `List[str]`           |
| `weather`     | `(keywords)`                                         | `List[dict]`          |

### Parallel

| Method        | Signature | Returns |
| ------------- | --------- | ------- |
| `search`      | `(query, region="us-en", safesearch="moderate", timelimit=None, page=1, objective=None, search_queries=None, session_id=None, model_name=None, timeout=None, max_results=None)` | `List[TextResult]` |
| `search_text` | `(query, *, objective=None, search_queries=None, session_id=None, model_name=None, timeout=None)` | `str` |
| `run`         | `(*args, **kwargs)` | `List[TextResult]` |

Parallel's `search()` converts structured MCP results into `TextResult` objects. If structured results are unavailable but the endpoint returns text, that text is preserved as a single result. `region`, `safesearch`, `timelimit`, and `page` are accepted only for interface compatibility.

### SerpBase

| Method        | Signature                                            | Returns               |
| ------------- | ---------------------------------------------------- | --------------------- |
| `text`        | `(keywords, max_results=None, **kwargs)`             | `List[TextResult]`   |
| `images`      | `(keywords, max_results=None, **kwargs)`             | `List[ImagesResult]` |

> [!WARNING]
> `SerpBase` requires an API key passed to the constructor (`SerpBase(api_key="...")`).

### Low-Level Engines (Mojeek, Wikipedia)

All share the same `run()` pattern:

| Engine      | `run()` Signature                                         | Returns           |
| ----------- | --------------------------------------------------------- | ----------------- |
| `Mojeek`    | `(*args, **kwargs)` — delegates to `search()`             | `List[TextResult]`|
| `Wikipedia` | `(*args, **kwargs)` — delegates to `search()`            | `List[TextResult]`|

---

## Related Docs

- [CLI Reference](cli.md) -- command-line usage
- [Architecture](architecture.md) -- how search fits into the system
- [Client](client.md) -- unified Python client with auto-failover
- [Getting Started](getting-started.md) -- quick-start guide
- [Troubleshooting](troubleshooting.md) -- common issues
