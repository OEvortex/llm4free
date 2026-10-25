"""Cookie harvester using agent-browser for sites behind Cloudflare or JS challenges.

Extracts cookies (including HTTP-only cf_clearance, session tokens) from any
website by launching a real Chromium browser via agent-browser. Supports
filtering by domain and exporting to a curl header, an LLM4Free session/client,
and Netscape format.

Usage:
    >>> from llm4free.Extra.cookie_harvester import CookieHarvester
    >>> ch = CookieHarvester()
    >>> cookies = ch.harvest("https://perchance.org/ai-text-to-image-generator")
    >>> curl_cmd = ch.to_curl("https://image-generation.perchance.org/api/generate")
"""

from __future__ import annotations

__all__ = [
    "CookieHarvester",
    "HarvestResult",
    "Cookie",
    "harvest_cookies",
    "AgentBrowserNotFound",
    "HarvestError",
]

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

AGENT_BROWSER = "agent-browser"


class AgentBrowserNotFound(Exception):
    pass


class HarvestError(Exception):
    pass


@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    httpOnly: bool = False
    expires: Optional[float] = None
    sameSite: str = "None"

    @classmethod
    def from_state_dict(cls, d: dict) -> Cookie:
        return cls(
            name=d["name"],
            value=d["value"],
            domain=d.get("domain", ""),
            path=d.get("path", "/"),
            secure=d.get("secure", False),
            httpOnly=d.get("httpOnly", False),
            expires=d.get("expires"),
            sameSite=d.get("sameSite", "None"),
        )

    def to_header(self) -> str:
        return f"{self.name}={self.value}"

    def to_netscape(self) -> str:
        domain = self.domain
        if domain.startswith("."):
            domain = domain[1:]
        include_sub = "TRUE" if self.domain.startswith(".") else "FALSE"
        secure_flag = "TRUE" if self.secure else "FALSE"
        expires = str(int(self.expires)) if self.expires else "0"
        return f"{domain}\t{include_sub}\t{self.path}\t{secure_flag}\t{expires}\t{self.name}\t{self.value}"


@dataclass
class HarvestResult:
    url: str
    cookies: list[Cookie] = field(default_factory=list)
    origins: dict[str, dict[str, str]] = field(default_factory=dict)
    state_path: Optional[str] = None
    elapsed: float = 0.0

    def domain_filter(self, *domains: str) -> list[Cookie]:
        return [c for c in self.cookies if any(d in c.domain for d in domains)]

    def by_name(self, name: str) -> Optional[Cookie]:
        for c in self.cookies:
            if c.name == name:
                return c
        return None


