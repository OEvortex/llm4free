"""OpenAI-compatible provider for the Qwen web API (``chat.qwen.ai``).

Reverse-engineered from ``https://chat.qwen.ai/`` (frontend 0.3.22). The
service exposes two API versions; ``v1`` still works and returns clean JSON
errors while ``v2`` paths are wrapped in extra browser-side anti-bot
(Alibaba BAXIA ``bx-ua``) headers, so the provider talks to ``v1``.

Flow (all HTTP, mirroring :mod:`llm4free.llm.gemini`, no browser required):

1. ``GET /`` so Aliyun WAF issues its ``acw_tc`` clearance cookie
   (a bare POST without the warm-up hits a JS challenge page).
   ``GET https://chat.qwen.ai/`` also seeds ``cna``; keep both.
2. ``POST /api/v1/chats/new`` to open a conversation and obtain a chat id:
   ``{"chatId": "", "models": ["qwen3.7-plus"], "project_id": "",
    "timestamp": <ms>, "chat_type": "t2t", "chat_mode": "guest"}``.
3. ``POST /api/v1/chat/completions?chatId=<id>`` with
   ``{"stream": true, "incremental_output": true, "chatId": <id>,
     "model": <model>, "messages": [...], "timestamp": <ms>,
     "chat_type": "t2t"}`` and consume the ``data:`` SSE stream.

Auth: guest chatting is server-side blocked (``401 Unauthorized`` for
``chat_mode: guest``), so a logged-in bearer token is REQUIRED. Copy the
``token`` cookie from a signed-in browser session::

    curl "https://chat.qwen.ai/api/v1/chat/completions?chatId=<chatid>" \\
      -X POST \\
      -H "Authorization: Bearer <your-token>" \\
      -H "Content-Type: application/json" \\
      -H "Referer: https://chat.qwen.ai/" \\
      -H "source: web" \\
      -H "Version: 0.3.22" \\
      -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36
          (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36" \\
      -d '{"stream":true,"incremental_output":true,"chatId":"<chatid>",
           "model":"qwen3.7-plus",
           "messages":[{"role":"user","content":"Hello!"}],
           "timestamp":1792823927724,"chat_type":"t2t"}'
    # Response: SSE lines "data: {...choices[0].message(delta).content...}"
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi import requests

from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
    Tool,
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

BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"

QWEN_BASE_URL = "https://chat.qwen.ai"
QWEN_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 180

# Model presets served by /api/v2/models/ at the time of reverse engineering.
# The list is refreshed in the background through get_models().
QWEN_AVAILABLE_MODELS = [
    "qwen3.7-plus",
    "qwen3.8-max",
    "qwen3.8-omni-flash",
]

# Model aliases accepted for convenience, resolved to the API model ids.
MODEL_ALIASES = {
    "auto": "qwen3.7-plus",
    "default": "qwen3.7-plus",
    "qwen-plus": "qwen3.7-plus",
    "qwen-max": "qwen3.8-max",
    "qwen-omni": "qwen3.8-omni-flash",
    "qwen-omni-flash": "qwen3.8-omni-flash",
}


def _resolve_model(name: str) -> str:
    """Map an alias/simplistic model name to the exact Qwen API id."""
    resolved = MODEL_ALIASES.get(name.lower(), name)
    if resolved not in QWEN_AVAILABLE_MODELS:
        raise ValueError(
            f"Unknown Qwen model: {name!r}. "
            f"Available models: {', '.join(QWEN_AVAILABLE_MODELS)}"
        )
    return resolved


def _convert_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalize OpenAI-style messages to role/content pairs for Qwen."""
    parts: List[Dict[str, str]] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            # Vision-style message arrays: keep only plain text segments.
            content = " ".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        if not content:
            continue
        parts.append({"role": role, "content": content})
    return parts


