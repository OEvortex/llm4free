"""
>>> from llm4free import YTTranscriber
>>> transcript = YTTranscriber.get_transcript('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
>>> print(transcript)
{'text': 'Never gonna give you up', 'start': 0.0, 'duration': 4.5}

"""

import html
import http.cookiejar as cookiejar
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Dict, List, Optional, Union
from xml.etree import ElementTree

from llm4free.browser_requests._http.compat import Session

from llm4free.exceptions import (
    CookiePathInvalidError,
    FailedToCreateConsentCookieError,
    InvalidVideoIdError,
    NoTranscriptFoundError,
    NotTranslatableError,
    TooManyRequestsError,
    TranscriptRetrievalError,
    TranscriptsDisabledError,
    TranslationLanguageNotAvailableError,
    VideoUnavailableError,
    YouTubeRequestFailedError,
)
from llm4free.litagent import LitAgent

# YouTube API settings
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1/player?key={api_key}"
INNERTUBE_CONTEXT = {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38"}}
MAX_WORKERS = 4


class YTTranscriber:
    """Transcribe YouTube videos with style! 🎤

    >>> transcript = YTTranscriber.get_transcript('https://youtu.be/dQw4w9WgXcQ')
    >>> print(transcript[0]['text'])
    'Never gonna give you up'
    """

    _session = None
    _executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @classmethod
    def _get_session(cls):
        if cls._session is None:
            cls._session = Session()
            cls._session.headers.update({"User-Agent": LitAgent().random()})
        return cls._session

    @classmethod
    @lru_cache(maxsize=100)
    def get_transcript(
        cls,
        video_url: str,
        languages: Optional[str] = "en",
        proxies: Optional[Dict[str, str]] = None,
        cookies: Optional[str] = None,
        preserve_formatting: bool = False,
    ) -> List[Dict[str, Union[str, float]]]:
        """
        Retrieves the transcript for a given YouTube video URL.

        Args:
            video_url (str): YouTube video URL (supports various formats).
            languages (str, optional): Language code for the transcript.
                                    If None, fetches the first available transcript.
                                    Defaults to 'en'.
            proxies (Dict[str, str], optional): Proxies to use for the request. Defaults to None.
            cookies (str, optional): Path to the cookie file. Defaults to None.
            preserve_formatting (bool, optional): Whether to preserve formatting tags. Defaults to False.

        Returns:
            List[Dict[str, Union[str, float]]]: A list of dictionaries, each containing:
                - 'text': The transcribed text.
                - 'start': The start time of the text segment (in seconds).
                - 'duration': The duration of the text segment (in seconds).

        Raises:
            TranscriptRetrievalError: If there's an error retrieving the transcript.
        """
        video_id = cls._extract_video_id(video_url)
        http_client = cls._get_session()

        if proxies:
            http_client.proxies.update(proxies)

        if cookies:
            cls._load_cookies(cookies, video_id)

        transcript_list = TranscriptListFetcher(http_client).fetch(video_id)
        language_codes = [languages] if languages else None
        transcript = transcript_list.find_transcript(language_codes)

        return transcript.fetch(preserve_formatting)

    @staticmethod
    def _extract_video_id(video_url: str) -> str:
        """Extracts the video ID from different YouTube URL formats."""
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"youtu\.be\/([0-9A-Za-z_-]{11})",
            r"youtube\.com\/embed\/([0-9A-Za-z_-]{11})",
            r"youtube\.com\/shorts\/([0-9A-Za-z_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, video_url)
            if match:
                return match.group(1)

        if re.match(r"^[0-9A-Za-z_-]{11}$", video_url):
            return video_url

        raise InvalidVideoIdError(video_url)

    @staticmethod
    def _load_cookies(cookies: str, video_id: str) -> cookiejar.MozillaCookieJar:
        """Loads cookies from a file."""
        try:
            cj = cookiejar.MozillaCookieJar(cookies)
            cj.load()
            return cj
        except (cookiejar.LoadError, FileNotFoundError):
            raise CookiePathInvalidError(video_id)


class TranscriptListFetcher:
    """Fetches the list of transcripts for a YouTube video using InnerTube API."""

    def __init__(self, http_client: Session):
        """Initializes TranscriptListFetcher."""
        self._http_client = http_client

    def fetch(self, video_id: str):
        """Fetches and returns a TranscriptList."""
        captions_json = self._fetch_captions_json(video_id)
        return TranscriptList.build(
            self._http_client,
            video_id,
            captions_json,
        )

    def _fetch_captions_json(self, video_id: str) -> dict:
        """Fetches captions JSON using InnerTube API."""
        # First get the HTML to extract the API key
        video_html = self._fetch_video_html(video_id)
        api_key = self._extract_innertube_api_key(video_html, video_id)

        # Use InnerTube API to get video data
        innertube_data = self._fetch_innertube_data(video_id, api_key)
        return self._extract_captions_from_innertube(innertube_data, video_id)

    def _extract_innertube_api_key(self, html_content: str, video_id: str) -> str:
        """Extracts the InnerTube API key from HTML."""
        pattern = r'"INNERTUBE_API_KEY":\s*"([a-zA-Z0-9_-]+)"'
        match = re.search(pattern, html_content)
        if match and len(match.groups()) == 1:
            return match.group(1)

        # Check for IP block
        if 'class="g-recaptcha"' in html_content:
            raise TooManyRequestsError(video_id)

        raise TranscriptRetrievalError(video_id, "Could not extract InnerTube API key")

    def _fetch_innertube_data(self, video_id: str, api_key: str) -> dict:
        """Fetches video data from InnerTube API."""
        response = self._http_client.post(
            INNERTUBE_API_URL.format(api_key=api_key),
            json={
                "context": INNERTUBE_CONTEXT,
                "videoId": video_id,
            },
        )
        return _raise_http_errors(response, video_id).json()

    def _extract_captions_from_innertube(self, innertube_data: dict, video_id: str) -> dict:
        """Extracts captions JSON from InnerTube API response."""
        # Check playability status
        playability_status = innertube_data.get("playabilityStatus", {})
        status = playability_status.get("status")

        if status == "ERROR":
            reason = playability_status.get("reason", "Unknown error")
            if "unavailable" in reason.lower():
                raise VideoUnavailableError(video_id)
            raise TranscriptRetrievalError(video_id, reason)

        if status == "LOGIN_REQUIRED":
            reason = playability_status.get("reason", "")
            if "bot" in reason.lower():
                raise TooManyRequestsError(video_id)
            if "age" in reason.lower() or "inappropriate" in reason.lower():
                raise TranscriptRetrievalError(video_id, "Video is age-restricted")
            raise TranscriptRetrievalError(video_id, reason or "Login required")

        # Get captions
        captions = innertube_data.get("captions", {})
        captions_json = captions.get("playerCaptionsTracklistRenderer")

        if captions_json is None or "captionTracks" not in captions_json:
            raise TranscriptsDisabledError(video_id)

        return captions_json

    def _create_consent_cookie(self, html_content, video_id):
        match = re.search('name="v" value="(.*?)"', html_content)
        if match is None:
            raise FailedToCreateConsentCookieError(video_id)
        try:
            self._http_client.cookies.set("CONSENT", "YES+" + match.group(1))
        except Exception:
            pass

    def _fetch_video_html(self, video_id):
        html_content = self._fetch_html(video_id)
        if 'action="https://consent.youtube.com/s"' in html_content:
            self._create_consent_cookie(html_content, video_id)
            html_content = self._fetch_html(video_id)
            if 'action="https://consent.youtube.com/s"' in html_content:
                raise FailedToCreateConsentCookieError(video_id)
        return html_content

    def _fetch_html(self, video_id):
        response = self._http_client.get(
            WATCH_URL.format(video_id=video_id), headers={"Accept-Language": "en-US"}
        )
        return html.unescape(_raise_http_errors(response, video_id).text)


class TranscriptList:
    """
    >>> transcript_list = TranscriptList.build(http_client, video_id, captions_json)
    >>> transcript = transcript_list.find_transcript(['en'])
    >>> print(transcript)
    en ("English")[TRANSLATABLE]
    """

    def __init__(
        self, video_id, manually_created_transcripts, generated_transcripts, translation_languages
    ):
        """Init that transcript list with all the good stuff! 💯"""
        self.video_id = video_id
        self._manually_created_transcripts = manually_created_transcripts
        self._generated_transcripts = generated_transcripts
        self._translation_languages = translation_languages

    @staticmethod
    def build(http_client, video_id, captions_json):
        """
        Factory method for TranscriptList.

        :param http_client: http client which is used to make the transcript retrieving http calls
        :type http_client: Session
        :param video_id: the id of the video this TranscriptList is for
        :type video_id: str
        :param captions_json: the JSON parsed from the YouTube API
        :type captions_json: dict
        :return: the created TranscriptList
        :rtype TranscriptList:
        """
        # Handle both old format (simpleText) and new format (runs)
        translation_languages = []
        for tl in captions_json.get("translationLanguages", []):
            lang_name = tl.get("languageName", {})
            if isinstance(lang_name, dict):
                # Try new format first (runs), then old format (simpleText)
                if "runs" in lang_name:
                    name = lang_name["runs"][0]["text"]
                elif "simpleText" in lang_name:
                    name = lang_name["simpleText"]
                else:
                    name = tl.get("languageCode", "Unknown")
            else:
                name = str(lang_name)
            translation_languages.append(
                {
                    "language": name,
                    "language_code": tl["languageCode"],
                }
            )

        manually_created_transcripts = {}
        generated_transcripts = {}

        for caption in captions_json["captionTracks"]:
            if caption.get("kind", "") == "asr":
                transcript_dict = generated_transcripts
            else:
                transcript_dict = manually_created_transcripts

            # Extract caption name - handle both formats
            caption_name = caption.get("name", {})
            if isinstance(caption_name, dict):
                if "runs" in caption_name:
                    name = caption_name["runs"][0]["text"]
                elif "simpleText" in caption_name:
                    name = caption_name["simpleText"]
                else:
                    name = caption.get("languageCode", "Unknown")
            else:
                name = str(caption_name) if caption_name else caption.get("languageCode", "Unknown")

            # Remove &fmt=srv3 from URL as it can cause issues
            base_url = caption["baseUrl"].replace("&fmt=srv3", "")

            transcript_dict[caption["languageCode"]] = Transcript(
                http_client,
                video_id,
                base_url,
                name,
                caption["languageCode"],
                caption.get("kind", "") == "asr",
                translation_languages if caption.get("isTranslatable", False) else [],
            )

        return TranscriptList(
            video_id,
            manually_created_transcripts,
            generated_transcripts,
            translation_languages,
        )

    def __iter__(self):
        return iter(
            list(self._manually_created_transcripts.values())
            + list(self._generated_transcripts.values())
        )

    def find_transcript(self, language_codes):
        """
        Finds a transcript for a given language code. If no language is provided, it will
        return the first available transcript.

        :param language_codes: A list of language codes in a descending priority.
        :type languages: list[str]
        :return: the found Transcript
        :rtype Transcript:
        :raises: NoTranscriptFound
        """
        if not language_codes:
            language_codes = ["any"]

        if "any" in language_codes:
            for transcript in self:
                return transcript
        return self._find_transcript(
            language_codes, [self._manually_created_transcripts, self._generated_transcripts]
        )

    def find_generated_transcript(self, language_codes):
        """
        Finds an automatically generated transcript for a given language code.

        :param language_codes: A list of language codes in a descending priority. For example, if this is set to
        ['de', 'en'] it will first try to fetch the german transcript (de) and then fetch the english transcript (en) if
        it fails to do so.
        :type languages: list[str]
        :return: the found Transcript
        :rtype Transcript:
        :raises: NoTranscriptFound
        """
        if not language_codes:
            language_codes = ["any"]

        if "any" in language_codes:
            for transcript in self:
                if transcript.is_generated:
                    return transcript
        return self._find_transcript(language_codes, [self._generated_transcripts])

    def find_manually_created_transcript(self, language_codes):
        """
        Finds a manually created transcript for a given language code.

        :param language_codes: A list of language codes in a descending priority. For example, if this is set to
        ['de', 'en'] it will first try to fetch the german transcript (de) and then fetch the english transcript (en) if
        it fails to do so.
        :type languages: list[str]
        :return: the found Transcript
        :rtype Transcript:
        :raises: NoTranscriptFound
        """
        if not language_codes:
            language_codes = ["any"]
        return self._find_transcript(language_codes, [self._manually_created_transcripts])

    def _find_transcript(self, language_codes, transcript_dicts):
        for language_code in language_codes:
            for transcript_dict in transcript_dicts:
                if language_code in transcript_dict:
                    return transcript_dict[language_code]

        raise NoTranscriptFoundError(self.video_id, language_codes, self)

    def __str__(self):
        return (
            "For this video ({video_id}) transcripts are available in the following languages:\n\n"
            "(MANUALLY CREATED)\n"
            "{available_manually_created_transcript_languages}\n\n"
            "(GENERATED)\n"
            "{available_generated_transcripts}\n\n"
            "(TRANSLATION LANGUAGES)\n"
            "{available_translation_languages}"
        ).format(
            video_id=self.video_id,
            available_manually_created_transcript_languages=self._get_language_description(
                str(transcript) for transcript in self._manually_created_transcripts.values()
            ),
            available_generated_transcripts=self._get_language_description(
                str(transcript) for transcript in self._generated_transcripts.values()
            ),
            available_translation_languages=self._get_language_description(
                '{language_code} ("{language}")'.format(
                    language=translation_language["language"],
                    language_code=translation_language["language_code"],
                )
                for translation_language in self._translation_languages
            ),
        )

    def _get_language_description(self, transcript_strings):
        description = "\n".join(
            " - {transcript}".format(transcript=transcript) for transcript in transcript_strings
        )
        return description if description else "None"


class Transcript:
    """Your personal transcript handler! 🎭

    >>> transcript = transcript_list.find_transcript(['en'])
    >>> print(transcript.language)
    'English'
    >>> if transcript.is_translatable:
    ...     es_transcript = transcript.translate('es')
    ...     print(es_transcript.language)
    'Spanish'
    """

    def __init__(
        self,
        http_client,
        video_id,
        url,
        language,
        language_code,
        is_generated,
        translation_languages,
    ):
        """Initialize with all the goodies! 🎁"""
        self._http_client = http_client
        self.video_id = video_id
        self._url = url
        self.language = language
        self.language_code = language_code
        self.is_generated = is_generated
        self.translation_languages = translation_languages
        self._translation_languages_dict = {
            translation_language["language_code"]: translation_language["language"]
            for translation_language in translation_languages
        }

    def fetch(self, preserve_formatting=False):
        """Get that transcript data! 🎯

        Args:
            preserve_formatting (bool): Keep HTML formatting? Default is nah fam.

        Returns:
            list: That sweet transcript data with text, start time, and duration! 📝
        """
        response = self._http_client.get(self._url, headers={"Accept-Language": "en-US"})
        return TranscriptParser(preserve_formatting=preserve_formatting).parse(
            _raise_http_errors(response, self.video_id).text,
        )

    def __str__(self):
        """String representation looking clean! 💅"""
        return '{language_code} ("{language}"){translation_description}'.format(
            language=self.language,
            language_code=self.language_code,
            translation_description="[TRANSLATABLE]" if self.is_translatable else "",
        )

    @property
    def is_translatable(self):
        """Can we translate this? 🌍"""
        return len(self.translation_languages) > 0

    def translate(self, language_code):
        """Translate to another language! 🌎

        Args:
            language_code (str): Which language you want fam?

        Returns:
            Transcript: A fresh transcript in your requested language! 🔄

        Raises:
            NotTranslatableError: If we can't translate this one 😢
            TranslationLanguageNotAvailableError: If that language isn't available 🚫
        """
        if not self.is_translatable:
            raise NotTranslatableError(self.video_id)

        if language_code not in self._translation_languages_dict:
            raise TranslationLanguageNotAvailableError(self.video_id)

        return Transcript(
            self._http_client,
            self.video_id,
            "{url}&tlang={language_code}".format(url=self._url, language_code=language_code),
            self._translation_languages_dict[language_code],
            language_code,
            True,
            [],
        )


class TranscriptParser:
    """Parsing those transcripts like a pro! 🎯

    >>> parser = TranscriptParser(preserve_formatting=True)
    >>> data = parser.parse(xml_data)
    >>> print(data[0])
    {'text': 'Never gonna give you up', 'start': 0.0, 'duration': 4.5}
    """

    _FORMATTING_TAGS = [
        "strong",  # For that extra emphasis 💪
        "em",  # When you need that italic swag 🎨
        "b",  # Bold and beautiful 💯
        "i",  # More italic vibes ✨
        "mark",  # Highlight that text 🌟
        "small",  # Keep it lowkey 🤫
        "del",  # Strike it out ⚡
        "ins",  # Insert new stuff 🆕
        "sub",  # Subscript gang 📉
        "sup",  # Superscript squad 📈
    ]

    def __init__(self, preserve_formatting=False):
        """Get ready to parse with style! 🎨"""
        self._html_regex = self._get_html_regex(preserve_formatting)

    def _get_html_regex(self, preserve_formatting):
        """Get that regex pattern ready! 🎯"""
        if preserve_formatting:
            formats_regex = "|".join(self._FORMATTING_TAGS)
            formats_regex = r"<\/?(?!\/?(" + formats_regex + r")\b).*?\b>"
            html_regex = re.compile(formats_regex, re.IGNORECASE)
        else:
            html_regex = re.compile(r"<[^>]*>", re.IGNORECASE)
        return html_regex

    def parse(self, plain_data):
        """Parse that XML data into something beautiful! ✨"""
        try:
            return [
                {
                    "text": re.sub(self._html_regex, "", html.unescape(xml_element.text or "")),
                    "start": float(xml_element.attrib["start"]),
                    "duration": float(xml_element.attrib.get("dur", "0.0")),
                }
                for xml_element in ElementTree.fromstring(plain_data)
                if xml_element.text is not None
            ]
        except ElementTree.ParseError:
            # If XML parsing fails, try to extract text manually
            return self._fallback_parse(plain_data)

    def _fallback_parse(self, plain_data):
        """Fallback parsing method if XML parsing fails."""
        results = []
        # Try regex pattern matching
        pattern = r'<text start="([^"]+)" dur="([^"]+)"[^>]*>([^<]*)</text>'
        matches = re.findall(pattern, plain_data, re.DOTALL)

        for start, dur, text in matches:
            text = html.unescape(text)
            text = re.sub(self._html_regex, "", text)
            if text.strip():
                results.append(
                    {
                        "text": text.strip(),
                        "start": float(start),
                        "duration": float(dur),
                    }
                )

        return results


def _raise_http_errors(response, video_id):
    """Handle those HTTP errors with style! 🛠️"""
    try:
        if response.status_code == 429:
            raise TooManyRequestsError(video_id)
        response.raise_for_status()
        return response
    except Exception as error:
        raise YouTubeRequestFailedError(video_id, error)


if __name__ == "__main__":
    # Let's get this party started! 🎉
    from rich import print

    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    transcript = YTTranscriber.get_transcript(video_url, languages=None)
    print("Here's what we got! 🔥")
    print(transcript[:5])
