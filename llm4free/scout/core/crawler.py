"""
Scout Crawler Module - Ultra Advanced Web Crawling System
"""

import concurrent.futures
import hashlib
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union
from urllib import robotparser

try:
    from llm4free.litagent import LitAgent
except ImportError:
    LitAgent: Any = None

try:
    from curl_cffi.requests import Session
except ImportError:
    from curl_cffi import requests

    Session: Any = requests.Session

from ..parsers import ParserRegistry
from .scout import Scout


@dataclass
class CrawlConfig:
    """Configuration for the crawler."""

    max_pages: int = 1000
    max_depth: int = 10
    delay: float = 0.5
    obey_robots: bool = True
    crawl_subdomains: bool = True
    max_workers: int = 10
    timeout: int = 30
    retry_attempts: int = 3
    include_external_links: bool = False
    extract_metadata: bool = True
    extract_structured_data: bool = True
    extract_semantic_content: bool = True


@dataclass
class PageData:
    """Comprehensive page data for LLM training."""

    url: str
    title: str
    text: str
    clean_text: str
    markdown_text: str
    links: List[str]
    internal_links: List[str]
    external_links: List[str]
    metadata: Dict[str, Any]
    structured_data: Dict[str, Any]
    semantic_content: Dict[str, Any]
    headers: Dict[str, str]
    status_code: int
    content_type: str
    language: str
    timestamp: str
    depth: int
    word_count: int


