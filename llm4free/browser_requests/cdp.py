"""Modular, engine-agnostic CDP client for llm4free.

Public API (unchanged from the legacy single-file version):

* :class:`CDPSession`     — async browser session (engine selectable)
* :class:`SyncCDPSession` — sync wrapper around the same backend
* :func:`find_agent_browser`, :func:`stealth_plugin_env` — CLI helpers
* :func:`launch_stealth_chrome`, :func:`find_chrome_binary` — stealth utils
* :func:`find_lightpanda_path`, :func:`CDPClient` — new native pieces

Engines (select with ``CDPSession(engine=...)`` or
``LLM4FREE_BROWSER_ENGINE``):

* ``agent-browser`` — Chrome via the agent-browser CLI (legacy default).
  Stealth plugin clears Cloudflare Turnstile; ~100-300 ms per command.
* ``lightpanda``    — 40 MB native-speed Zig engine over our own CDP client.
  One persistent TCP/WS connection, ms-level evaluate latency.
* ``chrome``        — stealth real Chrome driven over our own CDP client
  (Turnstile-capable headless, ms-level latency).
* ``native``        — auto: lightpanda when headless & installed, else chrome.

All engines must-satisfy the common interface in
:mod:`llm4free.browser_requests.backends.base`; the process pool in
:mod:`llm4free.browser_requests.browserproc` shares one browser process
across concurrent sessions to keep RAM flat.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from .backends import create_backend, resolve_engine
from .backends.agentbrowser import (
    AgentBrowserBackend,
    _encode_js,
    encode_js,  # noqa: F401 - public alias
    find_agent_browser,
    stealth_plugin_env,
)
from .backends.base import BaseBackend
from .browserproc import (
    cdp_alive,
    ensure_running,
    find_chrome_binary,
    find_lightpanda_path,
    free_port,
    launch_lightpanda,
    launch_stealth_chrome,
)
from .native_cdp import CDPClient, CDPError
from .stealth import CHROME_UA_FORMAT, STEALTH_INIT_JS, masked_chrome_user_agent

logger = logging.getLogger(__name__)


class CDPSession:
    """Async browser session with pluggable engines.

    Args:
        port: External CDP port. When given, the session *connects* to an
            already-listening engine instead of spawning a new one
            (native backend — any CDP server incl. lightpanda/Chrome works).
        host: CDP bind host (default ``127.0.0.1``).
        user_data_dir: profile name (agent-browser ``--profile``) or Chrome
            user-data-dir (native backends).
        headless: Engine launch mode.
        launch_stealth_chrome: Force the stealth-Chrome native route
            (Turnstile resolving *headless*). Implies a real Chrome.
        engine: ``"agent-browser" | "lightpanda" | "chrome" | "native"``.
            ``None`` resolves via env / smart defaults (see resolve_engine).
    """

    def __init__(
        self,
        port: Optional[int] = None,
        host: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        launch_stealth_chrome: bool = False,
        engine: Optional[str] = None,
    ) -> None:
        self.headless = headless
        self.host = host or "127.0.0.1"
        self.port = port
        self.launch_stealth_chrome = launch_stealth_chrome
        self.user_data_dir = user_data_dir
        self.engine = resolve_engine(
            engine,
            headless=headless,
            launch_stealth_chrome=launch_stealth_chrome,
            port=port,
        )
        self.session_id: str = f"llm4free-{uuid.uuid4().hex[:12]}"
        plumbed_port = self.port if (self.engine != "agent-browser" or launch_stealth_chrome) else None
        self._backend = create_backend(
            self.engine,
            session_id=self.session_id,
            host=self.host,
            port=plumbed_port,
            user_data_dir=user_data_dir,
            headless=headless,
            launch_stealth_chrome=launch_stealth_chrome,
        )

    # -- passthrough of historically public attrs ---------------------- #
    @property
    def network_requests(self) -> List[dict]:
        return self._backend.network_requests

    @property
    def network_responses(self) -> List[dict]:
        return self._backend.network_responses

    @property
    def backend(self) -> BaseBackend:
        """Underlying engine backend (for advanced / diagnostic use)."""
        return self._backend

    # -- public API (dispatched to backend) ---------------------------- #
    async def start(self) -> None:
        """Open a blank page so the session/browser is ready."""
        await self._backend.start()

    async def navigate(self, url: str, force: bool = False) -> None:
        """Navigate to ``url`` unless already there (``force=True`` reloads)."""
        await self._backend.navigate(url, force=force)

    async def evaluate_js(self, expression: str) -> Any:
        """Execute JavaScript and return the value."""
        return await self._backend.evaluate_js(expression)

    async def evaluate_js_stdin(self, expression: str) -> Any:
        """Execute large JavaScript through the engine's large-input path."""
        return await self._backend.evaluate_js_stdin(expression)

    async def get_user_agent(self) -> str:
        return await self._backend.get_user_agent()

    async def get_cookies(self) -> Dict[str, str]:
        cookies = await self.get_cookies_list()
        return {c["name"]: c["value"] for c in cookies}

    async def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        return await self._backend.get_cookies_list(urls)

    async def set_cookies(self, cookies: List[dict]) -> None:
        await self._backend.set_cookies(cookies)

    async def get_title(self) -> str:
        return await self._backend.get_title()

    async def click(self, x: int = 200, y: int = 400) -> None:
        """Human focus click; useful for Turnstile-style checks."""
        await self._backend.click(x, y)

    async def click_selector(self, selector: str) -> None:
        await self._backend.click_selector(selector)

    async def mouse_move(self, x: int, y: int) -> None:
        await self._backend.mouse_move(x, y)

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        await self._backend.scroll(direction, amount)

    async def bypass_turnstile(self) -> None:
        """Anti-detect gestures that nudge the Turnstile widget to resolve."""
        await self._backend.click(200, 400)
        await self._backend.mouse_move(_rand(100, 400), _rand(200, 500))
        await asyncio.sleep(0.2)

    async def install_console_capture(self) -> None:
        await self._backend.install_console_capture()

    async def poll_console(
        self, marker: str, timeout: float = 30.0, interval: float = 0.5
    ) -> Optional[str]:
        return await self._backend.poll_console(marker, timeout, interval)

    async def wait_for_event(self, method: str, timeout: float = 30.0) -> dict:
        return await self._backend.wait_for_event(method, timeout)

    def add_event_handler(self, method: str, queue: Any) -> None:
        self._backend.add_event_handler(method, queue)

    def remove_event_handler(self, method: str, queue: Any) -> None:
        self._backend.remove_event_handler(method, queue)

    async def close(self) -> None:
        await self._backend.close()