class QwenReversed:
    """Lightweight facade over the reverse-engineered Qwen web API.

    Args:
        token: Bearer token from a signed-in ``chat.qwen.ai`` session (the
            value of the browser's ``token`` cookie or the ``Authorization``
            header used by the web client).
        model: Model name from :attr:`AVAILABLE_MODELS`.
        timeout: Maximum seconds to wait for a complete answer.
        proxies: Optional curl_cffi proxies mapping.
    """

    AVAILABLE_MODELS = list(QWEN_AVAILABLE_MODELS)

    def __init__(
        self,
        token: str,
        model: str = "qwen3.7-plus",
        timeout: int = DEFAULT_TIMEOUT,
        proxies: Optional[dict] = None,
    ) -> None:
        if not token:
            raise ValueError(
                "A chat.qwen.ai bearer token is required. "
                "Sign in at https://chat.qwen.ai/ and copy the 'token' cookie."
            )
        try:
            self.model = _resolve_model(model)
        except ValueError:
            print(
                f"{BOLD}Warning: Model '{model}' not found, "
                f"using default 'qwen3.7-plus'{RESET}"
            )
            self.model = "qwen3.7-plus"
        self.token = token
        self.timeout = timeout
        self.timestamp = int(time.time() * 1000)
        self.session = requests.Session(impersonate="chrome136")
        self.session.timeout = timeout
        if proxies:
            self.session.proxies.update(cast(Any, proxies))

    def initialize(self) -> None:
        """Warm up the session so Aliyun WAF issues clearance cookies."""
        self.session.get(
            QWEN_BASE_URL + "/",
            headers={"User-Agent": QWEN_USER_AGENT},
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "User-Agent": QWEN_USER_AGENT,
            "Referer": QWEN_BASE_URL + "/",
            "Content-Type": "application/json",
            "source": "web",
            "Version": "0.3.22",
            "x-request-id": str(uuid.uuid4()),
            "Authorization": f"Bearer {self.token}",
        }

    def new_chat(self, model: Optional[str] = None) -> str:
        """Open a conversation via ``/api/v1/chats/new`` and return its id."""
        timestamp = int(time.time() * 1000)
        self.timestamp = timestamp
        payload = {
            "chatId": "",
            "models": [model or self.model],
            "project_id": "",
            "timestamp": timestamp,
            "chat_type": "t2t",
            "chat_mode": "guest",
        }
        response = self.session.post(
            QWEN_BASE_URL + "/api/v1/chats/new",
            json=payload,
            headers=self._headers(),
        )
        return self._extract_chat_id(response)

    def _extract_chat_id(self, response: requests.Response) -> str:
        """Pull the conversation id out of a chats/new response."""
        try:
            data = response.json()
        except json.JSONDecodeError as exc:  # WAF challenge or proxy error
            raise IOError(
                f"Qwen chats/new returned a non-JSON response "
                f"(HTTP {response.status_code}, likely WAF); "
                f"retry with a warm-up GET to {QWEN_BASE_URL}/"
            ) from exc
        error = data.get("error") or ""
        if error:
            raise IOError(f"Qwen chats/new failed: {error}")
        details = data.get("data")
        if not isinstance(details, dict) or not details.get("id"):
            raise IOError(f"Qwen chats/new returned no chat id: {str(data)[:300]}")
        return str(details["id"])

    def _post_completions(
        self,
        chat_id: str,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> requests.Response:
        """Send the streaming chat-completions request."""
        payload = {
            "stream": True,
            "incremental_output": True,
            "chatId": chat_id,
            "model": model,
            "messages": messages,
            "timestamp": int(time.time() * 1000),
            "chat_type": "t2t",
        }
        response = self.session.post(
            QWEN_BASE_URL + f"/api/v1/chat/completions?chatId={chat_id}",
            json=payload,
            headers=self._headers(),
            stream=True,
        )
        if response.status_code != 200:
            body = response.text or ""
            snippet = body[:300]
            if "_____tmd_____/punish" in snippet:
                raise IOError(
                    "Qwen WAF punished the request; re-run a warm-up GET to "
                    f"{QWEN_BASE_URL}/ or use a slower request rate"
                )
            if response.status_code in (401, 403):
                raise IOError(f"Qwen rejected the token (HTTP {response.status_code}): {snippet}")
            raise IOError(f"Qwen request failed (HTTP {response.status_code}): {snippet}")
        return response

    def complete(self, message: Union[str, List[Dict[str, Any]]], model: Optional[str] = None) -> str:
        """Return a complete answer for a single message or message list."""
        selected_model = _resolve_model(model or self.model)
        if isinstance(message, str):
            messages = [{"role": "user", "content": message}]
        else:
            messages = list(message)
        chat_id = self.new_chat(selected_model)
        response = self._post_completions(chat_id, messages, selected_model)
        return "".join(_iter_stream_deltas(response))


def _iter_stream_deltas(response: requests.Response) -> Generator[str, None, None]:
    """Yield assistant text deltas from a Qwen SSE ``data:`` stream.

    Qwen events carry the payload under ``choices[0].message`` with
    ``incremental_output: true``; the parser stays compatible with both
    ``message`` and ``delta`` key layouts. Thinking models may include
    ``reasoning_content`` which is ignored.
    """
    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="ignore")
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        raw = line[len("data:") :].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        choices = event.get("choices") or []
        if not choices:
            continue
        choice = choices[0] or {}
        piece = choice.get("delta") or choice.get("message") or choice
        content = piece.get("content")
        if not content:
            continue
        yield str(content)


