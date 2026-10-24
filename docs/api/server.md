# Server API Reference

## FastAPI Server

`llm4free` ships an OpenAI-compatible HTTP server built with FastAPI.

### Quick Start

```bash
# Install the server extras
pip install "llm4free[api]"

# Start on the default host/port (0.0.0.0:8000)
llm4free-server

# `llm4free-serve` is an alias
llm4free-serve --port 8080
```

The console scripts `llm4free-server` and `llm4free-serve` both point at
`llm4free.server.server:main`. You can also run it as a module:

```bash
python -m llm4free.server.server --port 8080
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/monitor/health` | Health check. |
| GET | `/v1/models` | List registered chat models. |
| GET | `/v1/models/{model}` | Check that a model resolves. |
| GET | `/v1/providers` | List chat providers, models, and parameters. |
| POST | `/v1/chat/completions` | OpenAI-compatible chat completions. |
| POST | `/v1/messages` | Anthropic-compatible messages. |
| GET | `/v1/messages` | List models in Anthropic format. |
| GET | `/v1/TTI/models` | List image models. |
| GET | `/v1/TTI/providers` | List image providers. |
| POST | `/v1/images/generations` | Generate images. |
| GET | `/v1/TTS/models` | List speech models. |
| GET | `/v1/TTS/providers` | List speech providers. |
| POST | `/v1/audio/speech` | Generate speech. |
| GET | `/search` | Unified web search. |
| GET | `/search/provider` | List search engines and categories. |
| GET | `/` | Landing page. |
| GET | `/docs`, `/redoc` | Swagger UI and ReDoc. |

### Model Identifiers

The server resolver is strict. Use `Provider/Model`, for example
`Gemini/gemini-3.6-flash` or `PollinationsAI/flux`. A bare model name is
resolved against `LLM4FREE_DEFAULT_PROVIDER` (default `ChatGPT`). `"auto"`,
fuzzy matching, and failover are **not** available on the server; they are
features of the Python `Client`.

Only providers with `required_auth = False` are registered in the server maps.

## Chat Completions API

**POST** `/v1/chat/completions`

```json
{
    "model": "Gemini/gemini-3.6-flash",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7,
    "max_tokens": 150,
    "stream": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | `Provider/Model` identifier. |
| `messages` | array | Yes | Chat messages. |
| `temperature` | float | No | Sampling temperature (0-2). |
| `top_p` | float | No | Nucleus sampling. |
| `n` | int | No | Number of completions (default 1). |
| `max_tokens` | int | No | Maximum tokens to generate. |
| `presence_penalty` | float | No | Presence penalty (-2 to 2). |
| `frequency_penalty` | float | No | Frequency penalty (-2 to 2). |
| `stop` | string / array | No | Stop sequences. |
| `stream` | boolean | No | Stream server-sent events. |
| `tools` | array | No | OpenAI tool definitions. |
| `tool_choice` | string / object | No | Tool selection hint. |
| `parallel_tool_calls` | boolean | No | Enable parallel tool calls. |

## Anthropic Messages API

**POST** `/v1/messages`

```json
{
    "model": "Gemini/gemini-3.6-flash",
    "max_tokens": 1024,
    "system": "You are helpful.",
    "messages": [
        {"role": "user", "content": "Hello!"}
    ],
    "stream": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | `Provider/Model` identifier. |
| `messages` | array | Yes | Messages. |
| `max_tokens` | int | Yes | Maximum tokens to generate. |
| `system` | string / array | No | System prompt. |
| `temperature` | float | No | Sampling temperature. |
| `top_p` | float | No | Nucleus sampling. |
| `top_k` | int | No | Top-k sampling. |
| `stop_sequences` | array | No | Custom stop sequences. |
| `tools` | array | No | Anthropic tool definitions. |
| `tool_choice` | object | No | Tool selection. |
| `stream` | boolean | No | Stream events. |

## Image Generation

**POST** `/v1/images/generations`

```json
{
    "model": "PollinationsAI/flux",
    "prompt": "A futuristic cityscape at sunset, digital art",
    "n": 1,
    "size": "1024x1024",
    "response_format": "url"
}
```

`model` is required. Optional provider-specific fields include `style`,
`aspect_ratio`, `image_format`, `seed`, and `timeout`.

## Text-to-Speech

**POST** `/v1/audio/speech`

```json
{
    "model": "ParlerTTS/parler-mini-v1",
    "input": "Hello, welcome to LLM4Free!",
    "voice": "alloy",
    "response_format": "mp3",
    "stream": false
}
```

## Web Search

**GET** `/search`

```bash
# Text search
curl "http://localhost:8000/search?q=Python+tutorials&engine=duckduckgo"

# News search
curl "http://localhost:8000/search?q=AI+news&engine=brave&type=news"

# Available engines
curl "http://localhost:8000/search/provider"
```

See [Search API](search.md) for the full parameter list.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM4FREE_PORT` (or `PORT`) | Server port | `8000` |
| `LLM4FREE_HOST` | Bind host | `0.0.0.0` |
| `LLM4FREE_WORKERS` | Worker processes | `1` |
| `LLM4FREE_LOG_LEVEL` | Uvicorn log level | `info` |
| `LLM4FREE_DEFAULT_PROVIDER` (or `DEFAULT_PROVIDER`) | Provider for bare model names | `ChatGPT` |
| `LLM4FREE_BASE_URL` (or `BASE_URL`) | Reported in startup output; does not prefix routes | none |
| `LLM4FREE_DEBUG` (or `DEBUG`) | Debug/reload mode | `false` |
| `LLM4FREE_REQUEST_LOGGING` | Log requests | `true` |
| `LLM4FREE_API_TITLE` | OpenAPI title | `LLM4Free API` |
| `LLM4FREE_API_DESCRIPTION` | OpenAPI description | built-in text |
| `LLM4FREE_API_VERSION` | OpenAPI version | `0.2.0` |
| `LLM4FREE_API_DOCS_URL` | Swagger UI path | `/docs` |
| `LLM4FREE_API_REDOC_URL` | ReDoc path | `/redoc` |
| `LLM4FREE_API_OPENAPI_URL` | OpenAPI schema path | `/openapi.json` |

### Command Line Options

```bash
llm4free-server \
    --port 8080 \
    --host 0.0.0.0 \
    --workers 4 \
    --default-provider ChatGPT \
    --base-url /api/v1 \
    --log-level info \
    --debug
```

> [!NOTE]
> The server does not implement its own authentication or rate limiting; both
> are disabled in `AppConfig` and reported as such at startup. Put it behind a
> reverse proxy if you need those controls.

## Docker Deployment

> [!NOTE]
> LLM4Free does **not** publish a pre-built Docker image. Build it yourself with
> the `Dockerfile` in this repo, or serve without Docker:
> `pip install "llm4free[api]"` then `llm4free-server`.

```bash
# Build and run
docker build -t llm4free-api .
docker run -p 8000:8000 llm4free-api

# With Docker Compose (builds on first run)
docker compose up -d
```

## SDK Usage

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)

response = client.chat.completions.create(
    model="Gemini/gemini-3.6-flash",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### Anthropic Python SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="not-needed",
)

message = client.messages.create(
    model="Gemini/gemini-3.6-flash",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
```
