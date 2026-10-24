# LLM4Free CLI Reference

> Source of truth: [`llm4free/cli.py`](../llm4free/cli.py)
> Engine map: `ddg`, `duckduckgo` (alias), `bing`, `yahoo`, `brave`, `mojeek`, `parallel`, `wikipedia`, `serpbase`.

The LLM4Free CLI provides a unified interface for multiple search engines. Every search command accepts an `--engine` (or `-e`) option to choose a provider; **DuckDuckGo (`ddg`)** is the default when `-e` is omitted.

> [!NOTE]
> The Python equivalent of the CLI is the unified `Client` (for chat, image, and audio generation) plus `DuckDuckGoSearch` (and other search engines) for web search. The `Client` auto-fails-over across providers with `model="auto"` — no provider wiring required:
> ```python
> from llm4free.client import Client
> from llm4free import DuckDuckGoSearch
> client = Client()
> client.chat.completions.create(model="auto", messages=[{"role": "user", "content": "Hello"}])
> ```

## Table of Contents

- [Getting Started](#getting-started)
- [Available Commands](#available-commands)
- [Common Options](#common-options)
- [Per-Command Details](#per-command-details)
- [Usage Examples](#usage-examples)
- [Related Documentation](#related-documentation)

---

## Getting Started

```bash
# Show all available commands
llm4free --help

# Show the CLI version
llm4free version

# Run a simple text search (defaults to DuckDuckGo)
llm4free text -k "python programming"
```

The CLI uses **Rich** for formatted table outputs and informative panels.

---

## Available Commands

| Command | Description | Engines that implement the method |
|---------|-------------|-----------------------------------|
| `version` | Print the installed `llm4free` version | — |
| `text` | General web/text search | all nine engines |
| `images` | Image search | `ddg`, `bing`, `yahoo`, `brave` |
| `videos` | Video search | `ddg`, `bing`, `yahoo`, `brave` |
| `news` | News search | `ddg`, `bing`, `yahoo`, `brave` |
| `weather` | Weather information | `ddg`, `yahoo` |
| `answers` | Instant answers | `ddg`, `bing`, `yahoo`, `brave` |
| `suggestions` | Query autocomplete | `ddg`, `bing`, `yahoo`, `brave` |
| `translate` | Text translation | `ddg`, `bing`, `yahoo`, `brave` |
| `maps` | POI / location search | `ddg`, `bing`, `yahoo`, `brave` |
| `search` | Shortcut for `text` with only `-k`, `-e`, `-m` | same as `text` |

> [!NOTE]
> Each command only succeeds if the selected engine implements the corresponding method. For example, `images` works on `ddg`/`bing`/`yahoo`/`brave` but will report "does not support image search" for engines that lack an `images()` method. The full engine map lives in `llm4free/cli.py` (`ENGINES`).

---

## Common Options

`text` (and its `search` shortcut) accepts these options:

| Option | Alias | Default | Description |
|--------|-------|---------|-------------|
| `--keywords` | `-k` | (required) | Search query or keywords |
| `--engine` | `-e` | `ddg` | Search engine to use |
| `--max-results` | `-m` | `10` | Maximum number of results to display |
| `--region` | `-r` | `None` → `wt-wt` for ddg, `us` otherwise | Region code (e.g., `us`, `uk`, `wt-wt`) |
| `--safesearch` | `-s` | `moderate` | SafeSearch: `on` / `moderate` / `off` |
| `--timelimit` | `-t` | (none) | Time filter: `d`, `w`, `m`, `y` |

`search` only defines `-k/--keywords`, `-e/--engine`, and `-m/--max-results`; it calls `text()` with the default region, SafeSearch, and time limit.

---

## Per-Command Details

### `text` / `search`

```bash
llm4free text -k "fastapi tutorial" -e ddg -m 5
```

Options: `-k/--keywords` (required), `-e/--engine` (default `ddg`), `-r/--region`, `-s/--safesearch`, `-t/--timelimit`, `-m/--max-results`.

> [!TIP]
> `search` is a shortcut for `text` — it accepts only `-k`, `-e`, and `-m` and then calls `text()` with the default region, SafeSearch, and time limit.

### `images`

```bash
llm4free images -k "cyberpunk art" -e bing
```

Options: `-k/--keywords` (required), `-e/--engine` (default `ddg`), `-m/--max-results`.

### `videos`

```bash
llm4free videos -k "space exploration" -e yahoo
```

Options: `-k/--keywords` (required), `-e/--engine` (default `ddg`), `-m/--max-results`.

### `news`

```bash
llm4free news -k "ai regulation" -e bing
```

Options: `-k/--keywords` (required), `-e/--engine` (default `ddg`), `-m/--max-results`.

### `weather`

```bash
llm4free weather -l "London" -e yahoo
```

Options: `-l/--location` (required), `-e/--engine` (default `ddg`). Prints a current-conditions panel and a 5-day forecast.

### `answers`

```bash
llm4free answers -k "why is the sky blue" -e ddg
```

Options: `-k/--keywords` (required), `-e/--engine` (default `ddg`).

### `suggestions`

```bash
llm4free suggestions -q "artificial i" -e ddg
```

Options: `-q/--query` (required), `-e/--engine` (default `ddg`).

### `translate`

```bash
llm4free translate -k "Hola mundo" --to en -e yahoo
```

Options:

- `-k/--keywords` (required) — text to translate
- `-f/--from-lang` (optional) — source language
- `-t/--to` (default `en`) — target language
- `-e/--engine` (default `ddg`)

### `maps`

```bash
llm4free maps -k "coffee shop" --place "Berlin" --radius 5 -e ddg
```

Options:

- `-k/--keywords` (required)
- `-p/--place` (optional) — place name
- `-r/--radius` (default `0`) — search radius in km
- `-e/--engine` (default `ddg`)

---

## Usage Examples

### 1. Multi-Engine Search

```bash
# Default (DuckDuckGo)
llm4free text -k "fastapi tutorial"

# Using Brave Search
llm4free text -k "fastapi tutorial" -e brave

# Using Wikipedia
llm4free text -k "Quantum Physics" -e wikipedia
```

### 2. Media & News Search

```bash
# Find images on Bing
llm4free images -k "cyberpunk art" -e bing

# Find news on Yahoo
llm4free news -k "space exploration" -e yahoo
```

### 3. Utility Commands

```bash
# Translate text via Yahoo
llm4free translate -k "Hola mundo" --to en -e yahoo

# Get suggestions from DuckDuckGo
llm4free suggestions -q "artificial i" -e ddg
```

---

## Related Documentation

- [docs/search.md](search.md) – Technical documentation for the Python Search API.
- [docs/architecture.md](architecture.md) – How the search module is structured.
- [docs/client.md](client.md) – Using the unified `Client`.
