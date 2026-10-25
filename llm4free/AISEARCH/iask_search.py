import asyncio
import re
import urllib.parse
from typing import Any, AsyncIterator, Dict, Generator, Literal, Optional, Union, cast

import lxml.html
from llm4free.browser_requests._http.compat import AsyncSession

from llm4free import exceptions
from llm4free.AIbase import AISearch, SearchResponse
from llm4free.litagent import LitAgent
from llm4free.scout import Scout

ModeType = Literal["question", "academic", "forums", "wiki", "thinking"]
DetailLevelType = Literal["concise", "detailed", "comprehensive"]


class IAsk(AISearch):
    """A class to interact with the IAsk AI search API.

    IAsk provides a powerful search interface that returns AI-generated responses
    based on web content. It supports both streaming and non-streaming responses,
    as well as different search modes and detail levels.

    Basic Usage:
        >>> from llm4free import IAsk
        >>> ai = IAsk()
        >>> # Non-streaming example
        >>> response = ai.search("What is Python?")
        >>> print(response)
        Python is a high-level programming language...

        >>> # Streaming example
        >>> for chunk in ai.search("Tell me about AI", stream=True):
        ...     print(chunk, end="", flush=True)
        Artificial Intelligence is...

        >>> # With specific mode and detail level
        >>> response = ai.search("Climate change", mode="academic", detail_level="detailed")
        >>> print(response)
        Climate change refers to...

    Args:
        timeout (int, optional): Request timeout in seconds. Defaults to 30.
        proxies (dict, optional): Proxy configuration for requests. Defaults to None.
        mode (ModeType, optional): Default search mode. Defaults to "question".
        detail_level (DetailLevelType, optional): Default detail level. Defaults to None.
    """

    def __init__(
        self,
        timeout: int = 30,
        proxies: Optional[dict] = None,
        mode: ModeType = "question",
        detail_level: Optional[DetailLevelType] = None,
    ):
        """Initialize the IAsk API client.

        Args:
            timeout (int, optional): Request timeout in seconds. Defaults to 30.
            proxies (dict, optional): Proxy configuration for requests. Defaults to None.
            mode (ModeType, optional): Default search mode. Defaults to "question".
            detail_level (DetailLevelType, optional): Default detail level. Defaults to None.
        """
        self.timeout = timeout
        self.proxies = proxies or {}
        self.default_mode = mode
        self.default_detail_level = detail_level
        self.api_endpoint = "https://iask.ai"
        self.query_endpoint = "https://iask.ai/q"
        self.last_response = {}
        self.agent = LitAgent()

    def create_url(
        self,
        query: str,
        mode: ModeType = "question",
        detail_level: Optional[DetailLevelType] = None,
    ) -> str:
        """Create a properly formatted URL with mode and detail level parameters.

        Args:
            query (str): The search query.
            mode (ModeType, optional): Search mode. Defaults to "question".
            detail_level (DetailLevelType, optional): Detail level. Defaults to None.

        Returns:
            str: Formatted URL with query parameters.

        Example:
            >>> ai = IAsk()
            >>> url = ai.create_url("Climate change", mode="academic", detail_level="detailed")
            >>> print(url)
            https://iask.ai/q?mode=academic&q=Climate+change&options%5Bdetail_level%5D=detailed
        """
        # Create a dictionary of parameters with flattened structure
        params = {"mode": mode, "q": query}

        # Add detail_level if provided using the flattened format
        if detail_level:
            params["options[detail_level]"] = detail_level

        # Encode the parameters and build the URL
        query_string = urllib.parse.urlencode(params)
        url = f"{self.query_endpoint}?{query_string}"

        return url

    def format_html(self, html_content: str) -> str:
        """Format HTML content into a more readable text format.

        Args:
            html_content (str): The HTML content to format.

        Returns:
            str: Formatted text.
        """
        scout = Scout(html_content, features="html.parser")
        output_lines = []

        for child in scout.find_all(["h1", "h2", "h3", "p", "ol", "ul", "div"]):
            if child.name in ["h1", "h2", "h3"]:
                output_lines.append(f"\n**{child.get_text().strip()}**\n")
            elif child.name == "p":
                text = child.get_text().strip()
                text = re.sub(
                    r"^According to Ask AI & Question AI www\.iAsk\.ai:\s*", "", text
                ).strip()
                # Remove footnote markers
                text = re.sub(r"\[\d+\]\(#fn:\d+ \'see footnote\'\)", "", text)
                output_lines.append(text + "\n")
            elif child.name in ["ol", "ul"]:
                for li in child.find_all("li"):
                    output_lines.append("- " + li.get_text().strip() + "\n")
            elif child.name == "div" and "footnotes" in child.get("class", []):
                output_lines.append("\n**Authoritative Sources**\n")
                for li in child.find_all("li"):
                    link = li.find("a")
                    if link:
                        output_lines.append(f"- {link.get_text().strip()} ({link.get('href')})\n")

        return "".join(output_lines)

    def search(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        mode: Optional[ModeType] = None,
        detail_level: Optional[DetailLevelType] = None,
        **kwargs: Any,
    ) -> Union[SearchResponse, Generator[Union[Dict[str, str], SearchResponse], None, None]]:
        """Search using the IAsk API and get AI-generated responses.

        This method sends a search query to IAsk and returns the AI-generated response.
        It supports both streaming and non-streaming modes, as well as raw response format.

        Args:
            prompt (str): The search query or prompt to send to the API.
            stream (bool, optional): If True, yields response chunks as they arrive.
                                   If False, returns complete response. Defaults to False.
            raw (bool, optional): If True, returns raw response dictionaries with 'text' key.
                                If False, returns Response objects that convert to text automatically.
                                Defaults to False.
            mode (ModeType, optional): Search mode to use. Defaults to None (uses instance default).
            detail_level (DetailLevelType, optional): Detail level to use. Defaults to None (uses instance default).

        Returns:
            Union[Response, Generator[Union[Dict[str, str], Response], None, None]]:
                - If stream=False: Returns complete response as Response object
                - If stream=True: Yields response chunks as either Dict or Response objects

        Raises:
            APIConnectionError: If the API request fails

        Examples:
            Basic search:
            >>> ai = IAsk()
            >>> response = ai.search("What is Python?")
            >>> print(response)
            Python is a programming language...

            Streaming response:
            >>> for chunk in ai.search("Tell me about AI", stream=True):
            ...     print(chunk, end="")
            Artificial Intelligence...

            Raw response format:
            >>> for chunk in ai.search("Hello", stream=True, raw=True):
            ...     print(chunk)
            {'text': 'Hello'}
            {'text': ' there!'}

            With specific mode and detail level:
            >>> response = ai.search("Climate change", mode="academic", detail_level="detailed")
            >>> print(response)
            Climate change refers to...
        """
        search_mode = cast(ModeType, mode or self.default_mode)  # ty:ignore[redundant-cast]
        search_detail_level = cast(
            Optional[DetailLevelType], detail_level or self.default_detail_level
        )  # ty:ignore[redundant-cast]

        # For non-streaming, run the async search and return the complete response
        if not stream:
            # Create a new event loop for this request
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self._async_search(prompt, False, raw, search_mode, search_detail_level)
                )
                return cast(
                    Union[
                        SearchResponse, Generator[Union[Dict[str, str], SearchResponse], None, None]
                    ],
                    result,
                )
            finally:
                loop.close()
        buffer = ""

        def sync_generator():
            nonlocal buffer

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Get the async generator
                async_gen_coro = self._async_search(
                    prompt, True, raw, search_mode, search_detail_level
                )
                async_gen = loop.run_until_complete(async_gen_coro)

                # Process chunks one by one
                if hasattr(async_gen, "__anext__"):
                    async_iterator = cast(AsyncIterator, async_gen)
                    while True:
                        try:
                            # Get the next chunk
                            chunk_coro = async_iterator.__anext__()
                            chunk = loop.run_until_complete(chunk_coro)

                            # Update buffer and yield the chunk
                            if isinstance(chunk, dict) and "text" in chunk:
                                buffer += chunk["text"]
                            elif isinstance(chunk, SearchResponse):
                                buffer += chunk.text
                            else:
                                buffer += str(chunk)

                            yield chunk
                        except StopAsyncIteration:
                            break
                        except Exception as e:
                            print(f"Error in generator: {e}")
                            break
                elif isinstance(async_gen, SearchResponse):
                    yield async_gen
                else:
                    yield str(async_gen)
            finally:
                # Store the final response and close the loop
                self.last_response = {"text": buffer}
                loop.close()

        return cast(
            Union[SearchResponse, Generator[Union[Dict[str, str], SearchResponse], None, None]],
            sync_generator(),
        )

    def _extract_answer(self, html_content: str) -> str:
        """Extract and format the answer HTML from the results page."""
        etree = lxml.html.fromstring(html_content)
        text_nodes = etree.xpath('//*[@id="text"]')
        if not text_nodes:
            raise exceptions.APIConnectionError("No answer content found in iAsk response.")
        text_node = text_nodes[0]
        text_html = lxml.html.tostring(text_node, encoding="unicode", method="html")
        return self.format_html(text_html).strip()

    def _iter_chunks(self, text: str) -> Generator[str, None, None]:
        """Yield a response string in readable chunks for streaming."""
        for line in text.splitlines(keepends=True):
            if line.strip() == "":
                yield line
                continue
            for chunk in re.findall(r".{1,800}(?:\s+|$)", line):
                yield chunk

    async def _async_search(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        mode: ModeType = "question",
        detail_level: Optional[DetailLevelType] = None,
    ) -> Union[SearchResponse, str, AsyncIterator[Union[str, Dict[str, str], SearchResponse]]]:
        """Internal async implementation of the search method."""

        async def fetch_answer() -> str:
            timeout = self.timeout
            params = {"mode": mode, "q": prompt}
            if detail_level:
                params["options[detail_level]"] = detail_level

            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": self.agent.random(),
            }

            async with AsyncSession() as session:
                response = await session.get(
                    self.query_endpoint,
                    params=params,
                    headers=headers,
                    proxies=self.proxies or None,
                    timeout=timeout,
                )
            if response.status_code != 200:
                raise exceptions.APIConnectionError(
                    "Failed to generate response - "
                    f"({response.status_code}, {response.reason}) - {response.text}"
                )
            return self._extract_answer(response.text)

        # For non-streaming, collect all chunks and return a single response
        if not stream:
            buffer = await fetch_answer()
            self.last_response = SearchResponse(buffer)
            return buffer if raw else self.last_response  # ty:ignore[invalid-return-type]

        # For streaming, create an async generator that yields chunks
        async def process_stream():
            buffer = ""
            text = await fetch_answer()
            for chunk in self._iter_chunks(text):
                buffer += chunk
                if raw:
                    yield chunk
                else:
                    yield SearchResponse(chunk)
            self.last_response = SearchResponse(buffer)

        # Return the async generator
        return process_stream()


if __name__ == "__main__":
    ai = IAsk()
    response = ai.search("What is Python?", stream=True, raw=True)
    if hasattr(response, "__iter__") and not isinstance(response, (str, SearchResponse)):
        for chunk in response:
            print(chunk, end="", flush=True)
    else:
        print(response)
