"""Transport selection helpers (the seam callers use)."""

from __future__ import annotations

from .base import AsyncTransport, ProxyInfo, RequestSpec, SyncTransport, Timeout
from .browser_profiles import KNOWN_TARGETS, normalize_browser_type
from .impersonation import (
    PrimpImpersonationTransport,
    PrimpPlainTransport,
    StdImpersonationTransport,
    get_sync_transport,
)
from .std_async import AsyncTransportFromSync
from .std_sync import SyncStdTransport


def get_async_transport(
    impersonate: str | None = None, *, backend: str = "primp", http2: bool = False
) -> AsyncTransport:
    sync = get_sync_transport(impersonate, backend=backend, http2=http2)
    return AsyncTransportFromSync(sync)


__all__ = [
    "SyncTransport",
    "AsyncTransport",
    "RequestSpec",
    "ProxyInfo",
    "Timeout",
    "SyncStdTransport",
    "PrimpImpersonationTransport",
    "PrimpPlainTransport",
    "StdImpersonationTransport",
    "KNOWN_TARGETS",
    "normalize_browser_type",
    "get_sync_transport",
    "get_async_transport",
]
