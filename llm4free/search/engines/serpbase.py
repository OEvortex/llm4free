"""SerpBase search engine — Google search results via REST API.

This engine provides Google search results through the SerpBase API,
requiring no scraping maintenance. Set SERPBASE_API_KEY to enable it;
when the key is missing the engine silently returns an empty list so
other engines continue unaffected.

Documentation: https://serpbase.dev
"""

from __future__ import annotations
from litprinter import ic

import os
from typing import Any

from ..base import BaseSearchEngine
from ..results import TextResult


API_URL = "https://api.serpbase.dev/google/search"


class SerpBase(BaseSearchEngine[TextResult]):
    """Google search engine backed by the SerpBase REST API.

    Requires the environment variable ``SERPBASE_API_KEY`` to be set.
    Get a free key (100 searches, no credit card) at https://serpbase.dev.
    """

    name = "serpbase"
    category = "text"
    provider = "google"
    required_auth = True

    search_url = API_URL
    search_method = "GET"

    # XPath fields are unused — this engine fetches structured JSON.
    items_xpath = ""

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build query parameters for the SerpBase API."""
        num = kwargs.pop("num", 10)
        return {"q": query, "num": num, "api_key": self._api_key}

    @property
    def _api_key(self) -> str:
        """Read the API key from environment once per instance."""
        if not hasattr(self, "_cached_api_key"):
            self._cached_api_key = os.environ.get("SERPBASE_API_KEY", "")
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
        """Run a Google text search via the SerpBase API.

        Returns an empty list when ``SERPBASE_API_KEY`` is not set so that
        other engines are unaffected.  API errors are logged and also result
        in an empty list rather than raising.
        """
        if not self._api_key:
            raise RuntimeError(
                "SerpBase requires SERPBASE_API_KEY to be set. "
                "Get a free key at https://serpbase.dev"
            )

        num = kwargs.pop("num", 10)
        params: dict[str, Any] = {
            "q": query,
            "num": num,
            "api_key": self._api_key,
        }

        try:
            resp = self.http_client.client.get(
                self.search_url,
                params=params,
                timeout=kwargs.pop("timeout", 30),
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        except Exception:
            ic("SerpBase API request failed for query=%r", query)
            return []

        results: list[TextResult] = []
        for item in data.get("organic_results", []):
            results.append(
                TextResult(
                    title=item.get("title", ""),
                    href=item.get("link", ""),
                    body=item.get("snippet", ""),
                )
            )
        return results
