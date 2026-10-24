import asyncio
import base64
import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
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
        "agent-browser CLI not found. Install it with: npm i -g agent-browser"
    )


def stealth_plugin_env() -> Dict[str, str]:
    """Environment entries registering the llm4free stealth plugin.

    The plugin (``agent_browser_stealth_plugin.py``, shipped next to this
    module) speaks the ``agent-browser.plugin.v1`` stdio protocol and mutates
    every *local* browser launch: ``--disable-blink-features=AutomationControlled``,
    a clean (non-``HeadlessChrome``) user agent, and a ``navigator.webdriver``
    mask init script. Together these let Cloudflare Turnstile resolve fully
    headless without any real-Chrome workaround.

    agent-browser reads ``AGENT_BROWSER_PLUGINS`` as a JSON registry override,
    so it must be present in the environment of the CLI calls that (may) spawn
    the daemon / start the browser.

    Returns:
        Extra environment variables to merge into ``subprocess.run`` ``env``
        when invoking the agent-browser CLI.
    """
    plugin_path = os.path.join(os.path.dirname(__file__), "agent_browser_stealth_plugin.py")
    try:
        if not os.access(plugin_path, os.X_OK):
            os.chmod(plugin_path, 0o755)
    except OSError as e:
        logger.debug(f"stealth plugin chmod failed: {e}")
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


