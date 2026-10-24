"""agent-browser CLI backend — drives Chrome through the shipped Rust CLI.

This is the traditional llm4free path: one ``agent-browser`` subprocess call
per command. It is the *stealth workhorse* (the shipped ``launch.mutate``
plugin clears Cloudflare Turnstile) at the cost of per-command process/IPC
overhead (~100-300 ms). Use the native CDP backend when latency matters.
"""

from __future__ import annotations
from litprinter import ic

import asyncio
import base64
import json
import os
import random
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from .base import BaseBackend



def find_agent_browser() -> str:
    """Locate the ``agent-browser`` executable.

    Raises:
        RuntimeError: If the CLI cannot be found.
    """
    env_path = os.environ.get("LLM4FREE_AGENT_BROWSER")
    if env_path and os.path.exists(env_path):
        return env_path
    found = shutil.which("agent-browser")
    if found:
        return found
    found = shutil.which("npx")
    if found:
        return found
    raise RuntimeError(
        "agent-browser CLI not found. Install it with: npm i -g agent-browser"
    )


def stealth_plugin_env() -> Dict[str, str]:
    """Environment entries registering the llm4free stealth plugin."""
    plugin_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "agent_browser_stealth_plugin.py"
    )
    try:
        if not os.access(plugin_path, os.X_OK):
            os.chmod(plugin_path, 0o755)
    except OSError as e:
        ic(f"stealth plugin chmod failed: {e}")
    registry = json.dumps(
        [
            {
                "name": "llm4free-stealth",
                "command": plugin_path,
                "capabilities": ["launch.mutate"],
            }
        ]
    )
    return {"AGENT_BROWSER_PLUGINS": registry}


def _encode_js(expression: str) -> List[str]:
    """agent-browser eval args for a JS expression (base64 for safety)."""
    b64 = base64.b64encode(expression.encode("utf-8")).decode("ascii")
    return ["eval", "-b", b64]


encode_js = _encode_js  # public alias


