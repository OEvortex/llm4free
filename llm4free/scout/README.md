# Scout — HTML parsing and web crawling

Scout is a lightweight HTML/XML parser and crawler with a BeautifulSoup-style API,
shipped as part of `llm4free`.

## 📦 Installation

```bash
pip install llm4free
```

Optional parsers:

```bash
pip install lxml       # features="lxml"
pip install html5lib   # features="html5lib"
```

The default `html.parser` backend needs no extra packages.

## 🚀 Quick Start

### Parsing

```python
from llm4free.scout import Scout

html = """
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

scout = Scout(html)

title = scout.find("h1")
print(title.get_text())          # Hello, Scout!

links = scout.find_all("a")
print(links.attrs("href"))       # ['https://example.com']
print(links.texts())             # ['Link']
```

`find()` returns a single `Tag` (or `None`). `find_all()` returns a
`ScoutSearchResult`, a list subclass with `texts()`, `attrs()`, `filter()`,
`map()`, and `analyze_text()` helpers.

### Crawling

```python
from llm4free.scout import ScoutCrawler

crawler = ScoutCrawler("https://example.com", max_pages=50)

for page in crawler.crawl():
    print(page["url"], page["title"], len(page["links"]), page["depth"])
```

`crawl()` is a generator that yields one dictionary per page with the keys
`url`, `title`, `links`, `text`, `depth`, `timestamp`, and `headers`.

`ScoutCrawler` constructor options:

| Argument | Default | Description |
|----------|---------|-------------|
| `base_url` | required | Starting URL |
| `max_pages` | `50` | Maximum pages to crawl |
| `tags_to_remove` | `["script", "style"]` | Tags removed before text extraction |
| `session` | `None` | Custom session (defaults to the built-in `llm4free.browser_requests._http` session) |
| `delay` | `0.5` | Minimum seconds between requests |
| `obey_robots` | `True` | Respect `robots.txt` |
| `allowed_domains` | base host | Hosts the crawler may visit |

Crawling is restricted to `allowed_domains`; subdomains are not crawled unless
you add them explicitly. Concurrency is capped at 10 worker threads.

### Text analysis

```python
from llm4free.scout import Scout

scout = Scout("<div><h1>Climate Change</h1><p>Email info@example.com or call 555-123-4567.</p></div>")

analysis = scout.analyze_text()
print(analysis["word_count"])
print(analysis["entities"])
print(analysis["tokens"])
```

`analyze_text()` returns `word_count`, `entities` (URLs, emails, phone
numbers, dates), and `tokens`.

## ✨ Features

### Parsers

| `features=` | Backend | Notes |
|-------------|---------|-------|
| `"html.parser"` | stdlib | Default, no extra dependency |
| `"lxml"` | `lxml` | Requires `lxml` |
| `"html5lib"` | `html5lib` | Requires `html5lib` |

`"lxml-xml"` is accepted by the constructor's allowlist but is not registered
in `ParserRegistry`, so it currently raises `ValueError`.

```python
scout = Scout(html, features="lxml")
```

An unknown parser raises `ValueError`; requesting `lxml`/`html5lib` without the
package raises `ImportError`.

### CSS selectors

```python
scout.select("p")
scout.select(".item")
scout.select("div.card")
scout.select("#header")
scout.select("nav#main-menu")
scout.select("a[href]")
scout.select('a[rel="nofollow"]')
scout.select("div p")
scout.select("ul > li")
scout.select('div.container > p.text[lang="en"]')
scout.select_one("p.intro")
```

Supported selector parts: tag, `.class`, `#id`, `[attr]`,
`[attr="value"]`, descendant (space), and child (`>`) combinators.

### Navigation

```python
results = scout.find_all("a", attrs={"class": "external", "rel": "nofollow"})

parent = element.find_parent("div")
siblings = element.find_next_siblings("p")
prev_sibling = element.find_previous_sibling("p")
```

Scout also provides `find_parents`, `find_next_sibling(s)`,
`find_previous_sibling(s)`, `find_next`, `find_all_next`, `find_previous`, and
`find_all_previous`.

