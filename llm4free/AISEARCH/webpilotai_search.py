import re
from typing import Any, Dict, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http import compat as requests
from llm4free.browser_requests._http.exceptions import RequestException, Timeout

from llm4free import exceptions
from llm4free.AIbase import AISearch, SearchResponse
from llm4free.litagent import LitAgent
from llm4free.sanitize import sanitize_stream


class webpilotai(AISearch):
    """A class to interact with the webpilotai (WebPilot) AI search API.

    webpilotai provides a web-based comprehensive search SearchResponse interface that returns AI-generated
    SearchResponses with source references and related questions. It supports both streaming and
    non-streaming SearchResponses.

    Basic Usage:
        >>> from llm4free import webpilotai
        >>> ai = webpilotai()
        >>> # Non-streaming example
        >>> response = ai.search("What is Python?")
        >>> print(response)
        Python is a high-level programming language...

        >>> # Streaming example
        >>> for chunk in ai.search("Tell me about AI", stream=True):
        ...     print(chunk, end="", flush=True)
        Artificial Intelligence is...

        >>> # Raw SearchResponse format
        >>> for chunk in ai.search("Hello", stream=True, raw=True):
        ...     print(chunk)
        {'text': 'Hello'}
        {'text': ' there!'}

    Args:
        timeout (int, optional): Request timeout in seconds. Defaults to 90.
        proxies (dict, optional): Proxy configuration for requests. Defaults to None.
    """

    def __init__(
        self,
        timeout: int = 90,
        proxies: Optional[dict] = None,
    ):
        """Initialize the webpilotai API client.

        Args:
            timeout (int, optional): Request timeout in seconds. Defaults to 90.
            proxies (dict, optional): Proxy configuration for requests. Defaults to None.
        """
        self.session = requests.Session()
        self.api_endpoint = "https://api.webpilotai.com/rupee/v1/search"
        self.timeout = timeout
        self.last_response = {}

        # The 'Bearer null' is part of the API's expected headers
        self.headers = {
            "Accept": "application/json, text/plain, */*, text/event-stream",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": "Bearer null",
            "Origin": "https://www.webpilot.ai",
            "Referer": "https://www.webpilot.ai/",
            "User-Agent": LitAgent().random(),
        }

        self.session.headers.update(self.headers)
        self.proxies = proxies

    def search(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        **kwargs: Any,
    ) -> Union[
        SearchResponse,
        Generator[Union[Dict[str, str], SearchResponse], None, None],
        List[Any],
        Dict[str, Any],
        str,
    ]:
        """Search using the webpilotai API and get AI-generated SearchResponses.

        This method sends a search query to webpilotai and returns the AI-generated SearchResponse.
        It supports both streaming and non-streaming modes, as well as raw SearchResponse format.

        Args:
            prompt (str): The search query or prompt to send to the API.
            stream (bool, optional): If True, yields SearchResponse chunks as they arrive.
                                   If False, returns complete SearchResponse. Defaults to False.
            raw (bool, optional): If True, returns raw SearchResponse dictionaries with 'text' key.
                                If False, returns SearchResponse objects that convert to text automatically.
                                Defaults to False.

        Returns:
            Union[SearchResponse, Generator[Union[Dict[str, str], SearchResponse], None, None]]:
                - If stream=False: Returns complete SearchResponse as SearchResponse object
                - If stream=True: Yields SearchResponse chunks as either Dict or SearchResponse objects

        Raises:
            APIConnectionError: If the API request fails
        """
        payload = {
            "q": prompt,
            "threadId": "",  # Empty for new search
        }

        # We'll use regex-based extraction for WebPilot events. The sanitizer will:
        #  - skip lines that are not "type":"data" events using skip_regexes
        #  - extract the "content" value using a regex that handles escaped quotes
        # The regex used below for extract_regexes is: r'"content"\s*:\s*"((?:\\.|[^"\\])*)"'
        # which captures the content string while allowing escaped characters such as \".

        def for_stream():
            try:
                response = self.session.post(
                    self.api_endpoint,
                    json=payload,
                    stream=True,
                    timeout=self.timeout,
                    proxies=self.proxies,
                )
                if not response.ok:
                    raise exceptions.APIConnectionError(
                        f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                    )

                processed_chunks = sanitize_stream(
                    data=response.iter_content(chunk_size=1024),
                    to_json=True,
                    # Extract content from parsed JSON payload similar to Monica
                    content_extractor=lambda chunk: (
                        (
                            (chunk.get("data") or {}).get("content")
                            if isinstance(chunk, dict)
                            else None
                        )
                        or (
                            (chunk.get("data") or {}).get("text")
                            if isinstance(chunk, dict)
                            else None
                        )
                        or (
                            (chunk.get("data") or {}).get("delta", {}).get("content")
                            if isinstance(chunk, dict)
                            else None
                        )
                    ),
                    skip_markers=["event:message"],
                    yield_raw_on_error=False,
                    encoding="utf-8",
                    encoding_errors="replace",
                    line_delimiter="\n",
                    raw=raw,
                    output_formatter=None
                    if raw
                    else lambda x: SearchResponse(x) if isinstance(x, str) else x,
                )

                for chunk in processed_chunks:
                    yield chunk

            except Timeout:
                raise exceptions.APIConnectionError("Request timed out")
            except RequestException as e:
                raise exceptions.APIConnectionError(f"Request failed: {e}")

        def for_non_stream():
            try:
                response = self.session.post(
                    self.api_endpoint,
                    json=payload,
                    stream=False,
                    timeout=self.timeout,
                    proxies=self.proxies,
                )
                if not response.ok:
                    raise exceptions.APIConnectionError(
                        f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                    )

                if raw:
                    return response.text

                # Process full response payload using sanitize_stream similar to streaming path
                processed_chunks = sanitize_stream(
                    data=response.content,
                    intro_value="",
                    to_json=True,
                    strip_chars=None,
                    start_marker=None,
                    end_marker=None,
                    content_extractor=lambda chunk: (
                        (
                            (chunk.get("data") or {}).get("content")
                            if isinstance(chunk, dict)
                            else None
                        )
                        or (
                            (chunk.get("data") or {}).get("text")
                            if isinstance(chunk, dict)
                            else None
                        )
                        or (
                            (chunk.get("data") or {}).get("delta", {}).get("content")
                            if isinstance(chunk, dict)
                            else None
                        )
                    ),
                    skip_markers=["event:message"],
                    yield_raw_on_error=False,
                    encoding="utf-8",
                    encoding_errors="replace",
                    buffer_size=8192,
                    output_formatter=lambda x: SearchResponse(x) if isinstance(x, str) else x,
                )

                full_response = ""
                for content_chunk in processed_chunks:
                    if content_chunk is not None:
                        full_response += str(content_chunk)

                formatted_response = self.format_SearchResponse(full_response)
                self.last_response = SearchResponse(formatted_response)
                return self.last_response

            except RequestException as e:
                raise exceptions.APIConnectionError(f"Request failed: {e}")

        if stream:
            return for_stream()
        else:
            return for_non_stream()

    @staticmethod
    def format_SearchResponse(text: str) -> str:
        """Format the SearchResponse text for better readability.

        Args:
            text (str): The raw SearchResponse text

        Returns:
            str: Formatted text with improved structure
        """
        # Clean up formatting
        # Remove excessive newlines
        clean_text = re.sub(r"\n{3,}", "\n\n", text)

        # Ensure consistent spacing around sections
        clean_text = re.sub(r"([.!?])\s*\n\s*([A-Z])", r"\1\n\n\2", clean_text)

        # Clean up any leftover HTML or markdown artifacts
        clean_text = re.sub(r"<[^>]*>", "", clean_text)

        # Remove trailing whitespace on each line
        clean_text = "\n".join(line.rstrip() for line in clean_text.split("\n"))

        return clean_text.strip()


if __name__ == "__main__":
    from rich import print

    ai = webpilotai()
    resp = ai.search("llm4free python package details", stream=True, raw=False)
    if hasattr(resp, "__iter__") and not isinstance(resp, (str, SearchResponse)):
        for chunk in resp:
            print(chunk, end="", flush=True)
    else:
        print(resp)
