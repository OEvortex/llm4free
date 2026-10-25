"""Synchronous httpx-style client plus shared request-preparation helpers.

The ``_prepare`` helpers are reused by :mod:`.async_client` so both clients build
requests identically.
"""

from __future__ import annotations

import json as _json
from typing import Any, Callable, cast
from urllib.parse import urljoin, urlsplit

from .auth import AuthBase, resolve_auth
from .exceptions import TooManyRedirects
from .models import Cookies, Headers, Response
from .multipart import encode_multipart
from .netconfig import best_mount, env_proxy_for, netrc_auth, no_proxy_match
from .transport import get_sync_transport
from .transport.base import (
    DEFAULT_MAX_REDIRECTS,
    CertType,
    ProxyInfo,
    REDIRECT_STATUSES,
    RequestSpec,
    SyncTransport,
    Timeout,
    VerifyType,
)
from .urls import build_url, encode_params

# Headers every stdlib request carries unless overridden. ``Connection:
# keep-alive`` lets the std transport pool and reuse sockets across requests.
DEFAULT_HEADERS = Headers(
    {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "User-Agent": "llm4free-http/1.0 (+stdlib)",
    }
)


def build_body(
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
) -> tuple[bytes | None, dict[str, str]]:
    """Serialize json/data/files into (body_bytes, extra_headers)."""
    extra: dict[str, str] = {}
    body: bytes | None = None

    if json is not None:
        body = _json.dumps(json).encode("utf-8")
        extra["Content-Type"] = "application/json"
    elif files is not None:
        body, ctype = encode_multipart(data, files)
        extra["Content-Type"] = ctype
    elif data is not None:
        if isinstance(data, (bytes, bytearray)):
            body = bytes(data)
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:  # mapping / sequence of pairs -> urlencoded form
            body = encode_params(data).encode("utf-8")
            extra["Content-Type"] = "application/x-www-form-urlencoded"

    if body is not None:
        extra["Content-Length"] = str(len(body))
    return body, extra


def make_request_spec(
    method: str,
    url: str,
    *,
    params: Any = None,
    headers: Headers,
    cookies: Cookies,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    base_url: str | None = None,
) -> RequestSpec:
    full_url = build_url(base_url, url, params)
    body, body_headers = build_body(json=json, data=data, files=files)

    merged = headers
    if body_headers:
        merged = merged.merged(body_headers)
    cookie_hdr = cookies.header_value()
    if cookie_hdr and "cookie" not in merged:
        merged = merged.merged({"Cookie": cookie_hdr})

    return RequestSpec(method=method.upper(), url=full_url, headers=merged, body=body)


_UNSET = object()


