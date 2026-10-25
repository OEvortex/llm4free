"""Impersonation transport seam.

Plain requests use the stdlib transport (zero dependencies). Two opt-in upgrades
route through ``primp`` (an *optional* extra, ``llm4free[impersonate]``):

* ``impersonate="chrome124"`` — real browser TLS/JA3 + HTTP/2 fingerprints for
  the fingerprint-sensitive scraping sites.
* ``http2=True`` (no impersonation) — plain HTTP/2 without any browser profile.

If ``primp`` is not installed, an impersonation request transparently degrades to
the stdlib ordered-header engine and an ``http2`` request degrades to HTTP/1.1,
instead of raising — so the optional dependency is genuinely optional.

This seam is the single integration point for swapping the impersonation engine
without touching any call site.
"""

from __future__ import annotations

import os
import re
import ssl
from typing import Any, Callable

from ....exceptions import MissingRequirementsError
from ..exceptions import ConnectError, HTTPError, ReadError
from ..exceptions import TimeoutError as HTTPTimeoutError
from ..models import Headers, Response
from .base import (
    CertType,
    ProxyInfo,
    RequestSpec,
    SyncTransport,
    Timeout,
    VerifyType,
)
from .browser_profiles import (
    KNOWN_TARGETS,
    normalize_browser_type,
)
from .std_sync import SyncStdTransport

SyncBackendFactory = Callable[[str], SyncTransport]

_registry: dict[str, SyncBackendFactory] = {}


def register_sync_backend(name: str, factory: SyncBackendFactory) -> None:
    _registry[name] = factory


def _primp_available() -> bool:
    try:
        import primp  # noqa: F401
    except Exception:  # broken/partial native install also lands here
        return False
    return True


# --- target -> primp name/os mapping --------------------------------------

# primp 2.x ships a narrow set of real fingerprints. Map the curl-style target
# names the call sites already pass onto the nearest supported primp target.
_PRIMP_SUPPORTED: dict[str, tuple[int, ...]] = {
    "chrome": (144, 145, 146),
    "edge": (144, 145, 146),
    "firefox": (140, 146),
    "safari": (26,),
}

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


class _PrimpBase:
    """Shared primp client construction with a per-config persistent cache.

    A ``primp.Client`` wraps a reqwest connection pool, so reusing one across
    requests (rather than rebuilding it per call) is what actually buys
    keep-alive. The cache is keyed on everything baked into the client at build
    time: proxy, TLS verification/CA, timeouts and the fingerprint/http2 flags.
    """

    _impersonate_name: str | None = None
    _impersonate_os: str | None = None
    _http2: bool = False

    def __init__(self) -> None:
        try:
            import primp
        except Exception as ex:  # broken/partial native install also lands here
            raise MissingRequirementsError(
                "the primp transport requires the optional 'primp' backend. "
                "Install it with `pip install llm4free[impersonate]`, or use "
                "backend='stdlib' for the header-only engine."
            ) from ex
        self._primp = primp
        self._clients: dict[tuple, Any] = {}

    def _config_key(
        self, timeout: Timeout, verify: VerifyType, cert: CertType, proxy: ProxyInfo | None
    ) -> tuple:
        return (
            timeout.connect, timeout.read,
            _verify_key(verify), _cert_key(cert),
            _proxy_key(proxy),
        )

    def _build_client(
        self, timeout: Timeout, verify: VerifyType, cert: CertType, proxy: ProxyInfo | None
    ) -> Any:
        kwargs: dict[str, Any] = {
            "follow_redirects": False,  # the client layer owns redirects
            "cookie_store": False,
            "referer": False,
        }
        if self._impersonate_name is not None:
            kwargs["impersonate"] = self._impersonate_name
            kwargs["impersonate_os"] = self._impersonate_os
        if self._http2:
            kwargs["http2_only"] = True

        # TLS verification / custom CA bundle.
        if verify is False:
            kwargs["verify"] = False
        elif isinstance(verify, (str, os.PathLike)):
            kwargs["verify"] = True
            kwargs["ca_cert_file"] = os.fspath(verify)
        else:
            kwargs["verify"] = True

        # ``cert`` (mTLS client certificate) is not a primp option; the stdlib
        # transport handles it. Here it is intentionally ignored.
        if proxy is not None:
            kwargs["proxy"] = _proxy_url(proxy)
        if timeout.connect is not None:
            kwargs["connect_timeout"] = timeout.connect
        if timeout.read is not None:
            kwargs["read_timeout"] = timeout.read
        return self._primp.Client(**kwargs)

    def _client_for(
        self, timeout: Timeout, verify: VerifyType, cert: CertType, proxy: ProxyInfo | None
    ) -> Any:
        key = self._config_key(timeout, verify, cert, proxy)
        client = self._clients.get(key)
        if client is None:
            client = self._build_client(timeout, verify, cert, proxy)
            self._clients[key] = client
        return client

    def _headers_for(self, headers: Headers) -> dict[str, str]:
        impersonating = self._impersonate_name is not None
        out: dict[str, str] = {}
        for name, value in headers.items():
            low = name.lower()
            if low in _FORBIDDEN:
                continue  # reqwest/primp owns these; passing them is an error
            if impersonating and _SYNTHETIC.get(low) == value:
                continue  # let primp supply the real browser value
            out[name] = value
        return out

    def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: VerifyType,
        cert: CertType = None,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        client = self._client_for(timeout, verify, cert, proxy)
        headers = self._headers_for(request.headers)
        call_kwargs: dict[str, Any] = {
            "method": request.method,
            "url": request.url,
            "content": _body_bytes(request.body),
            "stream": stream,
        }
        if headers:
            call_kwargs["headers"] = headers

        primp = self._primp
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
        self._clients.clear()


