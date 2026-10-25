# LLM4Free Documentation Hub

> Central entry point to everything LLM4Free.
> Source of truth: the modules inside the repository. Every page below links to a doc that lives in `docs/`.

This hub is organized around the actual modules that live inside the repository, so you can quickly jump from high-level concepts to concrete implementation details.

## Table of Contents

- [Quick Navigation](#quick-navigation)
- [How to Use This Hub](#how-to-use-this-hub)
- [Project Map at a Glance](#project-map-at-a-glance)
- [Recently Added Docs](#recently-added-docs)
- [Contributing to Documentation](#contributing-to-documentation)

---

## Quick Navigation

| Topic | Why it matters | Primary Reference |
|-------|----------------|-------------------|
| Overall architecture | Understand how CLI, server, client, providers, and extras fit together | [docs/architecture.md](architecture.md) |
| Command line tooling | Detailed reference for every `llm4free` CLI command and option | [docs/cli.md](cli.md) |
| Unified Python client | Auto-failover chat & image client backed by `llm4free/client.py` | [docs/client.md](client.md) |
| API reference | Structured entry point into the API docs | [docs/api-reference.md](api-reference.md) |
| Model registry | Enumerate LLM, TTS, and TTI models exposed via `llm4free/models.py` | [docs/models.md](models.md) |
| OpenAI-compatible API server | Deploy FastAPI server that proxies any LLM4Free provider | [docs/openai-api-server.md](openai-api-server.md) |
| Search stack | OpenAI-style `client.search` plus DuckDuckGo/Bing/Yahoo/Brave/Mojeek/Wikipedia/SerpBase/Parallel engines and CLI usage | [docs/search.md](search.md) |
| HTML parser & crawler | Deep dive into `llm4free/scout` | [docs/scout.md](scout.md) |
| Stream sanitizers | Advanced SSE/HTTP stream processing utilities | [docs/sanitize.md](sanitize.md) |
| Decorators & utilities | Retry/timing helpers from `llm4free/AIutel.py` | [docs/decorators.md](decorators.md) |
| Docker & deployment | Images, compose profiles, env vars | [docs/DOCKER.md](DOCKER.md) |
| GGUF tooling | Model conversion helpers (`llm4free/Extra/gguf.py`) | [docs/gguf.md](gguf.md) |
| Inferno local LLMs | Run local servers compatible with LLM4Free providers | [docs/inferno.md](inferno.md) |
| LitPrinter | Debug printing companion shipped with LLM4Free | [docs/litprinter.md](litprinter.md) |
| LitAgent | Advanced User Agent & IP rotation toolkit | [docs/litagent.md](litagent.md) |
| Provider list | Complete list of providers and locations | [docs/api/providers.md](api/providers.md) |

> [!NOTE]
> The search stack previously referenced a `Yep` engine and a `zeroart` toolkit.
> Neither is part of the current codebase. The supported CLI engines are `ddg`
> (also accepted as `duckduckgo`), `bing`, `yahoo`, `brave`, `mojeek`,
> `wikipedia`, `serpbase`, and `parallel` — see [cli.md](cli.md) and
> [search.md](search.md). Weather helpers still live in `llm4free/Extra` but have
> no dedicated doc page.

## How to Use This Hub

1. **Start with the architecture overview** if you are new to the codebase or planning a big change. It explains the flow between public interfaces, search engines, providers, and helper modules.
2. **Jump into topic-specific guides** (CLI, client, server, search, etc.) once you know which layer you want to extend.
3. **Reference module-level docs** (decorators, sanitizer, scout, GGUF, etc.) for implementation details or API signatures.
4. **Use the provider matrix** whenever you need to locate a provider implementation quickly.

## Project Map at a Glance

- `llm4free/cli.py` – `argparse` CLI with Rich-formatted output; commands cover text, images, videos, news, weather, answers, suggestions, translate, and maps across the engines above.
- `llm4free/client.py` – Unified chat, image, and audio client with provider/model resolution and automatic failover.
- `llm4free/server/` – FastAPI-based OpenAI-compatible server (`docs/openai-api-server.md` covers routes, config, env vars).
- `llm4free/search/` – Shared search abstractions (DuckDuckGo, Bing, Yahoo, Brave, Mojeek, Wikipedia, SerpBase, Parallel) plus result formatting helpers.
- `llm4free/llm/` – Chat provider implementations (no-auth plus authenticated under `llm4free/llm/Auth/`), base classes, and response utilities.
- `llm4free/TTI/`, `llm4free/TTS/`, `llm4free/STT/`, `llm4free/AISEARCH/` – Media generation and AI-search providers.
- `llm4free/Extra/` – Auxiliary toolkits like GGUF conversion, weather clients, temp mail, Git/YouTube utilities.
- `docs/` – This folder: each guide is sourced directly from the modules above so it stays true to the code.

## Recently Added Docs

- **Architecture Overview** — visual + textual description of the runtime layers.
- **CLI Reference** — exhaustive explanation of `llm4free` command families.
- **Unified Client Guide** — how to leverage the `Client` failover logic from Python code.
- **Model Registry Guide** — using the `models.llm`, `models.tts`, and `models.tti` helpers.

## Contributing to Documentation

- When you add a feature, update or append the relevant topic in this hub so future contributors can find it.
- If you introduce a brand new area (e.g., a new toolkit under `llm4free/Extra`), create a dedicated doc and list it in the table above.
- Keep examples synchronized with the code (import paths, parameter names, defaults, and behaviors should match the actual modules).

Need something that is not documented yet? Open an issue or PR and link back to this hub so we can keep the map current.
