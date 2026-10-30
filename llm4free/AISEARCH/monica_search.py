from typing import Any, Dict, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http import compat as requests
from llm4free.browser_requests._http.exceptions import RequestException

from llm4free import exceptions
from llm4free.AIbase import AISearch, SearchResponse
from llm4free.litagent import LitAgent
from llm4free.sanitize import sanitize_stream


class Monica(AISearch):
    """
    A class to interact with the Monica stream search API.
    """

    def __init__(
        self,
        timeout: int = 60,
        proxies: Optional[dict] = None,
    ):
        """Initializes the Monica API client."""
        import uuid

        self.session = requests.Session()
        self.api_endpoint = "https://monica.so/api/search_v1/search"
        self.stream_chunk_size = 64
        self.timeout = timeout
        self.last_response = {}
        self.client_id = str(uuid.uuid4())
        self.session_id = ""

        # Set initial headers
        self.headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "dnt": "1",
            "origin": "https://monica.so",
            "referer": "https://monica.so/answers",
            "sec-ch-ua": '"Microsoft Edge";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "user-agent": LitAgent().random(),
            "x-client-id": self.client_id,
            "x-client-locale": "en",
            "x-client-type": "web",
            "x-client-version": "5.4.3",
            "x-from-channel": "NA",
            "x-product-name": "Monica-Search",
            "x-time-zone": "Asia/Calcutta;-330",
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
        """
        Sends a prompt to the Monica API and returns the response.

        Args:
            prompt: The search query or prompt to send to the API
            stream: Whether to stream the response
            raw: If True, returns unprocessed response chunks without any
                processing or sanitization. Useful for debugging or custom
                processing pipelines. Defaults to False.

        Returns:
            When raw=False: SearchResponse object (non-streaming) or
                Generator yielding SearchResponse objects (streaming)
            When raw=True: Raw string response (non-streaming) or
                Generator yielding raw string chunks (streaming)

        Examples:
            >>> ai = Monica()
            >>> # Get processed response
            >>> response = ai.search("Hello")
            >>> print(response)

            >>> # Get raw response
            >>> raw_response = ai.search("Hello", raw=True)
            >>> print(raw_response)

            >>> # Stream raw chunks
            >>> for chunk in ai.search("Hello", stream=True, raw=True):
            ...     print(chunk, end='', flush=True)
        """
        import uuid

        task_id = str(uuid.uuid4())
        payload = {
            "pro": False,
            "query": prompt,
            "round": 1,
            "session_id": self.session_id,
            "language": "auto",
            "task_id": task_id,
        }

        def for_stream():
            try:
                # Set cookies for the session
                self.session.cookies.set("monica_home_theme", "auto")

                response = self.session.post(
                    self.api_endpoint,
                    json=payload,
                    stream=True,
                    timeout=self.timeout,
                    proxies=self.proxies
                )
                if not response.ok:
                    raise exceptions.APIConnectionError(
                        f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                    )

                processed_chunks = sanitize_stream(
                    data=response.iter_content(chunk_size=None),
                    to_json=True,
                    content_extractor=lambda chunk: (
                        chunk.get("text")
                        if isinstance(chunk, dict) and chunk.get("text") is not None
                        else None
                    ),
                    yield_raw_on_error=False,
                    encoding="utf-8",
                    encoding_errors="replace",
                    raw=raw,
                    output_formatter=None
                    if raw
                    else lambda x: SearchResponse(x) if isinstance(x, str) else x,
                )

                yield from processed_chunks

            except RequestException as e:
                raise exceptions.APIConnectionError(f"Request failed: {e}")

        def for_non_stream():
            try:
                # Set cookies for the session
                self.session.cookies.set("monica_home_theme", "auto")

                response = self.session.post(
                    self.api_endpoint,
                    json=payload,
                    stream=False,
                    timeout=self.timeout,
                    proxies=self.proxies
                )
                if not response.ok:
                    raise exceptions.APIConnectionError(
                        f"Failed to generate response - ({response.status_code}, {response.reason}) - {response.text}"
                    )

                if raw:
                    # Return raw response text when raw=True
                    return response.text
                else:
                    # Process response similar to streaming when raw=False
                    processed_chunks = sanitize_stream(
                        data=response.content,
                        intro_value="",
                        to_json=True,
                        skip_markers=[],
                        strip_chars=None,
                        start_marker=None,
                        end_marker=None,
                        content_extractor=lambda chunk: (
                            chunk.get("text")
                            if isinstance(chunk, dict) and chunk.get("text") is not None
                            else None
                        ),
                        yield_raw_on_error=False,
                        encoding="utf-8",
                        encoding_errors="replace",
                        buffer_size=8192,
                    )

                    full_response = ""
                    for content_chunk in processed_chunks:
                        if content_chunk is not None and isinstance(content_chunk, str):
                            full_response += content_chunk

                    self.last_response = SearchResponse(full_response)
                    return self.last_response

            except RequestException as e:
                raise exceptions.APIConnectionError(f"Request failed: {e}")

        return for_stream() if stream else for_non_stream()


if __name__ == "__main__":
    ai = Monica()
    response = ai.search("What is Python?", stream=True, raw=False)
    if hasattr(response, "__iter__") and not isinstance(response, (str, bytes, SearchResponse)):
        for chunks in response:
            print(chunks, end="", flush=True)
    else:
        print(response)