class Completions(BaseCompletions):
    def __init__(self, client: "Qwen") -> None:
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """Create a chat completion using the Qwen web API.

        Args:
            model: Model name or alias; resolved to the exact API id.
            messages: OpenAI-style conversation messages.
            max_tokens: Ignored by the web endpoint.
            stream: Return a chunk generator when ``True``.
            temperature: Ignored by the web endpoint.
            top_p: Ignored by the web endpoint.
            tools: Ignored here; enabled through the base provider's XML loop.
            tool_choice: Ignored by the web endpoint.
            timeout: Maximum seconds to wait for the answer.
            proxies: Optional curl_cffi proxies mapping.
            **kwargs: Extra parameters accepted for interface compatibility.

        Returns:
            A :class:`ChatCompletion` or a generator of
            :class:`ChatCompletionChunk` objects.
        """
        del max_tokens, temperature, top_p, tools, tool_choice, kwargs  # noqa: W0613
        try:
            resolved = _resolve_model(model)
        except ValueError:
            print(
                f"{BOLD}Warning: Model '{model}' not found, "
                f"using default 'qwen3.7-plus'{RESET}"
            )
            resolved = "qwen3.7-plus"
        qwen_messages = _convert_messages(messages)
        if not qwen_messages:
            raise ValueError("Qwen requires at least one non-empty message")
        del timeout, proxies  # the warm session already carries these

        chat_id = self._client.new_chat(resolved)
        response = self._client._post_completions(chat_id, qwen_messages, resolved)

        if stream:
            return self._create_streaming(response, resolved, model, chat_id)
        return self._create_non_streaming(response, resolved, model, chat_id, messages)

    def _create_streaming(
        self,
        response: requests.Response,
        resolved_model: str,
        requested_model: str,
        chat_id: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Yield OpenAI-compatible chunks from a Qwen SSE stream."""
        request_id = f"chatcmpl-{chat_id}"
        created_time = int(time.time())
        for delta_text in _iter_stream_deltas(response):
            if not delta_text:
                continue
            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=delta_text, role="assistant"),
                        finish_reason=None,
                    )
                ],
                created=created_time,
                model=requested_model,
            )
        yield ChatCompletionChunk(
            id=request_id,
            choices=[
                Choice(index=0, delta=ChoiceDelta(content=None), finish_reason="stop")
            ],
            created=created_time,
            model=requested_model,
        )

    def _create_non_streaming(
        self,
        response: requests.Response,
        resolved_model: str,
        requested_model: str,
        chat_id: str,
        messages: List[Dict[str, Any]],
    ) -> ChatCompletion:
        """Collect the Qwen SSE stream into a single completion object."""
        content = "".join(_iter_stream_deltas(response))
        if not content:
            raise IOError("Qwen returned no parseable response")
        prompt_text = format_prompt(messages)
        prompt_tokens = count_tokens(prompt_text)
        completion_tokens = count_tokens(content)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        message = ChatCompletionMessage(role="assistant", content=content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        return ChatCompletion(
            id=f"chatcmpl-{chat_id}",
            choices=[choice],
            created=int(time.time()),
            model=requested_model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "Qwen") -> None:
        self.completions = Completions(client)


class Qwen(OpenAICompatibleProvider):
    """OpenAI-compatible client for chat.qwen.ai.

    Usage:
        # Sign in at https://chat.qwen.ai/, copy the 'token' cookie value.
        token = "eyJhbGciOi...your.bearer.token"

        client = Qwen(api_key=token)
        response = client.chat.completions.create(
            model="qwen3.7-plus",
            messages=[{"role": "user", "content": "Hello!"}],
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
    """

    required_auth = True
    default_model = "qwen3.7-plus"
    AVAILABLE_MODELS = list(QWEN_AVAILABLE_MODELS)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Fetch the live model list from the public ``/api/v2/models/``."""
        try:
            session = requests.Session(impersonate="chrome136")
            session.timeout = 30
            # Warm-up GET clears the Aliyun WAF challenge cookie.
            session.get(QWEN_BASE_URL + "/", headers={"User-Agent": QWEN_USER_AGENT})
            response = session.get(
                QWEN_BASE_URL + "/api/v2/models/",
                headers={"User-Agent": QWEN_USER_AGENT, "Referer": QWEN_BASE_URL + "/"},
            )
            if response.status_code != 200:
                raise Exception(f"Failed to fetch models: HTTP {response.status_code}")
            data = response.json()
            entries = data["data"]["data"]
            models = [entry["id"] for entry in entries if entry.get("id")]
            if models:
                return models
            raise Exception("Invalid response format from API")
        except Exception as e:
            print(f"{BOLD}Warning: Failed to refresh Qwen models: {e}{RESET}")
            return list(QWEN_AVAILABLE_MODELS)

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Qwen client.

        Args:
            api_key: Required bearer token from a signed-in chat.qwen.ai
                session (the browser's ``token`` cookie value).
            timeout: Maximum seconds to wait for a complete answer.
            proxies: Optional curl_cffi proxies mapping.
            **kwargs: Accepted for interface compatibility.
        """
        if not api_key:
            raise ValueError(
                "API key (bearer token) is required for Qwen. Signed in at "
                "https://chat.qwen.ai/ and copy the 'token' cookie value."
            )
        super().__init__(api_key=api_key, proxies=proxies)
        self.timeout = timeout
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))
        self._reversed = QwenReversed(
            token=api_key,
            model=self.default_model,
            timeout=timeout,
            proxies=self.proxies,
        )
        # Mirror the live model list into a session cache without blocking.
        self._start_background_model_fetch(api_key=api_key)
        self.chat = Chat(self)

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None) -> None:
        """Refresh the static model list from the live endpoint."""
        del api_key
        try:
            cls.AVAILABLE_MODELS = cls.get_models()
        except Exception as e:  # keep the static list on refresh failure
            print(f"{BOLD}Warning: Failed to update Qwen models: {e}{RESET}")

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def convert_model_name(self, model: str) -> str:
        """Resolve an alias/name; falls back to the default model."""
        try:
            return _resolve_model(model)
        except ValueError:
            print(
                f"{BOLD}Warning: Model '{model}' not found, "
                f"using default 'qwen3.7-plus'{RESET}"
            )
            return self.default_model

    def new_chat(self, model: Optional[str] = None) -> str:
        """Open a conversation and return its chat id (see QwenReversed)."""
        return self._reversed.new_chat(model)

    def _post_completions(
        self,
        chat_id: str,
        messages: List[Dict[str, Any]],
        model: str,
    ) -> requests.Response:
        """Send the streaming completions request (see QwenReversed)."""
        return self._reversed._post_completions(chat_id, messages, model)


if __name__ == "__main__":
    import os

    from llm4free.AIutel import timeIt

    @timeIt
    def main() -> None:
        token = os.environ.get("QWEN_TOKEN") or input(
            "Enter your chat.qwen.ai token: "
        ).strip()
        client = Qwen(api_key=token, timeout=300)
        response = client.chat.completions.create(
            model="qwen3.7-plus",
            messages=[
                {"role": "user", "content": "How many r are in strawberry? Answer briefly."}
            ],
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()

    main()
