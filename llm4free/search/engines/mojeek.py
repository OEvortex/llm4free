"""Mojeek search engine implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from ...exceptions import RatelimitE
from ..base import BaseSearchEngine
from ..results import TextResult

_CAPTCHA_MARKERS = (
    "<title>captcha</title>",
    "altcha",
    "captcha-wrap",
    "challenge.js",
)


class Mojeek(BaseSearchEngine[TextResult]):
    """Mojeek search engine."""

    name = "mojeek"
    category = "text"
    provider = "mojeek"

    search_url = "https://www.mojeek.com/search"
    search_method = "GET"

    items_xpath = "//ul[contains(@class, 'results')]/li"
    elements_xpath: Mapping[str, str] = {
        "title": ".//h2//text()",
        "href": ".//h2/a/@href",
        "body": ".//p[@class='s']//text()",
    }

    def request(self, method: str, url: str, **kwargs: Any) -> str | None:
        """Fetch Mojeek results, surfacing its anti-bot challenge.

        The base implementation swallows request errors, which made blocked
        searches look like empty result sets. Mojeek answers automated
        traffic with a 403 or an ALTCHA challenge page, so both are reported
        explicitly instead.
        """
        try:
            response = self.http_client.request(cast(Any, method), url, **kwargs)
        except RatelimitE as ex:
            raise RatelimitE(
                "Mojeek blocked this request (403/429). Automated searches require "
                "a browser session; the engine returned no usable results."
            ) from ex

        html_text = response.text
        lowered = html_text.lower()
        if any(marker in lowered for marker in _CAPTCHA_MARKERS):
            raise RatelimitE(
                "Mojeek returned an ALTCHA/CAPTCHA challenge instead of results. "
                "Automated searches are being throttled; retry later or use "
                "a proxy/browser session."
            )
        return html_text

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build a payload for the search request."""
        safesearch_base = {"on": "1", "moderate": "0", "off": "0"}
        payload = {"q": query, "safe": safesearch_base[safesearch.lower()]}
        if page > 1:
            payload["s"] = f"{(page - 1) * 10 + 1}"
        return payload

    def run(self, *args, **kwargs) -> list[TextResult]:
        """Run text search on Mojeek.

        Args:
            keywords: Search query.
            region: Region code.
            safesearch: Safe search level.
            max_results: Maximum number of results (ignored for now).

        Returns:
            List of TextResult objects.

        Raises:
            RatelimitE: Mojeek responded with an anti-bot challenge.
        """
        keywords = args[0] if args else kwargs.get("keywords")
        if not keywords:
            raise ValueError("Keywords are mandatory")
        region = args[1] if len(args) > 1 else kwargs.get("region", "us-en")
        safesearch = args[2] if len(args) > 2 else kwargs.get("safesearch", "moderate")
        max_results = args[3] if len(args) > 3 else kwargs.get("max_results")

        results = self.search(query=keywords, region=region, safesearch=safesearch)
        if results and max_results:
            results = results[:max_results]
        return results or []
