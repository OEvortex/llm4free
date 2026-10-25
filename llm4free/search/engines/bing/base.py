"""Base class for Bing search implementations."""

from __future__ import annotations

from llm4free.browser_requests._http.compat import Session

from llm4free.litagent import LitAgent


class BingBase:
    """Base class for Bing search engines."""

    def __init__(
        self,
        timeout: int = 10,
        proxies: dict[str, str] | None = None,
        verify: bool = True,
        lang: str = "en-US",
        sleep_interval: float = 0.0,
        impersonate: str = "chrome110",
    ):
        self.timeout = timeout
        self.proxies = proxies
        self.verify = verify
        self.lang = lang
        self.sleep_interval = sleep_interval
        self.base_url = "https://www.bing.com"
        from typing import Any, Optional, cast

        self.session = Session(
            proxies=cast(Any, proxies),
            verify=verify,
            timeout=timeout,
            impersonate=cast(Any, impersonate),
        )
        self.session.headers.update(LitAgent().generate_fingerprint())
