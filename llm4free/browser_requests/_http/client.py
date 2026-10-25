"""Synchronous httpx-style client plus shared request-preparation helpers.

The ``_prepare`` helpers are reused by :mod:`.async_client` so both clients build
requests identically.
"""

from __future__ import annotations

import json as _json
from typing import Any
from urllib.parse import urljoin

from .exceptions import TooManyRedirects
from .models import Cookies, Headers, Response
from .multipart import encode_multipart
from .transport import get_sync_transport
from .transport.base import (
    DEFAULT_MAX_REDIRECTS,
    ProxyInfo,
    REDIRECT_STATUSES,
    RequestSpec,
    SyncTransport,
    Timeout,
)
from .urls import build_url, encode_params

# Headers every stdlib request carries unless overridden.
DEFAULT_HEADERS = Headers(
    {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
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


class Client:
    """A blocking HTTP client with sessions, cookies, redirects, and streaming."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        headers: Any = None,
        cookies: Any = None,
        timeout: Any = 30,
        verify: bool = True,
        proxy: str | None = None,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        impersonate: str | None = None,
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
        self.proxy = ProxyInfo.parse(proxy) if proxy else None
        self.max_redirects = max_redirects
        self.impersonate = impersonate
        self._transport = transport or get_sync_transport(impersonate, backend=backend)
        self._backend = backend
        self._transport_cache: dict[str | None, SyncTransport] = {impersonate: self._transport}

    def _resolve_transport(self, impersonate: str | None) -> SyncTransport:
        if impersonate is None or impersonate == self.impersonate:
            return self._transport
        if impersonate not in self._transport_cache:
            self._transport_cache[impersonate] = get_sync_transport(impersonate, backend=self._backend)
        return self._transport_cache[impersonate]

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
        verify: bool | None = None,
        allow_redirects: bool = True,
        stream: bool = False,
        impersonate: str | None = None,
        proxies: Any = None,
        auth: tuple[str, str] | None = None,
        **_ignored: Any,
    ) -> Response:
        req_headers = self.headers.merged(headers)
        if auth is not None:
            import base64

            token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
            req_headers = req_headers.merged({"Authorization": f"Basic {token}"})
        jar = self.cookies
        if cookies:
            jar = Cookies(jar.to_dict())
            jar.update(dict(cookies))

        tmo = Timeout.from_value(timeout) if timeout is not None else self.timeout
        vfy = self.verify if verify is None else verify

        proxy = self.proxy
        if proxies:
            purl = proxies.get("https") or proxies.get("http") if isinstance(proxies, dict) else proxies
            if purl:
                proxy = ProxyInfo.parse(purl)

        spec = make_request_spec(
            method,
            url,
            params=params,
            headers=req_headers,
            cookies=jar,
            json=json,
            data=data,
            files=files,
            base_url=self.base_url,
        )

        transport = self._resolve_transport(impersonate)

        return self._send_with_redirects(
            spec, timeout=tmo, verify=vfy, allow_redirects=allow_redirects,
            stream=stream, transport=transport, proxy=proxy,
        )

    def _send_with_redirects(
        self, spec: RequestSpec, *, timeout: Timeout, verify: bool,
        allow_redirects: bool, stream: bool,
        transport: SyncTransport | None = None,
        proxy: ProxyInfo | None = None,
    ) -> Response:
        transport = transport or self._transport
        proxy = self.proxy if proxy is None else proxy
        redirects = 0
        while True:
            resp = transport.handle(
                spec, timeout=timeout, verify=verify, proxy=proxy, stream=stream
            )
            self.cookies.update(resp.cookies.to_dict())

            if not allow_redirects or resp.status_code not in REDIRECT_STATUSES:
                return resp

            location = resp.headers.get("location")
            if not location:
                return resp
            if redirects >= self.max_redirects:
                raise TooManyRedirects(f"Exceeded {self.max_redirects} redirects for {spec.url}")
            redirects += 1

            next_url = urljoin(spec.url, location)
            spec = _follow_redirect(spec, next_url, resp.status_code)
            if redirects == 1:
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
        self._transport.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


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
