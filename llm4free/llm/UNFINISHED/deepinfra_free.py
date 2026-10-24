"""
DeepInfra (free, Turnstile-solving) chat provider.

A free, no-API-key chat provider ported from gpt4free (PR #3483). It solves the
Cloudflare Turnstile challenge in a real browser via the lightweight CDP client
:class:`SyncCDPSession` (backed by the ``agent-browser`` CLI) to obtain an
``X-DeepInfra-Turnstile`` token, then calls the OpenAI-compatible DeepInfra API.

NOTE: This is deliberately named ``DeepInfraFree`` to avoid colliding with the
existing API-key based ``DeepInfra`` provider in ``llm4free/llm/Auth``.
"""

import json
import socket
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
)
from llm4free.requests.cdp import SyncCDPSession

# Provider constants
URL = "https://deepinfra.com"
LOGIN_URL = "https://deepinfra.com/dash/api_keys"
BASE_URL = "https://api.deepinfra.com/v1/openai"
DEFAULT_MODEL = "zai-org/GLM-5.2"
AVAILABLE_MODELS = [
    "zai-org/GLM-5.2",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "deepseek-ai/DeepSeek-V3",
    "Qwen/Qwen2.5-72B-Instruct",
    "Google/gemma-2-27b-it",
]


def _find_free_port() -> int:
    """Return an ephemeral TCP port that is free on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _get_turnstile_token_sync(model: str) -> str:
    """Solve the Cloudflare Turnstile challenge and return its token.

    Launches a headful browser via :class:`SyncCDPSession`, navigates to the
    model page, clicks to give the window focus, and polls the
    ``cf-turnstile-response`` input for the issued token.

    Args:
        model: The DeepInfra model slug used in the page URL.

    Returns:
        The Turnstile token string.

    Raises:
        RuntimeError: If the token cannot be obtained within the window, or if
            Chrome / ``agent-browser`` is unavailable.
    """
    port = _find_free_port()
    session = SyncCDPSession(port=port, headless=False)
    try:
        session.start_chrome()
        session.navigate(f"{URL}/{model}")

        # Accept the cookie consent banner if present (best effort).
        try:
            session.evaluate_js(
                "document.querySelectorAll(\"[id*='accept'], button\").forEach(b => {"
                "  if (/accept/i.test(b.textContent || '')) b.click();"
                "});"
            )
        except RuntimeError:
            pass

        # Click to give the window focus; this speeds up token generation.
        # Prefer the actual Turnstile checkbox iframe if present, otherwise
        # fall back to a focus click on the body.
        try:
            session.click_selector("#cf-turnstile iframe, #cf-turnstile, body")
        except (RuntimeError, AttributeError):
            session.click(200, 400)

        # Poll for the turnstile token (up to 120s).
        token: Optional[str] = None
        for _ in range(240):
            token = session.evaluate_js(
                "document.querySelector(\"[name=cf-turnstile-response]\") "
                "? document.querySelector(\"[name=cf-turnstile-response]\").value : ''"
            )
            if token:
                break
            time.sleep(0.5)

        if not token:
            raise RuntimeError(
                "Failed to solve Cloudflare Turnstile for DeepInfra. "
                "Ensure Chrome is installed and reachable via agent-browser."
            )
        return token
    finally:
        session.close()


class Completions(BaseCompletions):
    """Chat completion implementation for the free DeepInfra provider."""

    def __init__(self, client: "DeepInfraFree"):
        """Initialize with a reference to the owning :class:`DeepInfraFree` client."""
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
        """Create a chat completion with the free DeepInfra API.

        Solves the Turnstile challenge (when needed) to obtain an
        ``X-DeepInfra-Turnstile`` header, then proxies the request to the
        OpenAI-compatible DeepInfra endpoint.

        Args:
            model: DeepInfra model slug (e.g. ``"zai-org/GLM-5.2"``).
            messages: Conversation messages.
            max_tokens: Maximum tokens to generate.
            stream: Whether to stream the response.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.
            timeout: Request timeout in seconds.
            proxies: Optional proxy configuration dict.
            **kwargs: Additional provider-specific parameters.

        Returns:
            A :class:`ChatCompletion` or a generator of
            :class:`ChatCompletionChunk` when streaming.
        """
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        # Solve the Turnstile challenge to get the anti-bot header.
        token = _get_turnstile_token_sync(model)

        headers = dict(self._client.headers)
        headers["X-DeepInfra-Turnstile"] = token

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        payload.update(kwargs)

        session = Session(impersonate="chrome")
        if proxies:
            session.proxies.update(proxies)  # ty:ignore[invalid-argument-type]

        response = session.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=timeout or 60,
        )
        if not response.ok:
            raise RuntimeError(
                f"DeepInfra request failed ({response.status_code}): {response.text}"
            )

        if stream:
            return self._create_streaming(response, request_id, created_time, model)
        return self._create_non_streaming(response, request_id, created_time, model)

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
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if data.get("choices"):
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        full_content += content
                        completion_tokens = count_tokens(full_content)
                        total_tokens = prompt_tokens + completion_tokens
                        chunk_delta = ChoiceDelta(content=content, role="assistant")
                        choice = Choice(
                            index=0, delta=chunk_delta, finish_reason=None
                        )
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
            raise IOError(f"DeepInfra streaming request failed: {exc}") from exc

    def _create_non_streaming(
        self,
        response: Any,
        request_id: str,
        created_time: int,
        model: str,
    ) -> ChatCompletion:
        """Collect the SSE stream into a single :class:`ChatCompletion`."""
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
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if data.get("choices"):
                    content = data["choices"][0].get("message", {}).get("content")
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
            return ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
        except Exception as exc:
            raise IOError(f"DeepInfra request failed: {exc}") from exc


class Chat(BaseChat):
    """Chat interface exposing ``completions`` for the free DeepInfra provider."""

    def __init__(self, client: "DeepInfraFree"):
        """Initialize the chat interface with the owning client."""
        self.completions = Completions(client)


class DeepInfraFree(OpenAICompatibleProvider):
    """OpenAI-compatible client for the free (Turnstile-based) DeepInfra API.

    Usage:
        client = DeepInfraFree()
        response = client.chat.completions.create(
            model="zai-org/GLM-5.2",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False

    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        tools: Optional[List] = None,
        proxies: Optional[Dict[str, str]] = None,
    ):
        """Initialize the free DeepInfra-compatible client.

        Args:
            tools: Optional list of tools to register with the provider.
            proxies: Optional proxy configuration dict.
        """
        super().__init__(api_key=None, tools=tools, proxies=proxies)

        self.url = URL
        self.login_url = LOGIN_URL
        self.base_url = BASE_URL
        self.default_model = DEFAULT_MODEL
        self.user_agent = agent().random()
        self.headers = {
            "X-Deepinfra-Source": "web-page",
            "Origin": URL,
            "Referer": f"{URL}/",
            "Content-Type": "application/json",
            "user-agent": self.user_agent,
        }

        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        """Return the list of available models."""
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print as rprint

    client = DeepInfraFree()
    rprint("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "Hello, how are you?"}],
    )
    rprint(response)