class PrimpImpersonationTransport(_PrimpBase):
    """Real browser TLS/JA3 + HTTP/2 fingerprinting via ``primp`` (optional dep)."""

    def __init__(self, impersonate: str) -> None:
        super().__init__()
        self._impersonate = impersonate
        self._impersonate_name, self._impersonate_os = _map_target(impersonate)


class PrimpPlainTransport(_PrimpBase):
    """Plain HTTP/2 via ``primp`` with no browser fingerprint."""

    def __init__(self) -> None:
        super().__init__()
        self._http2 = True


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
        verify: VerifyType,
        cert: CertType = None,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Response:
        from .browser_profiles import apply_profile

        headers = apply_profile(request.headers, self._impersonate)
        spec = RequestSpec(
            method=request.method, url=request.url, headers=headers, body=request.body
        )
        return self._inner.handle(
            spec, timeout=timeout, verify=verify, cert=cert, proxy=proxy, stream=stream
        )

    def close(self) -> None:
        self._inner.close()


# Synthetic values the plain client stamps on every request. primp supplies the
# real browser versions, so drop these before handing headers to the backend.
_SYNTHETIC: dict[str, str] = {
    "user-agent": "llm4free-http/1.0 (+stdlib)",
    "connection": "keep-alive",
    "accept-encoding": "gzip, deflate",
    "accept": "*/*",
}

# Framing/authority headers reqwest computes itself; sending them raises
# "malformed headers". Always stripped before handing headers to primp.
_FORBIDDEN = frozenset({"connection", "host", "content-length", "transfer-encoding"})


def _body_bytes(body: Any) -> Any:
    if body is None:
        return None
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    return b"".join(body)


def _proxy_key(proxy: ProxyInfo | None) -> tuple | None:
    if proxy is None:
        return None
    return (proxy.scheme, proxy.host, proxy.port, proxy.username)


def _verify_key(verify: VerifyType) -> tuple:
    if isinstance(verify, ssl.SSLContext):
        return ("ctx", id(verify))
    if isinstance(verify, (str, os.PathLike)):
        return ("path", os.fspath(verify))
    return ("bool", bool(verify))


def _cert_key(cert: CertType) -> Any:
    if cert is None:
        return None
    if isinstance(cert, (str, os.PathLike)):
        return os.fspath(cert)
    return tuple(os.fspath(x) if isinstance(x, (str, os.PathLike)) else x for x in cert)


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


def get_sync_transport(
    impersonate: str | None, *, backend: str = "primp", http2: bool = False
) -> SyncTransport:
    """Pick the transport for ``impersonate`` / ``http2``.

    ``backend`` controls the choice:

    * ``"primp"`` (default) — real TLS/JA3 impersonation (or plain HTTP/2) when
      ``primp`` is installed; a missing/broken install degrades transparently to
      the stdlib engine rather than raising.
    * ``"stdlib"`` — always the pure-stdlib ordered-header engine (HTTP/1.1).
    * any other name — looked up in the backend registry.
    """
    if impersonate is None:
        if http2 and backend != "stdlib" and _primp_available():
            return PrimpPlainTransport()
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
    "PrimpPlainTransport",
    "StdImpersonationTransport",
    "KNOWN_TARGETS",
]
