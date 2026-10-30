"""Proxy-URL parsing helpers for browser-level proxy routing.

The HTTP proxy strings produced by :class:`llm4free.Extra.proxy_manager.ProxyManager`
embed credentials in the userinfo component (e.g.
``http://<token>:1@host:port``) where the username is percent-encoded.
Chrome's ``--proxy-server`` flag takes *no* credentials, so the proxy is split
into two parts here:

* the server half (``scheme://host:port``) goes to the launch flag, and
* the (decoded) username/password pair is answered over CDP when Chrome fires
  ``Fetch.authRequired`` for a ``407`` proxy challenge.

Accepting either a plain URL or the ``{"http": ..., "https": ...}`` dict that
``ProxyManager.get()`` returns keeps the call sites in the providers short.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Union
from urllib.parse import unquote, urlsplit

ProxyLike = Union[str, dict, None]


@dataclasses.dataclass(frozen=True)
class ProxySpec:
    """A parsed HTTP/HTTPS/SOCKS proxy with optional credentials."""

    host: str
    port: int
    scheme: str = "http"
    username: str = ""
    password: str = ""

    @property
    def server(self) -> str:
        """``--proxy-server`` value: ``scheme://host:port`` (never credentials)."""
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def requires_auth(self) -> bool:
        return bool(self.username)


def resolve_proxy_str(proxy: ProxyLike) -> Optional[str]:
    """Normalize a proxy argument to a single URL string (or ``None``).

    Accepts a URL string or the ``{"http"/"https": url}`` dict returned by
    :meth:`llm4free.Extra.proxy_manager.ProxyManager.get`.
    """
    if not proxy:
        return None
    if isinstance(proxy, dict):
        return proxy.get("https") or proxy.get("http") or None
    text = str(proxy).strip()
    return text or None


def parse_proxy(proxy: ProxyLike) -> Optional[ProxySpec]:
    """Parse a proxy argument into a :class:`ProxySpec` (``None`` if empty).

    Raises:
        ValueError: when a non-empty proxy has no host.
    """
    url = resolve_proxy_str(proxy)
    if not url:
        return None
    parts = urlsplit(url if "://" in url else f"http://{url}")
    host = parts.hostname
    if not host:
        raise ValueError(f"proxy has no host: {proxy!r}")
    default_port = 1080 if parts.scheme.startswith("socks") else 80
    port = parts.port or default_port
    username = unquote(parts.username) if parts.username else ""
    password = unquote(parts.password) if parts.password else ""
    return ProxySpec(
        host=host,
        port=port,
        scheme=parts.scheme or "http",
        username=username,
        password=password,
    )


__all__ = ["ProxySpec", "ProxyLike", "parse_proxy", "resolve_proxy_str"]
