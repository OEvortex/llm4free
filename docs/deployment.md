# Deployment Guide

> **Last updated:** 2026-01-24  
> **Type:** Operations Guide  
> **Audience:** DevOps, system administrators

## Overview

LLM4Free can be deployed in multiple ways:

- **Docker** — Containerized deployment (recommended)
- **Docker Compose** — Multi-service orchestration
- **OpenAI-Compatible API Server** — Local HTTP API
- **Bare Metal** — Direct Python installation

---

## Table of Contents

1. [Docker Setup](#docker-setup)
2. [Docker Compose](#docker-compose)
3. [OpenAI-Compatible API Server](#openai-compatible-api-server)
4. [Environment Configuration](#environment-configuration)
5. [Production Considerations](#production-considerations)
6. [Troubleshooting](#troubleshooting)

---

## Docker Setup

> [!NOTE]
> LLM4Free does **not** publish a pre-built Docker image. Build it yourself with the
> `Dockerfile` in this repo, or serve the server without Docker:
> `pip install "llm4free[api]"` then `llm4free-server`. See [docs/DOCKER.md](DOCKER.md).

### Build and Run

```bash
# Build the image
docker build -t llm4free-api .

# Run the API server (the image's default command)
docker run -p 8000:8000 llm4free-api

# Override the default command, e.g. to inspect the CLI
docker run --rm llm4free-api llm4free --help
```

> [!NOTE]
> The image's `CMD` is `python -m llm4free.server.server`, so a plain
> `docker run llm4free-api` starts the API server. `llm4free-server` is available
> as a console script if you want to override the command explicitly.
> Provider API keys are **not** consumed by the HTTP server, because it only
> registers providers whose `required_auth` flag is `False` (see
> [Configure Providers](#configure-providers)).

### Build Custom Image

```dockerfile
FROM llm4free-api:latest

# Add custom requirements
RUN pip install additional-package

# Set default command
CMD ["llm4free", "--help"]
```

```bash
# Build
docker build -t my-llm4free .

# Run
docker run -it my-llm4free
```

---

## Docker Compose

### Basic Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  llm4free-api:
    build: .
    container_name: llm4free-api
    environment:
      - LLM4FREE_HOST=0.0.0.0
      - LLM4FREE_PORT=8000
      - LLM4FREE_WORKERS=1
      - LLM4FREE_LOG_LEVEL=info
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
    ports:
      - "8000:8000"
```

> [!NOTE]
> The repository already ships a `docker-compose.yml` with `default`,
> `production`, `development`, `nginx`, and `monitoring` profiles — see
> [DOCKER.md](DOCKER.md#service-profiles). The snippet above is a minimal
> equivalent.

### Run Compose Stack

```bash
# Start the server
docker-compose up -d

# View logs
docker-compose logs -f llm4free-api

# Stop services
docker-compose down
```

### With Authentication (Optional)

> [!WARNING]
> The current server implementation does **not** support API key authentication
> (`auth_required = False` in `ServerConfig`). Authentication is disabled by default
> and there is no `--api-key` CLI flag. If you need auth, put a reverse proxy
> (nginx/Caddy/Traefik) in front of the server.

```yaml
services:
  llm4free-api:
    build: .
    command: >
      llm4free-server
      --host 0.0.0.0
      --port 8001
    ports:
      - "8001:8001"
```

---

## OpenAI-Compatible API Server

### What It Does

Runs a FastAPI server that proxies any LLM4Free provider through OpenAI-compatible endpoints.

```
Your App → llm4free-server (OpenAI API) → Any LLM4Free Provider
```

### Start Server

> [!NOTE]
> The server reads configuration from **environment variables** only (prefixed with
> `LLM4FREE_`). It does **not** read `llm4free_config.json`, `llm4free.yaml`, or
> `.env` files directly. Set variables in your shell, `docker run -e`, or
> `docker-compose.yml` `environment:` blocks.

```bash
# Simple start
llm4free-server

# With custom host/port
llm4free-server --host 0.0.0.0 --port 8001

# With debug mode
llm4free-server --debug

# With default provider
llm4free-server --default-provider GROQ
```

### Configure Providers

Providers are discovered at startup from `llm4free/llm/__init__.py`. The server
registers **only providers with `required_auth = False`** — for example
`ChatGPT`, `Gemini`, `Toolbaz`, `AkashGPT`, `IBM`, `GptFree`, `Netwrck`,
`TypliAI`, and `PiAI`.
Providers that need API keys (`Groq`, `OpenRouter`, `TogetherAI`, `DeepInfra`,
`AI4Chat`, `TextPollinations`, `HuggingFace`, etc.) are **not** registered and
cannot be selected through HTTP, regardless of which environment variables you
set.

Use `Provider/Model` identifiers (or a bare model name, which is resolved against
`LLM4FREE_DEFAULT_PROVIDER`):

| Provider | Example model identifier |
|----------|--------------------------|
| `ChatGPT` | `ChatGPT/GPT-6-free` |
| `Gemini` | `Gemini/gemini-3.6-flash` |
| `Toolbaz` | `Toolbaz/toolbaz-v5` |

> [!NOTE]
> There is no `llm4free_config.json` or `llm4free.yaml` file format read by the server.
> All configuration is via environment variables documented in
> [docs/openai-api-server.md](openai-api-server.md) and [docs/DOCKER.md](DOCKER.md).

### Use with OpenAI Client

```python
from openai import OpenAI

# Point to your LLM4Free server
client = OpenAI(
    api_key="unused",  # the server does not authenticate requests
    base_url="http://localhost:8000/v1"
)

# Use exactly like OpenAI
response = client.chat.completions.create(
    model="ChatGPT/GPT-6-free",
    messages=[
        {"role": "user", "content": "Hello"}
    ]
)

print(response.choices[0].message.content)
```

### API Endpoints

#### Chat Completions

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ChatGPT/GPT-6-free",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

#### List Models

```bash
curl http://localhost:8000/v1/models
```

#### Health Check

```bash
curl http://localhost:8000/monitor/health
```

---

## Environment Configuration

### API Keys

The HTTP server only registers no-auth providers, so provider API keys have no
effect there. Keys matter only when you use the Python `Client` or import a
provider class directly. LLM4Free does **not** read keys from environment
variables; pass them explicitly:

```python
from llm4free import Client
from llm4free.llm.Auth.groq import Groq

# One key applied to whichever auth-required provider is selected
client = Client(api_key="gsk_...", drop_auth_providers=False)

# Or configure a single provider directly
groq = Groq(api_key="gsk_...")
```

### Server Environment Variables

Create a `.env` file for the **server** settings:

```bash
# Server Configuration
LLM4FREE_HOST=0.0.0.0
LLM4FREE_PORT=8000
LLM4FREE_DEBUG=false
```

Load with:

```bash
# Shell (the server does not parse .env itself)
set -a
source .env
set +a

# Or in Docker Compose
environment:
  - LLM4FREE_PORT=${LLM4FREE_PORT:-8000}
```

> [!NOTE]
> The server does **not** read `REQUEST_TIMEOUT`, `STREAM_TIMEOUT`, or any
> `python-dotenv`-loaded variables. Only `LLM4FREE_*` prefixed variables (and a few
> bare aliases like `PORT`, `DEBUG`, `BASE_URL`, `DEFAULT_PROVIDER`) are honored.
> See [docs/DOCKER.md](DOCKER.md) for the full list.

### Configuration File

> [!NOTE]
> The server does **not** read `llm4free.yaml`, `llm4free_config.json`, or any
> YAML/JSON configuration file. All configuration is via environment variables.
> This section is kept for reference only.

Create `llm4free.yaml` (not currently read by the server):

```yaml
server:
  host: 0.0.0.0
  port: 8000
  debug: false
  workers: 4
  timeout: 30

providers:
  GROQ:
    api_key: ${GROQ_API_KEY}
    model: llama-3.1-70b-versatile
    timeout: 60
  
  OpenAI:
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
    timeout: 30

logging:
  level: INFO
  format: json
```

---

## Production Considerations

### 1. Security

#### Use HTTPS

```bash
# With self-signed certificate
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem -days 365 -nodes

# Use with nginx reverse proxy
nginx
```

#### Environment Variables

```bash
# Never commit secrets
echo ".env" >> .gitignore

# Use secure secret management
# - Kubernetes Secrets
# - AWS Secrets Manager
# - HashiCorp Vault
# - Docker Secrets
```

#### Rate Limiting

```yaml
# In nginx config
limit_req_zone $binary_remote_addr zone=llm4free:10m rate=10r/s;

server {
    location / {
        limit_req zone=llm4free burst=20 nodelay;
        proxy_pass http://llm4free:8000;
    }
}
```

### 2. Monitoring

#### Health Checks

```bash
# Check if server is running
curl http://localhost:8000/monitor/health

# Inspect the built-in container HEALTHCHECK
docker inspect --format='{{.State.Health.Status}}' llm4free-api
```

> [!NOTE]
> The image already defines a `HEALTHCHECK` that calls `/monitor/health`, so no
> extra `docker run` flag is needed.

> [!NOTE]
> The health endpoint is `/monitor/health` (not `/health`). It returns
> `{"status": "healthy", "service": "llm4free-api", "version": "0.2.0"}`.

#### Logging

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

#### Metrics

> [!NOTE]
> The server does **not** expose a Prometheus `/metrics` endpoint. For metrics,
> rely on your infrastructure's standard monitoring (Docker stats, Kubernetes
> metrics server, or an external sidecar).

### 3. Performance

#### Caching

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_provider_instance(provider_name: str):
    return initialize_provider(provider_name)
```

#### Connection Pooling

```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
```

#### Load Balancing

```yaml
# docker-compose with multiple instances
services:
  llm4free-1:
    build: .
    ports:
      - "8001:8000"

  llm4free-2:
    build: .
    ports:
      - "8002:8000"

  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### 4. Scaling

#### Horizontal Scaling (Kubernetes)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm4free-deployment

spec:
  replicas: 3
  
  selector:
    matchLabels:
      app: llm4free
  
  template:
    metadata:
      labels:
        app: llm4free
    
    spec:
      containers:
      - name: llm4free
        image: llm4free-api:latest
        ports:
        - containerPort: 8000
        
        env:
        - name: GROQ_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm4free-secrets
              key: groq-api-key
        
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

---

## Troubleshooting

### "Connection refused" when accessing API

```bash
# Check if server is running
docker ps | grep llm4free

# Check logs
docker logs llm4free-api

# Verify port is open
netstat -tulpn | grep 8000

# Test locally
curl http://localhost:8000/monitor/health
```

### "API key not found" errors

```bash
# Verify environment variables are set
echo $GROQ_API_KEY
echo $OPENAI_API_KEY

# Check in Docker
docker exec llm4free-api env | grep -i api

# Set in docker-compose
environment:
  - GROQ_API_KEY=${GROQ_API_KEY}
```

### High memory usage

```bash
# Monitor container memory
docker stats llm4free-api

# Limit memory in docker-compose
services:
  llm4free:
    mem_limit: 1g
```

### SSL/TLS certificate errors

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/private.key \
  -out /etc/nginx/ssl/certificate.crt

# Use with proper nginx config
```

---

## Deployment Checklist

- [ ] API keys configured securely
- [ ] HTTPS/SSL enabled
- [ ] Health checks working
- [ ] Logging configured
- [ ] Monitoring in place
- [ ] Backups configured
- [ ] Rate limiting enabled
- [ ] Firewall rules set
- [ ] Documentation updated
- [ ] Test deployment first

---

## See Also

- [Getting Started](getting-started.md)
- [API Reference](api-reference.md)
- [Docker Documentation](DOCKER.md)
- [OpenAI API Server](openai-api-server.md)