class Client:
    """A blocking HTTP client with sessions, cookies, redirects, and streaming."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        headers: Any = None,
        cookies: Any = None,
        timeout: Any = 30,
        verify: VerifyType = True,
        cert: CertType = None,
        proxy: str | None = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        impersonate: str | None = None,
        http2: bool = False,
        trust_env: bool = True,
        auth: Any = None,
        event_hooks: Any = None,
        transport: SyncTransport | None = None,
        backend: str = "primp",
    ) -> None:
        self.base_url = base_url
        self.headers = DEFAULT_HEADERS.merged(headers) if headers else DEFAULT_HEADERS
        self.cookies = Cookies(cookies) if not isinstance(cookies, Cookies) else cookies
        if self.cookies is None:
            self.cookies = Cookies()
        if cookies and not isinstance(cookies, Cookies) and not isinstance(cookies, dict):
            self.cookies = Cookies(dict(cookies))
        self.timeout = Timeout.from_value(timeout)
        self.verify = verify
        self.cert = cert
        self.proxy = ProxyInfo.parse(proxy) if proxy else None
        self.max_redirects = max_redirects
        self.impersonate = impersonate
        self.http2 = http2
        self.trust_env = trust_env
        self.auth = auth
        self.mounts: dict[str, str] = {}
        self.event_hooks: dict[str, list[Callable[[Any], None]]] = {
            "request": [],
            "response": [],
        }
        for kind, callbacks in (event_hooks or {}).items():
            self.event_hooks.setdefault(kind, [])
            self.event_hooks[kind].extend(callbacks)
        self._backend = backend
        self._transport = transport or get_sync_transport(
            impersonate, backend=backend, http2=http2
        )
        self._transport_cache: dict[str | None, SyncTransport] = {impersonate: self._transport}

    def mount(self, prefix: str, value: str) -> None:
        """Register a proxy (or transport marker) for URLs starting with ``prefix``."""
        self.mounts[prefix] = value

    # --- resolution helpers ---
    def _resolve_transport(self, impersonate: str | None) -> SyncTransport:
        if impersonate is None or impersonate == self.impersonate:
            return self._transport
        if impersonate not in self._transport_cache:
            self._transport_cache[impersonate] = get_sync_transport(
                impersonate, backend=self._backend, http2=self.http2
            )
        return self._transport_cache[impersonate]

    def _resolve_proxy(self, url: str, proxies: Any) -> ProxyInfo | None:
        # 1. explicit per-request proxies mapping/string wins
        if proxies:
            purl = (
                (proxies.get("https") or proxies.get("http") or proxies.get("all"))
                if isinstance(proxies, dict)
                else proxies
            )
            if purl:
                return ProxyInfo.parse(purl)
        # 2. a mounted prefix (longest match)
        mounted = best_mount(self.mounts, url)
        if mounted:
            return ProxyInfo.parse(mounted)
        # 3. the client-level proxy
        if self.proxy is not None:
            return self.proxy
        # 4. the environment (only when trusted)
        if self.trust_env:
            parts = urlsplit(url)
            if parts.scheme in ("http", "https") and not no_proxy_match(parts.hostname or ""):
                env = env_proxy_for(parts.scheme, parts.hostname or "")
                if env:
                    return ProxyInfo.parse(env)
        return None

    def _resolve_auth(self, auth: Any, url: str) -> AuthBase | Callable[[Headers], Headers] | None:
        chosen = auth if auth is not None else self.auth
        resolved = resolve_auth(chosen)
        if resolved is None and self.trust_env:
            host = urlsplit(url).hostname
            if host:
                creds = netrc_auth(host)
                if creds:
                    resolved = resolve_auth(creds)
        return resolved

    # --- public request ---
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Any = None,
        data: Any = None,
        json: Any = None,
        headers: Any = None,
        cookies: Any = None,
        files: Any = None,
        timeout: Any = None,
        verify: VerifyType | None = None,
        cert: Any = _UNSET,
        allow_redirects: bool = True,
        stream: bool = False,
        impersonate: str | None = None,
        proxies: Any = None,
        auth: Any = None,
        **_ignored: Any,
    ) -> Response:
        req_headers = self.headers.merged(headers)
        jar = self.cookies
        if cookies:
            jar = Cookies(jar.to_dict())
            jar.update(dict(cookies))

        tmo = Timeout.from_value(timeout) if timeout is not None else self.timeout
        vfy = self.verify if verify is None else verify
        crtc = self.cert if cert is _UNSET else cert

        full_url = build_url(self.base_url, url, params)
        proxy = self._resolve_proxy(full_url, proxies)
        transport = self._resolve_transport(impersonate)
        authobj = self._resolve_auth(auth, full_url)

        def _spec_for(hdrs: Headers) -> RequestSpec:
            return make_request_spec(
                method, url, params=params, headers=hdrs, cookies=jar,
                json=json, data=data, files=files, base_url=self.base_url,
            )

        # non-challenge auth (Basic/Bearer/callable) is applied up front.
        if authobj is not None and not _needs_challenge(authobj):
            req_headers = _apply_auth(authobj, req_headers, method.upper(), full_url)

        spec = _spec_for(req_headers)
        self._fire("request", spec)

        resp = self._send_with_redirects(
            spec, timeout=tmo, verify=vfy, cert=crtc,
            allow_redirects=allow_redirects, stream=stream,
            transport=transport, proxy=proxy,
        )

        # digest-style challenge/response: retry once with the computed header.
        if authobj is not None and _needs_challenge(authobj) and resp.status_code == 401:
            challenge = resp.headers.get("www-authenticate")
            if challenge and challenge.lower().startswith("digest"):
                resp.close()
                cast(AuthBase, authobj).set_challenge(challenge)
                authed = _apply_auth(authobj, req_headers, method.upper(), resp.url or full_url)
                spec = _spec_for(authed)
                self._fire("request", spec)
                resp = self._send_with_redirects(
                    spec, timeout=tmo, verify=vfy, cert=crtc,
                    allow_redirects=allow_redirects, stream=stream,
                    transport=transport, proxy=proxy,
                )

        self._fire("response", resp)
        return resp

    def _fire(self, kind: str, arg: Any) -> None:
        for callback in self.event_hooks.get(kind, ()):
            callback(arg)

    def _send_with_redirects(
        self, spec: RequestSpec, *, timeout: Timeout, verify: VerifyType,
        cert: CertType, allow_redirects: bool, stream: bool,
        transport: SyncTransport | None = None,
        proxy: ProxyInfo | None = None,
    ) -> Response:
        transport = transport or self._transport
        proxy = self.proxy if proxy is None else proxy
        redirects = 0
        history: list[Response] = []
        while True:
            resp = transport.handle(
                spec, timeout=timeout, verify=verify, cert=cert, proxy=proxy, stream=stream
            )
            self.cookies.update(resp.cookies.to_dict())

            if not allow_redirects or resp.status_code not in REDIRECT_STATUSES:
                resp.history = history
                return resp

            location = resp.headers.get("location")
            if not location:
                resp.history = history
                return resp
            if redirects >= self.max_redirects:
                raise TooManyRedirects(f"Exceeded {self.max_redirects} redirects for {spec.url}")
            redirects += 1

            history.append(resp)
            next_url = urljoin(spec.url, location)
            spec = _follow_redirect(spec, next_url, resp.status_code)
            # Redirect hops are buffered+small; free the socket but keep the
            # recorded response (status/headers/content stay usable) in history.
            resp.close()

    def stream(self, method: str, url: str, **kwargs: Any) -> _StreamContext:
        kwargs.pop("stream", None)
        return _StreamContext(self, method, url, kwargs)

    # --- verb helpers ---
    def get(self, url: str, **kw: Any) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Response:
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw: Any) -> Response:
        return self.request("PUT", url, **kw)

    def patch(self, url: str, **kw: Any) -> Response:
        return self.request("PATCH", url, **kw)

    def delete(self, url: str, **kw: Any) -> Response:
        return self.request("DELETE", url, **kw)

    def head(self, url: str, **kw: Any) -> Response:
        return self.request("HEAD", url, **kw)

    def options(self, url: str, **kw: Any) -> Response:
        return self.request("OPTIONS", url, **kw)

    # --- back-compat with search/http_client.HttpClient ---
    def set_cookies(self, url: str, cookies: dict[str, str]) -> None:
        self.cookies.update(cookies)

    def close(self) -> None:
        for transport in list(self._transport_cache.values()):
            transport.close()
        self._transport.close()
        self._transport_cache.clear()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _needs_challenge(auth: Any) -> bool:
    return isinstance(auth, AuthBase) and auth.requires_challenge


def _apply_auth(
    auth: AuthBase | Callable[[Headers], Headers], headers: Headers, method: str, url: str
) -> Headers:
    if isinstance(auth, AuthBase):
        return auth.apply(headers, method, url)
    out = auth(headers)
    if out is None:
        return headers
    return out if isinstance(out, Headers) else Headers(out)


def _follow_redirect(spec: RequestSpec, next_url: str, status: int) -> RequestSpec:
    """Build the next request after a redirect (httpx status semantics)."""
    method = spec.method
    body = spec.body
    headers = spec.headers

    if status in (301, 302, 303) and method == "POST":
        method = "GET"
        body = None
        headers = headers.merged({"Content-Length": "0"})
        # strip content-type/body headers
        headers = Headers([(k, v) for k, v in headers.items() if k.lower() not in ("content-type", "content-length")])

    # Rebuild spec for the new URL (cookie header recomputed by caller side).
    p_url = next_url
    merged = Headers([(k, v) for k, v in headers.items() if k.lower() != "cookie"])
    return RequestSpec(method=method, url=p_url, headers=merged, body=body)


class _StreamContext:
    def __init__(self, client: Client, method: str, url: str, kwargs: dict[str, Any]) -> None:
        self._client = client
        self._method = method
        self._url = url
        self._kwargs = kwargs

    def __enter__(self) -> Response:
        kwargs = dict(self._kwargs)
        kwargs["stream"] = True
        self._resp = self._client.request(self._method, self._url, **kwargs)
        return self._resp

    def __exit__(self, *exc: Any) -> None:
        self._resp.close()


# --- module-level helpers ---
def request(method: str, url: str, **kw: Any) -> Response:
    stream = kw.pop("stream", False)
    with Client() as c:
        if stream:
            with c.stream(method, url, **kw) as r:
                return r
        return c.request(method, url, **kw)


def get(url: str, **kw: Any) -> Response:
    return request("GET", url, **kw)


def post(url: str, **kw: Any) -> Response:
    return request("POST", url, **kw)


def put(url: str, **kw: Any) -> Response:
    return request("PUT", url, **kw)


def patch(url: str, **kw: Any) -> Response:
    return request("PATCH", url, **kw)


def delete(url: str, **kw: Any) -> Response:
    return request("DELETE", url, **kw)


def head(url: str, **kw: Any) -> Response:
    return request("HEAD", url, **kw)


__all__ = [
    "Client",
    "request",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "build_body",
    "make_request_spec",
    "DEFAULT_HEADERS",
]
