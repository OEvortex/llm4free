"""Engine registry + resolution for browser backends.

Engines
-------
* ``agent-browser`` — Chrome via the bundled Rust CLI (stealth plugin capable
  of clearing Cloudflare Turnstile headless). Default, zero behavior change.
* ``lightpanda``    — 40 MB Zig engine, spoken to directly with our own
  zero-dep CDP client. Fastest + ~40 MB RAM.
* ``chrome``        — real stealth Chrome driven natively (same speed class
  as lightpanda adds real Chrome JS coverage).
* ``native``        — auto: lightpanda when installed & headless, else chrome.

Selection happens in :class:`...cdp.CDPSession` via ``engine=`` or the
``LLM4FREE_BROWSER_ENGINE`` environment variable.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .agentbrowser import AgentBrowserBackend
from .base import BaseBackend
from .native import NativeCDPBackend

BACKENDS: Dict[str, Any] = {
    "agent-browser": AgentBrowserBackend,
    "lightpanda": NativeCDPBackend,
    "chrome": NativeCDPBackend,
    "native": NativeCDPBackend,
}

ENV_ENGINE = "LLM4FREE_BROWSER_ENGINE"


def resolve_engine(engine: Optional[str], *, headless: bool = True,
                   launch_stealth_chrome: bool = False,
                   port: Optional[int] = None) -> str:
    """Map a requested engine name (or ``None``) to a concrete backend name.

    Rules (in order):
      1. explicit ``engine`` argument (validates against BACKENDS),
      2. ``LLM4FREE_BROWSER_ENGINE`` env var,
      3. ``launch_stealth_chrome=True`` → ``native`` (stealth chrome, driven
         by our own CDP client — strictly faster than the CLI connect flow),
      4. default: ``agent-browser`` (legacy behavior, Turnstile-capable).

    To *connect* to an already-running CDP endpoint without launching
    anything, pass ``engine="chrome"`` (or ``"lightpanda"``) together with
    ``port`` — the native backend adopts whatever is listening.

    Raises:
        ValueError: Unknown engine name.
    """
    if engine is None:
        engine = os.environ.get(ENV_ENGINE) or None
    if engine is None:
        if launch_stealth_chrome:
            return "native"
        return "agent-browser"
    key = engine.strip().lower()
    alias = {"browser-bridge": "agent-browser", "ab": "agent-browser"}
    key = alias.get(key, key)
    if key == "native":
        return "native"
    if key not in BACKENDS:
        raise ValueError(
            f"unknown engine {engine!r}; choose one of {sorted(BACKENDS)}"
        )
    return key


def create_backend(
    engine: str,
    *,
    session_id: str,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    user_data_dir: Optional[str] = None,
    headless: bool = True,
    launch_stealth_chrome: bool = False,
    proxy: Optional[str] = None,
) -> BaseBackend:
    """Instantiate the backend for ``engine``."""
    key = resolve_engine(engine, headless=headless, launch_stealth_chrome=launch_stealth_chrome, port=port)
    if key == "agent-browser":
        return AgentBrowserBackend(
            session_id,
            host=host,
            port=port,
            user_data_dir=user_data_dir,
            headless=headless,
        )
    # native family: choose the chrome vs lightpanda flavor:
    if key == "native":
        from ..browserproc import find_lightpanda_path

        if launch_stealth_chrome:
            key = "chrome"  # explicit stealth turnstile mode always wants Chrome
        elif headless and find_lightpanda_path() is not None:
            key = "lightpanda"
        else:
            key = "chrome"
    backend_cls: Any = BACKENDS[key]
    return backend_cls(
        session_id,
        engine=key,
        host=host,
        port=port,
        headless=headless,
        user_data_dir=user_data_dir,
        mask_user_agent=True,
        proxy=proxy,
    )


__all__ = ["BACKENDS", "resolve_engine", "create_backend"]