### Document analysis

```python
structure = scout.analyze_page_structure()
print(structure["tag_distribution"])
print(structure["class_distribution"])
print(structure["id_distribution"])
print(structure["depth_analysis"])

semantics = scout.extract_semantic_info()
print(semantics["headings"]["h1"])
print(semantics["lists"]["ul"])
print(semantics["tables"]["count"])
```

### Links, metadata, and URLs

```python
links = scout.extract_links(base_url="https://example.com")
for link in links:
    print(link["href"], link["text"], link["rel"], link["type"])

metadata = scout.extract_metadata()
print(metadata["title"])
print(metadata["description"])
print(metadata["keywords"])
print(metadata["og_metadata"])
print(metadata["twitter_metadata"])

parts = scout.url_parse("https://example.com/path?q=1")
print(parts["netloc"], parts["path"])
```

### Serialization and caching

```python
json_data = scout.to_json(indent=2)
pretty_html = scout.prettify()

content_hash = scout.hash_content(method="sha256")  # md5, sha1, or sha256

if not scout.cache("parsed_data"):
    data = scout.extract_semantic_info()
    scout.cache("parsed_data", data)
cached = scout.cache("parsed_data")
```

There is no Markdown or CSV exporter; use `to_json()` or traverse `Tag`
objects directly.

### Fetching remote pages

```python
scout = Scout("")
scout = scout.fetch_and_parse("https://example.com")
print(scout.find("title").get_text())
```

## 📚 API Reference

| Class | Description |
|-------|-------------|
| `Scout` | Main parser and traversal API |
| `ScoutCrawler` | Concurrent crawler yielding page dictionaries |
| `ScoutTextAnalyzer` | Tokenization, word counts, entity extraction |
| `ScoutWebAnalyzer` | Tag/class/id/depth statistics |
| `ScoutSearchResult` | List subclass with `texts`, `attrs`, `filter`, `map`, `analyze_text` |
| `Tag` | HTML/XML element |
| `NavigableString` | Text node |

### `Scout` methods

- `__init__(markup="", features="html.parser", from_encoding=None, exclude_encodings=None, element_classes=None)`
- `find(name=None, attrs={}, recursive=True, text=None, class_=None)`
- `find_all(name=None, attrs={}, recursive=True, text=None, limit=None, class_=None)`
- `find_parent`, `find_parents`, `find_next_sibling(s)`, `find_previous_sibling(s)`
- `find_next`, `find_all_next`, `find_previous`, `find_all_previous`
- `select(selector)`, `select_one(selector)`
- `get_text(separator="", strip=False)`, `get_text_robust(...)`
- `analyze_text(text=None)`, `analyze_page_structure()`, `extract_semantic_info()`
- `extract_links(base_url=None)`, `extract_metadata()`, `url_parse(url)`
- `to_json(indent=2)`, `prettify(formatter="minimal")`
- `hash_content(method="md5")`, `cache(key, value=None)`
- `fetch_and_parse(url, session=None, **kwargs)`
- `remove_tags(tags)`, `decompose`, `extract`, `clear`, `replace_with`
- `append`, `wrap`, `unwrap`, `insert_before`, `insert_after`

## 🔧 Dependencies

- Built-in `llm4free.browser_requests._http` client — used by `ScoutCrawler` for HTTP sessions (zero third-party dependencies; optionally `llm4free[impersonate]` for browser TLS/JA3)
- `lxml` — optional, enables `features="lxml"` / `"lxml-xml"`
- `html5lib` — optional, enables `features="html5lib"`

The parser core uses only the Python standard library.

## 🐍 Supported Python

Python 3.10+.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push the branch
5. Open a pull request

## 📄 License

Apache License 2.0 — see the repository `LICENSE` file.

---

<div align="center">
  <p>Part of the LLM4Free project</p>
  <p>
    <a href="https://github.com/OEvortex/llm4free">GitHub</a> •
    <a href="https://github.com/OEvortex/llm4free/issues">Issues</a>
  </p>
</div>