class _CLI:
    """Thin synchronous wrappers around the agent-browser CLI."""

    @staticmethod
    def run(
        session_id: Optional[str],
        *args: str,
        headless: bool = True,
        timeout: int = 120,
        use_npx: bool = False,
        input_text: Optional[str] = None,
        user_data_dir: Optional[str] = None,
    ) -> str:
        binary = find_agent_browser()
        cmd: List[str] = []
        cmd = [binary, "agent-browser"] if use_npx else [binary]
        if session_id is not None:
            cmd += ["--session", session_id]
        if user_data_dir:
            cmd += ["--profile", user_data_dir]
        cmd += list(args)
        if not headless and "--headed" not in args:
            cmd += ["--headed"]
        try:
            proc = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, **stealth_plugin_env()},
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"agent-browser CLI not found: {e}")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"agent-browser timed out: {' '.join(cmd)}") from e
        if proc.returncode != 0:
            raise RuntimeError(
                f"agent-browser failed ({proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip()

    @staticmethod
    def run_json(
        session_id: Optional[str],
        *args: str,
        headless: bool = True,
        timeout: int = 120,
        use_npx: Optional[bool] = None,
        input_text: Optional[str] = None,
        user_data_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        if use_npx is None:
            use_npx = find_agent_browser().endswith("npx")
        out = _CLI.run(
            session_id,
            *args,
            "--json",
            headless=headless,
            timeout=timeout,
            use_npx=use_npx,
            input_text=input_text,
            user_data_dir=user_data_dir,
        )
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            return {"success": True, "data": {"raw": out}, "error": None}
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"agent-browser error: {payload.get('error')}")
        return payload

    @classmethod
    def connect_cdp(cls, session_id: str, host: str, port: int,
                    headless: bool = True, user_data_dir: Optional[str] = None) -> None:
        """Attach the CLI daemon to an existing CDP endpoint."""
        try:
            cls.run(session_id, "connect", str(port), headless=headless,
                    timeout=60, user_data_dir=user_data_dir)
        except RuntimeError:
            ic("agent-browser connect: already connected (ignored)")


class AgentBrowserBackend(BaseBackend):
    """Chrome-CDP-via-CLI backend (identical behavior to the legacy class)."""

    engine = "agent-browser"

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
        connect_timeout: int = 60,
    ) -> None:
        # engine/mask_user_agent are accepted for uniform registry
        # construction; the CLI always talks to Chrome.
        self.session_id = session_id
        self.host = host
        self.port = port
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.launch_stealth_chrome = launch_stealth_chrome
        self.connect_timeout = connect_timeout
        self._started = False
        self._connected = False
        self.network_requests: List[dict] = []
        self.network_responses: List[dict] = []
        self._console_buffer: List[str] = []

    # -- helpers ------------------------------------------------------ #
    def _cli_run(
        self, *args: str, timeout: int = 120, input_text: Optional[str] = None
    ) -> str:
        return _CLI.run(
            self.session_id,
            *args,
            headless=self.headless,
            timeout=timeout,
            input_text=input_text,
            user_data_dir=self.user_data_dir,
        )

    def _cli_json(
        self,
        *args: str,
        timeout: int = 120,
        input_text: Optional[str] = None,
        use_npx: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if use_npx is None:
            use_npx = find_agent_browser().endswith("npx")
        return _CLI.run_json(
            self.session_id,
            *args,
            headless=self.headless,
            timeout=timeout,
            use_npx=use_npx,
            input_text=input_text,
            user_data_dir=self.user_data_dir,
        )

    # -- lifecycle ---------------------------------------------------- #
    async def start(self) -> None:
        if self._started:
            return
        if self.port is not None:
            if not _cli_alive(self.host, self.port):
                raise RuntimeError(
                    f"No CDP endpoint reachable on {self.host}:{self.port}"
                )
            try:
                await asyncio.to_thread(
                    _CLI.run,
                    self.session_id,
                    "connect",
                    str(self.port),
                    headless=self.headless,
                    timeout=self.connect_timeout,
                    user_data_dir=self.user_data_dir,
                )
            except RuntimeError:
                pass  # maybe already connected
            self._connected = True
            self._started = True
            return
        if self.launch_stealth_chrome:
            raise RuntimeError(
                "launch_stealth_chrome requires the native backend with a port"
            )
        await asyncio.to_thread(
            self._cli_run, "open", "about:blank", timeout=self.connect_timeout
        )
        self._started = True

    # -- navigation / eval -------------------------------------------- #
    async def navigate(self, url: str, force: bool = False) -> None:
        if not self._started:
            await self.start()
        if not force:
            try:
                current = await asyncio.to_thread(self._cli_run, "get", "url", timeout=30)
            except RuntimeError:
                current = ""
            if current.rstrip("/").split("?")[0] == url.rstrip("/").split("?")[0]:
                return
        await asyncio.to_thread(self._cli_run, "open", url, timeout=60)
        try:
            await asyncio.to_thread(
                self._cli_run, "wait", "--load", "networkidle", timeout=60
            )
        except RuntimeError as e:
            ic(f"navigate wait failed for {url}: {e}")

    async def evaluate_js(self, expression: str) -> Any:
        payload = await asyncio.to_thread(
            self._cli_json, *_encode_js(expression), timeout=60
        )
        return (payload.get("data") or {}).get("result")

    async def evaluate_js_stdin(self, expression: str) -> Any:
        payload = await asyncio.to_thread(
            self._cli_json,
            "eval",
            "--stdin",
            timeout=120,
            input_text=expression,
        )
        return (payload.get("data") or {}).get("result")

    # -- data ---------------------------------------------------------- #
    async def get_user_agent(self) -> str:
        return (await self.evaluate_js("navigator.userAgent")) or ""

    async def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        payload = await asyncio.to_thread(self._cli_json, "cookies", timeout=60)
        return (payload.get("data") or {}).get("cookies", []) or []

    async def set_cookies(self, cookies: List[dict]) -> None:
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name:
                continue
            args = ["cookies", "set", str(name), str(value)]
            if cookie.get("domain"):
                args += ["--domain", str(cookie["domain"])]
            await asyncio.to_thread(self._cli_run, *args, timeout=30)

    async def get_title(self) -> str:
        return await asyncio.to_thread(self._cli_run, "get", "title", timeout=30)

    # -- interaction ---------------------------------------------------- #
    async def click(self, x: int = 200, y: int = 400) -> None:
        try:
            await asyncio.to_thread(
                self._cli_run,
                "click",
                "iframe[id^='cf-chl-'], #challenge-stage, body",
                timeout=30,
            )
        except RuntimeError:
            try:
                await asyncio.to_thread(self._cli_run, "click", "body", timeout=30)
            except RuntimeError:
                pass

    async def click_selector(self, selector: str) -> None:
        await asyncio.to_thread(self._cli_run, "click", selector, timeout=30)

    async def mouse_move(self, x: int, y: int) -> None:
        await self.evaluate_js(
            f"window.dispatchEvent(new MouseEvent('mousemove', "
            f"{{clientX:{x}, clientY:{y}}}))"
        )

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        await asyncio.to_thread(
            self._cli_run, "scroll", direction, str(amount), timeout=30
        )

    # -- console -------------------------------------------------------- #
    async def install_console_capture(self) -> None:
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
        while asyncio.get_event_loop().time() < deadline:
            lines = (
                await self.evaluate_js(
                    "(window.__llm4free_console||[]).slice(arguments[0]).join('\\n')"
                )
                or ""
            )
            for line in str(lines).split("\n"):
                if marker in line:
                    return line
            await asyncio.sleep(interval)
        return None

    # -- events ---------------------------------------------------------- #
    async def wait_for_event(self, method: str, timeout: float = 30.0) -> dict:
        if method == "Page.loadEventFired":
            try:
                await asyncio.to_thread(
                    self._cli_run, "wait", "--load", "networkidle",
                    timeout=int(timeout),
                )
            except RuntimeError:
                pass
        return {}

    def add_event_handler(self, method: str, destination: Any) -> None:
        ic(
            "add_event_handler is a no-op on the agent-browser backend; "
            "use poll_console() or the native backend for live events."
        )

    def remove_event_handler(self, method: str, destination: Any) -> None:
        pass

    # -- shutdown -------------------------------------------------------- #
    async def close(self) -> None:
        try:
            await asyncio.to_thread(self._cli_run, "close", timeout=30)
        except RuntimeError as e:
            ic(f"agent-browser close failed: {e}")
        self._started = False
        self._connected = False


def _cli_alive(host: str, port: int) -> bool:
    from ..browserproc import cdp_alive

    return cdp_alive(host, port)


__all__ = ["AgentBrowserBackend", "find_agent_browser", "stealth_plugin_env", "_encode_js", "encode_js"]
