"""
NoteGPT OpenAI-compatible provider.

Works anonymously (no login, no API key) by reaching the legacy ``ai-tab``
completions endpoint on notegpt.io:

    1. GET  /api/v1/ai-tab/get-prod-config
           -> server-issued config (``t``, ``nonce``, ``sign``,
              ``secret_key``, ``app_id``, ``uid``). No client-side signing
              is required for this anonymous flow.
    2. POST /api/v2/llm/completions?<urlencoded config>
           body = {"text", "end_flag", "streaming", "model"}
           -> SSE stream of ``data: {"message": <delta>, "conversation_id": ...}``
              terminated by ``data: [DONE]``.

The anonymous endpoint serves a subset of NoteGPT's non-premium models
(``gpt-4.1-mini``, ``gpt-4o-mini``, ``gemini-3.1-flash-lite``,
``deepseek-v4-flash``). A fresh ``get-prod-config`` token is single-use, so one
is fetched per request. Other non-premium models require a signed-in session
and are not reachable here.
"""

import json
import time
import urllib.parse
import uuid
from typing import Any, Dict, Generator, List, Optional

from llm4free.browser_requests._http.compat import Session

from llm4free.litagent import LitAgent
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    count_tokens,
    format_prompt,
)

GET_PROD_CONFIG_URL = "https://notegpt.io/api/v1/ai-tab/get-prod-config"
COMPLETIONS_URL = "https://notegpt.io/api/v2/llm/completions"


DEFAULT_MODEL = "gpt-4.1-mini"
AVAILABLE_MODELS = [
    "gpt-4.1-mini",
    "gpt-4o-mini",
    "gemini-3.1-flash-lite",
    "deepseek-v4-flash",
]


class Completions(BaseCompletions):
    """Chat completions interface for the NoteGPT provider."""

    def __init__(self, client: "NoteGPT"):
        """
        Initialize the completions handler.

        Args:
            client: The parent NoteGPT provider instance.
        """
        self._client = client

    def create(
        self,
        *,
        model: str = DEFAULT_MODEL,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Create a chat completion with the NoteGPT anonymous endpoint.

        Mimics ``openai.chat.completions.create``.

        Args:
            model: The NoteGPT model to use (only ``gpt-4.1-mini`` is served
                anonymously).
            messages: List of message dictionaries.
            stream: Whether to yield ``ChatCompletionChunk`` deltas (``True``)
                or return a single ``ChatCompletion`` (``False``).
            temperature: Sampling temperature (ignored by NoteGPT).
            top_p: Nucleus sampling parameter (ignored by NoteGPT).
            max_tokens: Maximum tokens to generate (ignored by NoteGPT).
            timeout: Optional request timeout in seconds.
            proxies: Optional proxy configuration dict.
            **kwargs: Extra arguments (ignored).

        Returns:
            A ``ChatCompletion`` or a generator of ``ChatCompletionChunk``.
        """
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id, created_time, model, messages, timeout, proxies
            )

        return self._create_non_stream(
            request_id, created_time, model, messages, timeout, proxies
        )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Stream the completion as OpenAI-style delta chunks."""
        try:
            conversation = format_prompt(messages, include_system=True)

            # A fresh config token is issued per request.
            config = self._client._get_prod_config(timeout=timeout, proxies=proxies)
            url = f"{COMPLETIONS_URL}?{urllib.parse.urlencode(config)}"

            payload = {
                "text": conversation,
                "end_flag": True,
                "streaming": True,
                "model": model,
            }

            response = self._client.session.post(
                url,
                headers=self._client.post_headers(),
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                impersonate="chrome",
                proxies=proxies or self._client.proxies,
            )

            if not response.ok:
                raise IOError(
                    f"NoteGPT request failed: {response.status_code} - {response.text}"
                )

            first = True
            done = False

            for raw in response.iter_content(chunk_size=None):
                if done:
                    break
                if not raw:
                    continue

                text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw

                for line in text.split("\n"):
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        break

                    try:
                        item = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(item, dict):
                        continue

                    delta_text = (
                        item.get("message")
                        or item.get("content")
                        or item.get("delta")
                        or ""
                    )
                    if not delta_text:
                        continue

                    delta = ChoiceDelta(
                        content=delta_text,
                        role="assistant" if first else None,
                    )
                    first = False

                    yield ChatCompletionChunk(
                        id=request_id,
                        choices=[Choice(index=0, delta=delta, finish_reason=None)],
                        created=created_time,
                        model=model,
                    )

            # Final stop chunk.
            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(index=0, delta=ChoiceDelta(content=None), finish_reason="stop")
                ],
                created=created_time,
                model=model,
            )

        except Exception as e:
            raise IOError(f"NoteGPT stream request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        """Accumulate streamed deltas into a single completion."""
        full_content = ""
        for chunk in self._create_stream(
            request_id, created_time, model, messages, timeout, proxies
        ):
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_content += delta.content

        conversation = format_prompt(messages, include_system=True)
        prompt_tokens = count_tokens(conversation)
        completion_tokens = count_tokens(full_content)

        message = ChatCompletionMessage(role="assistant", content=full_content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    """Chat interface for the NoteGPT provider."""

    def __init__(self, client: "NoteGPT"):
        """
        Initialize the chat handler.

        Args:
            client: The parent NoteGPT provider instance.
        """
        self.client = client
        self.completions = Completions(client)


class NoteGPT(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for NoteGPT's anonymous (no-login) chat endpoint.

    Usage:
        client = NoteGPT()
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = False

    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(self, timeout: int = 60, proxies: Optional[Dict[str, str]] = None):
        """
        Initialize the NoteGPT-compatible client.

        Args:
            timeout: Request timeout in seconds.
            proxies: Optional proxy configuration dict.
        """
        self.timeout = timeout
        self.proxies = proxies or {}

        self.session = Session()
        self.user_agent = LitAgent().random()

        self.base_headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://notegpt.io",
            "referer": "https://notegpt.io/ai-chat",
            "user-agent": self.user_agent,
        }

        try:
            self.session.headers.update(self.base_headers)
        except Exception:
            self.session.headers = dict(self.base_headers)
        if self.proxies:
            try:
                self.session.proxies = {**(self.session.proxies or {}), **self.proxies}
            except Exception:
                self.session.proxies = dict(self.proxies)

        self.chat = Chat(self)

    def post_headers(self) -> Dict[str, str]:
        """Return the base headers with a JSON content type for POSTs."""
        return {**self.base_headers, "content-type": "application/json"}

    def _get_prod_config(
        self,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch the server-issued anonymous request config.

        Returns:
            The ``data`` mapping containing ``t``, ``nonce``, ``sign``,
            ``secret_key``, ``app_id`` and ``uid``.

        Raises:
            IOError: If the config cannot be retrieved.
        """
        try:
            response = self.session.get(
                GET_PROD_CONFIG_URL,
                headers=self.base_headers,
                timeout=timeout or self.timeout,
                impersonate="chrome",
                proxies=proxies or self.proxies,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            raise IOError(f"NoteGPT failed to fetch prod config: {e}") from e

        config = payload.get("data")
        if not isinstance(config, dict) or not config:
            raise IOError(
                f"NoteGPT prod config missing or malformed: {payload!r}"
            )
        return config

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = NoteGPT()

    print("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
    )
    print(response)

    print("STREAMING RESPONSE:")
    stream = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "Count from 1 to 5."}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            print(delta.content, end="", flush=True)
    print()
