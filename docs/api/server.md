# Server API Reference

## FastAPI Server

LLM4Free includes an OpenAI-compatible API server that can be started with a single command.

### Quick Start

```bash
# Start the server
llm4free serve

# Or with custom port
llm4free serve --port 8080

# Or with Python
python -m llm4free.server.server
```

### Server Features

- **OpenAI-Compatible API** at `/v1/chat/completions`
- **Anthropic-Compatible API** at `/v1/messages`
- **Image Generation** at `/v1/images/generations`
- **Text-to-Speech** at `/v1/audio/speech`
- **Web Search** at `/search`
- **Model Listing** at `/v1/models`

## Chat Completions API

### Create Chat Completion

**POST** `/v1/chat/completions`

```json
{
    "model": "HeckAI/deepseek/deepseek-v4-flash",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7,
    "max_tokens": 150,
    "stream": false
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID |
| `messages` | array | Yes | Chat messages |
| `temperature` | float | No | Sampling temperature (0-2) |
| `max_tokens` | int | No | Max tokens to generate |
| `top_p` | float | No | Nucleus sampling |
| `stream` | boolean | No | Enable streaming |
| `tools` | array | No | Tool definitions |

## Anthropic Messages API

**POST** `/v1/messages`

```json
{
    "model": "HeckAI/deepseek/deepseek-v4-flash",
    "max_tokens": 1024,
    "system": "You are helpful.",
    "messages": [
        {"role": "user", "content": "Hello!"}
    ],
    "stream": true
}
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model ID |
| `messages` | array | Yes | Messages |
| `max_tokens` | int | Yes | Max tokens to generate |
| `system` | string | No | System prompt |
| `temperature` | float | No | Sampling temperature |
| `tools` | array | No | Tool definitions |
| `stream` | boolean | No | Enable streaming |

## Model Listing

**GET** `/v1/models`

Returns list of available models in OpenAI format.

**GET** `/v1/messages`

Returns list of available models in Anthropic format.

## Web Search

**GET** `/search`

```bash
# Text search
curl "http://localhost:8000/search?q=Python&tutorials&engine=duckduckgo"

# News search
curl "http://localhost:8000/search?q=AI+news&type=news"
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM4FREE_PORT` | Server port | 8000 |
| `LLM4FREE_HOST` | Server host | 0.0.0.0 |
| `LLM4FREE_WORKERS` | Worker processes | 1 |
| `LLM4FREE_DEFAULT_PROVIDER` | Default provider | ChatGPT |
| `LLM4FREE_BASE_URL` | API base path | None |

### Command Line Options

```bash
llm4free serve \
    --port 8080 \
    --host 0.0.0.0 \
    --workers 4 \
    --default-provider ChatGPT \
    --base-url /api/v1 \
    --debug
```

## Docker Deployment

```bash
# Pull and run
docker pull oevortex/llm4free:latest
docker run -p 8000:8000 oevortex/llm4free

# With Docker Compose
docker-compose up -d
```

## SDK Usage

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="HeckAI/deepseek/deepseek-v4-flash",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Anthropic Python SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="not-needed"
)

message = client.messages.create(
    model="HeckAI/deepseek/deepseek-v4-flash",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
```
