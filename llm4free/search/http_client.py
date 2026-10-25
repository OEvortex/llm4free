"""HTTP client for search engines."""

from __future__ import annotations

from random import choice
from typing import Any, Literal, Optional, cast

from llm4free.browser_requests._http import compat as curl_cffi

from ..exceptions import LLM4FreeE, RatelimitE, TimeoutE


class HttpClient:
    """HTTP client wrapper for search engines."""

    # curl_cffi supported browser impersonations
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
        proxy: str | None = None,
        timeout: int | None = 10,
        verify: bool = True,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize HTTP client.

        Args:
            proxy: Proxy URL (supports http/https/socks5).
            timeout: Request timeout in seconds.
            verify: Whether to verify SSL certificates.
            headers: Default headers for requests.
        """
        self.proxy = proxy
        self.timeout = timeout
        self.verify = verify

        # Choose random browser to impersonate
        impersonate_browser = choice(self._impersonates)

        # Initialize curl_cffi session
        self.client = curl_cffi.requests.Session(
            headers=headers or {},
            proxies={"http": self.proxy, "https": self.proxy} if self.proxy else None,
            timeout=cast(Any, timeout),
            impersonate=impersonate_browser,  # ty:ignore[invalid-argument-type]
            verify=verify,
        )

    def request(
        self,
        method: Literal["GET", "POST", "HEAD", "OPTIONS", "DELETE", "PUT", "PATCH"],
        url: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | bytes | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> curl_cffi.requests.Response:
        """Make HTTP request.

        Args:
            method: HTTP method.
            url: Request URL.
            params: URL parameters.
            data: Request body data.
            json: JSON data to send.
            headers: Request headers.
            cookies: Request cookies.
            timeout: Request timeout (overrides default).
            **kwargs: Additional arguments passed to curl_cffi.

        Returns:
            Response object.

        Raises:
            TimeoutE: Request timeout.
            RatelimitE: Rate limit exceeded.
            LLM4FreeE: Other request errors.
        """
        try:
            request_kwargs: dict[str, Any] = {
                "params": params,
                "headers": headers,
                "json": json,
                "timeout": timeout or self.timeout,
                **kwargs,
            }

            if isinstance(cookies, dict):
                request_kwargs["cookies"] = cookies

            if data is not None:
                request_kwargs["data"] = data

            resp = self.client.request(method, url, **request_kwargs)

            # Check response status
            if resp.status_code == 200:
                return resp
            elif resp.status_code in (202, 301, 403, 400, 429, 418):
                raise RatelimitE(f"{resp.url} {resp.status_code} Rate limit")
            else:
                raise LLM4FreeE(f"{resp.url} returned {resp.status_code}")

        except LLM4FreeE:
            raise
        except Exception as ex:
            if "time" in str(ex).lower() or "timeout" in str(ex).lower():
                raise TimeoutE(f"{url} {type(ex).__name__}: {ex}") from ex
            raise LLM4FreeE(f"{url} {type(ex).__name__}: {ex}") from ex

    def get(self, url: str, **kwargs: Any) -> curl_cffi.requests.Response:
        """Make GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> curl_cffi.requests.Response:
        """Make POST request."""
        return self.request("POST", url, **kwargs)

    def set_cookies(self, url: str, cookies: dict[str, str]) -> None:
        """Set cookies for a domain.

        Args:
            url: URL to set cookies for.
            cookies: Cookie dictionary.
        """
        self.client.cookies.update(cookies)

    def close(self) -> None:
        """Close the HTTP client."""
        if hasattr(self.client, "close"):
            self.client.close()

    def __enter__(self) -> HttpClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