class ScoutCrawler:
    """
    Ultra-advanced web crawling utility optimized for LLM data collection.
    """

    def __init__(
        self,
        base_url: str,
        max_pages: int = 50,
        tags_to_remove: Optional[List[str]] = None,
        session: Optional[Any] = None,
        delay: float = 0.5,
        obey_robots: bool = True,
        allowed_domains: Optional[List[str]] = None,
    ):
        """
        Initialize the web crawler.

        Args:
            base_url (str): Starting URL to crawl
            max_pages (int, optional): Maximum number of pages to crawl
            tags_to_remove (List[str], optional): List of tags to remove
        """
        self.base_url = base_url
        self.max_pages = max_pages
        self.tags_to_remove = tags_to_remove if tags_to_remove is not None else ["script", "style"]
        self.visited_urls = set()
        self.crawled_pages = []
        self.session = session or Session()
        # LitAgent may not be available in minimal installs - provide a safe fallback
        if LitAgent is not None:
            self.agent = LitAgent()
        else:

            class _SimpleAgent:
                def generate_fingerprint(self) -> Dict[str, str]:
                    return {"user_agent": LitAgent().random()}

                def chrome(self) -> str:
                    return "Mozilla/5.0"

            self.agent = _SimpleAgent()

        # Use fingerprint to update session headers (normalize keys)
        fingerprint = self.agent.generate_fingerprint()
        headers: Dict[str, str] = {}
        if isinstance(fingerprint, dict):
            for k, v in fingerprint.items():
                if k == "user_agent":
                    headers["User-Agent"] = str(v)
                else:
                    headers[k.replace("_", "-").title()] = str(v)
        try:
            self.session.headers.update(headers)
        except Exception:
            # Some session implementations may not expose update() directly
            for hk, hv in headers.items():
                try:
                    self.session.headers[hk] = hv
                except Exception:
                    pass

        # Ensure a User-Agent is always present
        try:
            self.session.headers.setdefault("User-Agent", self.agent.chrome())
        except Exception:
            pass
        self.delay = delay
        self.obey_robots = obey_robots
        self.features = "lxml" if "lxml" in ParserRegistry.list_parsers() else "html.parser"

        # Secure domain handling
        parsed_base = urllib.parse.urlparse(base_url)
        self.base_netloc = parsed_base.netloc
        base_domain_parts = self.base_netloc.split(".")
        self.base_domain = (
            ".".join(base_domain_parts[-2:]) if len(base_domain_parts) > 1 else self.base_netloc
        )

        self.allowed_domains = allowed_domains or [self.base_netloc]
        self.last_request_time = 0
        self.url_hashes = set()

        if obey_robots:
            self.robots = robotparser.RobotFileParser()
            robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
            try:
                # Use session for robots.txt to respect headers/UA
                robots_resp = self.session.get(robots_url, timeout=5)
                if robots_resp.status_code == 200:
                    self.robots.parse(robots_resp.text.splitlines())
                else:
                    self.robots = None
            except Exception:
                self.robots = None
        else:
            self.robots = None

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing fragments and trailing slashes."""
        url = url.split("#")[0]
        return url.rstrip("/")

    def _is_valid_url(self, url: str) -> bool:
        """
        Check if a URL is valid and within allowed domains.
        """
        try:
            parsed_url = urllib.parse.urlparse(url)
            if parsed_url.scheme not in ["http", "https"]:
                return False

            # Secure domain check
            target_netloc = parsed_url.netloc.lower()
            is_allowed = False
            for allowed in self.allowed_domains:
                if target_netloc == allowed.lower() or target_netloc.endswith(
                    "." + allowed.lower()
                ):
                    is_allowed = True
                    break

            if not is_allowed:
                return False

            if self.obey_robots and self.robots:
                # Ensure we pass a str user-agent to robotparser.can_fetch
                ua = str(self.session.headers.get("User-Agent", "*"))
                return self.robots.can_fetch(ua, url)
            return True
        except Exception:
            return False

    def _is_duplicate(self, url: str) -> bool:
        norm = self._normalize_url(url)
        url_hash = hashlib.md5(norm.encode()).hexdigest()
        if url_hash in self.url_hashes:
            return True
        self.url_hashes.add(url_hash)
        return False

    def _extract_main_text(self, soup):
        # Try to extract main content (simple heuristic)
        main = soup.find("main")
        if main:
            return main.get_text(separator=" ", strip=True)
        article = soup.find("article")
        if article:
            return article.get_text(separator=" ", strip=True)
        # fallback to body
        body = soup.find("body")
        if body:
            return body.get_text(separator=" ", strip=True)
        return soup.get_text(separator=" ", strip=True)

    def _crawl_page(self, url: str, depth: int = 0) -> Dict[str, Any]:
        """
        Crawl a single page and extract information.

        Args:
            url (str): URL to crawl
            depth (int, optional): Current crawl depth

        Returns:
            Dict[str, Any]: Crawled page information
        """
        if url in self.visited_urls or self._is_duplicate(url):
            return {}
        # Log URL to crawl
        print(f"Attempting to crawl URL: {url} (depth: {depth})")

        # Throttle requests
        now = time.time()
        if self.last_request_time:
            elapsed = now - self.last_request_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self.last_request_time = time.time()
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            if not response.headers.get("Content-Type", "").startswith("text/html"):
                return {}
            scout = Scout(response.content, features=self.features)
            title_tag = scout.find("title")
            title = title_tag.get_text() if title_tag else ""

            # Remove only script and style tags before extracting text
            for tag_name in self.tags_to_remove:
                for tag in scout._soup.find_all(tag_name):
                    tag.decompose()

            visible_text = self._extract_main_text(scout._soup)

            # Extract links from header, footer, nav, etc.
            essential_links = []
            for essential_tag in ["header", "nav", "footer"]:
                elements = scout.find_all(essential_tag)
                for element in elements:
                    links = element.find_all("a", href=True)
                    essential_links.extend(
                        urllib.parse.urljoin(url, link.get("href"))
                        for link in links
                        if link.get("href")
                        and self._is_valid_url(urllib.parse.urljoin(url, link.get("href")))
                    )

            all_links = [
                urllib.parse.urljoin(url, link.get("href"))
                for link in scout.find_all("a", href=True)
                if self._is_valid_url(urllib.parse.urljoin(url, link.get("href")))
            ]

            combined_links = list(set(all_links + essential_links))

            page_info = {
                "url": url,
                "title": title,
                "links": combined_links,
                "text": visible_text,
                "depth": depth,
                "timestamp": datetime.now().isoformat(),
                "headers": dict(response.headers),
            }
            self.visited_urls.add(url)
            self.crawled_pages.append(page_info)
            return page_info
        except Exception as e:
            print(f"Error crawling {url}: {e}")
            return {}

    def crawl(self):
        """
        Start web crawling from base URL and yield each crawled page in real time.

        Yields:
            Dict[str, Union[str, List[str]]]: Crawled page information
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._crawl_page, self.base_url, 0)}
            submitted_links: Set[str] = set()

            while futures:
                if self.max_pages is not None and len(self.visited_urls) >= self.max_pages:
                    break
                done, not_done = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED
                )
                futures = not_done

                for future in done:
                    page_info = future.result()

                    if page_info:
                        yield page_info

                        if self.max_pages is not None and len(self.visited_urls) >= self.max_pages:
                            return

                        for link in page_info.get("links", []):
                            if (
                                (self.max_pages is None or len(self.visited_urls) < self.max_pages)
                                and link not in self.visited_urls
                                and link not in submitted_links
                            ):
                                submitted_links.add(link)
                                futures.add(
                                    executor.submit(
                                        self._crawl_page,
                                        link,
                                        int(page_info.get("depth", 0)) + 1,
                                    )
                                )
                    else:
                        print("No page info retrieved from crawling")
