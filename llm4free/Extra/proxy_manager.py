"""Lightweight proxy manager for streaming support and provider integration.

This module provides a simple, monkey-patchable proxy manager that rotates
through a pool of proxies. It works with both ``requests.Session`` and
``curl_cffi.requests.Session``.

Usage:
    >>> from llm4free.Extra.proxy_manager import ProxyManager
    >>> pm = ProxyManager(['http://proxy1:8080', 'http://proxy2:8080'])
    >>> pm.monkey_patch()  # Patch globally
    >>> # Now all providers use rotating proxies automatically

When ``auto_fetch=True`` the manager periodically obtains free proxies from
Urban VPN's public extension API.  The endpoint flow below was extracted from
the official browser extension (``URBAN_VPN_BROWSER_EXTENSION``):

1. register an anonymous user;
2. exchange that token for an ``accs`` security token;
3. download the country/server list;
4. exchange a server ``signature`` for an ``accs-proxy`` credential.

The credential is used as the proxy *username* and the literal password is
``"1"`` (this is what the extension itself does).
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from curl_cffi.requests import Session as CurlSession
from litprinter import ic

try:  # ``requests`` is an optional dependency of the rest of the project
    from requests.sessions import Session as HttpSession
except ImportError:  # pragma: no cover - only happens in minimal installs
    HttpSession = None  # type: ignore


_CLIENT_APP = "URBAN_VPN_BROWSER_EXTENSION"
_PROXY_PASSWORD = "1"

# ``urban-vpn.com`` is what the current extension uses.  ``falais.com`` is the
# older/alternate host and is kept as a fallback so one flaky DNS entry does
# not disable proxy fetching completely.
_API_BASES = (
    "https://api-pro.urban-vpn.com/rest/v1",
    "https://api-pro.falais.com/rest/v1",
)
_STATS_BASES = (
    "https://stats.urban-vpn.com/api/rest/v2",
    "https://stats.falais.com/api/rest/v2",
)

# Proxy credentials returned by the API expire after 30 minutes.  Refresh a
# little early so requests never use an expired credential.  The extension
# uses a 3 minute safety margin.
_TOKEN_SAFETY_MARGIN = 3 * 60
_DEFAULT_REFRESH_INTERVAL = 25 * 60
_DEFAULT_RETRY_INTERVAL = 60
_MAX_CONCURRENT_REQUESTS = 5
_REQUEST_ATTEMPTS = 2
_REQUEST_TIMEOUT = 10.0

# A single patched __init__ is installed per session class and dispatches to
# whichever manager is currently active.  Patching more than once (or
# patching from two managers) must not wrap the previous patch, otherwise
# creating a session would recurse forever.
_PATCH_LOCK = threading.Lock()
_ACTIVE_MANAGER: Optional[ProxyManager] = None
_ORIGINAL_SESSION_INITS: dict[type, Any] = {}


class ProxyManager:
    """Manages and rotates proxies with background Urban VPN fetching support."""

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        filepath: Optional[str] = None,
        auto_fetch: bool = False,
        debug: bool = False,
        refresh_interval: float = _DEFAULT_REFRESH_INTERVAL,
        retry_interval: float = _DEFAULT_RETRY_INTERVAL,
        max_servers: int = 10,
    ) -> None:
        self._proxies: list[str] = self._load_initial(proxies, filepath)
        self._index = 0
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._token_expires_at: Optional[float] = None
        self._refresh_interval = max(30.0, float(refresh_interval))
        self._retry_interval = max(5.0, float(retry_interval))
        self._max_servers = max(1, int(max_servers))
        self.debug = debug
        self._headers = {
            "origin": "chrome-extension://eppiocemhmnlbhjplcgkofciiegomcon",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/144.0.0.0 Safari/537.36"
            ),
            "accept": "application/json",
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "x-client-app": _CLIENT_APP,
        }

        if auto_fetch:
            self.start()

    # ------------------------------------------------------------------
    # Proxy pool
    # ------------------------------------------------------------------
    def _load_initial(self, proxies: Optional[list[str]], filepath: Optional[str]) -> list[str]:
        """Load proxies from an explicit list or a newline-separated file."""
        if proxies:
            return [proxy.strip() for proxy in proxies if proxy.strip()]

        if filepath:
            path = Path(filepath).expanduser()
            if path.exists():
                return [
                    line.strip()
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
        return []

    @property
    def proxies(self) -> list[str]:
        """Return a snapshot of the current proxy pool."""
        with self._lock:
            return list(self._proxies)

    def get(self) -> dict[str, str]:
        """Get the next proxy in rotation.

        Returns an empty dict when no proxies are available so callers can
        safely pass the result to ``Session.proxies.update``.
        """
        with self._lock:
            if not self._proxies:
                return {}
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index = (self._index + 1) % len(self._proxies)
            return {"http": proxy, "https": proxy}

    def _set_proxies(self, proxies: list[str]) -> None:
        # Keep ordering while dropping duplicates.
        unique = list(dict.fromkeys(proxy for proxy in proxies if proxy))
        if not unique:
            return
        with self._lock:
            self._proxies = unique
            self._index = 0

    # ------------------------------------------------------------------
    # Urban VPN fetching
    # ------------------------------------------------------------------
    async def _request(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Perform an HTTP request with a small retry for transient failures."""
        last_error: Optional[Exception] = None
        for attempt in range(_REQUEST_ATTEMPTS):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Retryable HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                # 4xx responses (except 429) will not improve on retry.
                if exc.response.status_code != 429 and exc.response.status_code < 500:
                    raise
            except httpx.HTTPError as exc:
                last_error = exc

            if attempt + 1 < _REQUEST_ATTEMPTS:
                await asyncio.sleep(0.75 * (attempt + 1))

        # ``last_error`` is always set because the loop runs at least once.
        assert last_error is not None
        raise last_error

    async def _fetch_from(
        self, api_base: str, stats_base: str
    ) -> tuple[list[str], Optional[float]]:
        """Fetch proxies from one pair of API hosts."""
        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(_REQUEST_TIMEOUT),
            follow_redirects=True,
        ) as client:
            # 1. Anonymous registration token.
            response = await self._request(
                client,
                "POST",
                f"{api_base}/registrations/clientApps/{_CLIENT_APP}/users/anonymous",
                json={"clientApp": {"name": _CLIENT_APP, "browser": "CHROME"}},
            )
            anon_token = response.json().get("value")
            if not anon_token:
                if self.debug:
                    ic(f"Urban VPN anon response: {response.text}")
                return [], None

            # 2. Security token used for the remaining API calls.
            response = await self._request(
                client,
                "POST",
                f"{api_base}/security/tokens/accs",
                headers={"authorization": f"Bearer {anon_token}"},
                json={"type": "accs", "clientApp": {"name": _CLIENT_APP}},
            )
            security_token = response.json().get("value")
            if not security_token:
                if self.debug:
                    ic(f"Urban VPN accs response: {response.text}")
                return [], None

            # 3. Country/server list.  The extension sends the security token
            #    through its request interceptor; callers must set it here.
            response = await self._request(
                client,
                "GET",
                f"{stats_base}/entrypoints/countries",
                headers={"authorization": f"Bearer {security_token}"},
            )
            countries = response.json().get("countries", {}).get("elements") or []

            # 4. Pick a handful of accessible servers across countries.
            candidates: list[dict[str, Any]] = []
            for country in countries:
                if country.get("accessType", "ACCESSIBLE") != "ACCESSIBLE":
                    continue

                servers = country.get("servers", {}).get("elements") or []
                accessible = [
                    server
                    for server in servers
                    if server.get("signature")
                    and server.get("accessType", "ACCESSIBLE") == "ACCESSIBLE"
                ]
                if not accessible:
                    continue

                # Prefer the "strong" pool when it is available: weak servers
                # are frequently overloaded and time out.
                strong = [server for server in accessible if server.get("pool") == "strong"]
                candidates.append(random.choice(strong or accessible))

            random.shuffle(candidates)
            candidates = candidates[: self._max_servers]
            if not candidates:
                return [], None

            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)

            async def fetch_credential(
                server: dict[str, Any],
            ) -> tuple[Optional[str], Optional[float]]:
                async with semaphore:
                    try:
                        response = await self._request(
                            client,
                            "POST",
                            f"{api_base}/security/tokens/accs-proxy",
                            headers={"authorization": f"Bearer {security_token}"},
                            json={
                                "type": "accs-proxy",
                                "clientApp": {"name": _CLIENT_APP},
                                "signature": server["signature"],
                            },
                        )
                        payload = response.json()
                    except Exception as exc:
                        if self.debug:
                            ic(f"Urban VPN credential request failed: {exc}")
                        return None, None

                    credential = payload.get("value")
                    if not credential:
                        if self.debug:
                            ic(f"Urban VPN cred response: {payload}")
                        return None, None

                    address = (server.get("address") or {}).get("primary") or {}
                    host = address.get("ip") or address.get("host")
                    port = address.get("port")
                    if not host or not port:
                        return None, None

                    username = quote(str(credential), safe="")
                    proxy_url = f"http://{username}:{_PROXY_PASSWORD}@{host}:{port}"

                    expires_at: Optional[float] = None
                    expiration = payload.get("expirationTime")
                    if isinstance(expiration, (int, float)):
                        expires_at = float(expiration) / 1000.0

                    return proxy_url, expires_at

            results = await asyncio.gather(
                *(fetch_credential(server) for server in candidates),
                return_exceptions=True,
            )

            new_proxies: list[str] = []
            expirations: list[float] = []
            for result in results:
                if isinstance(result, BaseException):
                    if self.debug:
                        ic(f"Urban VPN proxy collection failed: {result}")
                    continue
                proxy_url, expires_at = result
                if proxy_url:
                    new_proxies.append(proxy_url)
                if expires_at:
                    expirations.append(expires_at)

            return new_proxies, (min(expirations) if expirations else None)

    async def _fetch_urban_proxies(self) -> list[str]:
        """Fetch proxies from Urban VPN using whichever API host responds first.

        The official and legacy hosts are queried concurrently so a blocked or
        flaky DNS entry does not delay startup by the full request timeout.
        """
        tasks = {
            asyncio.create_task(self._fetch_from(api_base, stats_base)): api_base
            for api_base, stats_base in zip(_API_BASES, _STATS_BASES)
        }
        pending = set(tasks)
        last_error: Optional[Exception] = None

        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try:
                        proxies, expires_at = task.result()
                    except Exception as exc:
                        last_error = exc
                        if self.debug:
                            ic(f"Proxy fetch failed ({tasks[task]}): {exc}")
                        continue

                    if proxies:
                        with self._lock:
                            self._token_expires_at = expires_at
                        for remaining in pending:
                            remaining.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        return proxies
        finally:
            for remaining in pending:
                remaining.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        if last_error and self.debug:
            ic(f"Proxy fetch failed: {last_error}")
        return []

    @staticmethod
    def _run_sync(coroutine: Any) -> Any:
        """Run a coroutine from synchronous code, even inside a running loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: dict[str, Any] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(coroutine)
            except BaseException as exc:  # propagated to the caller below
                result["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def refresh(self) -> list[str]:
        """Synchronously fetch a fresh batch of proxies and update the pool."""
        proxies = self._run_sync(self._fetch_urban_proxies())
        if proxies:
            self._set_proxies(proxies)
            if self.debug:
                ic(f"Refreshed {len(proxies)} proxies")
        return proxies

    def _background_refresh(self) -> None:
        """Background loop that keeps the proxy pool fresh."""
        while not self._stop_event.is_set():
            try:
                proxies = asyncio.run(self._fetch_urban_proxies())
            except Exception as exc:  # keep the worker alive
                proxies = []
                if self.debug:
                    ic(f"Background proxy refresh failed: {exc}")

            if proxies:
                self._set_proxies(proxies)
                with self._lock:
                    expires_at = self._token_expires_at
                if expires_at:
                    delay = expires_at - time.time() - _TOKEN_SAFETY_MARGIN
                    delay = max(self._retry_interval, min(delay, self._refresh_interval))
                else:
                    delay = self._refresh_interval
                if self.debug:
                    ic(f"Refreshed {len(proxies)} proxies; next refresh in {delay:.0f}s")
            else:
                delay = self._retry_interval
                if self.debug:
                    ic(f"No proxies fetched; retrying in {delay:.0f}s")

            # ``wait`` lets stop() interrupt the sleep immediately.
            self._stop_event.wait(delay)

    def start(self) -> None:
        """Start the background refresh thread (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._background_refresh,
                name="ProxyManagerRefresh",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background refresh thread."""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        if self.debug:
            ic("Proxy manager stopped")

    # ------------------------------------------------------------------
    # Monkey patching
    # ------------------------------------------------------------------
    @staticmethod
    def _install_patch(session_class: type) -> None:
        with _PATCH_LOCK:
            if session_class in _ORIGINAL_SESSION_INITS:
                return

            original_init = session_class.__init__
            _ORIGINAL_SESSION_INITS[session_class] = original_init

            def patched_init(session_self: Any, *args: Any, **kwargs: Any) -> None:
                original_init(session_self, *args, **kwargs)
                manager = _ACTIVE_MANAGER
                if manager is None:
                    return
                # Never override proxies the caller passed explicitly.
                if getattr(session_self, "proxies", None):
                    return
                proxy = manager.get()
                if proxy:
                    session_self.proxies.update(proxy)

            setattr(session_class, "__init__", patched_init)

    def patch(self) -> None:
        """Patch ``requests`` and ``curl_cffi`` sessions to use this manager.

        This is safe to call multiple times and from multiple managers.  The
        most recently patched manager receives the proxy rotation.
        """
        global _ACTIVE_MANAGER
        with _PATCH_LOCK:
            _ACTIVE_MANAGER = self
        self._install_patch(CurlSession)
        if HttpSession is not None:
            self._install_patch(HttpSession)

    def unpatch(self) -> None:
        """Restore the original session constructors."""
        global _ACTIVE_MANAGER
        with _PATCH_LOCK:
            for session_class, original_init in list(_ORIGINAL_SESSION_INITS.items()):
                setattr(session_class, "__init__", original_init)
            _ORIGINAL_SESSION_INITS.clear()
            _ACTIVE_MANAGER = None

    def monkey_patch(self) -> None:
        """Alias for :meth:`patch` kept for backward compatibility."""
        self.patch()

    def __enter__(self) -> ProxyManager:
        self.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()


__all__ = ["ProxyManager"]


if __name__ == "__main__":
    manager = ProxyManager(auto_fetch=True)
    proxies = manager.refresh()
    print(f"Fetched {len(proxies)} proxies")
    print("Current proxy pool:", manager.proxies)
    manager.monkey_patch()

    from curl_cffi import requests as curl_requests

    try:
        # A fresh Session is created by ``get`` and receives a rotating proxy.
        result = curl_requests.get("https://api.ipify.org?format=json", timeout=30)
        print(result.json())
    finally:
        manager.stop()
        manager.unpatch()
