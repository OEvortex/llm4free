
import asyncio
import base64
import json
import logging
import os
import random
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# agent-browser discovery & subprocess backend
# --------------------------------------------------------------------------- #
def find_agent_browser() -> str:
    """Locate the ``agent-browser`` executable on PATH.

    Returns:
        Absolute path to the ``agent-browser`` binary.

    Raises:
        RuntimeError: If the binary cannot be found.
    """
    env_path = os.environ.get("LLM4FREE_AGENT_BROWSER")
    if env_path and os.path.exists(env_path):
        return env_path
    found = shutil.which("agent-browser")
    if found:
        return found
    # Common global npm install location fallback.
    found = shutil.which("npx")
    if found:
        return found
    raise RuntimeError(
        "agent-browser CLI not found. Install it with: npm i -g agent-browser && agent-browser install"
    )


def _run_agent_browser(
    session_id: Optional[str],
    *args: str,
    headless: bool = True,
    timeout: int = 120,
    use_npx: bool = False,
) -> str:
    """Run an ``agent-browser`` command and return its stdout.

    Args:
        session_id: Isolated session id, or ``None`` for the default session.
        *args: Subcommand and its arguments (e.g. ``"open", "https://..."``).
        headless: Whether to run headless (ignored when a session already runs).
        timeout: Process timeout in seconds.
        use_npx: Internal - whether the binary path is ``npx`` (prefix cmd).

    Returns:
        Captured stdout text (stripped).

    Raises:
        RuntimeError: If the command exits non-zero or the CLI is missing.
    """
    binary = find_agent_browser()
    cmd: List[str] = []
    if use_npx:
        cmd = [binary, "agent-browser"]
    else:
        cmd = [binary]

    if session_id is not None:
        cmd += ["--session", session_id]
    if headless and "--headed" not in args:
        # agent-browser defaults to headless; nothing to add. Headed opt-in is
        # handled by callers passing headless=False which we surface below.
        pass
    cmd += list(args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"agent-browser CLI not found: {e}")
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"agent-browser command timed out: {' '.join(cmd)}") from e

    if proc.returncode != 0:
        raise RuntimeError(
            f"agent-browser failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def _run_agent_browser_json(
    session_id: Optional[str],
    *args: str,
    headless: bool = True,
    timeout: int = 120,
    use_npx: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run an ``agent-browser`` command that emits JSON and parse it."""
    if use_npx is None:
        use_npx = find_agent_browser().endswith("npx")
    out = _run_agent_browser(
        session_id, *args, "--json", headless=headless, timeout=timeout, use_npx=use_npx
    )
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        # Some commands print non-JSON on success; wrap loosely.
        return {"success": True, "data": {"raw": out}, "error": None}
    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(f"agent-browser error: {payload.get('error')}")
    return payload


def _encode_js(expression: str) -> List[str]:
    """Return agent-browser eval args for a JS expression (base64 for safety)."""
    b64 = base64.b64encode(expression.encode("utf-8")).decode("ascii")
    return ["eval", "-b", b64]


# --------------------------------------------------------------------------- #
# Async CDP session (backed by agent-browser)
# --------------------------------------------------------------------------- #
class CDPSession:
    """Async browser session backed by the ``agent-browser`` CLI.

    Suitable for streaming providers (Cloudflare, Perchance). Each instance
    owns an isolated ``agent-browser --session`` so concurrent providers do
    not interfere.
    """

    def __init__(
        self,
        port: Optional[int] = None,
        host: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
    ) -> None:
        """Initialize the session.

        Args:
            port: Ignored for the agent-browser backend (kept for API parity).
            host: Ignored for the agent-browser backend (kept for API parity).
            user_data_dir: Optional profile name passed as ``--profile``.
            headless: Whether to run the browser headless.
        """
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.session_id: str = f"llm4free-{uuid.uuid4().hex[:12]}"
        self._started = False
        self._console_buffer: List[str] = []

        # Network event loggers (kept for API parity; populated by navigate).
        self.network_requests: List[dict] = []
        self.network_responses: List[dict] = []

    async def _run(self, *args: str, timeout: int = 120) -> str:
        """Run an agent-browser command on a thread executor."""
        profile = ["--profile", self.user_data_dir] if self.user_data_dir else []
        args = tuple(profile) + args if profile else args
        return await asyncio.to_thread(
            _run_agent_browser,
            self.session_id,
            *args,
            headless=self.headless,
            timeout=timeout,
        )

    async def _run_json(self, *args: str, timeout: int = 120) -> Dict[str, Any]:
        """Run an agent-browser JSON command on a thread executor."""
        profile = ["--profile", self.user_data_dir] if self.user_data_dir else []
        args = tuple(profile) + args if profile else args
        use_npx = find_agent_browser().endswith("npx")
        return await asyncio.to_thread(
            _run_agent_browser_json,
            self.session_id,
            *args,
            headless=self.headless,
            timeout=timeout,
            use_npx=use_npx,
        )

    async def start(self) -> None:
        """Open a blank page so the session/browser is ready."""
        if self._started:
            return
        await self._run("open", "about:blank", timeout=60)
        self._started = True

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the network to settle."""
        if not self._started:
            await self.start()
        await self._run("open", url, timeout=60)
        # Wait for load; ignore timeout failures (page may already be ready).
        try:
            await self._run("wait", "--load", "networkidle", timeout=60)
        except RuntimeError as e:
            logger.warning(f"navigate wait failed for {url}: {e}")

    async def evaluate_js(self, expression: str) -> Any:
        """Execute JavaScript and return the value.

        Args:
            expression: JavaScript expression to evaluate.

        Returns:
            The returned value (parsed from JSON), or ``None``.
        """
        payload = await self._run_json(*_encode_js(expression), timeout=60)
        return (payload.get("data") or {}).get("result")

    async def get_user_agent(self) -> str:
        """Retrieve the current browser user agent."""
        ua = await self.evaluate_js("navigator.userAgent")
        return ua or ""

    async def get_cookies(self) -> Dict[str, str]:
        """Retrieve all cookies from the browser as a name->value dict."""
        cookies = await self.get_cookies_list()
        return {c["name"]: c["value"] for c in cookies}

    async def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        """Retrieve full cookie objects from the browser session."""
        payload = await self._run_json("cookies", timeout=60)
        return (payload.get("data") or {}).get("cookies", []) or []

    async def set_cookies(self, cookies: List[dict]) -> None:
        """Set cookies in the browser session."""
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name:
                continue
            args = ["cookies", "set", str(name), str(value)]
            if cookie.get("domain"):
                args += ["--domain", str(cookie["domain"])]
            await self._run(*args, timeout=30)

    async def get_title(self) -> str:
        """Retrieve the current page title (plain text)."""
        return await self._run("get", "title", timeout=30)

    async def click(self, x: int = 200, y: int = 400) -> None:
        """Give the page focus / interact to satisfy bot checks.

        agent-browser manages focus internally, so we click the document body
        (or the Turnstile widget if present) to register a human-like action.

        Args:
            x: Ignored (kept for API parity with raw CDP).
            y: Ignored (kept for API parity with raw CDP).
        """
        # Prefer clicking the Turnstile widget; fall back to body.
        try:
            await self._run("click", "iframe[id^='cf-chl-'], #challenge-stage, body", timeout=30)
        except RuntimeError:
            try:
                await self._run("click", "body", timeout=30)
            except RuntimeError:
                pass

    async def click_selector(self, selector: str) -> None:
        """Click a specific element by CSS selector via agent-browser.

        Args:
            selector: A CSS selector (or comma-separated list of fallbacks).
        """
        await self._run("click", selector, timeout=30)

    async def mouse_move(self, x: int, y: int) -> None:
        """Best-effort pointer gesture (no-op for the CLI backend)."""
        await self.evaluate_js(
            f"window.dispatchEvent(new MouseEvent('mousemove', {{clientX:{x}, clientY:{y}}}))"
        )

    async def scroll(self, direction: str = "down", amount: int = 300) -> None:
        """Scroll the page to mimic human behaviour during Turnstile solving."""
        await self._run("scroll", direction, str(amount), timeout=30)

    async def bypass_turnstile(self) -> None:
        """Execute anti-detect actions to bypass Cloudflare Turnstile.

        agent-browser already applies stealth at launch; here we add the
        human-like gestures (focus click + scroll) that help the challenge
        resolve quickly.
        """
        try:
            await self.click(200, 400)
        except RuntimeError:
            pass
        try:
            await self.scroll("down", random.randint(100, 300))
        except RuntimeError:
            pass
        await asyncio.sleep(0.2)

    async def poll_console(
        self, marker: str, timeout: float = 30.0, interval: float = 0.5
    ) -> Optional[str]:
        """Poll the page for a console line containing ``marker``.

        Providers that previously relied on the CDP ``Runtime.consoleAPICalled``
        event (e.g. Cloudflare) can call this in a loop to read streamed tokens
        that the in-page script emits via ``console.log``.

        Args:
            marker: Substring to look for in console output (e.g. ``"CF_CHUNK:"``).
            timeout: Maximum seconds to poll.
            interval: Seconds between polls.

        Returns:
            The first matching console line, or ``None`` on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = await self.evaluate_js(
                "(window.__llm4free_console||[]).slice(arguments[0]).join('\\n')"
            ) or ""
            if not isinstance(lines, str):
                lines = str(lines)
            for line in lines.split("\n"):
                if marker in line:
                    return line
            await asyncio.sleep(interval)
        return None

    async def install_console_capture(self) -> None:
        """Inject a console.log buffer so :meth:`poll_console` can read tokens.

        Call this once after ``navigate`` for providers that pipe streamed
        output through ``console.log`` (e.g. Cloudflare).
        """
        await self.evaluate_js(
            "window.__llm4free_console = window.__llm4free_console || [];"
            "window.console.log = (function(orig){"
            "  return function(){"
            "    window.__llm4free_console.push(Array.prototype.join.call(arguments,' '));"
            "    orig.apply(console, arguments);"
            "  };"
            "})(window.console.log);"
        )

    async def wait_for_event(self, method: str, timeout: float = 30.0) -> dict:
        """Backwards-compatible shim.

        The CLI backend has no live event stream. We approximate the common
        ``Page.loadEventFired`` wait with a short settle; other events return
        an empty dict. Prefer :meth:`poll_console` for streamed tokens.
        """
        if method == "Page.loadEventFired":
            try:
                await self._run("wait", "--load", "networkidle", timeout=int(timeout))
            except RuntimeError:
                pass
        return {}

    def add_event_handler(self, method: str, queue: Any) -> None:
        """Not supported on the CLI backend. Use :meth:`poll_console` instead."""
        logger.warning(
            "add_event_handler is a no-op on the agent-browser backend; "
            "use CDPSession.poll_console() for streamed output."
        )

    def remove_event_handler(self, method: str, queue: Any) -> None:
        """No-op companion to :meth:`add_event_handler`."""
        pass

    async def close(self) -> None:
        """Close the agent-browser session."""
        try:
            await self._run("close", timeout=30)
        except RuntimeError as e:
            logger.warning(f"agent-browser close failed: {e}")
        self._started = False


# --------------------------------------------------------------------------- #
# Sync CDP session (backed by agent-browser)
# --------------------------------------------------------------------------- #
class SyncCDPSession:
    """Synchronous browser session backed by the ``agent-browser`` CLI.

    Mirrors :class:`CDPSession` but blocks on each call. Run it from an async
    context via ``loop.run_in_executor()``. Used by the DeepInfraFree Turnstile
    solver.

    Requires: ``npm i -g agent-browser && agent-browser install``
    """

    def __init__(
        self,
        port: int = 9222,
        host: str = "127.0.0.1",
        user_data_dir: Optional[str] = None,
        headless: bool = False,
    ) -> None:
        """Initialize the sync session.

        Args:
            port: Ignored for the agent-browser backend (kept for API parity).
            host: Ignored for the agent-browser backend (kept for API parity).
            user_data_dir: Optional profile name.
            headless: Whether to run the browser headless (default False so the
                challenge widget is interactive).
        """
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.session_id: str = f"llm4free-{uuid.uuid4().hex[:12]}"
        self._started = False

        self.network_requests: List[dict] = []
        self.network_responses: List[dict] = []

    def _run(self, *args: str, timeout: int = 120) -> str:
        profile = ["--profile", self.user_data_dir] if self.user_data_dir else []
        return _run_agent_browser(
            self.session_id, *(tuple(profile) + args), headless=self.headless, timeout=timeout
        )

    def _run_json(self, *args: str, timeout: int = 120) -> Dict[str, Any]:
        profile = ["--profile", self.user_data_dir] if self.user_data_dir else []
        use_npx = find_agent_browser().endswith("npx")
        return _run_agent_browser_json(
            self.session_id,
            *(tuple(profile) + args),
            headless=self.headless,
            timeout=timeout,
            use_npx=use_npx,
        )

    def start_chrome(self) -> None:
        """Open a blank page so the session/browser is ready."""
        if self._started:
            return
        self._run("open", "about:blank", timeout=60)
        self._started = True

    def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the network to settle."""
        if not self._started:
            self.start_chrome()
        self._run("open", url, timeout=60)
        try:
            self._run("wait", "--load", "networkidle", timeout=60)
        except RuntimeError as e:
            logger.warning(f"navigate wait failed for {url}: {e}")

    def evaluate_js(self, expression: str) -> Any:
        """Execute JavaScript and return the value."""
        payload = self._run_json(*_encode_js(expression), timeout=60)
        return (payload.get("data") or {}).get("result")

    def get_user_agent(self) -> str:
        """Retrieve the current browser user agent."""
        return self.evaluate_js("navigator.userAgent") or ""

    def get_cookies(self) -> Dict[str, str]:
        """Retrieve all cookies as a name->value dict."""
        cookies = self.get_cookies_list()
        return {c["name"]: c["value"] for c in cookies}

    def get_cookies_list(self, urls: Optional[List[str]] = None) -> List[dict]:
        """Retrieve full cookie objects from the browser session."""
        payload = self._run_json("cookies", timeout=60)
        return (payload.get("data") or {}).get("cookies", []) or []

    def set_cookies(self, cookies: List[dict]) -> None:
        """Set cookies in the browser session."""
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not name:
                continue
            args = ["cookies", "set", str(name), str(value)]
            if cookie.get("domain"):
                args += ["--domain", str(cookie["domain"])]
            self._run(*args, timeout=30)

    def click(self, x: int = 200, y: int = 400) -> None:
        """Give the page focus to speed up Turnstile token generation."""
        try:
            self._run("click", "iframe[id^='cf-chl-'], #challenge-stage, body", timeout=30)
        except RuntimeError:
            try:
                self._run("click", "body", timeout=30)
            except RuntimeError:
                pass

    def click_selector(self, selector: str) -> None:
        """Click a specific element by CSS selector via agent-browser."""
        self._run("click", selector, timeout=30)

    def bypass_turnstile(self) -> None:
        """Anti-detect gestures to help the Turnstile challenge resolve."""
        self.click(200, 400)
        try:
            self._run("scroll", "down", str(random.randint(100, 300)), timeout=30)
        except RuntimeError:
            pass
        time.sleep(0.2)

    def close(self) -> None:
        """Close the agent-browser session."""
        try:
            self._run("close", timeout=30)
        except RuntimeError as e:
            logger.warning(f"agent-browser close failed: {e}")
        self._started = False
