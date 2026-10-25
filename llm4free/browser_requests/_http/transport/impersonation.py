"""Impersonation transport seam.

Plain requests use the stdlib transport (zero dependencies). When ``impersonate``
is requested, the client asks :func:`get_sync_transport` for a backend. The
built-in real-fingerprint backend lazily imports ``primp`` — so primp is an
*optional* extra used solely by the fingerprint-sensitive scraping sites, never
for ordinary API calls. If it is not installed, a clear configuration error is
raised (and the selector transparently degrades to the stdlib header engine).

This seam is the single integration point for swapping the impersonation engine
without touching any call site.
"""

from __future__ import annotations

import re
import ssl
from typing import Any, Callable

from ....exceptions import MissingRequirementsError
from ..exceptions import ConnectError, HTTPError, ReadError
from ..exceptions import TimeoutError as HTTPTimeoutError
from ..models import Headers, Response
from .base import ProxyInfo, RequestSpec, SyncTransport, Timeout
from .browser_profiles import (
    KNOWN_TARGETS,
    normalize_browser_type,
)
from .std_sync import SyncStdTransport

SyncBackendFactory = Callable[[str], SyncTransport]

_registry: dict[str, SyncBackendFactory] = {}


def register_sync_backend(name: str, factory: SyncBackendFactory) -> None:
    _registry[name] = factory


# --- target -> primp name/os mapping --------------------------------------

# primp 2.x ships a narrow set of real fingerprints. Map the curl-style target
# names the call sites already pass onto the nearest supported primp target.
_PRIMP_SUPPORTED: dict[str, tuple[int, ...]] = {
    "chrome": (144, 145, 146),
    "edge": (144, 145, 146),
    "firefox": (140, 146),
    "safari": (26,),
}
_PRIMP_FAMILY_DEFAULT = 146

_TARGET_RE = re.compile(r"^(chrome|edge|safari|firefox|tor|okhttp|deku)", re.I)
_MAJOR_RE = re.compile(r"(\d+)")


def _map_target(target: str) -> tuple[str, str]:
    """Resolve a curl-style ``target`` to a ``(primp_name, primp_os)`` pair."""
    low = (target or "").lower()
    m = _TARGET_RE.match(low)
    family = m.group(1) if m else "chrome"
    if family in ("tor", "deku"):
        family = "firefox"
    elif family == "okhttp":
        family = "chrome"

    digits = _MAJOR_RE.search(low.split("_", 1)[0]) or _MAJOR_RE.search(low)
    major = int(digits.group(1)) if digits else 0
    # curl encodes majors like "chrome124" (124) or "safari2601" (260 -> 26.1).
    if family == "safari" and major >= 100:
        major = major // 10

    supported = _PRIMP_SUPPORTED.get(family)
    if supported is None:
        family, supported = "chrome", _PRIMP_SUPPORTED["chrome"]
    if not major:
        chosen = supported[-1]
    else:
        chosen = min(supported, key=lambda s: abs(s - major))

    if "_android" in low or low.endswith("android"):
        os_name = "android"
    elif "_ios" in low or "ios" in low:
        os_name = "ios"
    elif family == "safari":
        os_name = "macos"
    else:
        os_name = "windows"

    return f"{family}_{chosen}", os_name


class PrimpImpersonationTransport:
    """Real browser TLS/JA3 + HTTP/2 fingerprinting via ``primp`` (optional dep)."""

    def __init__(self, impersonate: str) -> None:
        try:
            import primp  # noqa: F401
        except Exception as ex:  # broken/partial native install also lands here
            raise MissingRequirementsError(
                "impersonate=%r requires the optional 'primp' backend. "
                "Install it with `pip install llm4free[impersonate]`, or use "
                "backend='stdlib' for the header-only engine." % impersonate
            ) from ex
        self._impersonate = impersonate
        self._name, self._os = _map_target(impersonate)

    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        import primp

        client_kwargs: dict[str, Any] = {
            "impersonate": self._name,
            "impersonate_os": self._os,
            "follow_redirects": False,  # the client layer owns redirects
            "verify": bool(verify),
            "cookie_store": False,
            "referer": False,
        }
        if proxy is not None:
            client_kwargs["proxy"] = _proxy_url(proxy)
        if timeout.connect is not None:
            client_kwargs["connect_timeout"] = timeout.connect
        if timeout.read is not None:
            client_kwargs["read_timeout"] = timeout.read

        headers = _browser_headers(request.headers)
        if headers:
            client_kwargs["headers"] = headers

        client = primp.Client(**client_kwargs)

        body = _body_bytes(request.body)
        call_kwargs: dict[str, Any] = {
            "method": request.method,
            "url": request.url,
            "content": body,
            "stream": stream,
        }

        try:
            resp = client.request(**call_kwargs)
        except primp.TimeoutError as ex:
            raise HTTPTimeoutError(str(ex)) from ex
        except (primp.ConnectError, primp.DNSError, primp.DNSTimeoutError) as ex:
            raise ConnectError(str(ex)) from ex
        except primp.PrimpError as ex:
            raise (ReadError(str(ex)) if stream else HTTPError(str(ex))) from ex

        return _adapt(resp, request.url, stream)

    def close(self) -> None:
        return None


