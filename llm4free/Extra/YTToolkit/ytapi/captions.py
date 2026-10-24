"""YouTube video captions and transcripts.

This module wraps the YTTranscriber for a simplified interface.
"""

import re
from llm4free import LitAgent
from typing import Any, Dict, List, Optional

from curl_cffi.requests import Session

# Use the existing robust YTTranscriber
from llm4free.Extra.YTToolkit.transcriber import TranscriptListFetcher, YTTranscriber


class Captions:
    """Class for YouTube captions and transcripts.

    Uses YTTranscriber internally for reliable transcript fetching.

    Example:
        >>> from llm4free.Extra.YTToolkit.ytapi import Captions
        >>> transcript = Captions.get_transcript("dQw4w9WgXcQ")
        >>> print(transcript[:100])
    """

    @staticmethod
    def _extract_video_id(video_id: str) -> str:
        """Extract clean video ID from URL or ID."""
        if not video_id:
            return ""

        patterns = [r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", r"^([a-zA-Z0-9_-]{11})$"]

        for pattern in patterns:
            match = re.search(pattern, video_id)
            if match:
                return match.group(1)

        return video_id

    @staticmethod
    def get_available_languages(video_id: str) -> List[Dict[str, Any]]:
        """
        Get available caption languages for a video.

        Args:
            video_id: YouTube video ID or URL

        Returns:
            List of dicts with 'code', 'name', 'is_auto' for each language
        """
        if not video_id:
            return []

        video_id = Captions._extract_video_id(video_id)

        try:
            session = Session()
            session.headers.update(
                {"User-Agent": LitAgent().random()}
            )

            fetcher = TranscriptListFetcher(session)
            transcript_list = fetcher.fetch(video_id)

            languages = []

            # Add manually created transcripts
            for transcript in transcript_list._manually_created_transcripts.values():
                languages.append(
                    {
                        "code": transcript.language_code,
                        "name": transcript.language,
                        "is_auto": False,
                    }
                )

            # Add generated transcripts
            for transcript in transcript_list._generated_transcripts.values():
                languages.append(
                    {"code": transcript.language_code, "name": transcript.language, "is_auto": True}
                )

            return languages
        except Exception:
            return []

    @staticmethod
    def get_transcript(video_id: str, language: str = "en") -> Optional[str]:
        """
        Get plain text transcript for a video.

        Args:
            video_id: YouTube video ID or URL
            language: Language code (e.g., 'en', 'es')

        Returns:
            Transcript text or None
        """
        timed = Captions.get_timed_transcript(video_id, language)
        if not timed:
            return None

        return " ".join([entry["text"] for entry in timed])

    @staticmethod
    def get_timed_transcript(video_id: str, language: str = "en") -> Optional[List[Dict[str, Any]]]:
        """
        Get transcript with timestamps.

        Args:
            video_id: YouTube video ID or URL
            language: Language code (e.g., 'en', 'es'). Use 'any' for first available.

        Returns:
            List of dicts with 'text', 'start', 'duration' or None
        """
        if not video_id:
            return None

        video_id = Captions._extract_video_id(video_id)

        try:
            # Use YTTranscriber for reliable fetching
            transcript = YTTranscriber.get_transcript(
                video_id, languages=language if language != "any" else None
            )
            return transcript
        except Exception:
            # If requested language fails, try any available
            if language != "any":
                try:
                    transcript = YTTranscriber.get_transcript(video_id, languages=None)
                    return transcript
                except Exception:
                    pass
            return None

    @staticmethod
    def search_transcript(video_id: str, query: str, language: str = "en") -> List[Dict[str, Any]]:
        """
        Search within a video's transcript.

        Args:
            video_id: YouTube video ID or URL
            query: Text to search for
            language: Language code

        Returns:
            List of matching segments with timestamps
        """
        if not query:
            return []

        transcript = Captions.get_timed_transcript(video_id, language)
        if not transcript:
            return []

        query_lower = query.lower()
        results = []

        for entry in transcript:
            if query_lower in entry["text"].lower():
                results.append(entry)

        return results


if __name__ == "__main__":
    # Test with a video that has captions
    video_id = "dQw4w9WgXcQ"

    print("Available languages:")
    langs = Captions.get_available_languages(video_id)
    for lang in langs[:5]:
        print(f"  - {lang['code']}: {lang['name']} (auto: {lang.get('is_auto', False)})")

    print("\nGetting transcript:")
    transcript = Captions.get_timed_transcript(video_id)
    if transcript:
        print(f"  Found {len(transcript)} segments")
        for entry in transcript[:3]:
            print(f"  {entry['start']:.1f}s: {entry['text'][:50]}")
    else:
        print("  No transcript available")
