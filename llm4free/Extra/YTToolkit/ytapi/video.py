import json
from llm4free import LitAgent
import re
from typing import Any, Dict, Generator, List, Optional

from .https import video_data

try:
    from llm4free.litagent.agent import LitAgent

    _USER_AGENT = LitAgent().random()
except ImportError:
    _USER_AGENT = LitAgent().random()


class Video:
    _HEAD = "https://www.youtube.com/watch?v="

    def __init__(self, video_id: str):
        """
        Represents a YouTube video

        Parameters
        ----------
        video_id : str
            The id or url of the video
        """
        pattern = re.compile(r".be/(.*?)$|=(.*?)$|shorts/(.*?)$|^(\w{11})$")  # noqa
        match = pattern.search(video_id)

        if not match:
            raise ValueError("Invalid YouTube video ID or URL")

        self._matched_id = match.group(1) or match.group(2) or match.group(3) or match.group(4)

        if self._matched_id:
            self._url = self._HEAD + self._matched_id
            self._video_data = video_data(self._matched_id)
            # Extract basic info for fallback
            title_match = re.search(r"<title>(.*?) - YouTube</title>", self._video_data)
            self.title = title_match.group(1) if title_match else None
            self.id = self._matched_id
        else:
            raise ValueError("Invalid YouTube video ID or URL")

    def __repr__(self):
        return f"<Video {self._url}>"

    @property
    def metadata(self) -> Dict[str, Any]:
        """
        Fetches video metadata in a dict format

        Returns
        -------
        Dict
            Video metadata in a dict format containing keys: title, id, views, duration, author_id,
            upload_date, url, thumbnails, tags, description, likes, genre, etc.
        """
        # Multiple patterns to try for video details extraction for robustness
        details_patterns = [
            re.compile(r"videoDetails\":(.*?)\"isLiveContent\":.*?}"),
            re.compile(r"videoDetails\":(.*?),\"playerConfig"),
            re.compile(r"videoDetails\":(.*?),\"playabilityStatus"),
        ]

        # Other metadata patterns
        upload_date_pattern = re.compile(r"<meta itemprop=\"uploadDate\" content=\"(.*?)\">")
        genre_pattern = re.compile(r"<meta itemprop=\"genre\" content=\"(.*?)\">")
        like_count_patterns = [
            re.compile(r"iconType\":\"LIKE\"},\"defaultText\":(.*?)}"),
            re.compile(r"\"likeCount\":\"(\d+)\""),
        ]
        channel_name_pattern = re.compile(r'"ownerChannelName":"(.*?)"')

        # Try each pattern for video details
        raw_details_match = None
        for pattern in details_patterns:
            match = pattern.search(self._video_data)
            if match:
                raw_details_match = match
                break

        if not raw_details_match:
            # Fallback metadata for search results or incomplete video data
            return {
                "title": getattr(self, "title", None),
                "id": getattr(self, "id", None),
                "views": getattr(self, "views", None),
                "streamed": False,
                "duration": None,
                "author_id": None,
                "author_name": None,
                "upload_date": None,
                "url": f"https://www.youtube.com/watch?v={getattr(self, 'id', '')}"
                if hasattr(self, "id")
                else None,
                "thumbnails": None,
                "tags": None,
                "description": None,
                "likes": None,
                "genre": None,
                "is_age_restricted": "age-restricted" in self._video_data.lower(),
                "is_unlisted": "unlisted" in self._video_data.lower(),
            }

        raw_details = raw_details_match.group(0)

        # Extract upload date
        upload_date_match = upload_date_pattern.search(self._video_data)
        upload_date = upload_date_match.group(1) if upload_date_match else None

        # Extract channel name
        channel_name_match = channel_name_pattern.search(self._video_data)
        channel_name = channel_name_match.group(1) if channel_name_match else None

        # Parse video details
        try:
            # Clean up the JSON string for parsing
            clean_json = raw_details.replace('videoDetails":', "")
            # Handle potential JSON parsing issues
            if clean_json.endswith(","):
                clean_json = clean_json[:-1]
            metadata = json.loads(clean_json)

            data = {
                "title": metadata.get("title"),
                "id": metadata.get("videoId", self._matched_id),
                "views": metadata.get("viewCount"),
                "streamed": metadata.get("isLiveContent", False),
                "duration": metadata.get("lengthSeconds"),
                "author_id": metadata.get("channelId"),
                "author_name": channel_name or metadata.get("author"),
                "upload_date": upload_date,
                "url": f"https://www.youtube.com/watch?v={metadata.get('videoId', self._matched_id)}",
                "thumbnails": metadata.get("thumbnail", {}).get("thumbnails"),
                "tags": metadata.get("keywords"),
                "description": metadata.get("shortDescription"),
                "is_age_restricted": metadata.get("isAgeRestricted", False)
                or "age-restricted" in self._video_data.lower(),
                "is_unlisted": "unlisted" in self._video_data.lower(),
                "is_family_safe": metadata.get("isFamilySafe", True),
                "is_private": metadata.get("isPrivate", False),
                "is_live_content": metadata.get("isLiveContent", False),
                "is_crawlable": metadata.get("isCrawlable", True),
                "allow_ratings": metadata.get("allowRatings", True),
            }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Fallback to basic metadata if JSON parsing fails
            return {
                "title": getattr(self, "title", None),
                "id": self._matched_id,
                "url": self._url,
                "error": f"Failed to parse video details: {str(e)}",
            }

        # Try to extract likes count
        likes = None
        for pattern in like_count_patterns:
            try:
                likes_match = pattern.search(self._video_data)
                if likes_match:
                    likes_text = likes_match.group(1)
                    # Handle different formats of like count
                    if "{" in likes_text:
                        likes = (
                            json.loads(likes_text + "}}}")["accessibility"]["accessibilityData"][
                                "label"
                            ]
                            .split(" ")[0]
                            .replace(",", "")
                        )
                    else:
                        likes = likes_text
                    break
            except (AttributeError, KeyError, json.decoder.JSONDecodeError):
                continue

        data["likes"] = likes

        # Try to extract genre
        try:
            genre_match = genre_pattern.search(self._video_data)
            data["genre"] = genre_match.group(1) if genre_match else None
        except AttributeError:
            data["genre"] = None

        return data

    @property
    def embed_html(self) -> str:
        """
        Get the embed HTML code for this video

        Returns:
            HTML iframe code for embedding the video
        """
        return f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{self._matched_id}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'

    @property
    def embed_url(self) -> str:
        """
        Get the embed URL for this video

        Returns:
            URL for embedding the video
        """
        return f"https://www.youtube.com/embed/{self._matched_id}"

    @property
    def thumbnail_url(self) -> str:
        """
        Get the thumbnail URL for this video

        Returns:
            URL of the video thumbnail (high quality)
        """
        return f"https://i.ytimg.com/vi/{self._matched_id}/hqdefault.jpg"

    @property
    def thumbnail_urls(self) -> Dict[str, str]:
        """
        Get all thumbnail URLs for this video in different qualities

        Returns:
            Dictionary of thumbnail URLs with quality labels
        """
        return {
            "default": f"https://i.ytimg.com/vi/{self._matched_id}/default.jpg",
            "medium": f"https://i.ytimg.com/vi/{self._matched_id}/mqdefault.jpg",
            "high": f"https://i.ytimg.com/vi/{self._matched_id}/hqdefault.jpg",
            "standard": f"https://i.ytimg.com/vi/{self._matched_id}/sddefault.jpg",
            "maxres": f"https://i.ytimg.com/vi/{self._matched_id}/maxresdefault.jpg",
        }

    @property
    def is_live(self) -> bool:
        """
        Check if video is currently live.

        Returns:
            True if video is live, False otherwise
        """
        return '"isLive":true' in self._video_data or '"isLiveNow":true' in self._video_data

    @property
    def is_short(self) -> bool:
        """
        Check if video is a YouTube Short.

        Returns:
            True if video is a Short, False otherwise
        """
        # Check duration (Shorts are max 60 seconds)
        meta = self.metadata
        duration = meta.get("duration")
        if duration and int(duration) <= 60:
            # Also check for shorts indicators
            if "shorts" in self._video_data.lower() or '"shorts"' in self._video_data:
                return True
        return False

    @property
    def hashtags(self) -> List[str]:
        """
        Get hashtags from video description and title.

        Returns:
            List of hashtags found
        """
        meta = self.metadata
        text = (meta.get("description", "") or "") + " " + (meta.get("title", "") or "")
        pattern = r"#([a-zA-Z0-9_]+)"
        matches = re.findall(pattern, text)
        return list(dict.fromkeys(matches))  # Remove duplicates

    def get_related_videos(self, limit: int = 10) -> List[str]:
        """
        Get related/suggested videos.

        Args:
            limit: Maximum number of video IDs to return

        Returns:
            List of related video IDs
        """
        # Find related videos in the page data
        pattern = r'"watchNextEndScreenRenderer".*?"videoId":"([a-zA-Z0-9_-]{11})"'
        matches = re.findall(pattern, self._video_data)

        if not matches:
            # Fallback pattern
            pattern = r'"compactVideoRenderer".*?"videoId":"([a-zA-Z0-9_-]{11})"'
            matches = re.findall(pattern, self._video_data)

        # Remove duplicates and self
        seen = set()
        unique = []
        for vid in matches:
            if vid not in seen and vid != self._matched_id:
                seen.add(vid)
                unique.append(vid)
                if len(unique) >= limit:
                    break

        return unique

    def get_chapters(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get video chapters if available.

        Returns:
            List of chapters with title, start_time, and thumbnail, or None
        """
        # Look for chapter data in the page
        pattern = r'"chapterRenderer":\s*\{[^}]*"title":\s*\{\s*"simpleText":\s*"([^"]+)"[^}]*"timeRangeStartMillis":\s*(\d+)'
        matches = re.findall(pattern, self._video_data)

        if not matches:
            # Alternative pattern
            pattern = r'"chapters":\s*\[(.*?)\]'
            chapter_match = re.search(pattern, self._video_data)
            if chapter_match:
                try:
                    # Parse as JSON if possible
                    chapters_str = "[" + chapter_match.group(1) + "]"
                    chapters_data = json.loads(chapters_str)
                    return chapters_data
                except Exception:
                    pass
            return None

        chapters = []
        for title, start_ms in matches:
            chapters.append(
                {
                    "title": title,
                    "start_seconds": int(start_ms) / 1000,
                    "start_time": f"{int(int(start_ms) / 1000 // 60)}:{int(int(start_ms) / 1000 % 60):02d}",
                }
            )

        return chapters if chapters else None

    def stream_comments(self, limit: int = 20) -> Generator[Dict[str, Any], None, None]:
        """
        Stream video comments from initial page load.

        Note: YouTube loads comments dynamically via JavaScript, so this method
        may not find comments for all videos. It works best when YouTube includes
        some initial comments in the page HTML.

        Args:
            limit: Maximum number of comments to yield

        Yields:
            Comment dictionaries with author, text, video_id
        """
        # Try multiple patterns for comments data
        patterns = [
            # Pattern for commentRenderer with simpleText
            r'"commentRenderer":\s*\{[^}]*"authorText":\s*\{[^}]*"simpleText":\s*"([^"]+)"[^}]*\}.*?"contentText":\s*\{[^}]*"runs":\s*\[\s*\{[^}]*"text":\s*"([^"]*)"',
            # Pattern for author and contentText
            r'"authorText":\s*\{[^}]*"simpleText":\s*"([^"]+)"[^}]*\}[^}]*"contentText":\s*\{[^}]*"text":\s*"([^"]*)"',
            # Simpler pattern
            r'"authorText":"([^"]+)".*?"contentText":"([^"]*)"',
        ]

        count = 0
        seen_comments = set()

        for pattern in patterns:
            if count >= limit:
                break
            matches = re.findall(pattern, self._video_data, re.DOTALL)
            for author, text in matches:
                if count >= limit:
                    break
                # Avoid duplicates
                comment_key = (author, text[:50])
                if comment_key in seen_comments:
                    continue
                seen_comments.add(comment_key)

                # Clean up text
                text = text.replace("\\n", "\n")
                text = text.replace("\\u0026", "&")
                text = text.replace("\\u003c", "<")
                text = text.replace("\\u003e", ">")

                yield {"author": author, "text": text, "video_id": self._matched_id}
                count += 1


if __name__ == "__main__":
    video = Video("https://www.youtube.com/watch?v=9bZkp7q19f0")
    print(video.metadata)
    print(f"\nIs Live: {video.is_live}")
    print(f"Is Short: {video.is_short}")
    print(f"Hashtags: {video.hashtags}")
    print(f"Related videos: {video.get_related_videos(5)}")

    chapters = video.get_chapters()
    if chapters:
        print(f"Chapters: {chapters[:3]}")