class StdImpersonationTransport:
    """Pure-stdlib impersonation: real, correctly *ordered* browser headers.

    Beats header-order / header-set based bot checks. It cannot fake the TLS
    ClientHello (JA3) or HTTP/2 fingerprint — install the optional ``primp``
    backend (``llm4free[impersonate]``) for fingerprint walls such as Cloudflare.
    """

    def __init__(self, impersonate: str) -> None:
        self._impersonate = impersonate
        self._inner = SyncStdTransport()

    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        from .browser_profiles import apply_profile

        headers = apply_profile(request.headers, self._impersonate)
        spec = RequestSpec(
            method=request.method, url=request.url, headers=headers, body=request.body
        )
        return self._inner.handle(
            spec, timeout=timeout, verify=verify, proxy=proxy, stream=stream
        )

    def close(self) -> None:
        return None


# Synthetic values the plain client stamps on every request. primp supplies the
# real browser versions, so drop these before handing headers to the backend.
_SYNTHETIC: dict[str, str] = {
    "user-agent": "llm4free-http/1.0 (+stdlib)",
    "connection": "close",
    "accept-encoding": "gzip, deflate",
    "accept": "*/*",
}


def _browser_headers(headers: Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in headers.items():
        if _SYNTHETIC.get(name.lower()) == value:
            continue
        out[name] = value
    return out


def _body_bytes(body: Any) -> Any:
    if body is None:
        return None
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return b"".join(body)


def _proxy_url(proxy: ProxyInfo) -> str:
    auth = ""
    if proxy.username is not None:
        auth = f"{proxy.username}:{proxy.password or ''}@"
    return f"{proxy.scheme}://{auth}{proxy.host}:{proxy.port}"


def _adapt(resp: Any, url: str, stream: bool) -> Response:
    from ..models import Cookies

    headers = Headers(dict(resp.headers)) if resp.headers is not None else Headers()
    cookies_obj = Cookies(dict(resp.cookies)) if resp.cookies is not None else Cookies()

    body_iter = None
    content = None
    if stream:
        def _chunks() -> Any:
            try:
                for chunk in resp.iter_bytes():
                    yield chunk if isinstance(chunk, bytes) else str(chunk).encode()
            finally:
                closer = getattr(resp, "close", None)
                if callable(closer):
                    closer()

        body_iter = _chunks()
    else:
        content = resp.content

    return Response(
        status_code=resp.status_code,
        reason="",
        headers=headers,
        url=resp.url if isinstance(getattr(resp, "url", None), str) else url,
        cookies=cookies_obj,
        content=content,
        stream=body_iter,
    )


def _primp_factory(impersonate: str) -> SyncTransport:
    return PrimpImpersonationTransport(impersonate)


def _stdlib_factory(impersonate: str) -> SyncTransport:
    return StdImpersonationTransport(impersonate)


# Register the built-in backends under stable names.
register_sync_backend("primp", _primp_factory)
register_sync_backend("stdlib", _stdlib_factory)


def get_sync_transport(impersonate: str | None, *, backend: str = "primp") -> SyncTransport:
    """Pick the transport for ``impersonate``.

    ``backend`` controls the choice:

    * ``"primp"`` (default) — real TLS/JA3 impersonation when ``primp`` is
      installed, otherwise a transparent fallback to the stdlib header engine.
    * ``"stdlib"`` — always the pure-stdlib ordered-header engine.
    * any other name — looked up in the backend registry.
    """
    if impersonate is None:
        return SyncStdTransport()
    target = normalize_browser_type(impersonate) or impersonate

    if backend == "stdlib":
        return StdImpersonationTransport(target)
    if backend == "primp":
        # Prefer the real TLS/JA3 backend when primp imports cleanly; a missing
        # *or* broken install transparently degrades to the ordered-header
        # stdlib engine instead of raising.
        try:
            return PrimpImpersonationTransport(target)
        except MissingRequirementsError:
            return StdImpersonationTransport(target)

    factory = _registry.get(backend)
    if factory is None:  # pragma: no cover - misconfiguration
        raise MissingRequirementsError(f"No impersonation backend named {backend!r}")
    return factory(target)


__all__ = [
    "get_sync_transport",
    "register_sync_backend",
    "PrimpImpersonationTransport",
    "StdImpersonationTransport",
    "KNOWN_TARGETS",
]
