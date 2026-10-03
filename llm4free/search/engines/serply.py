"""Serply search engine - Google search results via REST API.

This engine provides Google search results through the Serply API,
requiring no scraping maintenance. Set SERPLY_API_KEY to enable it;
the key is sent in the ``X-Api-Key`` header, never in the URL.

Documentation: https://serply.io/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import BaseSearchEngine
from ..results import TextResult

logger = logging.getLogger(__name__)

API_URL = "https://api.serply.io/v1/search"

# Serply returns at most one Google results page per call.
MAX_RESULTS = 10


class Serply(BaseSearchEngine[TextResult]):
    """Google search engine backed by the Serply REST API.

    Requires the environment variable ``SERPLY_API_KEY`` to be set.
    New accounts get 2,500 free credits for 30 days at https://serply.io.
    """

    name = "serply"
    category = "text"
    provider = "google"
    required_auth = True

    search_url = API_URL
    search_method = "GET"

    # XPath fields are unused - this engine fetches structured JSON.
    items_xpath = ""
    elements_xpath: dict[str, str] = {}

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build query parameters for the Serply API."""
        num = kwargs.pop("num", None)
        if num is None:
            num = kwargs.pop("max_results", None)
        if num is None:
            num = MAX_RESULTS
        return {"q": query, "num": max(1, min(int(num), MAX_RESULTS))}

    @property
    def _api_key(self) -> str:
        """Read the API key from environment once per instance."""
        if not hasattr(self, "_cached_api_key"):
            self._cached_api_key = os.environ.get("SERPLY_API_KEY", "")
        return self._cached_api_key

    def search(
        self,
        query: str,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
        **kwargs: Any,
    ) -> list[TextResult]:
        """Run a Google text search via the Serply API.

        Raises ``RuntimeError`` when ``SERPLY_API_KEY`` is not set.  API
        errors are logged and result in an empty list rather than raising.
        """
        if not self._api_key:
            raise RuntimeError(
                "Serply requires SERPLY_API_KEY to be set. Get a key at https://serply.io"
            )

        timeout = kwargs.pop("timeout", 30)
        params = self.build_payload(query, region, safesearch, timelimit, page, **kwargs)

        try:
            resp = self.http_client.client.get(
                self.search_url,
                params=params,
                headers={"X-Api-Key": self._api_key, "User-Agent": "llm4free"},
                timeout=timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception:
            logger.exception("Serply API request failed for query=%r", query)
            return []

        results: list[TextResult] = []
        for item in data.get("results", []):
            link = item.get("link", "")
            if not link.startswith(("http://", "https://")):
                continue
            results.append(
                TextResult(
                    title=item.get("title", ""),
                    href=link,
                    body=item.get("description", ""),
                )
            )
        return results[: params["num"]]
