# Docker Setup for LLM4Free

> [!IMPORTANT]
> LLM4Free does **not** publish a pre-built Docker image on Docker Hub. The
> `Dockerfile` in this repository builds the image from source at `docker build`
> time (it installs `llm4free[api]` from PyPI/git during the build). You must build
> it yourself, or serve the server without Docker:

```bash
# Serve without Docker
pip install "llm4free[api]"
llm4free-server --port 8000

# Or with uv
uv pip install "llm4free[api]"
uv run llm4free-server
```

This guide covers running the LLM4Free OpenAI-compatible API server in Docker. The image is built from the repository `Dockerfile` (a multi-stage build) and configured through the `docker-compose.yml` profiles. The server runs as a non-root user and exposes a health check at `/monitor/health`.

> [!NOTE]
> All environment variables below are read by [`llm4free/server/server.py`](../llm4free/server/server.py) and [`llm4free/server/config.py`](../llm4free/server/config.py), except the two marked "not read". Variables not read by the server (even if referenced in older docs) are listed separately and are **not** currently honored.

> [!NOTE]
> The server uses its own strict model resolver, which is **not** the Python `Client` resolver. Send `model="Provider/Model"` (e.g. `model="Gemini/gemini-3.6-flash"`) or a bare model name (resolved against `LLM4FREE_DEFAULT_PROVIDER`). `model="auto"`, fuzzy matching, and failover are `Client`-only.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Service Profiles](#service-profiles)
- [Health Checks](#health-checks)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Build and Run

```bash
# Build the image
docker build -t llm4free-api .

# Run the container (default port 8000)
docker run -p 8000:8000 llm4free-api

# Run with a custom port (e.g., 7860)
docker run -p 7860:7860 -e LLM4FREE_PORT=7860 llm4free-api

# Run with a MongoDB-less JSON data directory (already the default)
docker run -p 8000:8000 -e LLM4FREE_DATA_DIR=/app/data llm4free-api
```

### Using Docker Compose

```bash
# Basic setup (default profile)
docker-compose up llm4free-api

# With custom port
LLM4FREE_PORT=7860 docker-compose up llm4free-api

# Production setup with Gunicorn (4 workers)
docker-compose --profile production up llm4free-api-production

# Development setup with hot reload
docker-compose --profile development up llm4free-api-dev
```

> [!TIP]
> The `docker-compose.no-auth.yml` file is an *override* for development/demo mode. In practice the server already defaults to **no authentication** (`auth_required = False` in `ServerConfig`), so the override mainly changes log level and debug flags. Compose it with:
> ```bash
> docker-compose -f docker-compose.yml -f docker-compose.no-auth.yml up llm4free-api
> ```

---

## Configuration

### Environment Variables

The server reads the following variables at runtime. Where a value is shown as "from ServerConfig", it is the hardcoded default in [`llm4free/server/config.py`](../llm4free/server/config.py).

#### Core Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM4FREE_HOST` | `0.0.0.0` | Server bind host |
| `LLM4FREE_PORT` | `8000` | Server port (fallback: `PORT`) |
| `LLM4FREE_WORKERS` | `1` | Number of worker processes |
| `LLM4FREE_LOG_LEVEL` | `info` | Log level: `debug`, `info`, `warning`, `error`, `critical` |
| `LLM4FREE_DEBUG` | `false` | Enable debug mode (fallback: `DEBUG`) |
| `LLM4FREE_REQUEST_LOGGING` | `true` | Enable request logging |
| `LLM4FREE_DATA_DIR` | `/app/data` | Docker volume path (not read by the server; no persistence code uses it) |
| `LLM4FREE_CORS_ORIGINS` | `*` | Set in the image (not read; CORS middleware hardcodes `*`) |
| `LLM4FREE_DEFAULT_PROVIDER` | `ChatGPT` | Default LLM provider (fallback: `DEFAULT_PROVIDER`) |
| `LLM4FREE_BASE_URL` | (none) | Base URL for the API (fallback: `BASE_URL`) |

#### FastAPI Metadata

| Variable | Default |
|----------|---------|
| `LLM4FREE_API_TITLE` | `LLM4Free API` / `LLM4Free OpenAI API` |
| `LLM4FREE_API_DESCRIPTION` | `OpenAI API compatible interface for various LLM providers` |
| `LLM4FREE_API_VERSION` | `0.2.0` |
| `LLM4FREE_API_DOCS_URL` | `/docs` |
| `LLM4FREE_API_REDOC_URL` | `/redoc` |
| `LLM4FREE_API_OPENAPI_URL` | `/openapi.json` |

#### Legacy Variables (fallbacks)

For backward compatibility, the following legacy variables are also honored when the `LLM4FREE_*` equivalent is not set:

- `PORT` → `LLM4FREE_PORT`
- `DEBUG` → `LLM4FREE_DEBUG`
- `DEFAULT_PROVIDER` → `LLM4FREE_DEFAULT_PROVIDER`
- `BASE_URL` → `LLM4FREE_BASE_URL`

> [!WARNING]
> The following variables appear in **older** documentation but are **not** read by the current server implementation and have **no effect**:
> - `LLM4FREE_NO_AUTH`
> - `LLM4FREE_NO_RATE_LIMIT`
> - `LLM4FREE_API_KEY`
> - `MONGODB_URL`
>
> The server ships with authentication disabled by default (`auth_required = False`) and does not implement rate limiting or MongoDB persistence in this version. The `docker-compose.no-auth.yml` override notes this directly in its comments. Rely on the variables in the tables above.

---

## Service Profiles

The `docker-compose.yml` defines these profiles:

- **default** — Basic API server (single Uvicorn worker, no auth).
- **production** — Gunicorn with 4 workers and `warning` log level.
- **development** — Uvicorn with hot reload and `debug` logging.
- **nginx** — Optional reverse proxy (requires your own `nginx.conf`).
- **monitoring** — Optional Prometheus monitoring (requires your own `prometheus.yml`).

> [!NOTE]
> The Docker image does **not** include a MongoDB service profile. The
> `LLM4FREE_DATA_DIR` volume is mounted, but the current server has no
> persistence layer that reads or writes it.

---

## Health Checks

The container includes a `HEALTHCHECK` that calls `/monitor/health`:

```bash
curl -f http://localhost:8000/monitor/health
```

The health endpoint is defined in [`llm4free/server/routes.py`](../llm4free/server/routes.py) and returns a `200 OK` when the server is up.

---

## Security

- Runs as a non-root user (`llm4free:llm4free`)
- Minimal runtime dependencies (Python 3.11-slim)
- Security-hardened container settings (`no-new-privileges`)
- Writable, volume-mounted `/app/logs` and `/app/data` directories
- CORS is currently hardcoded to allow all origins. `LLM4FREE_CORS_ORIGINS` is
  set in the image but is **not** read by the server, so it cannot restrict origins.

> [!WARNING]
> Because authentication is disabled by default, do **not** expose the server to untrusted networks without adding your own auth/reverse-proxy layer.

---

## Troubleshooting

### Check container status

```bash
docker ps
```

### View logs

```bash
docker logs llm4free-api
# or with compose
docker-compose logs llm4free-api
```

### Test the health endpoint

```bash
curl -f http://localhost:8000/monitor/health
```

### Access the container shell

```bash
docker exec -it llm4free-api /bin/sh
```

> [!NOTE]
> There is no `Makefile` in this repository, so `make`-based commands from older docs are not available. Use the `docker` / `docker-compose` commands shown above.