class CookieHarvester:
    """Extract cookies from JS-heavy or Cloudflare-protected sites using agent-browser.

    Args:
        agent_browser: Path to agent-browser binary. Auto-detected if None.
        timeout: Max wait in seconds for page load + cookie extraction.
        headed: Whether to show the browser window (useful for Cloudflare challenges).
        session_name: Auto-save/restore session state across runs.
    """

    def __init__(
        self,
        agent_browser: Optional[str] = None,
        timeout: int = 60,
        headed: bool = False,
        session_name: Optional[str] = None,
    ) -> None:
        self._binary = agent_browser or self._resolve_binary()
        self._timeout = timeout
        self._headed = headed
        self._session_name = session_name
        self._last_result: Optional[HarvestResult] = None

    @staticmethod
    def _resolve_binary() -> str:
        try:
            result = subprocess.run(
                ["which", "agent-browser"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        for candidate in ("agent-browser", "npx agent-browser"):
            try:
                subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    timeout=5,
                )
                return candidate
            except Exception:
                continue

        raise AgentBrowserNotFound(
            "agent-browser not found. Install: npm i -g agent-browser && agent-browser install"
        )

    def _run(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess:
        cmd = [self._binary]
        if self._session_name:
            cmd.extend(["--session-name", self._session_name])
        cmd.extend(args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=kwargs.get("timeout", self._timeout),
            env={**os.environ, **kwargs.get("env", {})},
        )

    def harvest(
        self,
        url: str,
        *,
        wait: float = 5.0,
        domain_filter: Optional[list[str]] = None,
        save_path: Optional[str] = None,
        extra_wait_for: Optional[str] = None,
        max_retries: int = 3,
    ) -> HarvestResult:
        """Open a URL in agent-browser, wait for JS to execute, and extract cookies.

        Detects Cloudflare challenges and prompts user to solve in headed mode.
        Retries until cookies are found or max_retries reached.

        Args:
            url: The target URL to visit.
            wait: Seconds to wait after page load for JS execution.
            domain_filter: If set, only return cookies for matching domains.
            save_path: Where to save the state JSON. Auto-tempfile if None.
            extra_wait_for: Optional text to wait for on the page before extracting.
            max_retries: Number of times to retry if no cookies found.

        Returns:
            HarvestResult with extracted cookies and origins.
        """
        result = HarvestResult(url=url)
        start = time.time()
        state_path = save_path or tempfile.mktemp(suffix=".json", prefix="cookie_harvester_")  # ty:ignore[deprecated]
        result.state_path = state_path

        try:
            # Close any stale sessions
            subprocess.run(
                [self._binary, "close", "--all"],
                capture_output=True,
                timeout=10,
            )
            time.sleep(0.5)

            # Open the URL
            open_args = ["open", url]
            if self._headed:
                open_args.insert(0, "--headed")
            r = self._run(*open_args)
            if r.returncode != 0:
                raise HarvestError(f"Failed to open {url}: {r.stderr.strip() or r.stdout.strip()}")

            # Initial wait for page load
            time.sleep(wait)

            for attempt in range(max_retries):
                if extra_wait_for:
                    self._run("wait", f"--text={extra_wait_for}", timeout=self._timeout)

                # Save state
                r = self._run("state", "save", state_path)
                if r.returncode != 0:
                    raise HarvestError(f"Failed to save state: {r.stderr.strip()}")

                # Quick parse to check cookie count
                try:
                    with open(state_path) as f:
                        preview = json.load(f)
                    if len(preview.get("cookies", [])) > 0:
                        break
                except Exception:
                    pass

                if attempt < max_retries - 1:
                    print(
                        "  No cookies yet — likely behind a Cloudflare/JS challenge. Waiting 10s..."
                        if not self._headed
                        else "  Solve the Cloudflare challenge in the browser window... "
                        "retrying in 10s",
                    )
                    time.sleep(10)

        finally:
            self._run("close", "--all", timeout=10)

        # Parse the state file
        try:
            with open(state_path) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HarvestError(f"Failed to parse state file: {e}")

        # Extract cookies
        raw_cookies = state.get("cookies", [])
        all_cookies = [Cookie.from_state_dict(c) for c in raw_cookies]

        if domain_filter:
            result.cookies = [c for c in all_cookies if any(d in c.domain for d in domain_filter)]
        else:
            result.cookies = all_cookies

        result.origins = state.get("origins", {})
        result.elapsed = time.time() - start
        self._last_result = result
        return result

    @property
    def last_result(self) -> Optional[HarvestResult]:
        return self._last_result

    # ── Export helpers ──────────────────────────────────────────

    def to_curl_header(
        self,
        *domains: str,
        result: Optional[HarvestResult] = None,
    ) -> str:
        """Format harvested cookies as a curl ``-H "Cookie: ..."`` header."""
        r = result or self._last_result
        if not r:
            return ""
        cookies = r.domain_filter(*domains) if domains else r.cookies
        parts = [c.to_header() for c in cookies]
        return ' -H "Cookie: ' + "; ".join(parts) + '"'

    def to_netscape_file(
        self,
        path: str,
        *domains: str,
        result: Optional[HarvestResult] = None,
    ) -> str:
        """Write a Netscape-format cookie file (usable with curl -b, wget, requests).

        Returns the path written to.
        """
        r = result or self._last_result
        if not r:
            raise HarvestError("No harvest result available")
        cookies = r.domain_filter(*domains) if domains else r.cookies
        lines = ["# Netscape HTTP Cookie File"]
        for c in cookies:
            lines.append(c.to_netscape())
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def to_requests_session(
        self,
        *domains: str,
        result: Optional[HarvestResult] = None,
    ):
        """Build a :class:`llm4free.browser_requests._http.compat.Session` with cookies set.

        Returns the session object.
        """
        from ..browser_requests._http.compat import Session

        r = result or self._last_result
        if not r:
            raise HarvestError("No harvest result available")
        cookies = r.domain_filter(*domains) if domains else r.cookies

        session = Session()
        for c in cookies:
            session.cookies.set(c.name, c.value)
        return session

    def to_httpx_client(self, *domains: str, result: Optional[HarvestResult] = None):
        """Build an LLM4Free http :class:`Client` with cookies pre-set."""
        from ..browser_requests._http import Client

        r = result or self._last_result
        if not r:
            raise HarvestError("No harvest result available")
        cookies = r.domain_filter(*domains) if domains else r.cookies

        jar: dict[str, str] = {}
        for c in cookies:
            jar[c.name] = c.value
        return Client(cookies=jar)

    def to_dict(
        self,
        *domains: str,
        result: Optional[HarvestResult] = None,
    ) -> dict[str, dict[str, str]]:
        """Return cookies as ``{domain: {name: value}}``."""
        r = result or self._last_result
        if not r:
            return {}
        cookies = r.domain_filter(*domains) if domains else r.cookies
        out: dict[str, dict[str, str]] = {}
        for c in cookies:
            out.setdefault(c.domain, {})[c.name] = c.value
        return out

    def to_environ(
        self,
        *domains: str,
        prefix: str = "COOKIE_",
        result: Optional[HarvestResult] = None,
    ) -> dict[str, str]:
        """Return cookies as environment-variable-friendly flat dict."""
        r = result or self._last_result
        if not r:
            return {}
        cookies = r.domain_filter(*domains) if domains else r.cookies
        out = {}
        for c in cookies:
            key = f"{prefix}{c.domain.replace('.', '_').replace('-', '_')}__{c.name}".upper()
            out[key] = c.value
        return out


def harvest_cookies(
    url: str,
    *,
    domain_filter: Optional[list[str]] = None,
    wait: float = 5.0,
    headed: bool = False,
    timeout: int = 60,
) -> HarvestResult:
    """Convenience function: one-shot cookie harvest."""
    ch = CookieHarvester(headed=headed, timeout=timeout)
    return ch.harvest(url, wait=wait, domain_filter=domain_filter)

if __name__ == "__main__":
    from rich import print
    ch = CookieHarvester(headed=False, timeout=60)
    result = ch.harvest("https://ttsopen.ai", wait=5.0,)
    print(result)
