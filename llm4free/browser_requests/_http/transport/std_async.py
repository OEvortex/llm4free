"""Async transport.

Rather than maintain a second, asyncio-specific copy of the HTTP/1.1 framing and
content-decoding parser (a large surface for subtle bugs), the async layer reuses
the synchronous transports and runs their blocking I/O on the default executor
thread-pool. Callers get a genuine ``await``-based API; the connection itself is
still opened, sent, and read by the single shared implementation.

Swapping in a true event-loop transport later only means providing a class with
``async def handle(...)`` — the client layer does not change.
"""

from __future__ import annotations

import asyncio
import functools
import ssl
from typing import Any

from .base import AsyncTransport, ProxyInfo, RequestSpec, SyncTransport, Timeout


class AsyncTransportFromSync(AsyncTransport):
    def __init__(self, sync: SyncTransport) -> None:
        self._sync = sync

    async def handle(
        self,
        request: RequestSpec,
        *,
        timeout: Timeout,
        verify: bool | ssl.SSLContext,
        proxy: ProxyInfo | None,
        stream: bool,
    ) -> Any:  # -> Response
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._sync.handle,
                request,
                timeout=timeout,
                verify=verify,
                proxy=proxy,
                stream=stream,
            ),
        )

    async def aclose(self) -> None:
        close = getattr(self._sync, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):  # pragma: no cover
                await result


__all__ = ["AsyncTransportFromSync"]
