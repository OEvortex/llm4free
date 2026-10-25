"""Base class for DuckDuckGo search implementations."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
from itertools import cycle, islice
from random import choice
from time import sleep, time
from typing import Any, Optional, cast

from llm4free.browser_requests._http import compat as curl_cffi

try:
    from lxml.html import HTMLParser as LHTMLParser
    from lxml.html import document_fromstring

    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    LHTMLParser = None
    document_fromstring = None

from llm4free.litagent import LitAgent

from ....exceptions import LLM4FreeE, RatelimitE, TimeoutE
from ....utils import (
    _extract_vqd,
    _normalize,
    _normalize_url,
    json_loads,
)


class DuckDuckGoBase:
    """Base class for DuckDuckGo search operations."""

    _executor: ThreadPoolExecutor = ThreadPoolExecutor()
    _impersonates = (
        "chrome99",
        "chrome100",
        "chrome101",
        "chrome104",
        "chrome107",
        "chrome110",
        "chrome116",
        "chrome119",
        "chrome120",
        "chrome123",
        "chrome124",
        "chrome131",
        "chrome133a",
        "chrome99_android",
        "chrome131_android",
        "safari15_3",
        "safari15_5",
        "safari17_0",
        "safari17_2_ios",
        "safari18_0",
        "safari18_0_ios",
        "edge99",
        "edge101",
        "firefox133",
        "firefox135",
    )

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
        proxies: dict[str, str] | str | None = None,
        timeout: int | None = 10,
        verify: bool = True,
    ) -> None:
        """Initialize DuckDuckGo base client.

        Args:
            headers: Dictionary of headers for the HTTP client.
            proxy: Proxy for the HTTP client (http/https/socks5).
            proxies: Deprecated, use proxy instead.
            timeout: Timeout value for the HTTP client.
            verify: SSL verification when making requests.
        """
        ddgs_proxy: str | None = os.environ.get("DDGS_PROXY")
        self.proxy: str | None = ddgs_proxy if ddgs_proxy else proxy

        if not proxy and proxies:
            self.proxy = (
                proxies.get("http") or proxies.get("https")
                if isinstance(proxies, dict)
                else proxies
            )

        default_headers = {
            **LitAgent().generate_fingerprint(),
            "Origin": "https://duckduckgo.com",
            "Referer": "https://duckduckgo.com/",
        }

        self.headers = headers if headers else {}
        self.headers.update(default_headers)

        impersonate_browser = choice(self._impersonates)
        self.client = curl_cffi.requests.Session(
            headers=self.headers,
            proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None,
            timeout=timeout,  # ty:ignore[invalid-argument-type]
            impersonate=impersonate_browser,  # ty:ignore[invalid-argument-type]
            verify=verify,
        )
        self.timeout = timeout
        self.sleep_timestamp = 0.0

        # Utility methods
        self.cycle = cycle
        self.islice = islice

    @cached_property
    def parser(self) -> Any:
        """Get HTML parser."""
        if not LXML_AVAILABLE:
            raise ImportError("lxml is required for HTML parsing")

        class Parser:
            def __init__(self):
                self.lhtml_parser = (
                    LHTMLParser(
                        remove_blank_text=True,
                        remove_comments=True,
                        remove_pis=True,
                        collect_ids=False,
                    )
                    if LHTMLParser
                    else None
                )
                self.etree = __import__("lxml.etree", fromlist=["Element"])

            def fromstring(self, html: bytes | str) -> Any:
                return (
                    document_fromstring(html, parser=self.lhtml_parser)
                    if document_fromstring and self.lhtml_parser
                    else None
                )

        return Parser()

    def _sleep(self, sleeptime: float = 0.75) -> None:
        """Sleep between API requests."""
        delay = (
            0.0
            if not self.sleep_timestamp
            else 0.0
            if time() - self.sleep_timestamp >= 20
            else sleeptime
        )
        self.sleep_timestamp = time()
        sleep(delay)

    def _get_url(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        json: Any = None,
        timeout: float | None = None,
    ) -> Any:
        """Make HTTP request."""
        self._sleep()
        try:
            request_kwargs: dict[str, Any] = {
                "params": params,
                "headers": headers,
                "json": json,
                "timeout": timeout or self.timeout,
            }

            if isinstance(cookies, dict):
                request_kwargs["cookies"] = cookies

            if method == "GET":
                if content:
                    request_kwargs["data"] = content
                resp = self.client.get(url, **request_kwargs)
            elif method == "POST":
                if data or content:
                    request_kwargs["data"] = data or content
                resp = self.client.post(url, **request_kwargs)
            else:
                if data or content:
                    request_kwargs["data"] = data or content
                resp = self.client.request(cast(Any, method), url, **request_kwargs)
        except Exception as ex:
            if "time" in str(ex).lower():
                raise TimeoutE(f"{url} {type(ex).__name__}: {ex}") from ex
            raise LLM4FreeE(f"{url} {type(ex).__name__}: {ex}") from ex

        if resp.status_code == 200:
            return resp
        elif resp.status_code in (202, 301, 403, 400, 429, 418):
            raise RatelimitE(f"{resp.url} {resp.status_code} Ratelimit")
        raise LLM4FreeE(f"{resp.url} return None. {params=} {content=} {data=}")

    def _get_vqd(self, keywords: str) -> str:
        """Get vqd value for a search query."""
        resp_content = self._get_url(
            "GET", "https://duckduckgo.com", params={"q": keywords}
        ).content
        return _extract_vqd(resp_content, keywords)

    def json_loads(self, obj: str | bytes) -> Any:
        """Load JSON from string or bytes."""
        return json_loads(obj)

    def _normalize(self, text: str) -> str:
        """Normalize text."""
        return _normalize(text)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL."""
        return _normalize_url(url)
