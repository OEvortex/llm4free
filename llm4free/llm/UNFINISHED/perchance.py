"""
Perchance (text-generation.perchance.org) chat provider.

A TURNSTILE-solving TEXT chat provider ported from gpt4free (PR #3483). It
uses the async CDP client :class:`CDPSession` and a hybrid in-memory cache of
``userKey`` / ``cookies`` / ``headers`` to avoid re-launching the browser on
every request.

This module is the chat/text provider. It is distinct from
``llm4free/TTI/perchance.py`` which handles image generation.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

from curl_cffi.requests import Session

from llm4free.litagent import LitAgent as agent
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
from llm4free.requests.cdp import CDPSession

# Provider constants
URL = "https://perchance.org/ai-chat"
API_ENDPOINT = "https://text-generation.perchance.org/api/generate"
VERIFY_URL = "https://text-generation.perchance.org/embed?thread=0"
DEFAULT_MODEL = "perchance"
AVAILABLE_MODELS = ["perchance"]


def _solve_user_key() -> None:
    """Solve the Turnstile challenge and populate the class-level cache.

    Runs the async CDP solve to completion via :func:`asyncio.run`, which
    always spins up a fresh event loop and avoids reuse problems.

    Raises:
        RuntimeError: If the ``userKey`` cannot be retrieved within the
            polling window.
    """
    return asyncio.run(_solve_user_key_async())


async def _solve_user_key_async() -> None:
    """Async implementation of the Turnstile solve and credential harvest."""
    session = CDPSession(headless=False)
    try:
        await session.start()
        await session.navigate(VERIFY_URL)

        # Listen for stream/verified messages so the verify postMessage is
        # processed by the page's listeners.
        await session.evaluate_js(
            "window.addEventListener('message', e => { if(e.data && "
            "(e.data.type==='stream' || e.data.type==='verified')) "
            "console.log('PK:'+e.data.type); });"
        )

        # Trigger Cloudflare Turnstile verification.
        await session.evaluate_js("window.postMessage({type:'verifyUser'}, '*')")

        # Perform anti-detect mouse/scroll actions to solve the challenge.
        await session.bypass_turnstile()

        # Poll localStorage for the issued userKey (up to 30s).
        key: Optional[str] = None
        for _ in range(60):
            key = await session.evaluate_js("localStorage.getItem('userKey-0')")
            if key:
                break
            await asyncio.sleep(0.5)

        if not key:
            raise RuntimeError("auth_failed: could not retrieve userKey")

        cookies = await session.get_cookies()
        ua = await session.get_user_agent()

        Perchance._user_key = key
        Perchance._cookies = cookies
        Perchance._headers = {
            "user-agent": ua,
            "Origin": "https://text-generation.perchance.org",
            "Referer": VERIFY_URL,
        }
    finally:
        await session.close()


class Completions(BaseCompletions):
    """Chat completion implementation for the Perchance provider."""

    def __init__(self, client: "Perchance"):
        """Initialize with a reference to the owning :class:`Perchance` client."""
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Create a chat completion with the Perchance API.

        Mimics ``openai.chat.completions.create``. If the cached ``userKey`` is
        missing or rejected by the server, the Turnstile challenge is solved
        once and the request is retried.

        Args:
            model: Model name (only ``"perchance"`` is supported).
            messages: Conversation messages.
            max_tokens: Unused for this provider; accepted for compatibility.
            stream: Whether to stream the response.
            temperature: Unused; accepted for compatibility.
            top_p: Unused; accepted for compatibility.
            timeout: Request timeout in seconds.
            proxies: Optional proxy configuration dict.
            **kwargs: Additional provider-specific parameters.

        Returns:
            A :class:`ChatCompletion` or a generator of
            :class:`ChatCompletionChunk` when streaming.

        Raises:
            RuntimeError: If authentication cannot be re-established.
        """
        prompt = format_prompt(messages)
        created_time = int(time.time())
        request_id = f"chatcmpl-{uuid.uuid4().hex}"

        # Ensure we have a valid key; reset and retry once on auth failure.
        try:
            if Perchance._user_key is None:
                _solve_user_key()
            return self._generate(prompt, request_id, created_time, stream, timeout, proxies)
        except RuntimeError as exc:
            if "auth_failed" in str(exc):
                Perchance._user_key = None
                _solve_user_key()
                return self._generate(
                    prompt, request_id, created_time, stream, timeout, proxies
                )
            raise

    def _generate(
        self,
        prompt: str,
        request_id: str,
        created_time: int,
        stream: bool,
        timeout: Optional[int],
        proxies: Optional[dict],
    ) -> Any:
        """Build the request and dispatch to streaming/non-streaming paths."""
        payload = {
            "instruction": prompt,
            "startWith": "",
            "stopSequences": ["\n\n", "\nAnon:", "\nBot:"],
            "generatorName": "ai-chat",
            "startWithTokenCount": 0,
            "instructionTokenCount": len(prompt) // 4,
        }

        rand = uuid.uuid4().hex
        url = (
            f"{self._client.api_endpoint}?userKey={Perchance._user_key}"
            f"&thread=0&requestId=aiTextCompletion{rand}&__cacheBust={rand}"
        )

        session = Session(
            headers=Perchance._headers,
            cookies=Perchance._cookies,
            impersonate="chrome",
        )
        if proxies:
            session.proxies.update(proxies)  # ty:ignore[invalid-argument-type]

        response = session.post(url, json=payload, stream=True, timeout=timeout or 60)
        body = response.text

        if response.status_code in (401, 403) or any(
            marker in body
            for marker in ("invalid_key", "failed_verification")
        ):
            raise RuntimeError("auth_failed")

        if stream:
            return self._create_streaming(
                response, request_id, created_time, self._client.default_model
            )
        return self._create_non_streaming(
            response, request_id, created_time, self._client.default_model
        )

    def _create_streaming(
        self,
        response: Any,
        request_id: str,
        created_time: int,
        model: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Yield :class:`ChatCompletionChunk` objects from the SSE stream."""
        prompt_tokens = 0
        completion_tokens = 0
        full_content = ""

        try:
            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                line = line.strip()

                if line.startswith("t:"):
                    data = json.loads(line[2:])
                    content = data.get("text", "")
                    if not content:
                        continue

                    full_content += content
                    completion_tokens = count_tokens(full_content)
                    total_tokens = prompt_tokens + completion_tokens

                    delta = ChoiceDelta(content=content, role="assistant")
                    choice = Choice(index=0, delta=delta, finish_reason=None)
                    chunk = ChatCompletionChunk(
                        id=request_id,
                        choices=[choice],
                        created=created_time,
                        model=model,
                    )
                    chunk.usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    }
                    yield chunk

            if completion_tokens == 0:
                completion_tokens = count_tokens(full_content)
            total_tokens = prompt_tokens + completion_tokens

            final_delta = ChoiceDelta(content=None)
            final_choice = Choice(index=0, delta=final_delta, finish_reason="stop")
            final_chunk = ChatCompletionChunk(
                id=request_id,
                choices=[final_choice],
                created=created_time,
                model=model,
            )
            final_chunk.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
            yield final_chunk
        except Exception as exc:
            raise IOError(f"Perchance streaming request failed: {exc}") from exc

    def _create_non_streaming(
        self,
        response: Any,
        request_id: str,
        created_time: int,
        model: str,
    ) -> ChatCompletion:
        """Collect the full SSE stream into a single :class:`ChatCompletion`."""
        prompt_tokens = 0
        completion_tokens = 0
        full_content = ""

        try:
            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                line = line.strip()

                if line.startswith("t:"):
                    data = json.loads(line[2:])
                    content = data.get("text", "")
                    if content:
                        full_content += content

            if completion_tokens == 0:
                completion_tokens = count_tokens(full_content)
            total_tokens = prompt_tokens + completion_tokens

            message = ChatCompletionMessage(role="assistant", content=full_content)
            choice = Choice(index=0, message=message, finish_reason="stop")
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            completion = ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
            return completion
        except Exception as exc:
            raise IOError(f"Perchance request failed: {exc}") from exc


class Chat(BaseChat):
    """Chat interface exposing ``completions`` for the Perchance provider."""

    def __init__(self, client: "Perchance"):
        """Initialize the chat interface with the owning client."""
        self.completions = Completions(client)


class Perchance(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for the Perchance text-generation API.

    Usage:
        client = Perchance()
        response = client.chat.completions.create(
            model="perchance",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False

    # Class-level hybrid cache shared across all instances (text chat only).
    _user_key: Optional[str] = None
    _cookies: Optional[dict] = None
    _headers: Optional[dict] = None

    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        tools: Optional[List] = None,
        proxies: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the Perchance-compatible client.

        Args:
            tools: Optional list of tools to register with the provider.
            proxies: Optional proxy configuration dict.
        """
        super().__init__(api_key=None, tools=tools, proxies=proxies)

        self.url = URL
        self.api_endpoint = API_ENDPOINT
        self.verify_url = VERIFY_URL
        self.default_model = DEFAULT_MODEL
        self.user_agent = agent().random()

        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        """Return the list of available models."""
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print as rprint

    client = Perchance()
    rprint("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model="perchance",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
    )
    rprint(response)
    rprint("\nSTREAMING RESPONSE:")
    stream_response = client.chat.completions.create(
        model="perchance",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        stream=True,
    )
    for chunk in stream_response:
        rprint(chunk)
