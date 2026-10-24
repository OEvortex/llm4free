from litprinter import ic
"""
Requests package for llm4free.

Exposes a modular, engine-agnostic Chrome DevTools Protocol (CDP) client
plus a convenience helper, :func:`get_args_from_cdp`, that returns
browser-derived cookies, user-agent and headers ready to pass into a
``curl_cffi`` session.

Engines (``CDPSession(engine=...)`` or ``LLM4FREE_BROWSER_ENGINE``):

* ``agent-browser`` — Chrome via the agent-browser CLI (default; the
  shipped stealth plugin clears Cloudflare Turnstile headless);
* ``lightpanda`` — ~40 MB Zig headless engine driven by our own zero-dep
  CDP client over one persistent WebSocket (fastest, lowest RAM);
* ``chrome`` — real stealth Chrome driven by our own CDP client;
* ``native`` — lightpanda when available (headless), else chrome.
"""

import asyncio
import time
from typing import Any, Dict, Optional

try:
    from .cdp import CDPSession, SyncCDPSession
    from .native_cdp import CDPClient, CDPError
    from .backends.agentbrowser import find_agent_browser
    from .browserproc import find_chrome_binary, find_lightpanda_path, launch_lightpanda

    has_cdp = True
except ImportError:  # pragma: no cover - cdp is always present in this package
    CDPSession = None
    SyncCDPSession = None
    CDPClient = None
    CDPError = None
    has_cdp = False



async def get_args_from_cdp(
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 120,
    user_data_dir: Optional[str] = None,
    headless: bool = True,
) -> Dict[str, Any]:
    """Open a browser, solve any interstitial, and return request kwargs.

    The returned dict is consumable by a ``curl_cffi`` session (or any
    ``requests``-compatible session) for making authenticated requests to a
    site that normally sits behind a Cloudflare/Turnstile challenge.

    Args:
        url: The site URL to navigate to (and harvest cookies from).
        proxy: Optional proxy URL passed through to the request layer.
        timeout: Maximum seconds to wait for the interstitial to clear.
        user_data_dir: Optional Chrome profile directory name or path. When
            omitted, the CDP session uses an isolated temporary browser state
            rather than reusing any saved profile.
        headless: Whether to launch the browser headless.

    Returns:
        A dict with keys: ``impersonate``, ``cookies``, ``headers``, ``proxy``.
    """
    if not has_cdp:
        raise RuntimeError("CDP client is not available")

    session_cls = CDPSession
    assert session_cls is not None  # implied by has_cdp
    session = session_cls(user_data_dir=user_data_dir, headless=headless)
    try:
        await session.start()
        await session.navigate(url)

        # Poll until the Cloudflare interstitial is gone.
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = await session.evaluate_js("document.title")
            body = await session.evaluate_js(
                "document.body ? document.body.innerText : ''"
            )
            if title and "Just a moment" not in title and "Attention Required" not in title:
                if "cf-browser-verification" not in (body or ""):
                    break
            await asyncio.sleep(1.0)

        cookies = await session.get_cookies()
        user_agent = await session.get_user_agent()
    finally:
        await session.close()

    return {
        "impersonate": "chrome",
        "cookies": cookies,
        "headers": {
            "user-agent": user_agent,
            "referer": f"{url.rstrip('/')}/",
        },
        "proxy": proxy,
    }


__all__ = [
    "CDPSession",
    "SyncCDPSession",
    "CDPClient",
    "CDPError",
    "has_cdp",
    "get_args_from_cdp",
    "find_agent_browser",
    "find_chrome_binary",
    "find_lightpanda_path",
    "launch_lightpanda",
]
