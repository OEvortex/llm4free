"""Yahoo image search engine with advanced filters."""

from __future__ import annotations
from llm4free import LitAgent

from collections.abc import Mapping
from typing import Any, Optional

from ...results import ImagesResult
from .base import YahooSearchEngine


class YahooImages(YahooSearchEngine[ImagesResult]):
    """Yahoo image search engine with filter support.

    Features:
    - Size filters (small, medium, large, wallpaper)
    - Color filters (color, bw, red, orange, yellow, etc.)
    - Type filters (photo, clipart, lineart, transparent)
    - Layout filters (square, wide, tall)
    - Time filters
    - Pagination support

    Note: Yahoo does not support reverse image search (searching by image upload/URL).
    For reverse image search functionality, use Google Images or Bing Images instead.
    """

    name = "yahoo"
    category = "images"

    search_url = "https://images.search.yahoo.com/search/images"
    search_method = "GET"
    search_headers = {
        "User-Agent": LitAgent().random()
    }

    # XPath selectors
    items_xpath = "//li[contains(@class, 'tile') and contains(@class, 'Sr')]"
    elements_xpath: Mapping[str, str] = {
        "title": ".//*[contains(@class, 'tile-title')]//text()",
        "image": ".//@data-origurl",
        "thumbnail": ".//img/@src",
        "url": ".//@data-referenceurl",
        "source": ".//*[contains(@class, 'tile-domain')]//text()",
        "width": "",
        "height": "",
    }

    # Filter mappings
    SIZE_FILTERS = {
        "small": "small",
        "medium": "medium",
        "large": "large",
        "wallpaper": "wallpaper",
        "all": "",
    }

    COLOR_FILTERS = {
        "color": "color",
        "bw": "bw",
        "black": "black",
        "white": "white",
        "red": "red",
        "orange": "orange",
        "yellow": "yellow",
        "green": "green",
        "teal": "teal",
        "blue": "blue",
        "purple": "purple",
        "pink": "pink",
        "brown": "brown",
        "gray": "gray",
        "all": "",
    }

    TYPE_FILTERS = {
        "photo": "photo",
        "clipart": "clipart",
        "lineart": "linedrawing",
        "transparent": "transparent",
        "gif": "animatedgif",
        "all": "",
    }

    LAYOUT_FILTERS = {
        "square": "square",
        "wide": "wide",
        "tall": "tall",
        "all": "",
    }

    def build_payload(
        self,
        query: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build image search payload with filters.

        Args:
            query: Search query
            region: Region code
            safesearch: Safe search level (on/moderate/off)
            timelimit: Time filter (d, w, m)
            page: Page number
            **kwargs: Additional filters including:
                - size: Image size filter
                - color: Color filter
                - type: Image type filter
                - layout: Layout/aspect ratio filter
                - license: Usage rights filter

        Returns:
            Query parameters dictionary
        """
        payload = {
            "p": query,
        }

        # Pagination - Yahoo images use 'b' parameter
        if page > 1:
            # Each page shows approximately 40 images
            payload["b"] = f"{(page - 1) * 40 + 1}"

        # Safe search
        if safesearch == "on":
            payload["safe"] = "active"
        elif safesearch == "off":
            payload["safe"] = "off"

        # Time filter
        if timelimit:
            time_map = {
                "d": "1d",  # Past 24 hours
                "w": "1w",  # Past week
                "m": "1m",  # Past month
            }
            if timelimit in time_map:
                payload["age"] = time_map[timelimit]

        # Size filter
        if "size" in kwargs and kwargs["size"] in self.SIZE_FILTERS:
            size_val = self.SIZE_FILTERS[kwargs["size"]]
            if size_val:
                payload["imgsz"] = size_val

        # Color filter
        if "color" in kwargs and kwargs["color"] in self.COLOR_FILTERS:
            color_val = self.COLOR_FILTERS[kwargs["color"]]
            if color_val:
                payload["imgc"] = color_val

        # Type filter
        if "type" in kwargs and kwargs["type"] in self.TYPE_FILTERS:
            type_val = self.TYPE_FILTERS[kwargs["type"]]
            if type_val:
                payload["imgt"] = type_val

        # Layout filter
        if "layout" in kwargs and kwargs["layout"] in self.LAYOUT_FILTERS:
            layout_val = self.LAYOUT_FILTERS[kwargs["layout"]]
            if layout_val:
                payload["imgsp"] = layout_val

        return payload

    def post_extract_results(self, results: list[ImagesResult]) -> list[ImagesResult]:
        """Post-process image results to clean URLs and metadata.

        Args:
            results: Raw extracted results

        Returns:
            Cleaned results with proper URLs and metadata
        """
        from urllib.parse import unquote

        cleaned_results = []

        for result in results:
            if not result.image and result.thumbnail:
                result.image = result.thumbnail

            # Clean URLs if they exist
            if result.url:
                result.url = unquote(result.url)
            if result.image:
                result.image = unquote(result.image)
            if result.thumbnail:
                result.thumbnail = unquote(result.thumbnail)

            cleaned_results.append(result)

        return cleaned_results

    def search(
        self,
        query: str,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        page: int = 1,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> list[ImagesResult] | None:
        """Search Yahoo Images with pagination.

        Args:
            query: Image search query
            region: Region code
            safesearch: Safe search level
            timelimit: Time filter
            page: Starting page
            max_results: Maximum results to return
            **kwargs: Additional filters (size, color, type, layout)

        Returns:
            List of ImageResult objects
        """
        results = []
        current_page = page
        max_pages = kwargs.get("max_pages", 5)

        while current_page <= max_pages:
            payload = self.build_payload(
                query=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                page=current_page,
                **kwargs,
            )

            html_text = self.request(self.search_method, self.search_url, params=payload)
            if not html_text:
                break

            html_text = self.pre_process_html(html_text)
            page_results = self.extract_results(html_text)

            if not page_results:
                break

            results.extend(page_results)

            if max_results and len(results) >= max_results:
                break

            current_page += 1

        results = self.post_extract_results(results)

        if max_results:
            results = results[:max_results]

        return results if results else None

    def run(
        self,
        keywords: str,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        size: str | None = None,
        color: str | None = None,
        type_image: str | None = None,
        layout: str | None = None,
        license_image: str | None = None,
        max_results: int | None = None,
    ) -> list[ImagesResult]:
        """Run image search.

        Args:
            keywords: Search query.
            region: Region code.
            safesearch: Safe search level.
            timelimit: Time filter.
            size: Image size filter.
            color: Color filter.
            type_image: Image type filter.
            layout: Layout filter.
            license_image: License filter.
            max_results: Maximum number of results.

        Returns:
            List of ImagesResult objects.
        """
        results = self.search(
            query=keywords,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit,
            size=size,
            color=color,
            type_image=type_image,
            layout=layout,
            license_image=license_image,
            max_results=max_results,
        )
        return results or []