def _rand(lo: int, hi: int) -> int:
    import random

    return random.randint(lo, hi)


class SyncCDPSession:
    """Synchronous mirror of :class:`CDPSession` (one background loop thread).

    The same backend implementations power both classes — no logic is
    duplicated. Thread tools (e.g. the DeepInfraFree Turnstile solver) can
    keep blocking calls: ``sess.evaluate_js(...)``, ``sess.close()``.
    """

    def __init__(
        self,
        port: int = 9222,
        host: str = "127.0.0.1",
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        launch_stealth_chrome: bool = False,
        engine: Optional[str] = None,
    ) -> None:
        self._async = CDPSession(
            port=port,
            host=host,
            user_data_dir=user_data_dir,
            headless=headless,
            launch_stealth_chrome=launch_stealth_chrome,
            engine=engine,
        )
        self.session_id = self._async.session_id
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    # -- private plumbing --------------------------------------------- #
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name=f"llm4free-cdp-{self.session_id}",
                daemon=True,
            )
            self._thread.start()
        return self._loop

    def _run(self, coro, timeout: float = 240.0) -> Any:
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    # -- legacy alias ---------------------------------------------------#
    def start_chrome(self) -> None:
        """Backwards-compatible alias for :meth:`start`."""
        self._run(self._async.start())

    start = start_chrome  # unified name

    # -- sync API --------------------------------------------------------#
    def navigate(self, url: str, force: bool = False) -> None:
        self._run(self._async.navigate(url, force=force))

    def evaluate_js(self, expression: str) -> Any:
        return self._run(self._async.evaluate_js(expression))

    def evaluate_js_stdin(self, expression: str) -> Any:
        return self._run(self._async.evaluate_js_stdin(expression))

    def get_user_agent(self) -> str:
        return self._run(self._async.get_user_agent())

    def get_cookies(self) -> Dict[str, str]:
        return self._run(self._async.get_cookies())

    def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        return self._run(self._async.get_cookies_list(urls))

    def set_cookies(self, cookies: List[dict]) -> None:
        self._run(self._async.set_cookies(cookies))

    def get_title(self) -> str:
        return self._run(self._async.get_title())

    def click(self, x: int = 200, y: int = 400) -> None:
        self._run(self._async.click(x, y))

    def click_selector(self, selector: str) -> None:
        self._run(self._async.click_selector(selector))

    def mouse_move(self, x: int, y: int) -> None:
        self._run(self._async.mouse_move(x, y))

    def scroll(self, direction: str = "down", amount: int = 300) -> None:
        self._run(self._async.scroll(direction, amount))

    def bypass_turnstile(self) -> None:
        self._run(self._async.bypass_turnstile())

    def install_console_capture(self) -> None:
        self._run(self._async.install_console_capture())

    def poll_console(self, marker: str, timeout: float = 30.0,
                     interval: float = 0.5) -> Optional[str]:
        return self._run(self._async.poll_console(marker, timeout, interval))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._run(self._async.close())
        finally:
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=10)


__all__ = [
    "CDPSession",
    "SyncCDPSession",
    "CDPClient",
    "CDPError",
    "AgentBrowserBackend",
    "find_agent_browser",
    "stealth_plugin_env",
    "encode_js",
    "launch_stealth_chrome",
    "launch_lightpanda",
    "find_chrome_binary",
    "find_lightpanda_path",
    "cdp_alive",
    "free_port",
    "ensure_running",
    "CHROME_UA_FORMAT",
    "STEALTH_INIT_JS",
    "masked_chrome_user_agent",
]

# Kept so tests that patch ``cdp_module.subprocess.run`` keep working.
import subprocess  # noqa: E402,F401  (test patching surface)
