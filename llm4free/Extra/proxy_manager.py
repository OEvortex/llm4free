"""Lightweight proxy manager for streaming support and provider integration.

This module provides a simple, monkey-patchable proxy manager that rotates
through a pool of proxies. It works with both requests.Session and curl_cffi.

Usage:
    >>> from llm4free.Extra.proxy_manager import ProxyManager
    >>> pm = ProxyManager(['http://proxy1:8080', 'http://proxy2:8080'])
    >>> pm.monkey_patch()  # Patch globally
    >>> # Now all providers use rotating proxies automatically
"""

import asyncio
import threading
import time
from itertools import cycle
from pathlib import Path
from typing import Any, Iterator, Optional, cast

import httpx
from curl_cffi import requests
from curl_cffi.requests import Session as CurlSession
from litprinter import ic


class ProxyManager:
    """Manages and rotates proxies with background Urban VPN fetching support."""

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        filepath: Optional[str] = None,
        auto_fetch: bool = False,
        debug: bool = False,
    ) -> None:
        self._proxies: list[str] = self._load_initial(proxies, filepath)
        self._pool: Iterator[str] = cycle(self._proxies) if self._proxies else iter([])
        self._lock = threading.Lock()
        self.debug = debug
        self._headers = {
            "origin": "chrome-extension://eppiocemhmnlbhjplcgkofciiegomcon",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }
        if auto_fetch or not self._proxies:
            threading.Thread(target=self._background_refresh, daemon=True).start()

    def _load_initial(self, proxies: Optional[list[str]], filepath: Optional[str]) -> list[str]:
        if proxies:
            return [p.strip() for p in proxies if p.strip()]
        if filepath and (p := Path(filepath)).exists():
            return [line.strip() for line in p.read_text().splitlines() if line.strip()]
        return []

    async def _fetch_urban_proxies(self) -> list[str]:
        """Fetch proxies from Urban VPN API."""
        async with httpx.AsyncClient(headers=self._headers, timeout=10) as client:
            try:
                # 1. Anon Token
                r = await client.post(
                    "https://api-pro.falais.com/rest/v1/registrations/clientApps/URBAN_VPN_BROWSER_EXTENSION/users/anonymous",
                    json={
                        "clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION", "browser": "CHROME"}
                    },
                )
                r.raise_for_status()
                anon_response = r.json()
                if "value" not in anon_response:
                    if self.debug:
                        ic(f"Urban VPN anon response: {anon_response}")
                    return []
                anon_token = anon_response["value"]

                # 2. Access Token
                r = await client.post(
                    "https://api-pro.falais.com/rest/v1/security/tokens/accs",
                    headers={"authorization": f"Bearer {anon_token}"},
                    json={"type": "accs", "clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION"}},
                )
                r.raise_for_status()
                accs = r.json()
                if "value" not in accs:
                    if self.debug:
                        ic(f"Urban VPN accs response: {accs}")
                    return []
                token = accs["value"]

                # 3. Countries
                r = await client.get(
                    "https://stats.falais.com/api/rest/v2/entrypoints/countries",
                    headers={
                        "authorization": f"Bearer {token}",
                        "x-client-app": "URBAN_VPN_BROWSER_EXTENSION",
                    },
                )
                r.raise_for_status()
                countries_response = r.json()
                if (
                    "countries" not in countries_response
                    or "elements" not in countries_response["countries"]
                ):
                    if self.debug:
                        ic(f"Urban VPN countries response: {countries_response}")
                    return []
                countries = countries_response["countries"]["elements"]

                # 4. Fetch credentials for a few random servers to keep it fast
                new_proxies = []
                for country in countries[:10]:  # Limit to 10 countries for speed
                    if "servers" not in country or not country["servers"]["elements"]:
                        continue
                    for server in country["servers"]["elements"][:1]:  # 1 server per country
                        if not server.get("signature"):
                            continue
                        r = await client.post(
                            "https://api-pro.falais.com/rest/v1/security/tokens/accs-proxy",
                            headers={"authorization": f"Bearer {token}"},
                            json={
                                "type": "accs-proxy",
                                "clientApp": {"name": "URBAN_VPN_BROWSER_EXTENSION"},
                                "signature": server["signature"],
                            },
                        )
                        r.raise_for_status()
                        cred_response = r.json()
                        if "value" not in cred_response:
                            if self.debug:
                                ic(f"Urban VPN cred response: {cred_response}")
                            continue
                        cred = cred_response["value"]
                        if "address" not in server or "primary" not in server["address"]:
                            continue
                        server_addr = server["address"]["primary"]
                        if "ip" not in server_addr or "port" not in server_addr:
                            continue
                        new_proxies.append(
                            f"http://{cred}:{cred}@{server_addr['ip']}:{server_addr['port']}"
                        )
                return new_proxies
            except Exception as e:
                if self.debug:
                    ic(f"Proxy fetch failed: {e}")
                return []

    def _background_refresh(self) -> None:
        """Background loop to refresh proxies."""
        while True:
            proxies = asyncio.run(self._fetch_urban_proxies())
            if proxies:
                with self._lock:
                    self._proxies = proxies
                    self._pool = cycle(self._proxies)
                if self.debug:
                    ic(f"Refreshed {len(proxies)} proxies background")
            time.sleep(1800)  # Refresh every 30 mins

    def get(self) -> dict[str, str]:
        """Get next proxy in rotation."""
        with self._lock:
            if not self._proxies:
                return {}
            proxy = next(self._pool)
            return {"http": proxy, "https": proxy}

    def patch(self) -> None:
        """Patch requests and curl_cffi to use this manager."""
        original_req_init = requests.Session.__init__
        original_curl_init = CurlSession.__init__
        pm = self

        def patched_req(self: requests.Session, *a, **k) -> None:
            original_req_init(self, *a, **k)
            if p := pm.get():
                self.proxies.update(cast(Any, p))

        def patched_curl(self: CurlSession, *a, **k) -> None:
            k["proxies"] = k.get("proxies") or pm.get()
            original_curl_init(self, *a, **k)

        requests.Session.__init__ = patched_req
        CurlSession.__init__ = patched_curl

    def monkey_patch(self) -> None:
        """Alias for patch() for backward compatibility."""
        self.patch()


__all__ = ["ProxyManager"]

if __name__ == "__main__":
    pm = ProxyManager(auto_fetch=True, debug=True)
    print("Initial proxies:", pm._proxies)
    pm.monkey_patch()
    # Example usage with requests
    import requests

    r = requests.get("http://httpbin.org/ip")
    print(r.json())