# LLM4Free Architecture Overview

> **Last updated:** 2026-07-16
> **Relates to:** `llm4free/cli.py`, `llm4free/client.py`, `llm4free/server/`, `llm4free/search/`, `llm4free/llm/`, `llm4free/Extra/`

LLM4Free bundles multiple user-facing entry points (CLI, Python client, and an OpenAI-compatible API server) on top of a shared set of engines, providers, and utilities. This document maps how these layers interact so you can reason about changes confidently.

## Table of Contents

- [Layered View](#layered-view)
- [Entry Points](#entry-points)
- [Core Modules](#core-modules)
- [Typical Data Flows](#typical-data-flows)
- [When Adding New Functionality](#when-adding-new-functionality)
- [Testing & Debugging Hooks](#testing--debugging-hooks)
- [Related Documents](#related-documents)

---

## Layered View

```mermaid
flowchart TD
    subgraph EntryPoints
        CLI[CLI (llm4free/cli.py)]
        Client[Python Client (llm4free/client.py)]
        Server[OpenAI-Compatible Server (llm4free/server)]
    end

    subgraph Core
        Search[Search Engines (llm4free/search)]
        Providers[Providers (llm4free/llm)]
        Extras[Extras & Toolkits (llm4free/Extra)]
        Utilities[Utilities (sanitize.py, AIutel.py, etc.)]
        Models[Model Registry (llm4free/models.py)]
    end

    CLI --> Search
    CLI --> Providers
    Client --> Providers
    Client --> Extras
    Client --> Models
    Server --> Providers
    Server --> Utilities
    Search --> Providers
    Extras --> Providers
```

- **Entry Points** convert user intent (commands/API calls) into provider requests.
- **Core Modules** encapsulate the heavy lifting: crawling websites, calling remote LLMs, handling audio/image generation, sanitizing streams, and enumerating models.

---

## Entry Points

### Command Line Interface (`llm4free/cli.py`)

- Built on `Rich` with separate command groups for DuckDuckGo, Yep, Bing, Yahoo, and weather utilities.
- Uses `_print_data` / `_print_weather` helpers to keep terminal output consistent.
- Relies on the same search/provider classes exported in `llm4free/__init__.py`, so CLI behavior matches the Python API.

### Unified Python Client (`llm4free/client.py`)

> [!NOTE]
> **The Client is the primary Python entry point.** For almost all use cases it should be the first thing you reach for — it sits *above* the search, provider, and extras layers and handles model resolution + failover for you, so you rarely need to import a provider class directly.

- Provides auto-failover chat, image, and audio APIs through `Client.chat.completions.create()`, `Client.images.generate()` (alias `Client.images.create()`), and `Client.audio.speech.create()`.
- Dynamically discovers OpenAI-compatible providers (`llm4free.llm`), TTI providers (`llm4free.TTI`), and TTS providers (`llm4free.TTS`), caches instances, and performs fuzzy model resolution.
- Accepts three `model` specifications — `"auto"` (pick any working provider/model), `"ProviderName/ModelName"` (force a specific provider), or a bare model name (fuzzy-matched) — which are identical to what the server accepts over HTTP.
- Exposes runtime provider discovery helpers (`Client.get_chat_providers()`, `Client.get_free_chat_providers()`, `Client.get_image_providers()`, `Client.get_tts_providers()`) and can start the OpenAI-compatible server itself via the module-level `run_api()` / `start_server()` helpers.
- Shares provider cache with the server, so runtime cost of imports stays low.

### OpenAI-Compatible Server (`llm4free/server/`)

- FastAPI app that exposes `/v1/*` routes mirroring OpenAI's schema.
- Uses `providers.py` to map model names like `ProviderName/model-id` back to actual provider classes.
- Pulls configuration from `config.py` plus environment variables documented in `docs/openai-api-server.md` and `docs/DOCKER.md`.

---

## Core Modules

### Search Stack (`llm4free/search/`)

- Houses protocol-specific engines (see `llm4free/search/engines/*`) plus shared HTTP client and result serializers.
- DuckDuckGo/Yep/Bing/Yahoo commands import from here, so adding new CLI options usually starts with an engine update.

### Providers (`llm4free/llm/`)

- Normal providers and OpenAI-compatible wrappers live together under `llm4free/llm`, with authenticated providers in the `llm4free/llm/Auth/` subpackage.
- Specialty directories at the package root: `TTI`, `TTS`, `STT`, `AISEARCH`, and `Provider/UNFINISHED` (providers whose upstreams have gone away and are no longer part of the public API).
- The matrix in `Provider.md` maps every provider to its implementation file.

> [!NOTE]
> The legacy `llm4free/Provider/OPENAI` directory no longer exists. OpenAI-compatible chat providers now live in `llm4free/llm` (and authenticated ones in `llm4free/llm/Auth`).

### Extras (`llm4free/Extra/`)

- Optional toolkits packaged with LLM4Free (GGUF converter, weather clients, temp mail, YT toolkit, Git API helper, etc.).
- Exported through `llm4free/Extra/__init__.py` so they become part of the public API when you `import llm4free`.

### Utilities

- `llm4free/sanitize.py` – SSE/stream sanitization for server + client streaming paths.
- `llm4free/AIutel.py` – Decorators for retry/timing (documented in `docs/decorators.md`).
- `llm4free/update_checker.py` – Optional PyPI update notifier executed in `llm4free/__init__.py`.

### Models Registry (`llm4free/models.py`)

- Enumerates LLM, TTS, and TTI models exposed by providers.
- Used by documentation examples (README, docs/models.md) and can power custom tooling (e.g., provider dashboards).

---

## Typical Data Flows

1. **CLI -> Search Engine -> Provider**
   - `llm4free images -k "python"` -> `DuckDuckGoSearch.images()` (HTTP scraping) -> results printed via `_print_data`.
2. **Client -> Provider Failover**
   - `Client().chat.completions.create(model="gpt-4o")` -> resolves provider & model -> tries preferred provider -> falls back through fuzzily-matched providers if necessary.
3. **Server -> Provider -> sanitize_stream**
   - `/v1/chat/completions` request hits FastAPI -> provider resolved -> streaming responses run through `sanitize_stream()` before being sent to clients.
4. **Extras -> Providers**
   - GGUF converter uses huggingface + llama.cpp builders and is fully independent, but still exported to users alongside the main modules.

---

## When Adding New Functionality

| Task | Touch Points |
|------|--------------|
| Add a CLI command | `llm4free/cli.py` + corresponding engine/provider + update `docs/cli.md` |
| Add a provider | Implement in `llm4free/llm/` (or `llm4free/llm/Auth/` for authenticated), update `Provider.md`, consider `models.py` exposure |
| Add server capability | Update `llm4free/server/*`, document in `docs/openai-api-server.md`, ensure CLI/Client can hit the new route if needed |
| Extend Extras | Implement under `llm4free/Extra/`, export in `__init__.py`, add documentation entry under `docs/README.md` |
| Add new registry info | Update `llm4free/models.py` or referencing docs (`docs/models.md`) |

---

## Testing & Debugging Hooks

- CLI commands can be run locally with `uv run llm4free ...` to ensure option parsing remains correct.
- Client failover prints last provider when `print_provider_info=True` – useful when debugging provider availability.
- The server exposes `/monitor/health` to monitor deployments.
- `sanitize_stream` and decorators have dedicated docs you can reference when debugging streaming issues or retries.

---

## Related Documents

- [docs/cli.md](cli.md) – exhaustive CLI reference.
- [docs/client.md](client.md) – deep dive into the unified client.
- [docs/models.md](models.md) – using the model registry helpers.
- [docs/openai-api-server.md](openai-api-server.md) – server configuration & endpoints.
- [Provider.md](../Provider.md) – provider matrix you can cross-reference while navigating the codebase.
