"""Brave text search."""

from __future__ import annotations
from llm4free import LitAgent

from time import sleep
from typing import List, Optional

from llm4free.scout import Scout

from ....search.results import TextResult
from .base import BraveBase


class BraveTextSearch(BraveBase):
    """Brave text/web search."""

    name = "brave"
    category = "text"

    def run(self, *args, **kwargs) -> List[TextResult]:
        """Perform text search on Brave using offset pagination.

        Uses server-rendered HTML and parses result containers with CSS selectors.
        """
        from typing import cast

        keywords = args[0] if args else kwargs.get("keywords")
        if not keywords:
            raise ValueError("Keywords are mandatory")

        safesearch = args[2] if len(args) > 2 else kwargs.get("safesearch", "moderate")
        max_results = args[3] if len(args) > 3 else kwargs.get("max_results", 10)
        if max_results is None:
            max_results = 10

        safesearch_map = {"on": "strict", "moderate": "moderate", "off": "off"}
        safesearch_value = safesearch_map.get(safesearch.lower(), "moderate")

        start_offset = int(kwargs.get("start_offset", 0))
        offset = start_offset

        fetched_results: List[TextResult] = []
        fetched_hrefs: set[str] = set()

        def fetch_html(params: dict) -> str:
            url = f"{self.base_url}/search"
            # Keep the Brave request headers minimal; curl_cffi streaming works reliably
            # with a clean browser-like header set.
            headers = {
                "User-Agent": self.session.headers.get(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://search.brave.com/",
            }
            attempts = 3
            backoff = 1.0
            last_exc: Exception | None = None
            for attempt in range(attempts):
                try:
                    resp = self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout,
                        stream=True,
                    )
                    resp.raise_for_status()

                    # Unit tests use a lightweight fake response without streaming APIs.
                    if not hasattr(resp, "iter_content"):
                        return getattr(resp, "text", "") or ""

                    chunks: list[bytes] = []
                    total = 0
                    try:
                        for chunk in resp.iter_content():
                            if not chunk:
                                continue
                            chunks.append(chunk)
                            total += len(chunk)
                            # We only need enough HTML for the result containers.
                            if total >= 256_000:
                                break
                    except Exception:
                        # curl_cffi may report a stream error after enough body data has
                        # already been received. Keep the partial HTML if we have it.
                        if not chunks:
                            raise

                    body = b"".join(chunks)
                    encoding = getattr(resp, "encoding", None) or "utf-8"
                    return body.decode(encoding, errors="replace")
                except Exception as exc:  # network or HTTP errors
                    last_exc = exc
                    # If it's a 429 / transient server error, back off and retry
                    try:
                        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                    except Exception:
                        code = None
                    if code in (429, 500, 502, 503, 504):
                        sleep(backoff)
                        backoff *= 2
                        continue
                    raise Exception(f"Failed to GET {url} with {params}: {exc}") from exc
            raise Exception(f"Failed to GET {url} after retries: {last_exc}") from last_exc

        # Pagination: offset param is a 0-based page index
        while len(fetched_results) < max_results:
            params = {"q": keywords, "source": "web", "offset": str(offset), "spellcheck": "0"}
            if safesearch_value:
                params["safesearch"] = safesearch_value

            html = fetch_html(params)
            # Parse and extract results using helper
            page_results = self._parse_results_from_html(html)

            if not page_results:
                break

            for res in page_results:
                if len(fetched_results) >= max_results:
                    break
                if res.href and res.href not in fetched_hrefs:
                    fetched_hrefs.add(res.href)
                    fetched_results.append(res)

            offset += 1
            if self.sleep_interval:
                sleep(self.sleep_interval)

        return fetched_results[:max_results]

    def _parse_results_from_html(self, html: str) -> List[TextResult]:
        """Parse HTML and extract text search results.

        This method is separated for testability.
        """
        soup = Scout(html)
        containers = soup.select("div.result-content")
        results: List[TextResult] = []

        for container in containers:
            a_elem = container.select_one("a[href]")
            # Title may be in .title.search-snippet-title or nested inside the anchor
            title_elem = container.select_one(".title.search-snippet-title") or (
                a_elem.select_one(".title") if a_elem else None
            )

            # Try multiple snippet locations: inside container, sibling .snippet, parent fallbacks
            body = ""
            candidates = []
            # inside container
            candidates.append(container.select_one(".generic-snippet"))
            candidates.append(container.select_one(".snippet .generic-snippet"))
            candidates.append(container.select_one(".description"))
            candidates.append(container.select_one(".result-snippet"))
            candidates.append(container.select_one("p"))

            # sibling .snippet
            try:
                fn = getattr(container, "find_next_sibling", None)
                if callable(fn):
                    sib = fn("div", class_="snippet")
                    if sib:
                        candidates.append(sib.select_one(".generic-snippet"))
            except Exception:
                pass

            # parent-level fallbacks
            if container.parent:
                candidates.append(container.parent.select_one(".snippet .generic-snippet"))
                candidates.append(container.parent.select_one(".generic-snippet"))

            for c in candidates:
                if c:
                    text = c.get_text(strip=True)
                    if text:
                        body = text
                        break

            if a_elem and title_elem:
                href = a_elem.get("href", "").strip()
                title = title_elem.get_text(strip=True)
                results.append(TextResult(title=title, href=href, body=body))

        return results