def _run_agent_browser(
    session_id: Optional[str],
    *args: str,
    headless: bool = True,
    timeout: int = 120,
    use_npx: bool = False,
    input_text: Optional[str] = None,
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
    input_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Run an ``agent-browser`` command that emits JSON and parse it."""
    if use_npx is None:
        use_npx = find_agent_browser().endswith("npx")
    out = _run_agent_browser(
        session_id,
        *args,
        "--json",
        headless=headless,
        timeout=timeout,
        use_npx=use_npx,
        input_text=input_text,
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
# Stealth Chrome launcher (headless Turnstile support)
# --------------------------------------------------------------------------- #
_STEALTH_UA_FORMAT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
)


def find_chrome_binary() -> str:
    """Locate a real Chrome/Chromium binary for stealth mode.

    Search order: ``$LLM4FREE_CHROME_PATH``, common binaries on PATH, then
    the browser agent-browser installs under the Playwright cache.

    Raises:
        RuntimeError: If no Chrome/Chromium binary can be found.
    """
    env_path = os.environ.get("LLM4FREE_CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return found
    # agent-browser install fallback (chromium-<rev>/chrome-linux*/chrome).
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    if os.path.isdir(cache_dir):
        for entry in sorted(
            (e for e in os.listdir(cache_dir) if e.startswith("chromium-")),
            reverse=True,
        ):
            for sub in ("chrome-linux64", "chrome-linux", "chrome"):
                candidate = os.path.join(cache_dir, entry, sub, "chrome")
                if os.path.exists(candidate):
                    return candidate
    raise RuntimeError(
        "Chrome/Chromium not found for stealth mode. "
        "Install Chrome or set LLM4FREE_CHROME_PATH."
    )


def _chrome_user_agent(binary: str) -> str:
    """Realistic (HeadlessChrome-free) user agent string for the launch flag."""
    try:
        version_out = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        version_out = ""
    match = re.search(r"(\d+)\.", version_out)
    major = match.group(1) if match else "131"
    return _STEALTH_UA_FORMAT.format(major=major)


def _chrome_cdp_alive(host: str, port: int) -> bool:
    """Check whether a CDP endpoint already answers on ``host:port``."""
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/json/version", timeout=1
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def launch_stealth_chrome(
    port: int = 9222,
    host: str = "127.0.0.1",
    user_data_dir: Optional[str] = None,
    headless: bool = True,
) -> Tuple[Any, Optional[str]]:
    """Launch a real Chrome optimized to pass Cloudflare Turnstile headless.

    The critical parts are a *genuine* Chrome process (not driverless
    shell) with ``--disable-blink-features=AutomationControlled`` so
    ``navigator.webdriver`` is ``false``, a non-"HeadlessChrome" user
    agent, and ``--headless=new`` semantics. Turnstile then clears by
    itself in seconds without any clicking.

    Args:
        port: CDP ``--remote-debugging-port`` to listen on.
        host: Bind host (default ``127.0.0.1`` only).
        user_data_dir: Optional persistent profile directory; a throwaway
            temp profile is created otherwise.
        headless: Launch in ``--headless=new`` mode (default).

    Returns:
        ``(process, profile_dir_or_None)`` — the ``Popen`` handle so the
        caller can terminate the browser later.
    """
    if _chrome_cdp_alive(host, port):
        # A CDP-capable Chrome already runs on this port: reuse it.
        return None, None

    binary = find_chrome_binary()
    flags = [
        binary,
        f"--remote-debugging-port={port}",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1366,768",
        f"--user-agent={_chrome_user_agent(binary)}",
    ]
    if headless:
        flags.append("--headless=new")

    profile_dir: Optional[str] = None
    if user_data_dir:
        profile_dir = user_data_dir
        flags.append(f"--user-data-dir={profile_dir}")
    elif headless:
        # Keep headless runs contained in an ephemeral profile.
        profile_dir = tempfile.mkdtemp(prefix="llm4free-chrome-")
        flags.append(f"--user-data-dir={profile_dir}")

    flags.append("about:blank")

    for attempt in range(5):
        proc = subprocess.Popen(
            flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                break  # crashed (e.g. port taken) — retry with a new profile
            if _chrome_cdp_alive(host, port):
                return proc, profile_dir
            time.sleep(0.5)
        if proc.poll() is None:
            proc.terminate()
        time.sleep(1.0)
    raise RuntimeError(f"Failed to launch stealth Chrome on port {port}")


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
        launch_stealth_chrome: bool = False,
    ) -> None:
        """Initialize the session.

        Args:
            port: External CDP port. When given, the session *connects* to
                a Chrome running there instead of spawning its own
                agent-browser browser. Pair with
                ``launch_stealth_chrome=True`` to auto-launch a stealth
                Chrome (headless Turnstile-capable).
            host: CDP bind host (default ``127.0.0.1``).
            user_data_dir: Optional profile name passed as ``--profile``
                (agent-browser mode) or used as ``--user-data-dir``
                (stealth Chrome mode).
            headless: Whether to run the browser headless (stealth Chrome
                uses ``--headless=new``; agent-browser mode passes
                ``--headed`` otherwise).
            launch_stealth_chrome: Auto-launch a real Chrome with
                ``--disable-blink-features=AutomationControlled`` and a
                clean user agent, then connect to it. This is what lets
                Cloudflare Turnstile resolve *headless*.
        """
        self.headless = headless
        self.host = host or "127.0.0.1"
        self.port = port if launch_stealth_chrome or port is not None else None
        self.launch_stealth_chrome = launch_stealth_chrome
        self.user_data_dir = user_data_dir
        self.session_id: str = f"llm4free-{uuid.uuid4().hex[:12]}"
        self._started = False
        self._connected = False
        self._chrome_proc: Optional[Any] = None
        self._chrome_profile: Optional[str] = None
        self._console_buffer: List[str] = []

        # Network event loggers (kept for API parity; populated by navigate).
        self.network_requests: List[dict] = []
        self.network_responses: List[dict] = []

    async def _run(self, *args: str, timeout: int = 120, input_text: Optional[str] = None) -> str:
        """Run an agent-browser command, optionally providing stdin."""
        profile = ["--profile", self.user_data_dir] if self.user_data_dir else []
        args = tuple(profile) + args if profile else args
        return await asyncio.to_thread(
            _run_agent_browser,
            self.session_id,
            *args,
            headless=self.headless,
            timeout=timeout,
            input_text=input_text,
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

    async def _launch_chrome(self) -> None:
        """Start the stealth Chrome process and register its handle."""
        if self._chrome_proc is not None:
            return
        if self._chrome_cdp_ready():
            return  # an external Chrome already listens on the port
        proc, profile_dir = await asyncio.to_thread(
            launch_stealth_chrome,
            self.port or 9222,
            self.host,
            self.user_data_dir,
            self.headless,
        )
        self._chrome_proc = proc
        self._chrome_profile = profile_dir

    def _chrome_cdp_ready(self) -> bool:
        if self.port is None:
            return False
        return _chrome_cdp_alive(self.host, self.port)

    async def start(self) -> None:
        """Open a blank page so the session/browser is ready.

        In stealth/connect mode this attaches agent-browser to a real
        Chrome process (launched if ``launch_stealth_chrome``), which is
        what lets Turnstile challenges clear headless.
        """
        if self._started:
            return
        if self.port is not None:
            if self.launch_stealth_chrome:
                await self._launch_chrome()
            if not self._chrome_cdp_ready():
                raise RuntimeError(
                    f"No CDP endpoint reachable on {self.host}:{self.port}"
                )
            try:
                await self._run("connect", str(self.port), timeout=60)
            except RuntimeError:
                # Maybe already connected for this session — fine.
                pass
            self._connected = True
            self._started = True
            return
        await self._run("open", "about:blank", timeout=60)
        self._started = True

    async def navigate(self, url: str, force: bool = False) -> None:
        """Navigate to a URL and wait for the network to settle.

        A navigation reloads the page, which aborts any in-flight challenge
        solve (e.g. Cloudflare Turnstile). By default the navigation is
        skipped when the browser already sits on ``url``; pass
        ``force=True`` to reload regardless.

        Args:
            url: Target URL.
            force: Force a reload even when already on ``url``.
        """
        if not self._started:
            await self.start()
        if not force:
            try:
                current = await self._run("get", "url", timeout=30)
            except RuntimeError:
                current = ""
            if current.rstrip("/").split("?")[0] == url.rstrip("/").split("?")[0]:
                return
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

    async def evaluate_js_stdin(self, expression: str) -> Any:
        """Execute a large JavaScript expression through agent-browser stdin."""
        payload = await self._run_json_stdin("eval", "--stdin", input_text=expression, timeout=120)
        return (payload.get("data") or {}).get("result")

    async def _run_json_stdin(
        self, *args: str, input_text: str, timeout: int = 120
    ) -> Dict[str, Any]:
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
            input_text=input_text,
        )

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
            lines = (
                await self.evaluate_js(
                    "(window.__llm4free_console||[]).slice(arguments[0]).join('\\n')"
                )
                or ""
            )
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
        """Close the agent-browser session (and any Chrome we launched)."""
        try:
            await self._run("close", timeout=30)
        except RuntimeError as e:
            logger.warning(f"agent-browser close failed: {e}")
        self._started = False
        self._connected = False

        proc = self._chrome_proc
        if proc is not None:
            self._chrome_proc = None
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception as e:
                logger.debug(f"stealth Chrome terminate failed: {e}")
        profile = self._chrome_profile
        if profile is not None:
            self._chrome_profile = None
            await asyncio.to_thread(shutil.rmtree, profile, True)


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
        launch_stealth_chrome: bool = False,
    ) -> None:
        """Initialize the sync session.

        Args:
            port: External CDP port. With ``launch_stealth_chrome=True`` a
                real Chrome is auto-launched on this port and the session
                connects to it (headless Turnstile-capable).
            host: CDP bind host (default ``127.0.0.1``).
            user_data_dir: Optional profile name / Chrome user-data dir.
            headless: Whether to run the browser headless (default False so
                agent-browser challenges get an interactive window; stealth
                Chrome headless mode works too via ``--headless=new``).
            launch_stealth_chrome: Auto-launch a stealth Chrome
                (``--disable-blink-features=AutomationControlled``) and
                connect to it.
        """
        self.host: str = host
        self.port: int = port
        self.headless = headless
        self.launch_stealth_chrome = launch_stealth_chrome
        self.user_data_dir = user_data_dir
        self.session_id: str = f"llm4free-{uuid.uuid4().hex[:12]}"
        self._started = False
        self._connected = False
        self._chrome_proc: Optional[Any] = None
        self._chrome_profile: Optional[str] = None

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

    def _launch_chrome(self) -> None:
        """Start the stealth Chrome process and register its handle."""
        if self._chrome_proc is not None:
            return
        if _chrome_cdp_alive(self.host, self.port):
            return  # an external Chrome already listens on the port
        proc, profile_dir = launch_stealth_chrome(
            self.port, self.host, self.user_data_dir, self.headless
        )
        self._chrome_proc = proc
        self._chrome_profile = profile_dir

    def _chrome_cdp_ready(self) -> bool:
        return _chrome_cdp_alive(self.host, self.port)

    def start_chrome(self) -> None:
        """Open a blank page so the session/browser is ready.

        Stealth/connect mode attaches to a real Chrome (launched if
        ``launch_stealth_chrome``) for headless Turnstile support.
        """
        if self._started:
            return
        if self.launch_stealth_chrome:
            self._launch_chrome()
            if not self._chrome_cdp_ready():
                raise RuntimeError(
                    f"No CDP endpoint reachable on {self.host}:{self.port}"
                )
            try:
                self._run("connect", str(self.port), timeout=60)
            except RuntimeError:
                pass  # maybe already connected for this session
            self._connected = True
            self._started = True
            return
        self._run("open", "about:blank", timeout=60)
        self._started = True

    def navigate(self, url: str, force: bool = False) -> None:
        """Navigate to a URL and wait for the network to settle.

        Skips the navigation when the browser is already on ``url`` so
        in-flight challenge solves are not interrupted (see
        :meth:`CDPSession.navigate`).

        Args:
            url: Target URL.
            force: Force a reload even when already on ``url``.
        """
        if not self._started:
            self.start_chrome()
        if not force:
            try:
                current = self._run("get", "url", timeout=30)
            except RuntimeError:
                current = ""
            if current.rstrip("/").split("?")[0] == url.rstrip("/").split("?")[0]:
                return
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
        """Close the agent-browser session (and any Chrome we launched)."""
        try:
            self._run("close", timeout=30)
        except RuntimeError as e:
            logger.warning(f"agent-browser close failed: {e}")
        self._started = False
        self._connected = False

        proc = self._chrome_proc
        if proc is not None:
            self._chrome_proc = None
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception as e:
                logger.debug(f"stealth Chrome terminate failed: {e}")
        profile = self._chrome_profile
        if profile is not None:
            self._chrome_profile = None
            shutil.rmtree(profile, ignore_errors=True)
