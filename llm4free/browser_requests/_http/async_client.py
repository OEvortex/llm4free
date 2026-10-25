"""Asynchronous httpx-style client.

Shares request preparation with :mod:`.client` and the transport seam with
:mod:`llm4free.browser_requests._http.transport`. The transport runs blocking I/O on an executor
(see ``transport/std_async.py``), giving a correct ``await`` API on top of the
single shared framing implementation.
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import Any, AsyncIterator, Callable, cast
from urllib.parse import urljoin, urlsplit

from .auth import AuthBase, resolve_auth
from .client import (
    DEFAULT_HEADERS,
    _apply_auth,
    _follow_redirect,
    _needs_challenge,
    make_request_spec,
)
from .exceptions import TooManyRedirects
from .models import Cookies, Headers, Response
from .netconfig import best_mount, env_proxy_for, netrc_auth, no_proxy_match
from .sse import ServerSentEvent
from .transport import get_async_transport
from .transport.base import (
    DEFAULT_MAX_REDIRECTS,
    CertType,
    ProxyInfo,
    REDIRECT_STATUSES,
    RequestSpec,
    Timeout,
    VerifyType,
)
from .urls import build_url

_UNSET = object()


async def _run(func: Any) -> Any:
    return await asyncio.get_running_loop().run_in_executor(None, func)


class AsyncResponse:
    def __init__(self, resp: Response) -> None:
        self._resp = resp

    @property
    def status_code(self) -> int:
        return self._resp.status_code

    @property
    def reason(self) -> str:
        return self._resp.reason

    @property
    def headers(self) -> Headers:
        return self._resp.headers

    @property
    def url(self) -> str:
        return self._resp.url

    @property
    def cookies(self) -> Cookies:
        return self._resp.cookies

    @property
    def ok(self) -> bool:
        return self._resp.ok

    def raise_for_status(self) -> "AsyncResponse":
        self._resp.raise_for_status()
        return self

    async def aread(self) -> bytes:
        return await _run(self._resp.read)

    async def atext(self) -> str:
        return (await self.aread()).decode(self._resp._encoding(), "replace")

    async def ajson(self) -> Any:
        return _json.loads(await self.atext())

    async def aiter_bytes(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        resp = self._resp
        if resp._content is not None:
            data = resp._content
            for i in range(0, len(data), chunk_size):
                yield data[i : i + chunk_size]
            return
        gen = resp._stream
        if gen is None:
            return
        sentinel = object()

        def _next() -> Any:
            try:
                return next(gen)
            except StopIteration:
                return sentinel

        while True:
            chunk = await _run(_next)
            if chunk is sentinel:
                break
            yield chunk

    async def aiter_lines(self, keep_blank: bool = False) -> AsyncIterator[str]:
        buf = b""
        async for raw in self.aiter_bytes():
            buf += raw
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                text = line.decode("utf-8", "replace").rstrip("\r")
                if text or keep_blank:
                    yield text
        if buf:
            text = buf.decode("utf-8", "replace").rstrip("\r")
            if text or keep_blank:
                yield text

    async def aiter_text(self) -> AsyncIterator[str]:
        enc = self._resp._encoding()
        async for raw in self.aiter_bytes():
            yield raw.decode(enc, "replace")

    async def aiter_sse(self) -> AsyncIterator[ServerSentEvent]:
        """Incremental SSE parser (mirrors :mod:`.sse`) over an async line source."""
        data_lines: list[str] = []
        event_type = ""
        event_id: str | None = None
        retry: int | None = None

        def dispatch() -> ServerSentEvent | None:
            nonlocal data_lines, event_type, event_id, retry
            if not data_lines:
                event_type = ""
                retry = None
                return None
            data = "\n".join(data_lines)
            if data.endswith("\n"):
                data = data[:-1]
            ev = ServerSentEvent(event=event_type or "message", data=data, id=event_id, retry=retry)
            data_lines, event_type, retry = [], "", None
            return ev

        async for line in self.aiter_lines(keep_blank=True):
            if line == "":
                ev = dispatch()
                if ev is not None:
                    yield ev
                continue
            if line.startswith(":"):
                continue
            if ":" in line:
                name, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]
            else:
                name, value = line, ""
            if name == "data":
                data_lines.append(value)
            elif name == "event":
                event_type = value
            elif name == "id":
                event_id = value
            elif name == "retry" and value.isdigit():
                retry = int(value)

    async def aclose(self) -> None:
        await _run(self._resp.close)


class AsyncClient:
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
        backend: str = "primp",
    ) -> None:
        self.base_url = base_url
        self.headers = DEFAULT_HEADERS.merged(headers) if headers else DEFAULT_HEADERS
        self.cookies = cookies if isinstance(cookies, Cookies) else Cookies(cookies or None)
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
        self._transport = get_async_transport(impersonate, backend=backend, http2=http2)

    def mount(self, prefix: str, value: str) -> None:
        self.mounts[prefix] = value

    def _resolve_proxy(self, url: str, proxies: Any) -> ProxyInfo | None:
        if proxies:
            purl = (
                (proxies.get("https") or proxies.get("http") or proxies.get("all"))
                if isinstance(proxies, dict)
                else proxies
            )
            if purl:
                return ProxyInfo.parse(purl)
        mounted = best_mount(self.mounts, url)
        if mounted:
            return ProxyInfo.parse(mounted)
        if self.proxy is not None:
            return self.proxy
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

    def _fire(self, kind: str, arg: Any) -> None:
        for callback in self.event_hooks.get(kind, ()):
            callback(arg)

    async def request(
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
    ) -> AsyncResponse:
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
        authobj = self._resolve_auth(auth, full_url)

        if authobj is not None and not _needs_challenge(authobj):
            req_headers = _apply_auth(authobj, req_headers, method.upper(), full_url)

        def _spec_for(hdrs: Headers) -> RequestSpec:
            return make_request_spec(
                method, url, params=params, headers=hdrs, cookies=jar,
                json=json, data=data, files=files, base_url=self.base_url,
            )

        spec = _spec_for(req_headers)
        self._fire("request", spec)

        resp = await self._send_with_redirects(
            spec, timeout=tmo, verify=vfy, cert=crtc,
            allow_redirects=allow_redirects, stream=stream, proxy=proxy,
        )

        if authobj is not None and _needs_challenge(authobj) and resp.status_code == 401:
            challenge = resp.headers.get("www-authenticate")
            if challenge and challenge.lower().startswith("digest"):
                await resp.aclose()
                cast(AuthBase, authobj).set_challenge(challenge)
                authed = _apply_auth(authobj, req_headers, method.upper(), resp.url or full_url)
                spec = _spec_for(authed)
                self._fire("request", spec)
                resp = await self._send_with_redirects(
                    spec, timeout=tmo, verify=vfy, cert=crtc,
                    allow_redirects=allow_redirects, stream=stream, proxy=proxy,
                )

        self._fire("response", resp)
        return resp

    async def _send_with_redirects(
        self, spec: RequestSpec, *, timeout: Timeout, verify: VerifyType,
        cert: CertType, allow_redirects: bool, stream: bool, proxy: ProxyInfo | None,
    ) -> AsyncResponse:
        redirects = 0
        history: list[Response] = []
        while True:
            resp: Response = await self._transport.handle(
                spec, timeout=timeout, verify=verify, cert=cert, proxy=proxy, stream=stream
            )
            self.cookies.update(resp.cookies.to_dict())
            if not allow_redirects or resp.status_code not in REDIRECT_STATUSES:
                resp.history = history
                return AsyncResponse(resp)
            location = resp.headers.get("location")
            if not location:
                resp.history = history
                return AsyncResponse(resp)
            if redirects >= self.max_redirects:
                raise TooManyRedirects(f"Exceeded {self.max_redirects} redirects")
            redirects += 1
            history.append(resp)
            spec = _follow_redirect(spec, urljoin(spec.url, location), resp.status_code)
            resp.close()

    def stream(self, method: str, url: str, **kwargs: Any) -> "_AsyncStreamCtx":
        return _AsyncStreamCtx(self, method, url, kwargs)

    async def get(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("POST", url, **kw)

    async def put(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("PUT", url, **kw)

    async def patch(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("PATCH", url, **kw)

    async def delete(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("DELETE", url, **kw)

    async def head(self, url: str, **kw: Any) -> AsyncResponse:
        return await self.request("HEAD", url, **kw)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


class _AsyncStreamCtx:
    def __init__(self, client: AsyncClient, method: str, url: str, kwargs: dict[str, Any]) -> None:
        self._c = client
        self._m = method
        self._u = url
        self._kw = kwargs
        self._resp: AsyncResponse | None = None

    async def __aenter__(self) -> AsyncResponse:
        self._resp = await self._c.request(self._m, self._u, stream=True, **self._kw)
        return self._resp

    async def __aexit__(self, *exc: Any) -> None:
        if self._resp is not None:
            await self._resp.aclose()


__all__ = ["AsyncClient", "AsyncResponse"]
