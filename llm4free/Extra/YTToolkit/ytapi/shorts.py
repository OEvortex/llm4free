"""YouTube Shorts functionality."""

import re
from llm4free import LitAgent
from typing import List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .patterns import _ExtraPatterns as Patterns
from .utils import dup_filter, request

try:
    from llm4free.litagent.agent import LitAgent

    _USER_AGENT = LitAgent().random()
except ImportError:
    _USER_AGENT = LitAgent().random()


class Shorts:
    """Class for YouTube Shorts operations."""

    SHORTS_URL = "https://www.youtube.com/shorts"

    @staticmethod
    def is_short(video_id: str) -> bool:
        """
        Check if a video is a YouTube Short.

        Args:
            video_id: YouTube video ID

        Returns:
            True if video is a Short, False otherwise
        """
        if not video_id:
            return False

        # Clean video ID
        if "youtube.com" in video_id or "youtu.be" in video_id:
            match = re.search(r"(?:v=|shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})", video_id)
            if match:
                video_id = match.group(1)

        url = f"https://www.youtube.com/shorts/{video_id}"

        try:
            headers = {"User-Agent": _USER_AGENT, "Accept": "text/html"}
            req = Request(url, headers=headers, method="HEAD")
            response = urlopen(req, timeout=10)
            # If we get a 200 and URL contains /shorts/, it's a Short
            final_url = response.geturl()
            return "/shorts/" in final_url
        except HTTPError as e:
            if e.code == 303 or e.code == 302:
                # Redirect means it's not a Short (redirects to /watch)
                return False
            return False
        except Exception:
            return False

    @staticmethod
    def get_trending(limit: int = 20) -> List[str]:
        """
        Get trending YouTube Shorts.

        Args:
            limit: Maximum number of Shorts to return

        Returns:
            List of video IDs for trending Shorts
        """
        try:
            html = request("https://www.youtube.com/shorts")
            # Find video IDs in shorts context
            pattern = r'"videoId":"([a-zA-Z0-9_-]{11})"'
            video_ids = re.findall(pattern, html)
            return dup_filter(video_ids, limit)
        except Exception:
            return []

    @staticmethod
    def search(query: str, limit: int = 20) -> List[str]:
        """
        Search for YouTube Shorts.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of video IDs for matching Shorts
        """
        if not query:
            return []

        from urllib.parse import quote

        # sp=EgIYAQ%253D%253D is the filter for Shorts
        url = f"https://www.youtube.com/results?search_query={quote(query)}&sp=EgIYAQ%253D%253D"

        try:
            html = request(url)
            video_ids = Patterns.video_id.findall(html)
            return dup_filter(video_ids, limit)
        except Exception:
            return []


if __name__ == "__main__":
    print("Testing Shorts.is_short:")
    # Test with a known Short ID (you'd replace with an actual Short ID)
    print(f"  is_short test: {Shorts.is_short('abc123')}")

    print("\nTrending Shorts:")
    trending = Shorts.get_trending(5)
    for vid in trending:
        print(f"  - {vid}")

    print("\nSearch Shorts:")
    results = Shorts.search("funny cats", 5)
    for vid in results:
        print(f"  - {vid}")
