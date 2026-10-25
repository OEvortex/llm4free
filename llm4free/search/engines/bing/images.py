"""Bing images search."""

from __future__ import annotations

import json
from time import sleep
from typing import List
from urllib.parse import urlencode, urlparse

from llm4free.scout import Scout
from llm4free.search.results import ImagesResult

from .base import BingBase


def _as_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


class BingImagesSearch(BingBase):
    name = "bing"
    category = "images"

    def _extract_from_html(self, html: str, max_results: int) -> List[ImagesResult]:
        """Extract images from Bing's ``a.iusc`` cards.

        Each card carries its metadata JSON in the ``m`` attribute
        (``murl`` full image, ``turl`` thumbnail, ``purl`` source page,
        ``t``/``desc`` title), so the anchor is the source of truth rather
        than the nested thumbnail ``img``.
        """
        soup = Scout(html)
        results: List[ImagesResult] = []

        for anchor in soup.select("a.iusc"):
            if len(results) >= max_results:
                break

            metadata: dict[str, str] = {}
            raw_metadata = anchor.get("m")
            if raw_metadata:
                try:
                    metadata = json.loads(raw_metadata)
                except (TypeError, ValueError):
                    metadata = {}

            img = anchor.select_one("img.mimg") or anchor.select_one("img")
            fallback_src = img.get("src", "") if img else ""

            image_url = metadata.get("murl") or fallback_src
            if not image_url:
                continue

            thumbnail = metadata.get("turl") or fallback_src
            page_url = metadata.get("purl") or image_url
            title = metadata.get("t") or metadata.get("desc") or (img.get("alt", "") if img else "")

            results.append(
                ImagesResult(
                    title=title,
                    image=image_url,
                    thumbnail=thumbnail,
                    url=page_url,
                    height=_as_int(img.get("height") if img else None),
                    width=_as_int(img.get("width") if img else None),
                    source=urlparse(page_url).netloc if page_url else "",
                )
            )

        return results

    def run(self, *args, **kwargs) -> List[ImagesResult]:
        keywords = args[0] if args else kwargs.get("keywords")
        args[1] if len(args) > 1 else kwargs.get("region", "us")
        safesearch = args[2] if len(args) > 2 else kwargs.get("safesearch", "moderate")
        max_results = args[3] if len(args) > 3 else kwargs.get("max_results", 10)

        if max_results is None:
            max_results = 10

        if not keywords:
            raise ValueError("Keywords are mandatory")

        safe_map = {"on": "strict", "moderate": "moderate", "off": "off"}
        adult_filter = safe_map.get(str(safesearch).lower(), "moderate")

        # Bing images URL
        url = f"{self.base_url}/images/async"
        params = {
            "q": keywords,
            "first": "1",
            "count": "35",  # Fetch more to get max_results
            "cw": "1177",
            "ch": "759",
            "tsc": "ImageHoverTitle",
            "layout": "RowBased_Landscape",
            "t": "0",
            "IG": "",
            "SFX": "0",
            "iid": "images.1",
            "adlt": adult_filter,
        }

        results: List[ImagesResult] = []
        seen: set[str] = set()
        first = 1
        sfx = 0

        while len(results) < max_results:
            params["first"] = str(first)
            params["SFX"] = str(sfx)
            full_url = f"{url}?{urlencode(params)}"

            try:
                response = self.session.get(full_url, timeout=self.timeout)
                response.raise_for_status()
                html = response.text
            except Exception as e:
                raise Exception(f"Failed to fetch images: {str(e)}")

            if not html:
                break

            page_results = self._extract_from_html(html, max_results - len(results))
            added = 0
            for result in page_results:
                if result.image in seen:
                    continue
                seen.add(result.image)
                results.append(result)
                added += 1
                if len(results) >= max_results:
                    break

            if not added:
                break

            first += 35
            sfx += 1

            if self.sleep_interval:
                sleep(self.sleep_interval)

        return results[:max_results]
