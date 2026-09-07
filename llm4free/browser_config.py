"""
Browser configuration for the lightweight CDP client.

This mirrors the small ``BrowserConfig`` shim used by gpt4free so that ported
providers and :mod:`llm4free.browser_requests.cdp` can read a single, consistent
source of truth for the Chrome executable path and the CDP host/port.

Override any of these attributes at runtime (or via environment variables) to
point the CDP client at a specific browser / debugging endpoint.
"""

import os
from typing import Optional


class BrowserConfig:
    """Configuration holder for the CDP browser client."""

    # Path to the Chrome/Chromium/Edge binary. ``None`` lets the CDP client
    # auto-detect it from PATH and well-known install locations.
    executable_path: Optional[str] = os.environ.get("LLM4FREE_CHROME_PATH")

    # Host/port the DevTools remote-debugging endpoint binds to.
    host: str = os.environ.get("LLM4FREE_CDP_HOST", "127.0.0.1")
    port: Optional[int] = (
        int(os.environ["LLM4FREE_CDP_PORT"])
        if os.environ.get("LLM4FREE_CDP_PORT")
        else None
    )
