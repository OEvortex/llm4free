#!/usr/bin/env python3
"""agent-browser ``launch.mutate`` stealth plugin (agent-browser.plugin.v1).

This is a standard agent-browser plugin: it reads ONE JSON request envelope
from stdin and writes ONE JSON response to stdout. agent-browser registers it
automatically for every *local* launch (``open`` on a fresh browser) and
applies the launch mutation below, which is what lets Cloudflare Turnstile
resolve in a headless browser:

* ``--disable-blink-features=AutomationControlled`` -- makes
  ``navigator.webdriver`` false at the browser level (the header-level
  signal Turnstile checks hardest);
* a realistic ``userAgent`` override -- replaces the
  ``HeadlessChrome/...`` user agent that agent-browser ships with by
  default. The override is applied natively (both the HTTP header and
  ``navigator.userAgent``), so there is no JS-vs-HTTP UA mismatch for
  the challenge to detect;
* an init script masking any residual ``navigator.webdriver`` and adding
  a ``window.chrome`` stub (defense in depth).

Registered from Python via::

    AGENT_BROWSER_PLUGINS='[{"name":"llm4free-stealth","command":"<this file>",
    "capabilities":["launch.mutate"]}]'

Only stdout carries the protocol response (any other output breaks the
daemon's JSON parsing).
"""

from __future__ import annotations

import json
import os
import sys

PROTOCOL = "agent-browser.plugin.v1"

# Stealth init script applied to every page (all frames) before page JS.
STEALTH_INIT_SCRIPT = """
(() => {
  try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch (e) {}
  try { window.chrome = window.chrome || { runtime: {} }; } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
  } catch (e) {}
})();
"""

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
]

# A clean desktop-Chrome UA without the "HeadlessChrome" marker.
STEALTH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def reply(body: dict) -> None:
    """Write exactly one protocol JSON response line to stdout."""
    sys.stdout.write(json.dumps({"protocol": PROTOCOL, **body}))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main() -> None:
    try:
        envelope = json.loads(sys.stdin.read() or "{}")
    except Exception:
        envelope = {}
    if envelope.get("protocol") != PROTOCOL:
        reply({"success": False, "error": "unsupported protocol"})
        return

    req_type = envelope.get("type", "")

    if req_type == "plugin.manifest":
        reply(
            {
                "success": True,
                "manifest": {
                    "name": "llm4free-stealth",
                    "capabilities": ["launch.mutate"],
                    "description": (
                        "llm4free headless stealth: AutomationControlled off, "
                        "clean UA, webdriver mask init script"
                    ),
                },
            }
        )
        return

    if req_type == "launch.mutate":
        reply(
            {
                "success": True,
                "launch": {
                    "args": STEALTH_ARGS,
                    "initScripts": [STEALTH_INIT_SCRIPT],
                    "userAgent": STEALTH_USER_AGENT,
                },
            }
        )
        return

    reply({"success": False, "error": f"unsupported request type: {req_type}"})


if __name__ == "__main__":
    main()
