import base64
import json
import os
import time
from typing import Any, Dict, Generator, List, Optional, Union
from urllib.parse import quote, urlencode

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from llm4free import exceptions
from llm4free.AIbase import AISearch, SearchResponse
from llm4free.litagent import LitAgent

BRAVE_URL = "https://search.brave.com"
BRAVE_ASK_URL = f"{BRAVE_URL}/ask"
DATA_ENDPOINT = f"{BRAVE_ASK_URL}/__data.json"
API_BASE = f"{BRAVE_URL}/api/tap/v1"
NEW_ENDPOINT = f"{API_BASE}/new"
STREAM_ENDPOINT = f"{API_BASE}/stream"

DEEP_RESEARCH_TIMEOUT = 600


class BraveSearch(AISearch):
    """A class to interact with the Brave Search Ask AI API.

    Supports both regular and Deep Research modes:
    - brave: Standard Ask Brave (fast, single-pass answer)
    - brave-deep-research: Deep Research mode (multi-iteration web crawling,
      generates comprehensive research reports, takes 1-5 minutes)

    Basic Usage:
        >>> from llm4free import BraveSearch
        >>> ai = BraveSearch()
        >>> response = ai.search("What is Python?")
        >>> print(response)
        Python is a high-level programming language...

        >>> for chunk in ai.search("Tell me about AI", stream=True):
        ...     print(chunk, end="", flush=True)
    """

    def __init__(
        self,
        cookies: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        proxies: Optional[Dict[str, str]] = None,
    ):
        self.timeout = timeout
        self.proxies = proxies or {}
        self.last_response = {}
        self.agent = LitAgent()
        self.headers = {
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "user-agent": self.agent.random(),
        }
        self.session = requests.Session(
            headers=self.headers, cookies=cookies or {}, impersonate="chrome"
        )
        if proxies:
            from typing import cast

            self.session.proxies.update(cast(Any, proxies))
        self._conversation_id: Optional[str] = None
        self._symmetric_key = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")

    def _parse_sveltekit_tap_data(self, raw_json: dict) -> Dict[str, str]:
        """Parse SvelteKit __data.json format to extract nonce and sig."""
        result: Dict[str, str] = {}

        if raw_json.get("type") != "data" or "nodes" not in raw_json:
            return result

        for node in raw_json["nodes"]:
            if node.get("type") != "data" or "data" not in node:
                continue

            node_data = node["data"]
            if not isinstance(node_data, list) or len(node_data) < 2:
                continue

            schema = node_data[0]
            if not isinstance(schema, dict):
                continue

            page_idx = schema.get("page")
            if not (isinstance(page_idx, int) and 0 < page_idx < len(node_data)):
                continue
            if node_data[page_idx] != "tap":
                continue

            token_idx = schema.get("token")
            if isinstance(token_idx, int) and 0 < token_idx < len(node_data):
                token = node_data[token_idx]
                if isinstance(token, dict):
                    for key, val_idx in token.items():
                        if isinstance(val_idx, int) and 0 < val_idx < len(node_data):
                            result[key] = node_data[val_idx]
            break

        return result

    def _process_research_event(self, event: dict) -> Optional[str]:
        """Process a Deep Research event and return status message."""
        inner = event.get("event", {})
        if not isinstance(inner, dict):
            return None

        research_event = inner.get("event", "")

        if research_event == "queries":
            queries = inner.get("queries", [])
            if queries:
                return f"[Brave Deep Research] Researching: {', '.join(queries[:3])}"
        elif research_event == "analyzing":
            query = inner.get("query", "")
            urls = inner.get("urls", 0)
            return f"[Brave Deep Research] Analyzing {urls} sources for: {query}"
        elif research_event == "thinking":
            query = inner.get("query", "")
            chunks = inner.get("chunks_analyzed", 0)
            urls = inner.get("urls_analyzed", 0)
            return f"[Brave Deep Research] Processing {chunks} chunks from {urls} sources: {query}"
        elif research_event == "progress":
            iterations = inner.get("number_of_iterations", 0)
            queries = inner.get("number_of_queries", 0)
            urls = inner.get("number_of_urls_analyzed", 0)
            elapsed = inner.get("elasped_seconds", 0)
            return f"[Brave Deep Research] Iteration {iterations}: {queries} queries, {urls} URLs analyzed ({elapsed:.0f}s)"
        elif research_event == "blindspots":
            spots = inner.get("blindspots", [])
            if spots:
                return f"[Brave Deep Research] Identified gaps: {', '.join(spots[:3])}"
        elif research_event == "answer" and inner.get("final"):
            return "[Brave Deep Research] Research complete, generating final answer"

        return None

    def _drain_readable_chunks(self, text: str, final: bool = False) -> tuple[List[str], str]:
        """Split buffered text into readable chunks, retaining a partial word."""
        if not text:
            return [], ""

        chunks: List[str] = []
        while len(text) >= 800:
            split_at = text.rfind(" ", 1, 800)
            if split_at <= 0:
                split_at = 800
            else:
                split_at += 1
            chunks.append(text[:split_at])
            text = text[split_at:]

        if final and text:
            chunks.append(text)
            text = ""
        return chunks, text

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
        """Search using the Brave Search Ask API.

        Args:
            prompt: The search query or prompt to send to the API.
            stream: Whether to stream the response.
            raw: If True, returns unprocessed response chunks without any
                processing. Useful for debugging or custom processing pipelines.
            **kwargs: Additional arguments:
                - model: Model to use ('brave' or 'brave-deep-research').
                - max_retries: Maximum number of retry attempts (default 3).
        """
        model = kwargs.get("model", "brave")
        is_deep = model == "brave-deep-research"
        max_retries = kwargs.get("max_retries", 3)
        effective_timeout = DEEP_RESEARCH_TIMEOUT if is_deep else self.timeout

        def for_stream():
            full_text = ""
            buffer = ""
            try:
                for raw_line in self._iter_stream(prompt, is_deep, max_retries, effective_timeout):
                    if raw:
                        yield raw_line
                        continue

                    try:
                        event = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    if event_type == "text_delta":
                        delta = event.get("delta", "")
                        if isinstance(delta, str) and delta:
                            full_text += delta
                            buffer += delta
                            chunks, buffer = self._drain_readable_chunks(buffer)
                            for chunk in chunks:
                                yield SearchResponse(chunk)
                    elif event_type == "research":
                        status = self._process_research_event(event)
                        if status:
                            chunks, buffer = self._drain_readable_chunks(buffer, final=True)
                            for chunk in chunks:
                                yield SearchResponse(chunk)
                            status_chunk = f"\n{status}\n"
                            full_text += status_chunk
                            yield SearchResponse(status_chunk)

                chunks, _ = self._drain_readable_chunks(buffer, final=True)
                for chunk in chunks:
                    yield SearchResponse(chunk)
            finally:
                if not raw:
                    self.last_response = SearchResponse(full_text)

        def for_non_stream():
            try:
                full_text = self._fetch_response(prompt, is_deep, max_retries, effective_timeout)
                if raw:
                    return full_text
                self.last_response = SearchResponse(full_text)
                return self.last_response
            except requests.RequestsError as e:
                raise exceptions.APIConnectionError(f"Request failed: {e}")

        return for_stream() if stream else for_non_stream()

    def _setup_conversation(self, prompt: str, is_deep: bool, timeout: int) -> str:
        """Get nonce/sig and create conversation. Returns conversation ID."""
        data_params: Dict[str, str] = {
            "q": prompt,
            "x-sveltekit-invalidated": "11",
        }
        if is_deep:
            data_params["enable_research"] = "true"

        referer = f"{BRAVE_ASK_URL}?q=&source=llmSuggest"
        if self._conversation_id:
            referer = (
                f"{BRAVE_ASK_URL}?q={quote(prompt)}&source=llmSuggest"
                f"&conversation={self._conversation_id}"
            )

        response = self.session.get(
            DATA_ENDPOINT,
            params=data_params,
            headers={"referer": referer},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise exceptions.APIConnectionError(
                f"Failed to get data.json: {response.status_code} - {response.text}"
            )
        tap_data = self._parse_sveltekit_tap_data(response.json())
        nonce = tap_data.get("nonce")
        sig = tap_data.get("sig")
        if not nonce or not sig:
            raise RuntimeError(f"Failed to extract nonce/sig from __data.json. Got: {tap_data}")

        new_params = {
            "language": "en",
            "country": "us",
            "ui_lang": "en-us",
            "safesearch": "moderate",
            "force_safesearch": "0",
            "units_of_measurement": "metric",
            "use_location": "1",
            "geoloc": "50.457x30.532",
            "premium_cookie_name": "__Secure-sku#brave-search-premium",
            "symmetric_key": self._symmetric_key,
            "source": "newThread" if is_deep else "llmSuggest",
            "enable_research": "true" if is_deep else "false",
            "q": prompt,
            "nonce": nonce,
            "sig": sig,
        }

        response = self.session.get(
            NEW_ENDPOINT,
            params=new_params,
            headers={"referer": f"{BRAVE_ASK_URL}?q={quote(prompt)}&source=newThread"},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise exceptions.APIConnectionError(
                f"Failed to create conversation: {response.status_code} - {response.text}"
            )
        new_data = response.json()
        conv_id = new_data.get("id")
        if not conv_id:
            raise RuntimeError(f"Failed to get conversation ID from /new: {new_data}")
        self._conversation_id = conv_id
        return conv_id

    def _build_stream_url(self, prompt: str, conv_id: str) -> str:
        """Build the stream endpoint URL."""
        stream_params = {
            "language": "en",
            "country": "us",
            "ui_lang": "en-us",
            "safesearch": "moderate",
            "force_safesearch": "0",
            "units_of_measurement": "metric",
            "use_location": "1",
            "geoloc": "50.457x30.532",
            "premium_cookie_name": "__Secure-sku#brave-search-premium",
            "id": conv_id,
            "query": prompt,
            "symmetric_key": self._symmetric_key,
            "enable_inline_entities": "true",
        }
        return f"{STREAM_ENDPOINT}?{urlencode(stream_params)}"

    def _iter_stream(
        self,
        prompt: str,
        is_deep: bool = False,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> Generator[str, None, None]:
        """Yield raw SSE lines from the Brave stream endpoint."""
        for attempt in range(max_retries):
            try:
                conv_id = self._setup_conversation(prompt, is_deep, timeout)
                stream_url = self._build_stream_url(prompt, conv_id)

                response = self.session.get(
                    stream_url,
                    headers={
                        "accept": "text/event-stream",
                        "origin": "https://search.brave.com",
                        "referer": (
                            f"{BRAVE_ASK_URL}?q={quote(prompt)}&source=newThread"
                            f"&conversation={conv_id}"
                        ),
                    },
                    stream=True,
                    timeout=timeout,
                )
                if response.status_code != 200:
                    raise exceptions.APIConnectionError(
                        f"Failed to stream response: {response.status_code} - {response.text}"
                    )

                buffer = b""
                for chunk in response.iter_content(chunk_size=None):
                    if not chunk:
                        continue
                    buffer += chunk

                    while b"\n" in buffer:
                        line_bytes, buffer = buffer.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if line:
                            yield line

                if buffer:
                    line = buffer.decode("utf-8", errors="replace").strip()
                    if line:
                        yield line

                return

            except (requests.RequestsError, Exception) as e:
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                if isinstance(e, exceptions.APIConnectionError):
                    raise
                raise exceptions.FailedToGenerateResponseError(f"Error: {str(e)}")

        raise exceptions.FailedToGenerateResponseError(
            "Failed to get response after multiple attempts"
        )

    def _fetch_response(
        self,
        prompt: str,
        is_deep: bool = False,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> str:
        """Fetch the complete response text (non-streaming)."""
        full_text = ""
        for raw_line in self._iter_stream(prompt, is_deep, max_retries, timeout):
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type", "")
            if event_type == "text_delta":
                delta = event.get("delta", "")
                if delta:
                    full_text += delta
            elif event_type == "research":
                status = self._process_research_event(event)
                if status:
                    full_text += f"\n{status}\n"
        return full_text


if __name__ == "__main__":
    ai = BraveSearch()
    response = ai.search("What is Python?", stream=True, raw=True)
    if hasattr(response, "__iter__") and not isinstance(response, (str, SearchResponse)):
        for chunk in response:
            print(chunk, end="", flush=True)
    else:
        print(response)
