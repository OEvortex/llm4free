"""Shared stealth helpers for browser backends.

Centralizes the pieces that must stay in sync across engines:
* the realistic ``Chrome`` user-agent format ( ``HeadlessChrome`` never leaks),
* an init script that patches the automation fingerprints at document start
  (``navigator.webdriver``, ``plugins``/``languages`` wiring, ``chrome`` shim).
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Optional

# Realistic (HeadlessChrome-free) user agent template whose major version is
# filled in from the actual browser found on the machine.
CHROME_UA_FORMAT = (
    "Mozilla/5.0 ({platform}) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/{major}.0.0.0 {suffix}"
)

# Stealth init script: evaluated on every new document *before* page scripts.
STEALTH_INIT_JS = """
(() => {
  try { Object.defineProperty(Navigator.prototype, 'webdriver', {get: () => undefined}); } catch (e) {}
  try {
    if (!window.chrome) {
      window.chrome = window.chrome || {};
      window.chrome.app = {isInstalled: false, InstallState: {INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'}, RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'}};
      window.chrome.runtime = window.chrome.runtime || {};
      window.chrome.csi = function() {};
      window.chrome.loadTimes = function() {};
    }
  } catch (e) {}
  try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
      if (param === 37445) return 'Intel Inc.';
      if (param === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.apply(this, [param]);
    };
  } catch (e) {}
})();
"""


def masked_chrome_user_agent(
    platform: str = "X11; Linux x86_64",
    major: Optional[int] = None,
    binary: Optional[str] = None,
) -> str:
    """Return a clean Chrome user agent (no automation tokens).

    Args:
        platform: OS platform fragment baked into the UA string.
        major: Explicit Chrome major version; auto-detected from ``binary``
            when omitted, falling back to the version of a locally
            discovered browser.
        binary: Chrome executable used to detect the real major version.

    Returns:
        A UA string such as ``"...Chrome/131.0.0.0 Safari/537.36"``.
    """
    suffix = "Safari/537.36"
    if major is None:
        if binary is None:
            os.environ.setdefault("PATH", "/usr/bin:/bin")
            for name in ("google-chrome", "chromium", "chrome"):
                try:
                    from shutil import which

                    binary = which(name)
                    if binary:
                        break
                except Exception:
                    pass
        if binary:
            try:
                out = subprocess.run(
                    [binary, "--version"], capture_output=True, text=True, timeout=15
                ).stdout
                match = re.search(r"(\d+)\.", out)
                if match:
                    major = int(match.group(1))
            except Exception:
                pass
    if major is None:
        # Derive from the UA of a locally running agent-browser install, or
        # a sane current default.
        major = 131
        probe = os.environ.get("LLM4FREE_CHROME_MAJOR")
        if probe and probe.isdigit():
            major = int(probe)
    return CHROME_UA_FORMAT.format(
        platform=platform, major=major, suffix=suffix
    )


def no_headless_token(ua: str) -> bool:
    """Whether ``ua`` leaks the ``HeadlessChrome``/``Headless`` token."""
    lowered = ua.lower()
    return "headless" not in lowered and "lightpanda" not in lowered


ENV_NO_MASK_UA = "LLM4FREE_LIGHTPANDA_NO_MASK"


def should_mask_engine_ua(engine: str) -> bool:
    """Whether the engine's own UA should be replaced with a Chrome-like UA."""
    if engine.lower() == "lightpanda":
        return not os.environ.get(ENV_NO_MASK_UA)
    return False


__all__ = [
    "CHROME_UA_FORMAT",
    "STEALTH_INIT_JS",
    "masked_chrome_user_agent",
    "no_headless_token",
    "should_mask_engine_ua",
]
