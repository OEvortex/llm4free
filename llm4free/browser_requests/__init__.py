"""
Requests package for llm4free.

Exposes a lightweight Chrome DevTools Protocol (CDP) client plus a convenience
helper, :func:`get_args_from_cdp`, that returns browser-derived cookies,
user-agent and headers ready to pass into a ``curl_cffi`` session.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

try:
    from .cdp import CDPSession, SyncCDPSession

    has_cdp = True
except ImportError:  # pragma: no cover - cdp is always present in this package
    CDPSession = None  # type: ignore
    SyncCDPSession = None  # type: ignore
    has_cdp = False

logger = logging.getLogger(__name__)


async def get_args_from_cdp(
    url: str,
    proxy: Optional[str] = None,
    timeout: int = 120,
    user_data_dir: str = "cdp",
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
        user_data_dir: Profile directory name for the shared browser.
        headless: Whether to launch the browser headless.

    Returns:
        A dict with keys: ``impersonate``, ``cookies``, ``headers``, ``proxy``.
    """
    if not has_cdp:
        raise RuntimeError("CDP client is not available")

    session = CDPSession(user_data_dir=user_data_dir, headless=headless)
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
    "has_cdp",
    "get_args_from_cdp",
]
