"""Native CDP backend — speaks raw Chrome DevTools Protocol over our own
zero-dependency WebSocket client (:mod:`..native_ws` + :mod:`..native_cdp`).

One persistent browser-level connection drives any CDP-speaking engine:
* **lightpanda** — the ~40 MB Zig headless engine (started on demand);
* **chrome** — real/stealth Chrome with ``--disable-blink-features=
  AutomationControlled`` (Turnstile-capable headless).

Benefits over the CLI bridge: no per-command process spawn, single TCP
connection, millisecond-level evaluate latency, live CDP event stream, and
N sessions share ONE browser process via the refcounted pool (low RAM).
"""

from __future__ import annotations
from litprinter import ic

import asyncio
import random
from typing import Any, List, Optional

from ..browserproc import acquire, release
from ..native_cdp import CDPClient, CDPError
from ..proxy_auth import ProxySpec, parse_proxy
from ..stealth import STEALTH_INIT_JS
from .base import BaseBackend



class NativeCDPBackend(BaseBackend):
    """Generic CDP backend for lightpanda / Chrome / any CDP endpoint."""

    engine = "native"

    def __init__(
        self,
        session_id: str,
        engine: Optional[str] = None,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        launch_stealth_chrome: bool = False,
        mask_user_agent: bool = True,
        load_wait: float = 45.0,
        proxy: Optional[str] = None,
    ) -> None:
        """Configure the backend.

        Args:
            session_id: Cosmetic id carried over from the facade.
            engine: ``"chrome"`` or ``"lightpanda"`` (shared process pool key).
            host: CDP host to bind/connect.
            port: CDP port; ``None`` picks a free one for newly launched
                browsers, or adopts anything already listening.
            headless: Chrome launch mode (lightpanda is always headless).
            user_data_dir: persistent Chrome profile directory.
            mask_user_agent: try a CDP-level UA override (engine-dependent).
            load_wait: max seconds to wait for navigation loads/events.
            proxy: HTTP(S)/SOCKS proxy for the launched Chrome. Credentials are
                applied over CDP (``Fetch.authRequired``) so the in-page
                ``fetch`` used by anonymous providers egresses through it.

        Unused args are accepted for uniform registry construction.
        """
        self.session_id = session_id
        self.engine_name = "lightpanda" if (engine or "chrome") == "lightpanda" else "chrome"
        self.host = host
        self.port = port
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.mask_user_agent = mask_user_agent
        self.load_wait = load_wait
        self._proxy = proxy
        self._proxy_spec: Optional[ProxySpec] = parse_proxy(proxy)
        self._client: Optional[CDPClient] = None
        self._flat_session: Optional[str] = None
        self._target_id: Optional[str] = None
        self._current_url = ""
        self._ours = False
        self._console_buffer: List[str] = []
        self.network_requests: List[dict] = []
        self.network_responses: List[dict] = []
        self._dom_handle_cache: dict = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    @property
    def started(self) -> bool:
        return self._client is not None and self._client.connected

    async def start(self) -> None:
        """Launch/attach the engine, open a tab, enable domains.

        On any failure the process-pool lease is released again so a broken
        engine never leaks a browser process.
        """
        if self.started:
            return
        try:
            host, port, ours = await acquire(
                self.engine_name,
                self.host,
                self.port,
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                mask_user_agent=self.mask_user_agent,
                proxy=self._proxy,
            )
            self.host, self.port, self._ours = host, port, ours

            client = CDPClient(host, port)
            await client.connect()
            self._client = client
        except Exception:
            if self._ours:
                await release(self.host, self.port or 0, self.engine_name)
                self._ours = False
            raise

        target = await client.call("Target.createTarget", {"url": "about:blank"})
        self._target_id = target["targetId"]
        attached = await client.call(
            "Target.attachToTarget",
            {"targetId": self._target_id, "flatten": True},
        )
        self._flat_session = attached["sessionId"]

        sid = self._flat_session
        for enable in ("Runtime.enable", "Page.enable"):
            try:
                await client.call(enable, session_id=sid)
            except CDPError as e:
                ic(f"{enable} unsupported by {self.engine_name}: {e}")
        try:
            await client.call("Network.enable", session_id=sid)
        except CDPError:
            ic("Network.enable unavailable; request logging disabled")
        try:
            await client.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": STEALTH_INIT_JS},
                session_id=sid,
            )
        except CDPError:
            ic(f"stealth init script rejected by {self.engine_name}")

        # Mask the engine's own identity (e.g. lightpanda's ``Lightpanda/1.0``
        # HTTP header + sec-ch-ua) with a genuine Chrome UA.
        if self.mask_user_agent and self.engine_name == "lightpanda":
            from ..stealth import masked_chrome_user_agent

            ua = masked_chrome_user_agent()
            for method, params in (
                ("Network.setUserAgentOverride", {"userAgent": ua}),
                ("Emulation.setUserAgentOverride",
                 {"userAgent": ua, "platform": "Win32"}),
            ):
                try:
                    await client.call(method, params, session_id=sid)
                    break
                except CDPError:
                    continue

        # Route per-session events onto our buffers.
        client.on_event("Runtime.consoleAPICalled", self._console_sink)
        client.on_event("Network.requestWillBeSent", self._request_sink)
        client.on_event("Network.responseReceived", self._response_sink)

        if self._proxy_spec is not None:
            await self._setup_proxy_auth(client, sid)

    async def _setup_proxy_auth(self, client: CDPClient, sid: str) -> None:
        """Answer ``407`` proxy-auth challenges for ``--proxy-server`` auth.

        ``Fetch.enable`` with ``handleAuthRequests`` makes Chrome emit
        ``Fetch.authRequired`` instead of failing the request; we reply with
        ``Fetch.continueWithAuth`` (Basic credentials).

        * Credentialed proxy: a catch-all pattern (the Playwright-proven mode
          for proxy auth) so every request reaches our handlers — normal ones
          are resumed via ``Fetch.continueRequest``, challenges via
          ``continueWithAuth``.
        * Anonymous proxy: no patterns, so nothing is intercepted (``--proxy-server``
          alone routes the traffic) and there is no per-request overhead.

        Only applies to the Chrome engine.
        """
        if self.engine_name != "chrome" or self._proxy_spec is None:
            return
        spec = self._proxy_spec
        try:
            await client.call(
                "Fetch.enable",
                {
                    "patterns": (
                        [{"urlPattern": "*"}] if spec.requires_auth else []
                    ),
                    "handleAuthRequests": True,
                },
                session_id=sid,
            )
        except CDPError as e:
            ic(f"Fetch.enable failed for proxy auth: {e}")
            return

        async def _on_auth_required(event: dict) -> None:
            if not self._own(event):
                return
            request_id = (event.get("params") or {}).get("requestId")
            if not request_id:
                return
            try:
                await client.call(
                    "Fetch.continueWithAuth",
                    {
                        "requestId": request_id,
                        "authChallengeResponse": {
                            "response": "ProvideCredentials",
                            "username": spec.username,
                            "password": spec.password,
                        },
                    },
                    session_id=sid,
                    timeout=30,
                )
            except Exception as e:  # noqa: BLE001 - best effort
                ic(f"proxy auth response failed: {e}")

        async def _on_request_paused(event: dict) -> None:
            if not self._own(event):
                return
            params = event.get("params") or {}
            request_id = params.get("requestId")
            if not request_id:
                return
            try:
                await client.call(
                    "Fetch.continueRequest",
                    {"requestId": request_id},
                    session_id=sid,
                    timeout=30,
                )
            except Exception:  # noqa: BLE001 - already handled/canceled
                pass

        client.on_event("Fetch.authRequired", _on_auth_required)
        client.on_event("Fetch.requestPaused", _on_request_paused)

    def _own(self, event: dict) -> bool:
        """Whether ``event`` belongs to this session's tab."""
        return self._flat_session is not None and event.get("sessionId") == self._flat_session

    async def _console_sink(self, event: dict) -> None:
        if not self._own(event):
            return
        params = event.get("params") or {}
        text = " ".join(
            str(arg.get("value", ""))
            for arg in params.get("args", [])
            if isinstance(arg, dict)
        )
        if text:
            self._console_buffer.append(text)

    async def _request_sink(self, event: dict) -> None:
        if not self._own(event):
            return
        params = event.get("params") or {}
        request = params.get("request") or {}
        self.network_requests.append(
            {"url": request.get("url"), "method": request.get("method"),
             "headers": request.get("headers"), "type": params.get("type")}
        )

    async def _response_sink(self, event: dict) -> None:
        if not self._own(event):
            return
        params = event.get("params") or {}
        response = params.get("response") or {}
        self.network_responses.append(
            {"url": response.get("url"), "status": response.get("status"),
             "headers": response.get("headers"), "type": params.get("type")}
        )

    # ------------------------------------------------------------------ #
    # Navigation & evaluation
    # ------------------------------------------------------------------ #
    async def navigate(self, url: str, force: bool = False) -> None:
        """Navigate to ``url`` and wait for the in-session load event."""
        if not self.started:
            await self.start()
        client = self._client
        if client is None or self._flat_session is None:
            raise RuntimeError("backend could not start")
        neutral = url.rstrip("/").split("?")[0]
        current = self._current_url.rstrip("/").split("?")[0]
        if current == neutral and not force:
            return
        sid = self._flat_session
        load: asyncio.Task = asyncio.ensure_future(
            client.wait_event(
                "Page.loadEventFired", timeout=self.load_wait, session_filter=sid
            )
        )
        try:
            await client.call(
                "Page.navigate", {"url": url}, session_id=sid, timeout=self.load_wait
            )
            try:
                await asyncio.wait_for(asyncio.shield(load), self.load_wait)
            except asyncio.TimeoutError:
                pass  # some SPAs never fire load; title polling is next
        finally:
            load.cancel()
        self._current_url = url
        # Small settle for late JS-driven rewrites (Turnstile iframes etc.).
        try:
            await self.wait_title_nonempty(3.0)
        except asyncio.TimeoutError:
            pass

    async def wait_title_nonempty(self, timeout: float) -> str:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            title = await self._eval_raw("document.title || ''")
            if title:
                return title
            await asyncio.sleep(0.05)
        return ""

    async def _eval_raw(self, expression: str, timeout: float = 60.0) -> Any:
        """Runtime.evaluate returning the plain ``result.value``."""
        client = self._client
        if client is None or self._flat_session is None:
            raise RuntimeError("backend not started")
        result = await client.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=self._flat_session,
            timeout=timeout,
        )
        payload = result or {}
        if payload.get("exceptionDetails"):
            detail = payload["exceptionDetails"].get("text", "evaluate failed")
            ic("evaluate_js error: %s", detail)
            return None
        return (payload.get("result") or {}).get("value")

    async def evaluate_js(self, expression: str) -> Any:
        if not self.started:
            await self.start()
        try:
            return await self._eval_raw(expression)
        except (CDPError, asyncio.TimeoutError) as e:
            ic(f"evaluate_js failed: {e}")
            return None

    async def evaluate_js_stdin(self, expression: str) -> Any:
        """Native sockets carry arbitrarily large payloads — same as eval."""
        return await self.evaluate_js(expression)

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    async def get_user_agent(self) -> str:
        return (await self.evaluate_js("navigator.userAgent")) or ""

    async def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        client = self._client
        if client is None or self._flat_session is None:
            return []
        urls = [self._current_url] if urls is None else urls
        payload = await client.call(
            "Network.getCookies", {"urls": urls},
            session_id=self._flat_session,
        )
        return payload.get("cookies", []) or []

    async def set_cookies(self, cookies: List[dict]) -> None:
        client = self._client
        if not cookies or client is None or self._flat_session is None:
            return
        await client.call(
            "Network.setCookies", {"cookies": cookies},
            session_id=self._flat_session,
        )

    async def get_title(self) -> str:
        return (await self.evaluate_js("document.title")) or ""

    # ------------------------------------------------------------------ #
    # Interaction
    # ------------------------------------------------------------------ #
    async def click(self, x: int = 200, y: int = 400) -> None:
        """Best-effort real mouse click; falls back to a DOM click."""
        try:
            if not self.started:
                await self.start()
            await self._dispatch_click(x, y)
        except Exception:
            await self.evaluate_js(
                f"(document.elementFromPoint({x},{y})||{{}}).click?.()"
            )

    async def _dispatch_click(self, x: int, y: int) -> None:
        client = self._client
        if client is None or self._flat_session is None:
            raise RuntimeError("backend not started")
        for press, button_type in (
            ("mousePressed", "mousePressed"),
            ("mouseReleased", "mouseReleased"),
        ):
            await client.call(
                "Input.dispatchMouseEvent",
                {
                    "type": button_type,
                    "x": x, "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
                session_id=self._flat_session,
            )

    async def click_selector(self, selector: str) -> None:
        if not self.started:
            await self.start()
        import json as _json

        quoted = _json.dumps(selector)
        script = (
            f"var els = document.querySelectorAll({quoted});"
            f"var el = els && els[0];"
            f"if (el && el.click) el.click(); (!!el) + ''"
        )
        await self.evaluate_js(script)

    async def mouse_move(self, x: int, y: int) -> None:
        client = self._client
        try:
            if client is None:
                raise RuntimeError("backend not started")
            await client.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": x, "y": y},
                session_id=self._flat_session,
            )
        except Exception:
            await self.evaluate_js(
                f"document.dispatchEvent(new MouseEvent('mousemove', "
                f"{{clientX:{x}, clientY:{y}}}))"
            )

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        delta = amount if direction == "down" else -amount
        await self.evaluate_js(f"window.scrollBy(0, {delta})")

    async def bypass_turnstile(self) -> None:
        await self.click(random.randint(150, 350), random.randint(300, 500))
        await self.mouse_move(random.randint(100, 400), random.randint(200, 500))
        await asyncio.sleep(0.2)

    # ------------------------------------------------------------------ #
    # Console streaming
    # ------------------------------------------------------------------ #
    async def install_console_capture(self) -> None:
        self._console_buffer.clear()
        await self.evaluate_js(
            "window.__llm4free_console = window.__llm4free_console || [];"
            "window.console.log = (function(orig){"
            "  return function(){"
            "    window.__llm4free_console.push(Array.prototype.join.call(arguments,' '));"
            "    orig.apply(console, arguments);"
            "  };"
            "})(window.console.log);"
        )

    async def poll_console(
        self, marker: str, timeout: float = 30.0, interval: float = 0.5
    ) -> Optional[str]:
        deadline = asyncio.get_event_loop().time() + timeout
        consumed = 0
        while asyncio.get_event_loop().time() < deadline:
            # Live CDP console events arrive instantly (no polling overhead).
            for line in self._console_buffer[consumed:]:
                consumed += 1
                if marker in line:
                    return line
            # Fallback to the in-page buffer (covers page-init logs).
            try:
                line = (await self.evaluate_js(expr_marker_scan(marker))) or ""
                for candidate in str(line).split("\n"):
                    if marker in candidate:
                        return candidate
            except Exception:
                pass
            await asyncio.sleep(interval)
        return None

    # ------------------------------------------------------------------ #
    # Events
    # ------------------------------------------------------------------ #
    async def wait_for_event(self, method: str, timeout: float = 30.0) -> dict:
        client = self._client
        if client is None or not self.started:
            return {}
        try:
            return await client.wait_event(
                method, timeout=timeout, session_filter=self._flat_session
            )
        except asyncio.TimeoutError:
            return {}

    def add_event_handler(self, method: str, destination: Any) -> None:
        if self._client is None:
            raise RuntimeError("backend not started; call start() first")
        if self._flat_session:
            def _wrap(event: dict, _destination=destination) -> None:
                if not self._own(event):
                    return
                if isinstance(_destination, list):
                    _destination.append(event["params"])
                elif hasattr(_destination, "put_nowait"):
                    _destination.put_nowait(event)
            self._client.on_event(method, _wrap)

    def remove_event_handler(self, method: str, destination: Any) -> None:
        if self._client is None:
            return
        self._client.off_event(method, destination)

    # ------------------------------------------------------------------ #
    # Shutdown
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        if self._target_id:
            try:
                await client.call(
                    "Target.closeTarget", {"targetId": self._target_id}, timeout=5
                )
            except Exception:
                pass
        sid = self._flat_session
        self._flat_session = None
        try:
            await client.close()
        finally:
            if self._ours:
                await release(self.host, self.port or 0, self.engine_name)


def expr_marker_scan(marker: str) -> str:
    """JS that scans the in-page console buffer for the marker."""
    import json as _json

    quoted = _json.dumps(marker)
    return f"(window.__llm4free_console||[]).join('\\n').split('\\n').find(l => l.indexOf({quoted}) !== -1) || null"


__all__ = ["NativeCDPBackend"]
