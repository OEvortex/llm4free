# Search API Reference

## Search Engines

`llm4free.search` exposes both high-level multi-purpose classes and individual
engines. All results are dataclasses with dict-like access; text results have
`title`, `href`, and `body` fields.

### Multi-Purpose Classes

| Class | Categories |
|-------|------------|
| `DuckDuckGoSearch` | text, news, images, videos, suggestions, answers, maps, translate, weather |
| `BingSearch` | text, news, images, videos, suggestions, answers, maps, translate |
| `BraveSearch` | text, news, images, videos, suggestions, answers, maps, translate |
| `YahooSearch` | text, news, images, videos, suggestions, answers, maps, translate, weather |

### Individual Engines

`Mojeek`, `Parallel`, `Wikipedia`, and `SerpBase` are single-category text
engines. `ENGINES` (in `llm4free.search.engines`) maps each category to the
engines that support it:

```python
from llm4free.search.engines import ENGINES

for category, engines in ENGINES.items():
    print(category, sorted(engines))
```

| Category | Engines |
|----------|---------|
| text | bing, brave, duckduckgo, mojeek, parallel, serpbase, yahoo |
| images | bing, brave, duckduckgo, yahoo |
| videos | brave, duckduckgo, yahoo |
| news | bing, brave, duckduckgo, yahoo |
| suggestions | bing, brave, duckduckgo, yahoo |
| answers | duckduckgo |
| maps | duckduckgo |
| translate | duckduckgo |
| weather | duckduckgo |

## Using Search Engines

```python
from llm4free.search import DuckDuckGoSearch

searcher = DuckDuckGoSearch()
results = searcher.text(
    keywords="Python programming",
    region="wt-wt",
    safesearch="moderate",
    max_results=10,
)

for result in results:
    print(result.title, result.href)
    print(result.body)
```

News search:

```python
from llm4free.search import DuckDuckGoSearch

for item in DuckDuckGoSearch().news(keywords="AI", max_results=5):
    print(item.title, item.href)
```

Single-category engines use `run()` (or `search()`):

```python
from llm4free.search import Mojeek, Wikipedia

for result in Mojeek().run(keywords="Python", max_results=5):
    print(result.title, result.href)

for result in Wikipedia().run(keywords="Python (programming language)", max_results=5):
    print(result.title, result.href)
```

## Server API

The API server exposes search at `GET /search`:

```bash
# Text search
curl "http://localhost:8000/search?q=Python+tutorials&engine=duckduckgo"

# News search
curl "http://localhost:8000/search?q=AI+news&engine=brave&type=news"

# List available engines and their categories
curl "http://localhost:8000/search/provider"
```

### Search Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | required | Search query. |
| `engine` | string | `duckduckgo` | Engine name from the table above. |
| `max_results` | int | `10` | Maximum number of results. |
| `region` | string | `all` | Region code. |
| `safesearch` | string | `moderate` | `on`, `moderate`, or `off`. |
| `type` | string | `text` | `text`, `news`, `images`, `videos`, `suggestions`, `answers`, `maps`, `translate`, `weather`. |
| `place`, `street`, `city`, `county`, `state`, `country`, `postalcode`, `latitude`, `longitude`, `radius` | string/int | — | Map search fields. |
| `from_` | string | `None` | Source language for `translate`. |
| `to` | string | `en` | Target language for `translate`. |
| `language` | string | `en` | Language for `weather`. |

Unsupported engine/type combinations return a JSON object with an `error` key.

## CLI Usage

```bash
# Text search
llm4free text -k "Python tutorials" -e ddg

# News search with a specific engine
llm4free news -k "AI news" -e brave

# Unified text search
llm4free search -k "Python tutorials" -e bing -m 10
```
