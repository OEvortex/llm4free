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

# Run container (interactive mode)
docker run -it llm4free-api

# With API key mounted
docker run -it \
  -e OPENAI_API_KEY="your-api-key" \
  llm4free-api

# With port forwarding (for API server)
docker run -it \
  -p 8000:8000 \
  -e OPENAI_API_KEY="your-api-key" \
  llm4free-api \
  llm4free-server
```

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
  llm4free:
    build: .
    container_name: llm4free-app
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GROQ_API_KEY=${GROQ_API_KEY}
    volumes:
      - ./data:/app/data
    ports:
      - "8000:8000"
    stdin_open: true
    tty: true

  llm4free-server:
    build: .
    container_name: llm4free-api
    command: llm4free-server --host 0.0.0.0 --port 8001
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GROQ_API_KEY=${GROQ_API_KEY}
    ports:
      - "8001:8001"
    depends_on:
      - llm4free
```

### Run Compose Stack

```bash
# Create .env file with your API keys
cat > .env << EOF
OPENAI_API_KEY=your-api-key-here
GROQ_API_KEY=your-groq-key-here
EOF

# Start services
docker-compose up -d

# View logs
docker-compose logs -f llm4free-server

# Stop services
docker-compose down
```

### With Authentication (Optional)

> [!WARNING]
> The current server implementation does **not** support API key authentication
> (`auth_required = False` in `ServerConfig`). Authentication is disabled by default
> and there is no `--api-key` CLI flag. This section is kept for reference; if you
> need auth, put a reverse proxy (nginx/Caddy/Traefik) in front of the server.

```yaml
services:
  llm4free-server:
    build: .
    command: >
      llm4free-server
      --host 0.0.0.0
      --port 8001
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
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

Providers are discovered dynamically at startup. Set API keys as environment variables:

```bash
export OPENAI_API_KEY="sk-your-openai-key"
export GROQ_API_KEY="gsk_your-groq-key"
export COHERE_API_KEY="co_your-cohere-key"
export GEMINI_API_KEY="your-gemini-key"
```

> [!NOTE]
> There is no `llm4free_config.json` or `llm4free.yaml` file format read by the server.
> All configuration is via environment variables documented in
> [docs/openai-api-server.md](openai-api-server.md) and [docs/DOCKER.md](DOCKER.md).

### Use with OpenAI Client

```python
from openai import OpenAI

# Point to your LLM4Free server
client = OpenAI(
    api_key="any-key-or-gsk_...",
    base_url="http://localhost:8000/v1"
)

# Use exactly like OpenAI
response = client.chat.completions.create(
    model="GROQ",
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
  -H "Authorization: Bearer YOUR-API-KEY" \
  -d '{
    "model": "GROQ",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

#### List Models

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer YOUR-API-KEY"
```

#### Health Check

```bash
curl http://localhost:8000/monitor/health
```

---

## Environment Configuration

### API Keys

Set environment variables:

```bash
# Linux/macOS
export OPENAI_API_KEY="sk-..."
export GROQ_API_KEY="gsk_..."
export COHERE_API_KEY="..."

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
$env:GROQ_API_KEY = "gsk_..."

# Windows CMD
set OPENAI_API_KEY=sk-...
```

### Using .env File

Create `.env`:

```bash
# AI Provider Keys
OPENAI_API_KEY=sk-your-openai-key
GROQ_API_KEY=gsk_your-groq-key
COHERE_API_KEY=co_your-cohere-key
GEMINI_API_KEY=your-gemini-key

# Server Configuration
LLM4FREE_HOST=0.0.0.0
LLM4FREE_PORT=8000
LLM4FREE_DEBUG=false
```

Load with:

```bash
# Shell
set -a
source .env
set +a

# Or in Docker Compose
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - LLM4FREE_PORT=${LLM4FREE_PORT:-8000}
```

> [!NOTE]
> The server does **not** read `REQUEST_TIMEOUT`, `STREAM_TIMEOUT`, or any
> `python-dotenv`-loaded variables. Only `LLM4FREE_*` prefixed variables (and a few
> bare aliases like `PORT`, `DEBUG`, `BASE_URL`) are honored. See
> [docs/DOCKER.md](DOCKER.md) for the full list.

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

# In Docker
docker run --healthcheck=CMD curl -f http://localhost:8000/monitor/health
```

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
        build: .
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
