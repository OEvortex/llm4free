# Scout: HTML Parser & Web Crawler

> A zero-dependency, BeautifulSoup-compatible HTML parsing and web crawling library for AI/LLM data collection.

`Scout` is an HTML parsing and web crawling library designed for extracting, analyzing, and processing web content. It exposes a familiar BeautifulSoup-style API enhanced with modern features such as text/entity analysis, semantic extraction, URL parsing, and a concurrent web crawler.

> [!NOTE]
> Scout is included with LLM4Free and is used internally by the search engines. Import it directly with `from llm4free.scout import Scout`.

> [!NOTE]
> Scout is for HTML parsing and web crawling — not for talking to LLMs. For AI chat, image, and audio generation, use the unified `Client` instead: `from llm4free.client import Client; client.chat.completions.create(model="auto", messages=[...])`. See [client.md](client.md).

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Supported Parsers](#supported-parsers)
- [API Reference](#api-reference)
- [ScoutCrawler](#scoutcrawler)
- [ScoutSearchResult](#scoutsearchresult)
- [LLM4Free Integration](#llm4free-integration)
- [Dependencies](#dependencies)

---

## Installation

Scout ships with LLM4Free:

```bash
pip install llm4free
```

Or install the latest version from GitHub:

```bash
pip install git+https://github.com/OEvortex/LLM4Free.git
```

---

## Quick Start

### Basic Parsing

```python
from llm4free.scout import Scout

html_content = """
<html>
    <body>
        <h1>Hello, Scout!</h1>
        <div class="content">
            <p>Web parsing made easy.</p>
            <a href="https://example.com">Link</a>
        </div>
    </body>
</html>
"""

scout = Scout(html_content)

# Find a single element (returns a Tag or None)
title = scout.find('h1')
links = scout.find_all('a')

# Extract text and attributes
print(title.get_text())                       # Output: Hello, Scout!
print([a.get('href') for a in links])         # Output: ['https://example.com']
```

> [!WARNING]
> `Scout.find()` returns a **single** `Tag` (or `None`), not a list. Use `find_all()` when you expect multiple results. The older `title[0].get_text()` pattern is **not** valid for `find()`.

### Text Analysis

```python
from llm4free.scout import Scout

html = """<div><h1>Climate Change</h1><p>Email us at info@example.com or call 555-123-4567.</p>
<p>Visit https://climate-action.org for more information.</p></div>"""
scout = Scout(html)

analysis = scout.analyze_text()
print(f"Word count: {analysis['word_count']}")
print(f"Entities: {analysis['entities']}")
```

`analyze_text()` returns a dict with `word_count`, `entities`, and `tokens`.

### CSS Selectors

Scout includes a CSS selector engine that supports common selector types:

```python
# Tag, class, and ID selectors
paragraphs = scout.select('p')
cards = scout.select('div.card')
header = scout.select_one('#header')

# Attribute selectors
links = scout.select('a[href]')
external = scout.select('a[rel="nofollow"]')

# Descendant and child combinators
nested = scout.select('div p')
direct = scout.select('ul > li')

# Combined selectors
complex = scout.select('div.container > p.text[lang="en"]')
```

Supported selector types include tag (`p`), class (`.class`, `div.class`), ID (`#id`), attribute (`[attr]`, `[attr="value"]`), descendant (`div p`), child (`div > p`), and combined (`p.class#id[attr="value"]`).

---

## Supported Parsers

Scout supports multiple HTML/XML parsers, selectable via the `features` argument:

| Parser | Description | Best For |
|--------|-------------|----------|
| `html.parser` | Python's built-in parser | General-purpose parsing, no dependencies |
| `lxml` | Fast C-based parser | Performance-critical applications |
| `html5lib` | Highly compliant HTML5 parser (optional) | Handling malformed HTML |
| `lxml-xml` | XML parser | XML document parsing |

```python
scout = Scout(html_content, features='lxml')      # For speed
# html5lib requires: pip install html5lib
scout = Scout(html_content, features='html5lib')  # For compliance
```

---

## API Reference

### Core Classes

| Class | Description |
|-------|-------------|
| `Scout` | Main class for HTML parsing and traversal |
| `ScoutCrawler` | Concurrent web crawler for fetching and parsing multiple pages |
| `ScoutTextAnalyzer` | Text analysis utilities (word count, tokenize, entity extraction) |
| `ScoutWebAnalyzer` | Web page structure analysis utilities |
| `ScoutSearchResult` | `list` subclass of results with filtering and analysis helpers |
| `Tag` | Represents an HTML/XML tag |
| `NavigableString` | Represents text within an HTML/XML document |

### `Scout` methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(markup="", features="html.parser", from_encoding=None, ...)` | Initialize with HTML content |
| `find` | `(name=None, attrs={}, recursive=True, text=None, class_=None, **kwargs)` | Find the first matching element (returns `Tag` or `None`) |
| `find_all` | `(name=None, attrs={}, recursive=True, text=None, limit=None, class_=None, **kwargs)` | Find all matching elements (returns `ScoutSearchResult`) |
| `find_parent` / `find_parents` | `(name=None, attrs={}, ...)` | Traverse upward to parent elements |
| `find_next_sibling` / `find_next_siblings` | `(name=None, attrs={}, ...)` | Traverse forward siblings |
| `find_previous_sibling` / `find_previous_siblings` | `(name=None, attrs={}, ...)` | Traverse backward siblings |
| `find_next` / `find_all_next` | `(name=None, attrs={}, text=None, ...)` | Find next element(s) in document order |
| `find_previous` / `find_all_previous` | `(name=None, attrs={}, text=None, ...)` | Find previous element(s) in document order |
| `select` | `(selector)` | Find elements using a CSS selector (returns `list[Tag]`) |
| `select_one` | `(selector)` | Find the first element matching a CSS selector (returns `Tag` or `None`) |
| `get_text` | `(separator="", strip=False, types=None)` | Extract text from the document |
| `analyze_text` | `(text=None)` | Perform text analysis; returns `word_count`, `entities`, `tokens` |
| `analyze_page_structure` | `()` | Analyze document structure (via `ScoutWebAnalyzer`) |
| `extract_semantic_info` | `()` | Extract headings, lists, and tables |
| `extract_links` | `(base_url=None)` | Extract all `<a>`/`<link>` hrefs |
| `extract_metadata` | `()` | Extract title, description, keywords, Open Graph, and Twitter card metadata |
| `hash_content` | `(method="md5")` | Generate a hash of the parsed content (`md5`, `sha1`, `sha256`) |
| `url_parse` | `(url)` | Parse a URL into its components |
| `to_json` | `(indent=2)` | Convert the document to a JSON string |
| `prettify` | `(formatter="minimal")` | Pretty-print the HTML |
| `remove_tags` | `(tags)` | Remove the given tag names and their contents |
| `cache` | `(key, value=None)` | Simple per-instance cache for parsed content |
| `fetch_and_parse` | `(url, session=None, **kwargs)` | Fetch HTML from a URL (uses `curl_cffi` when available) and parse it |

> [!WARNING]
> `Scout` does **not** implement `to_markdown()`. Use `to_json()` or `prettify()` to serialize parsed content. The earlier docs that referenced `to_markdown()` were inaccurate.

### Working with `find_all` results

`find_all()` returns a `ScoutSearchResult` (a `list` subclass) with extra helpers:

```python
from llm4free.scout import Scout

scout = Scout(html_content)
paragraphs = scout.find_all('p')

# Extract all text from the results
all_text = paragraphs.texts(separator='\n')

# Extract a specific attribute from each result
hrefs = paragraphs.attrs('href')

# Filter with a predicate
important = paragraphs.filter(lambda p: 'important' in p.get('class', []))

# Transform results
word_counts = paragraphs.map(lambda p: len(p.get_text().split()))

# Analyze text across results
analysis = paragraphs.analyze_text()
```

`ScoutSearchResult` methods:

| Method | Returns |
|--------|---------|
| `texts(separator=" ", strip=True)` | `list[str]` of text from each result |
| `attrs(attr_name)` | `list` of the given attribute from each result |
| `filter(predicate)` | A new `ScoutSearchResult` filtered by the predicate |
| `map(transform)` | `list` produced by applying `transform` to each result |
| `analyze_text()` | `dict` with `total_results`, `word_count`, `entities` |

### Metadata & Link Extraction

```python
metadata = scout.extract_metadata()
print(metadata['title'])
print(metadata['description'])
print(metadata['og_metadata'])
print(metadata['twitter_metadata'])

links = scout.extract_links(base_url='https://example.com')
for link in links:
    print(link['href'], link['text'])
```

---

## ScoutCrawler

`ScoutCrawler` is a concurrent, domain-scoped web crawler.

```python
from llm4free.scout import ScoutCrawler

# Crawl with defaults (max_pages=50)
crawler = ScoutCrawler('https://example.com')

# Or customize
crawler = ScoutCrawler(
    'https://example.com',
    max_pages=100,
    tags_to_remove=['script', 'style', 'nav'],
)

for page in crawler.crawl():
    print(f"URL: {page['url']}")
    print(f"Title: {page['title']}")
    print(f"Links found: {len(page['links'])}")
    print(f"Crawl depth: {page['depth']}")
```

> [!NOTE]
> `crawl()` is a **generator** — it yields each page as it is crawled rather than returning a single list. Each yielded page is a dict with `url`, `title`, `links`, `text`, `depth`, `timestamp`, and `headers`.

The crawler automatically:

- Stays within the base URL's domain (and respects `allowed_domains`)
- Uses concurrent requests for faster crawling
- Removes unwanted tags (e.g., `script`, `style`) for cleaner text
- Tracks crawl depth per page
- Honors `robots.txt` when `obey_robots=True` (the default)

### `ScoutCrawler` constructor

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_url` | (required) | Starting URL to crawl |
| `max_pages` | `50` | Maximum number of pages to crawl |
| `tags_to_remove` | `["script", "style"]` | Tags removed before text extraction |
| `session` | `None` | Optional pre-configured HTTP session |
| `delay` | `0.5` | Delay between requests (seconds) |
| `obey_robots` | `True` | Whether to honor `robots.txt` |
| `allowed_domains` | `[base_netloc]` | Domains considered in-scope |

---

## LLM4Free Integration

Scout is deeply integrated into LLM4Free's search engines, providing HTML parsing without external dependencies.

### Why Scout in LLM4Free?

- **Zero Dependencies** for basic parsing — no need to install `lxml` separately.
- **Enhanced Features** — CSS selectors, text analysis, web crawling, and more.
- **Better Performance** — optimized parsing and traversal.

The search engines leverage Scout's CSS selector capabilities exactly like BeautifulSoup:

```python
from llm4free.scout import Scout

soup = Scout(html)

# BeautifulSoup-compatible find methods
soup.find('div', attrs={'class': 'content'})
soup.find_all('p', limit=10)

# Text extraction
soup.get_text(separator='\n', strip=True)

# Tree traversal
tag.find_parent('div')
tag.find_next_sibling('p')

# Serialization
soup.to_json(indent=2)
soup.prettify()
```

---

## Dependencies

- `curl_cffi` — HTTP library used by `fetch_and_parse` (falls back to `requests` if unavailable)
- `lxml` — Fast parser (optional, recommended for `features='lxml'`)
- `html5lib` — Standards-compliant HTML parser (optional)
- `concurrent.futures` — Asynchronous execution (standard library)

> [!TIP]
> Core parsing works with the stdlib `html.parser`. Install `lxml` for significantly faster parsing in production crawls.

---

*GitHub · Issues · PyPI*
