# HTTP Client

LLM4Free ships its own HTTP client — `llm4free.browser_requests._http` — so that
providers, search engines, and the crawler all talk to the network through **one
small, predictable surface** instead of three third‑party libraries.

It is a **zero‑dependency, httpx‑shaped client built on the Python standard
library**, with an *optional* browser‑fingerprinting backend for the sites that
actually need it.

```python
from llm4free.browser_requests._http import Client

with Client(base_url="https://api.example.com", timeout=(5, 30)) as client:
    resp = client.post("/v1/chat", json={"message": "hello"})
    resp.raise_for_status()
    print(resp.status_code, resp.json())
```

---

## Table of contents

- [Why it exists](#why-it-exists)
- [Install](#install)
- [Design](#design)
- [Quick start](#quick-start)
- [Requests](#requests)
- [Responses](#responses)
- [Sessions & connection pooling](#sessions--connection-pooling)
- [Streaming & Server-Sent Events](#streaming--server-sent-events)
- [Authentication](#authentication)
- [Proxies, `NO_PROXY` and mounts](#proxies-no_proxy-and-mounts)
- [TLS: verification, CA bundles and client certs](#tls-verification-ca-bundles-and-client-certs)
- [HTTP/2](#http2)
- [Browser impersonation](#browser-impersonation)
- [Event hooks](#event-hooks)
- [Exceptions](#exceptions)
- [Async client](#async-client)
- [Compatibility façade (`compat`)](#compatibility-facade-compat)
- [Migrating from curl_cffi / requests / httpx](#migrating-from-curl_cffi--requests--httpx)
- [Backend matrix](#backend-matrix)
- [Limitations](#limitations)

---

## Why it exists

Before this client, every outbound call fanned through **three** libraries:
`curl_cffi` (which drags in a ~24 MB `libcurl-impersonate` native binary),
`requests`, and `httpx`. Most of that traffic — plain OpenAI‑style API calls to
providers — never needed browser fingerprinting at all.

The new client:

- **Removes `curl_cffi`, `requests`, and `httpx` as dependencies.** Plain HTTP
  runs on `socket`/`ssl`/`http` from the standard library only.
- **Confines fingerprinting to one optional seam.** Browser TLS/JA3 is only
  engaged when you pass `impersonate=...` or `http2=True`, backed by the
  optional [`primp`](https://pypi.org/project/primp/) extra.
- **Keeps a single API to teach.** Every provider, search engine, and the Scout
  crawler now import the same client (directly, or through the
  [`compat`](#compatibility-facade-compat) façade).

> [!NOTE]
> The goal is **dependency weight and control**, not raw throughput. A
> pure‑Python HTTP/1.1 stack is not faster than curl's C path; on ordinary API
> calls the win is a smaller install and one consistent surface.

## Install

Nothing extra is required for normal use — the core client is pure stdlib.

```bash
# Core package (stdlib HTTP)
pip install -U llm4free

# Add real browser TLS/JA3 + HTTP/2 fingerprinting
pip install -U "llm4free[impersonate]"     # pulls in primp
```

```bash
uv add llm4free
uv add "llm4free[impersonate]"             # optional fingerprinting backend
```

Without the extra, `impersonate=`/`http2=` requests **degrade gracefully** to the
stdlib engine (ordered browser headers over HTTP/1.1) instead of raising — see
[Browser impersonation](#browser-impersonation).

## Design

```
llm4free/browser_requests/_http/
├── client.py         # Client (sync) + module-level get/post/... helpers
├── async_client.py   # AsyncClient + AsyncResponse
├── models.py         # Headers, Cookies, Response (history, links, iter_*)
├── auth.py           # BasicAuth, BearerAuth, DigestAuth, resolve_auth
├── netconfig.py      # NO_PROXY, env proxies, mounts, netrc
├── urls.py           # URL join + query-param encoding
├── multipart.py      # multipart/form-data encoder
├── sse.py            # text/event-stream parser
├── compat.py         # requests / curl_cffi.requests drop-in façade
├── exceptions.py     # HTTPLLError hierarchy + curl/requests aliases
└── transport/
    ├── base.py         # Transport protocol, RequestSpec, TLS context builder
    ├── std_sync.py     # stdlib HTTP/1.1 + keep-alive connection pool
    ├── std_async.py    # async wrapper (blocking I/O on the executor)
    ├── proxy.py        # HTTP CONNECT tunnel + SOCKS5 handshake (stdlib)
    ├── browser_profiles.py     # ordered-header engine (no primp needed)
    └── impersonation.py        # optional primp backend + plain HTTP/2
```

The request body (`json=` / `data=` / `files=`) is always serialized to bytes by
the client layer **before** it reaches a transport, so every backend — stdlib or
primp — sees the same prepared request and the feature surface is uniform.

## Quick start

=== "Sync"

    ```python
    from llm4free.browser_requests._http import Client

    with Client(headers={"Accept": "application/json"}) as client:
        r = client.get("/search", params={"q": "python"})
        print(r.status_code, r.json())
    ```

=== "Async"

    ```python
    from llm4free.browser_requests._http import AsyncClient

    async with AsyncClient() as client:
        r = await client.get("https://api.github.com/events")
        print(r.status_code)
        print(await r.ajson())
    ```

=== "Module helpers"

    ```python
    from llm4free.browser_requests._http import get, post

    r = get("https://example.com", params={"a": 1})
    r = post("https://example.com", json={"hello": "world"})
    ```

    Each helper opens a short‑lived `Client` for you. For cookie/keep‑alive reuse,
    use a `Client` instance directly.

## Requests

`Client.request(method, url, **options)` — and the verb shortcuts
(`get/post/put/patch/delete/head/options`) — accept:

| Option | Type | Meaning |
|---|---|---|
| `params` | `dict`/`list`/`tuple` | Query string. `None` values skipped; list/tuple values repeat the key (`a=1&a=2`); `bool` → `true`/`false`. |
| `json` | `Any` | JSON body (sets `Content-Type: application/json`). |
| `data` | `dict`/`str`/`bytes`/pairs | Form‑urlencoded or raw body. |
| `files` | `dict`/list | `multipart/form-data` upload; combine with `data` for extra fields. |
| `headers` | `dict`/`Headers` | Merged over the session headers. |
| `cookies` | `dict` | Sent with this request **and** merged into the jar. |
| `timeout` | `float` or `(connect, read)` | Per‑request override. |
| `verify` | `bool`/`str`/`PathLike`/`SSLContext` | TLS verification (see [TLS](#tls-verification-ca-bundles-and-client-certs)). |
| `cert` | `str`/`PathLike`/`tuple` | Client certificate (mTLS). |
| `allow_redirects` | `bool` | Follow 3xx (default `True`). |
| `stream` | `bool` | Return lazily‑read content (see [Streaming](#streaming--server-sent-events)). |
| `proxies` | `dict`/`str` | Per‑request proxy override. |
| `auth` | `tuple`/`AuthBase`/callable | Credentials for this request. |
| `impersonate` | `str` | Route this call through the impersonation backend. |

`Client()` also accepts the same defaults up front (`base_url`, `headers`,
`cookies`, `timeout`, `verify`, `cert`, `proxy`, `max_redirects`, `impersonate`,
`http2`, `trust_env`, `auth`, `event_hooks`), plus `backend` and an injected
`transport`.

### Redirects

Redirects are followed by the client layer, with full
[history](#responses). Method and body are rewritten exactly like `httpx`/`requests`
(POST → GET on 301/302/303; body and content headers stripped). `max_redirects`
(default 20) raises `TooManyRedirects` past the limit.

## Responses

`Response` mirrors both `httpx` and the attributes previously read off
`curl_cffi` responses, so migration is mostly an import swap.

| Member | Description |
|---|---|
| `status_code` / `reason` | HTTP status and reason phrase. |
| `ok` | `True` for 2xx/3xx. |
| `headers` | Case‑insensitive, multi‑value `Headers`. |
| `cookies` | Jar of `Set‑Cookie` values from this response. |
| `text` | Decoded body (charset‑aware). |
| `content` | Raw `bytes`. |
| `json()` | Parsed JSON body. |
| `url` | Final URL after redirects. |
| `history` | `list[Response]` of intermediate redirect hops (oldest first). |
| `links` | Parsed `Link` header → `{rel: {"url": ..., ...}}` (RFC 5988). |
| `raise_for_status()` | Raises `HTTPStatusError` for 4xx/5xx. |
| `iter_bytes(chunk_size=None)` | Yield body chunks; `chunk_size=None` yields the whole buffered body / natural stream chunks. |
| `iter_content(chunk_size, decode_unicode=False)` | `requests`‑compatible chunk iterator. |
| `iter_lines(decode_unicode=...)` | `requests`‑compatible line iterator (str by default; bytes with `decode_unicode=False`). |
| `iter_sse()` | Yields [`ServerSentEvent`](#streaming--server-sent-events). |
| `close()` | Release the socket / return it to the pool. |

```python
r = client.get("/items", params={"page": 2})
for rel in ("next", "last"):
    if rel in r.links:
        print(rel, r.links[rel]["url"])

print([h.status_code for h in r.history])   # e.g. [302, 302]
```

## Sessions & connection pooling

A `Client` is a session: it persists cookies and headers across calls and — on
the stdlib backend — **reuses keep‑alive connections**. Connections are pooled per
`(origin, proxy, TLS settings)`.

```python
with Client() as c:
    c.get("https://api.example.com/a")   # opens a socket …
    c.get("https://api.example.com/b")   # … reuses it (same origin)
```

A pooled socket that the peer closed while idle is transparently re‑established —
but **only if the failure happens before the request hits the wire**, so a POST is
never accidentally submitted twice. Streaming responses are not pooled; neither
are keep‑alive‑unsafe frames. Only fully‑read, non‑stream responses are returned
to the pool, so there is no cross‑request data bleed.

> [!TIP]
> Pooling is enabled by default (`pool=True`, up to 10 sockets). Pass a custom
> transport to change it:
> `Client(transport=SyncStdTransport(pool=False))`.

## Streaming & Server-Sent Events

Use the `stream()` context manager; the body is read lazily.

```python
with client.stream("GET", "/big") as r:
    for chunk in r.iter_bytes(chunk_size=8192):
        handle(chunk)
```

For `text/event-stream` (used heavily by streaming LLM providers):

```python
with client.stream("GET", "/chat/stream") as r:
    for ev in r.iter_sse():
        if ev.data == "[DONE]":
            break
        print(ev.event, ev.id, ev.data)
```

`ServerSentEvent` exposes `event`, `data`, `id`, and `retry`. The async client
provides `aiter_bytes`, `aiter_lines`, and `aiter_sse`.

## Authentication

`auth=` accepts a `(username, password)` tuple, an auth object, or any callable
`(Headers) -> Headers`.

```python
from llm4free.browser_requests._http.auth import BasicAuth, BearerAuth, DigestAuth

client.get(url, auth=("user", "pw"))            # Basic
client.get(url, auth=BasicAuth("user", "pw"))   # Basic
client.get(url, auth=BearerAuth("token"))        # Bearer
client.get(url, auth=lambda h: h.merged({"X-Key": "abc"}))  # callable

# Digest — challenge/response, retried once after a 401 automatically
client.get(url, auth=DigestAuth("user", "pw"))
```

`DigestAuth` implements RFC 7616 (MD5, SHA‑256, SHA‑512‑256 and the `-sess`
variants). The client sends the first request, reads `WWW-Authenticate: Digest`,
computes the response, and retries — transparently.

You can also set `auth=` on the `Client` to apply it to every request. With
`trust_env=True` (default) and no other credentials, the client falls back to
**netrc** (`~/.netrc`, or `$NETRC`) for the target host.

## Proxies, `NO_PROXY` and mounts

A proxy is resolved per request with this precedence — **highest first**:

1. the per‑request `proxies=` / `proxy=` argument;
2. the longest‑matching `mount()` prefix;
3. the client‑level `proxy=`;
4. the environment (`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`) — only when
   `trust_env=True` and the host is not matched by `NO_PROXY`.

```python
# Single proxy (http, https, or socks5)
client = Client(proxy="socks5://user:pass@127.0.0.1:1080")

# Per-prefix mounts
client.mount("https://api.example.com", "http://corp-proxy:3128")

# Per-request override
client.get(url, proxies={"https": "http://other:8888"})
```

`NO_PROXY` (and lowercase `no_proxy`) supports `*`, exact hosts, and
dot‑suffixes (`.example.com` matches `api.example.com`). Both HTTP CONNECT
tunnels (for `https` origins) and the SOCKS5 handshake are implemented in pure
stdlib (`transport/proxy.py`).

## TLS: verification, CA bundles and client certs

`verify` accepts several forms, matching `requests`:

```python
Client(verify=False)                          # skip verification (opt-in only!)
Client(verify="/etc/ssl/ca-bundle.pem")      # custom CA file
Client(verify="/etc/ssl/certs")              # CA directory (capath)
Client(verify=ssl.create_default_context())  # a pre-built context
```

Client certificates (mTLS) via `cert`:

```python
Client(cert="/path/client.pem")
Client(cert=("/path/client.pem", "/path/client.key"))
Client(cert=("/path/combined.pem", None, "keyfile-password"))
```

> [!WARNING]
> `verify=False` disables certificate **and** hostname checking. It is never the
> default and should only be used deliberately for local/internal endpoints.

## HTTP/2

For plain HTTP/2 without a browser profile:

```python
Client(http2=True)
```

This selects the primp HTTP/2 backend. If `primp` is not installed, it silently
falls back to the stdlib HTTP/1.1 transport. When `impersonate=` is set, HTTP/2 is
already part of the real browser fingerprint, so `http2` is unnecessary.

## Browser impersonation

Some sites (Cloudflare, Bing, DuckDuckGo HTML, Perplexity, …) gate on the **TLS
ClientHello (JA3)** or the **HTTP/2 SETTINGS frame** — not just headers. Pure
stdlib Python *cannot* fake these (OpenSSL's ClientHello is fixed; no GREASE /
extension‑order / SETTINGS control). That capability is provided by the optional
`primp` backend, reached through a single seam.

```python
# Real browser TLS/JA3 + HTTP/2 fingerprint (requires llm4free[impersonate])
client = Client(impersonate="chrome124")
```

`transport/impersonation.py::get_sync_transport(impersonate, backend=, http2=)`
is the **only** place that chooses an engine. Behavior:

- **`primp` installed** → real fingerprints. curl‑style names are mapped to the
  nearest supported primp target (e.g. `chrome124` → a supported `chrome_14x`),
  with the OS inferred from `_android`/`_ios` suffixes; `safari` desktop → `macos`.
- **`primp` missing or broken** → transparently degrades to the pure‑stdlib
  **ordered‑header engine** (`transport/browser_profiles.py`), which defeats
  header‑set / header‑order checks but not JA3. It never raises.
- **`backend="stdlib"`** → always the ordered‑header engine, regardless of primp.

```python
from llm4free.browser_requests._http.transport import get_sync_transport

get_sync_transport(None)                       # stdlib HTTP/1.1, pooled
get_sync_transport("chrome124")                # primp (or ordered-header fallback)
get_sync_transport("chrome124", backend="stdlib")  # force ordered-header engine
get_sync_transport(None, http2=True)           # primp plain HTTP/2
```

Known target aliases and their concrete resolutions live in
`transport/browser_profiles.py` (`KNOWN_TARGETS`, `normalize_browser_type`).

## Event hooks

Register callables fired around each request/response (like `httpx`):

```python
def on_request(request):
    print("→", request.method, request.url)

def on_response(response):
    print("←", response.status_code)

client = Client(event_hooks={"request": [on_request], "response": [on_response]})
```

Response hooks fire on the final response (after redirects).

## Exceptions

Everything derives from `HTTPLLError`, and the names map onto the LLM4Free error
types used across providers (`LLM4FreeE` / `TimeoutE` / `RatelimitE`).

```
HTTPLLError
├── HTTPError
│   └── HTTPStatusError          # raise_for_status()
├── ConnectError                 # DNS / connection refused
├── ReadError
├── ProxyError
├── SSLError
├── TimeoutError
│   └── ReadTimeout
└── TooManyRedirects
```

For drop‑in compatibility, `CurlError`, `RequestException`, and `RequestsError`
are aliases of the same base, and `compat.exceptions` mirrors
`curl_cffi.requests.exceptions`.

```python
from llm4free.browser_requests._http import exceptions as http

try:
    client.get(url).raise_for_status()
except http.TimeoutError:
    ...
except http.HTTPStatusError as ex:
    print(ex.response.status_code)
except http.ConnectError:
    ...
```

## Async client

`AsyncClient` has the same surface as `Client` and a genuine `await` API. It
reuses the shared framing implementation with blocking I/O on the executor, and
supports `impersonate=`, `http2=`, `auth=`, `proxies=`, `mounts`, `cert`,
`event_hooks`, and `history`.

```python
from llm4free.browser_requests._http import AsyncClient

async with AsyncClient(timeout=30) as client:
    r = await client.get(url, params={"q": "python"})
    text = await r.atext()
    async for ev in client.stream("GET", "/sse"):
        async for event in ev.aiter_sse():
            print(event.data)
```

## Compatibility façade (`compat`)

`llm4free.browser_requests._http.compat` reproduces the `requests` /
`curl_cffi.requests` surface — `Session`, `AsyncSession`, module‑level
`get/post/request`, `impersonate=`, `proxies=`, `stream=True`,
`iter_content()`, `iter_lines(decode_unicode=...)`, and the `exceptions`
namespace — so most provider files migrate by **changing one import line**.

```python
# from curl_cffi import requests          # before
from llm4free.browser_requests._http import compat as requests   # after

with requests.Session(impersonate="chrome124") as s:
    r = s.get(url, timeout=15, stream=True)
    for chunk in r.iter_content(chunk_size=8192):
        ...
```

> [!NOTE]
> A `compat.Session` holds **one pooled `Client`** for its lifetime, so
> keep‑alive connections are reused across every request. Mutable settings that
> change after construction — `session.headers`, `session.proxies` (used by the
> proxy‑rotation manager), `verify`, `cert`, `auth`, `timeout` — are re‑forwarded
> per request, so mid‑session mutations are always honored.

## Migrating from curl_cffi / requests / httpx

| Before | After |
|---|---|
| `from curl_cffi import requests` | `from llm4free.browser_requests._http import compat as requests` |
| `from curl_cffi.requests import Session` | `from llm4free.browser_requests._http.compat import Session` |
| `import requests` | `from llm4free.browser_requests._http import compat as requests` |
| `import httpx` | `from llm4free.browser_requests._http import Client, AsyncClient` |
| `except CurlError` | `from llm4free.browser_requests._http import exceptions` → `except exceptions.CurlError` |

Keep calling `impersonate=`, `proxies=`, `json=`, `data=`, `files=`,
`stream=True`, `iter_content()`, `iter_lines()` exactly as before — the façade
accepts them and routes plain traffic to stdlib and fingerprinted traffic to the
optional backend.

## Backend matrix

| `impersonate` | `http2` | primp installed? | Result |
|---|---|---|---|
| `None` | `False` | — | stdlib HTTP/1.1, pooled |
| `None` | `True` | yes | primp plain HTTP/2 |
| `None` | `True` | no | stdlib HTTP/1.1 (degraded) |
| `"chrome124"` | — | yes | primp real TLS/JA3 + HTTP/2 |
| `"chrome124"` | — | no | stdlib ordered‑header engine (degraded) |
| any, `backend="stdlib"` | — | — | always stdlib ordered‑header engine |

## Limitations

- **Stdlib transport is HTTP/1.1 only** and cannot fake a browser TLS/JA3 or
  HTTP/2 fingerprint. Use the `impersonate` extra for those walls.
- **mTLS client certs (`cert=`) are honored only on the stdlib backend**; primp
  has no client‑certificate option and ignores `cert`.
- **`verify=False` on the primp backend** maps to primp's own verify toggle; a
  custom CA **path** maps to `ca_cert_file`. A pre‑built `SSLContext` cannot be
  passed to primp (use the stdlib backend for that).
- **`aiohttp` remains** a dependency for the temp‑mail module only; it is not part
  of this client.

---

*See the tests in [`tests/http/`](../tests/http/) for executable examples of every
feature above.*
