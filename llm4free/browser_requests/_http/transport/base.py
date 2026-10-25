"""Transport protocol, request spec, and shared connection helpers."""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Protocol, runtime_checkable
from urllib.parse import urlsplit

from ..models import Headers


@dataclass
class Timeout:
    """Resolved connect / read timeouts (seconds). ``None`` means block-free."""

    connect: float | None = None
    read: float | None = None

    @classmethod
    def from_value(cls, value: Any) -> "Timeout":
        if value is None:
            return cls(None, None)
        if isinstance(value, Timeout):
            return value
        if isinstance(value, (tuple, list)):
            connect = value[0] if len(value) > 0 else None
            read = value[1] if len(value) > 1 else connect
            return cls(connect, read)
        # scalar applies to both phases
        return cls(value, value)

    def with_read(self, value: float | None) -> "Timeout":
        return Timeout(self.connect, value if value is not None else self.read)


@dataclass
class ProxyInfo:
    scheme: str  # "http" | "https" | "socks5"
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @classmethod
    def parse(cls, url: str) -> "ProxyInfo":
        parts = urlsplit(url)
        scheme = (parts.scheme or "http").lower()
        if scheme in ("socks5h", "socks5"):
            scheme = "socks5"
        default_port = 1080 if scheme == "socks5" else (443 if scheme == "https" else 80)
        return cls(
            scheme=scheme,
            host=parts.hostname or "",
            port=parts.port or default_port,
            username=parts.username,
            password=parts.password,
        )


@dataclass
class RequestSpec:
    """A fully prepared request handed to a transport."""

    method: str
    url: str
    headers: Headers
    body: bytes | Iterator[bytes] | None = None
    # split pieces (computed once)
    scheme: str = ""
    host: str = ""
    port: int = 0
    path: str = "/"
    is_https: bool = False

    def __post_init__(self) -> None:
        p = urlsplit(self.url)
        self.scheme = p.scheme
        self.is_https = p.scheme == "https"
        self.host = p.hostname or ""
        self.port = p.port or (443 if self.is_https else 80)
        self.path = p.path or "/"
        if p.query:
            self.path = f"{self.path}?{p.query}"


@runtime_checkable
class SyncTransport(Protocol):
    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Any:  # -> Response
        ...

    def close(self) -> None: ...


@runtime_checkable
class AsyncTransport(Protocol):
    async def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Any:  # -> Response
        ...

    async def aclose(self) -> None: ...


def build_ssl_context(verify: bool | ssl.SSLContext) -> ssl.SSLContext:
    """Build a client TLS context honoring the ``verify`` toggle."""
    if isinstance(verify, ssl.SSLContext):
        return verify
    ctx = ssl.create_default_context()
    if verify is False:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# Redirect status codes handled by the client layer.
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
DEFAULT_MAX_REDIRECTS = 20


def iter_or_repeat(body: bytes | Iterable[bytes] | None, chunk: int = 65536) -> Iterator[bytes]:
    if body is None:
        return
    if isinstance(body, (bytes, bytearray)):
        data = bytes(body)
        for i in range(0, len(data), chunk):
            yield data[i : i + chunk]
    else:
        yield from body  # type: ignore[union-attr]


__all__ = [
    "Timeout",
    "ProxyInfo",
    "RequestSpec",
    "SyncTransport",
    "AsyncTransport",
    "build_ssl_context",
    "REDIRECT_STATUSES",
    "DEFAULT_MAX_REDIRECTS",
]
