"""Bing news search."""

from __future__ import annotations

from time import sleep
from typing import List
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from llm4free.scout import Scout
from llm4free.search.results import NewsResult

from .base import BingBase


class BingNewsSearch(BingBase):
    name = "bing"
    category = "news"

    def _absolute_url(self, url: str) -> str:
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"{self.base_url}{url}"
        return url

    def _resolve_article_url(self, href: str) -> str:
        """Unwrap Bing's ``apiclick`` tracker into the publisher URL."""
        if not href:
            return href
        href = self._absolute_url(href)
        if "apiclick.aspx" in href:
            query = parse_qs(urlparse(href).query)
            target = query.get("url")
            if target:
                return unquote(target[0])
        return href

    def _extract_from_html(self, html: str, max_results: int) -> List[NewsResult]:
        """Extract news cards from Bing's infinitescroll markup.

        Current cards are ``div.news-card.newsitem`` elements that expose
        ``data-title``/``data-url``/``data-author`` directly, the relative
        date in ``.source span[aria-label]``, and the article image in
        ``div.image img`` (the publisher logo lives in ``.publogo``).
        Cards are marked ``nosnip`` and genuinely ship without a snippet.
        """
        soup = Scout(html)
        results: List[NewsResult] = []

        for item in soup.select("div.newsitem"):
            if len(results) >= max_results:
                break

            title_tag = item.select_one("a.title")
            title = item.get("data-title", "") or (
                title_tag.get_text(strip=True) if title_tag else ""
            )
            href = item.get("data-url", "") or item.get("url", "")
            if not href and title_tag:
                href = title_tag.get("href", "")
            if not title or not href:
                continue

            publisher = item.get("data-author", "")
            if not publisher and title_tag:
                publisher = title_tag.get("data-author", "")
            if not publisher:
                logo = item.select_one("a.biglogo_link[aria-label]")
                publisher = logo.get("aria-label", "") if logo else ""
            if not publisher:
                pubimg = item.select_one("img.pubimg")
                publisher = pubimg.get("title", "") if pubimg else ""

            date_tag = item.select_one(".source span[aria-label]")
            date = date_tag.get("aria-label", "") if date_tag else ""

            image = ""
            image_tag = item.select_one("div.image img")
            if image_tag:
                src = image_tag.get("data-src") or image_tag.get("src") or ""
                image = self._absolute_url(src)
            else:
                for img in item.select("img"):
                    classes = img.get("class", "")
                    class_list = classes if isinstance(classes, list) else str(classes).split()
                    if "pubimg" in class_list:
                        continue
                    src = img.get("data-src") or img.get("src") or ""
                    if src:
                        image = self._absolute_url(src)
                        break

            snippet = item.select_one("div.snippet") or item.select_one(".t_s p")
            results.append(
                NewsResult(
                    title=title,
                    url=self._resolve_article_url(href),
                    body=snippet.get_text(strip=True) if snippet else "",
                    source=publisher,
                    date=date,
                    image=image,
                )
            )

        return results

    def run(self, *args, **kwargs) -> List[NewsResult]:
        keywords = args[0] if args else kwargs.get("keywords")
        region = args[1] if len(args) > 1 else kwargs.get("region", "us")
        args[2] if len(args) > 2 else kwargs.get("safesearch", "moderate")
        max_results = args[3] if len(args) > 3 else kwargs.get("max_results", 10)

        if max_results is None:
            max_results = 10

        if not keywords:
            raise ValueError("Keywords are mandatory")

        # Bing news URL
        url = f"{self.base_url}/news/infinitescrollajax"
        params = {
            "q": keywords,
            "InfiniteScroll": "1",
            "first": "1",
            "SFX": "0",
            "cc": region.lower(),
            "setlang": self.lang.split("-")[0],
        }

        results: List[NewsResult] = []
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
                raise Exception(f"Failed to fetch news: {str(e)}")

            if not html:
                break

            page_results = self._extract_from_html(html, max_results - len(results))
            added = 0
            for result in page_results:
                if result.url in seen:
                    continue
                seen.add(result.url)
                results.append(result)
                added += 1
                if len(results) >= max_results:
                    break

            if not added:
                break

            first += 10
            sfx += 1

            if self.sleep_interval:
                sleep(self.sleep_interval)

        return results[:max_results]
