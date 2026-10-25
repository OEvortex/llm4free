"""A ``requests`` / ``curl_cffi.requests``-compatible façade over the client.

Provider modules use ``curl_cffi.requests.Session()``, module-level
``requests.get/post/request(...)``, ``impersonate=``, ``proxies=``, ``stream=True``,
``resp.iter_content()`` and ``except CurlError``. This module mirrors that surface
so a provider migrates by changing **one import line**::

    from llm4free.browser_requests._http import compat as requests       # was: from curl_cffi import requests

Plain calls go through the stdlib transport; calls that pass (or were constructed
with) ``impersonate=`` transparently route to the optional primp backend via
the transport seam.
"""

from __future__ import annotations

import sys
from typing import Any

from .async_client import AsyncClient, AsyncResponse
from .client import Client
from .exceptions import (
    ConnectError,
    ConnectionError,
    CurlError,
    HTTPError,
    ReadError,
    ReadTimeout,
    RequestException,
    RequestsError,
    SSLError,
    Timeout,
    TimeoutError,
    TooManyRedirects,
)
from .models import Cookies, Headers, Response
from .transport.base import ProxyInfo


def _first_proxy(proxies: Any, proxy: Any) -> str | None:
    if proxy:
        return proxy
    if isinstance(proxies, dict):
        return proxies.get("https") or proxies.get("http") or proxies.get("all")
    if isinstance(proxies, str):
        return proxies
    return None


class Session:
    """A persistent, cookie-aware, curl/requests-compatible session."""

    def __init__(
        self,
        headers: Any = None,
        cookies: Any = None,
        proxy: str | None = None,
        proxies: Any = None,
        timeout: Any = None,
        verify: bool = True,
        impersonate: str | None = None,
        allow_redirects: bool = True,
        **_ignored: Any,
    ) -> None:
        self.headers: dict[str, str] = dict(headers or {})
        self.cookies = cookies if isinstance(cookies, Cookies) else Cookies(cookies or None)
        self.timeout = timeout
        self.verify = verify
        self.impersonate = impersonate
        self.allow_redirects = allow_redirects
        # ``proxies`` mirrors ``requests.Session.proxies`` so the proxy-rotation
        # manager can populate it after construction (``.update({...})``).
        self.proxies: dict[str, str] = {}
        self.proxy = _first_proxy(proxies, proxy)

    def _client(self, headers: Any, cookies: Any, **_kw: Any) -> Client:
        merged = dict(self.headers)
        if headers:
            merged.update(dict(headers))
        jar = self.cookies
        if cookies:
            jar = Cookies(jar.to_dict())
            jar.update(dict(cookies))
        return Client(
            headers=merged,
            cookies=jar,
            timeout=self.timeout,
            verify=self.verify,
            proxy=_first_proxy(self.proxies, self.proxy),
            impersonate=self.impersonate,
        )

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        client = self._client(kwargs.get("headers"), kwargs.get("cookies"))
        kwargs.setdefault("allow_redirects", self.allow_redirects)
        resp = client.request(method, url, **kwargs)
        # persist cookies acquired during the request back onto the session
        self.cookies.update(resp.cookies.to_dict())
        client.close()
        return resp

    def _verb(self, method: str, url: str, **kwargs: Any) -> Response:
        return self.request(method, url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> Response:
        kwargs.setdefault("allow_redirects", False)
        return self.request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> Response:
        return self.request("OPTIONS", url, **kwargs)

    def close(self) -> None:
        return None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncSession:
    """Async curl-compatible session (mirrors :class:`Session`)."""

    def __init__(
        self,
        headers: Any = None,
        cookies: Any = None,
        proxy: str | None = None,
        proxies: Any = None,
        timeout: Any = None,
        verify: bool = True,
        impersonate: str | None = None,
        **_ignored: Any,
    ) -> None:
        self.headers = dict(headers or {})
        self.cookies = cookies if isinstance(cookies, Cookies) else Cookies(cookies or None)
        self.timeout = timeout
        self.verify = verify
        self.impersonate = impersonate
        self.proxies: dict[str, str] = {}
        self.proxy = _first_proxy(proxies, proxy)

    def _client(self, headers: Any = None) -> AsyncClient:
        merged = dict(self.headers)
        if headers:
            merged.update(dict(headers))
        return AsyncClient(
            headers=merged,
            cookies=self.cookies,
            timeout=self.timeout,
            verify=self.verify,
            proxy=_first_proxy(self.proxies, self.proxy),
            impersonate=self.impersonate,
        )

    async def request(self, method: str, url: str, **kwargs: Any) -> AsyncResponse:
        kwargs.pop("cookies", None)
        ac = self._client(kwargs.get("headers"))
        return await ac.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> AsyncResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> AsyncResponse:
        return await self.request("POST", url, **kwargs)

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> "AsyncSession":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


# --- module-level, stateless helpers (requests.get / curl_cffi.requests.get) ---
def request(method: str, url: str, **kwargs: Any) -> Response:
    with Session(
        headers=kwargs.pop("headers", None),
        cookies=kwargs.pop("cookies", None),
        proxy=kwargs.pop("proxy", None),
        proxies=kwargs.pop("proxies", None),
        timeout=kwargs.pop("timeout", None),
        verify=kwargs.pop("verify", True),
        impersonate=kwargs.pop("impersonate", None),
    ) as s:
        return s.request(method, url, **kwargs)


def get(url: str, **kwargs: Any) -> Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs: Any) -> Response:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs: Any) -> Response:
    return request("PUT", url, **kwargs)


def patch(url: str, **kwargs: Any) -> Response:
    return request("PATCH", url, **kwargs)


def delete(url: str, **kwargs: Any) -> Response:
    return request("DELETE", url, **kwargs)


def head(url: str, **kwargs: Any) -> Response:
    return request("HEAD", url, **kwargs)


def options(url: str, **kwargs: Any) -> Response:
    return request("OPTIONS", url, **kwargs)


# Exception namespace mirroring ``curl_cffi.requests.exceptions``.
class exceptions:  # noqa: N801 - lowercase namespace by intent
    HTTPError = HTTPError
    RequestException = RequestException
    RequestsError = RequestsError
    CurlError = CurlError
    ConnectionError = ConnectionError
    ConnectError = ConnectError
    ReadError = ReadError
    Timeout = Timeout
    TimeoutError = TimeoutError
    ReadTimeout = ReadTimeout
    SSLError = SSLError
    TooManyRedirects = TooManyRedirects


# Mirror ``curl_cffi.requests`` so ``import curl_cffi.requests``-style call
# sites (``curl_cffi.requests.Session`` / ``.exceptions``) map by swapping the
# import to ``from llm4free.browser_requests._http import compat as curl_cffi``.
requests = sys.modules[__name__]


__all__ = [
    "Session",
    "AsyncSession",
    "request",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "Response",
    "Headers",
    "Cookies",
    "exceptions",
    "RequestException",
    "RequestsError",
    "CurlError",
    "Timeout",
]
