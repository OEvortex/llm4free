"""Native Chrome DevTools Protocol (CDP) client with zero dependencies.

Built on :class:`.native_ws.WsConnection`. One persistent browser-level
WebSocket carries every tab's traffic (CDP "flat sessions"), which is
exactly the topology Lightpanda and modern Chrome both expose — one TCP
connection for the whole browser means:
* no per-tab sockets (lower RAM),
* a single event dispatch thread (lower latency),
* reconnects are one TCP handshake (fast failover).

Events are dispatched to registered handlers; commands are matched to
in-flight futures by id. Both directions are JSON only.
"""

from __future__ import annotations
from litprinter import ic

import asyncio
import itertools
import json
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from .native_ws import WsConnection, WebSocketError


EventDestination = Union[
    "asyncio.Queue[Dict[str, Any]]",
    "queue.Queue[Dict[str, Any]]",
    List,
    Callable[[Dict[str, Any]], Any],
]

import queue  # noqa: E402  (used in typing + isinstance checks)


class CDPError(Exception):
    """A CDP command returned an error object."""

    def __init__(self, message: str, method: str = "", code: int = 0) -> None:
        super().__init__(message)
        self.method = method
        self.code = code


def discover_ws_path(host: str, port: int, timeout: float = 3.0) -> Optional[str]:
    """Read ``/json/version`` and return the WS path of the browser socket.

    Chrome exposes the browser-level socket under
    ``/devtools/browser/<uid>``, whereas lightpanda serves it at ``/``.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/json/version", timeout=timeout
        ) as resp:
            info = json.loads(resp.read())
        url = info.get("webSocketDebuggerUrl", "")
        urlparse = url.split("://", 1)[-1] if url else ""
        if urlparse and "/" in urlparse:
            return "/" + urlparse.split("/", 1)[1]
    except Exception:
        pass
    return None


class CDPClient:
    """Asynchronous browser-level CDP client (flat sessions, event routing)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9222,
                 ws_path: Optional[str] = None) -> None:
        self.host = host
        self.port = port
        self.ws_path = ws_path  # None → try "/" then discover
        self._ws = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._handlers: Dict[str, List[EventDestination]] = {}
        self._listener: Optional[asyncio.Task] = None
        self._id = itertools.count(1)
        self._closing = False

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    @property
    def connected(self) -> bool:
        return self._listener is not None and not self._listener.done()

    async def connect(self, timeout: float = 10.0) -> None:
        """Open the WebSocket (with brief retries) and start the receive loop.

        Some engines (e.g. lightpanda) answer ``/json/version`` moments
        before their WebSocket router is live, so a first ``/`` upgrade can
        fail; others (Chrome) serve the browser socket under a discovered
        ``/devtools/browser/<uid>`` path. We retry ``/`` briefly and fall
        back to ``/json/version`` discovery.
        """
        if self.connected:
            return
        last_error: Optional[Exception] = None
        for attempt in range(6):
            path = self.ws_path or "/"
            self._ws = WsConnection(self.host, self.port)
            try:
                await self._ws.connect(timeout, path)
                break
            except WebSocketError as e:
                last_error = e
                transient = "upgrade refused" in str(e)
                if not transient:
                    raise
                if attempt == 2 and not self.ws_path:
                    # Stop hammering "/" — perhaps this engine keeps its
                    # browser socket at a discovered path (Chrome-style).
                    import urllib.request

                    try:
                        with urllib.request.urlopen(
                            f"http://{self.host}:{self.port}/json/version",
                            timeout=3,
                        ) as resp:
                            info = json.loads(resp.read())
                        url = info.get("webSocketDebuggerUrl") or ""
                        if "//" in url:
                            tail = url.split("://", 1)[1].split("/", 1)
                            if len(tail) == 2 and tail[1]:
                                self.ws_path = "/" + tail[1]
                            else:
                                self.ws_path = "/"
                    except Exception:
                        pass
                await asyncio.sleep(0.25 + 0.1 * attempt)
        else:  # no break — every attempt failed
            raise last_error  # type: ignore[misc]
        self._closing = False
        self._listener = asyncio.ensure_future(self._receive_loop())
        ic("CDPClient connected to %s:%s", self.host, self.port)

    async def close(self) -> None:
        """Detach the listener and close the socket."""
        self._closing = True
        listener = self._listener
        self._listener = None
        if listener is not None and not listener.done():
            listener.cancel()
            try:
                await listener
            except (Exception, asyncio.CancelledError):  # noqa: BLE001 - teardown best effort
                pass
        await self._ws.close() if self._ws is not None else None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(WebSocketError("CDP connection closed"))
        self._pending.clear()
        ic("CDPClient disconnected (%s:%s)", self.host, self.port)

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    async def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Send a CDP command and await its result.

        Args:
            method: e.g. ``"Page.navigate"``.
            params: method parameters.
            session_id: flat-session id for tab-specific commands.
            timeout: seconds to wait for the response.

        Returns:
            The ``result`` object from the CDP response.

        Raises:
            CDPError: when the response carries an ``error`` object.
        """
        pending_ws = self._ws
        if not self.connected or pending_ws is None:
            raise WebSocketError("CDPClient is not connected")
        message = {"id": next(self._id), "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[message["id"]] = fut
        try:
            await pending_ws.send_text(json.dumps(message))
            payload = await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(message["id"], None)
        if payload.get("error"):
            err = payload["error"]
            raise CDPError(str(err.get("message", err)), method, err.get("code", 0))
        return payload.get("result") or {}

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    def on_event(self, method: str, destination: EventDestination) -> None:
        """Route ``method`` events to a queue/list/callback."""
        self._handlers.setdefault(method, []).append(destination)

    def off_event(self, method: str, destination: EventDestination) -> None:
        """Remove a previously registered event destination."""
        handlers = self._handlers.get(method)
        if handlers and destination in handlers:
            handlers.remove(destination)
            if not handlers:
                self._handlers.pop(method, None)

    async def wait_event(
        self,
        method: str,
        predicate: Optional[Callable[[Dict[str, Any]], bool]] = None,
        timeout: float = 25.0,
        session_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Await the next ``method`` event (optionally filtered).

        Args:
            method: CDP event name, e.g. ``"Page.loadEventFired"``.
            predicate: optional callable returning True on the wanted event.
            timeout: seconds to wait before raising ``asyncio.TimeoutError``.
            session_filter: only accept events whose ``sessionId`` matches.
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        def _dispatch(event: Dict[str, Any]) -> None:
            if (session_filter is None or event.get("sessionId") == session_filter) \
                    and (predicate is None or predicate(event.get("params") or {})):
                if not fut.done():
                    fut.set_result(event.get("params") or {})

        self.on_event(method, _dispatch)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self.off_event(method, _dispatch)

    async def _receive_loop(self) -> None:
        """Route incoming JSON messages: ids -> futures, methods -> events."""
        ws = self._ws
        try:
            while ws is not None:
                text = await ws.recv_text(timeout=3600)
                if self._closing:
                    break
                obj = json.loads(text)
                if isinstance(obj, dict) and obj.get("id") in self._pending:
                    fut = self._pending.pop(obj["id"])
                    if not fut.done():
                        fut.set_result(obj)
                elif isinstance(obj, dict) and "method" in obj:
                    self._dispatch_event(obj)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # connection failure floods pending futures
            if not self._closing:
                ic("CDP reader loop ended: %s", e)
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(WebSocketError(f"connection lost: {e}"))
            self._pending.clear()

    def _dispatch_event(self, obj: Dict[str, Any]) -> None:
        handlers = self._handlers.get(obj["method"])
        if not handlers:
            return
        event = {"method": obj["method"], "params": obj.get("params") or {},
                 "sessionId": obj.get("sessionId")}
        for destination in list(handlers):
            try:
                if isinstance(destination, asyncio.Queue) or isinstance(destination, queue.Queue):
                    destination.put_nowait(event)
                elif isinstance(destination, list):
                    destination.append(event["params"])
                elif callable(destination):
                    result = destination(event)
                    if asyncio.iscoroutine(result):
                        asyncio.get_event_loop().create_task(result)
            except Exception as e:  # noqa: BLE001 - one bad handler must not kill the loop
                ic("CDP event handler error for %s: %s", obj["method"], e)


__all__ = ["CDPClient", "CDPError", "WebSocketError"]
