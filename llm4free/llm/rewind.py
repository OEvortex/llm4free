"""Rewind.ai provider (https://rewind.ai).

OpenAI-compatible wrapper around Rewind.ai's anonymous chat API.

Authentication (anonymous):
    GET https://api.rewind.ai/v1/users/me
    -> response header ``x-anon-token: <JWT>`` (valid ~30 days).

Chat:
    POST https://api.rewind.ai/v1/chat/completions/
    Authorization: Bearer <token>
    body: {"messages": [...], "model": "...", "stream": true|false}
    response: JSON or text/event-stream (SSE) chunks.

Models:
    GET https://api.rewind.ai/v1/models
"""

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi.requests import Session

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
)

BASE_URL = "https://api.rewind.ai"
CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions/"
MODELS_ENDPOINT = f"{BASE_URL}/v1/models"
USERS_ME_ENDPOINT = f"{BASE_URL}/v1/users/me"

DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"

# Models available to anonymous (no-signup) users.
ANONYMOUS_MODELS = [
    "deepseek/deepseek-v4-flash-0731",
    "google/gemini-3.1-flash-lite",
    "google/gemma-4-26b-a4b-it",
    "google/gemma-4-26b-a4b-it:free",
    "mistralai/ministral-8b-2512",
    "qwen/qwen-2.5-7b-instruct",
    "qwen/qwen3-30b-a3b",
    "qwen/qwen3-30b-a3b-instruct-2507",
    "qwen/qwen3-coder-30b-a3b-instruct",
    "qwen/qwen3-coder",
    "qwen/qwen3-coder-flash",
    "black-forest-labs/flux.2-flex",
    # "black-forest-labs/flux.2-klein-4b",
    # "bytedance-seed/seedream-4.5",
    # "flux2-klein-4b-fp8",
    # "recraft/recraft-v4-pro",
    # "sdxl",
    # "google/lyria-3-clip-preview",
    # "hexgrad/kokoro-82m",
    # "openai/whisper-1",
]


class Completions(BaseCompletions):
    def __init__(self, client: "RewindAI"):
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        model = model or self._client.default_model
        messages = messages or []
        timeout = timeout or self._client.timeout

        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        if stream:
            return self._stream(request_id, created_time, model, messages, timeout, proxies, **kwargs)

        content = ""
        for chunk in self._stream(request_id, created_time, model, messages, timeout, proxies, **kwargs):
            choice = chunk.choices[0]
            if choice.delta and choice.delta.content:
                content += choice.delta.content

        prompt_tokens = sum(count_tokens(str(m.get("content", ""))) for m in messages)
        completion_tokens = count_tokens(content)
        return ChatCompletion(
            id=request_id,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            created=created_time,
            model=model,
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    def _request(
        self,
        payload: Dict[str, Any],
        timeout: int,
        proxies: Optional[Dict[str, str]],
        stream: bool,
    ) -> Any:
        client = self._client
        headers = {
            "Accept": "text/event-stream" if stream else "application/json",
            "Content-Type": "application/json",
            "Referer": "https://rewind.ai/",
            "Origin": "https://rewind.ai",
        }
        if client.token:
            headers["Authorization"] = f"Bearer {client.token}"

        return client.session.post(
            client.chat_endpoint,
            headers=headers,
            json=payload,
            stream=stream,
            timeout=timeout,
            impersonate="chrome120",
            proxies=cast(Any, proxies or client.proxies),
        )

    def _stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: int,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Generator[ChatCompletionChunk, None, None]:
        client = self._client
        payload: Dict[str, Any] = {
            "messages": messages,
            "model": model,
            "stream": True,
        }
        if kwargs:
            payload.update(kwargs)

        response = self._request(payload, timeout, proxies, stream=True)
        if response.status_code == 401 and not client.api_key:
            client._fetch_anonymous_token()
            response = self._request(payload, timeout, proxies, stream=True)

        if response.status_code != 200:
            raise IOError(
                f"RewindAI request failed ({response.status_code}): {response.text}"
            )

        prompt_tokens = sum(count_tokens(str(m.get("content", ""))) for m in messages)
        completion_tokens = 0
        full_content = ""

        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", "replace") if isinstance(raw_line, bytes) else raw_line
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                if data == "[DONE]":
                    break
                continue

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            choices = event.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    full_content += content
                    completion_tokens += count_tokens(content)
                    yield ChatCompletionChunk(
                        id=request_id,
                        choices=[
                            Choice(
                                index=0,
                                delta=ChoiceDelta(content=content, role="assistant"),
                                finish_reason=None,
                            )
                        ],
                        created=created_time,
                        model=model,
                    )

                finish_reason = choice.get("finish_reason")
                if finish_reason:
                    pass

        yield ChatCompletionChunk(
            id=request_id,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                )
            ],
            created=created_time,
            model=model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )


class Chat(BaseChat):
    def __init__(self, client: "RewindAI"):
        self.completions = Completions(client)


class RewindAI(OpenAICompatibleProvider):
    """Rewind.ai provider (OpenAI-compatible)."""

    required_auth = False
    AVAILABLE_MODELS = list(ANONYMOUS_MODELS)
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 60,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ):
        super().__init__(api_key=api_key, proxies=proxies, **kwargs)
        self.timeout = timeout
        self.proxies = proxies or {}
        self.api_key = api_key
        self.token: Optional[str] = api_key
        self.chat_endpoint = CHAT_ENDPOINT
        self.models_endpoint = MODELS_ENDPOINT
        self.users_me_endpoint = USERS_ME_ENDPOINT
        self.session = Session()
        self.session.timeout = (10.0, 30.0)
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))

        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "referer": "https://rewind.ai/",
            "origin": "https://rewind.ai",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }
        self.session.headers.update(self.headers)

        if not self.api_key:
            self._fetch_anonymous_token()

        self.chat = Chat(self)

    def _fetch_anonymous_token(self) -> str:
        response = self.session.get(
            self.users_me_endpoint,
            headers={"Accept": "application/json", "Content-Type": "application/json", "Referer": "https://rewind.ai/"},
            timeout=self.timeout,
            impersonate="chrome120",
            proxies=cast(Any, self.proxies or None),
        )
        token = response.headers.get("x-anon-token") or response.headers.get("X-Anon-Token")
        if not token:
            raise IOError(f"RewindAI: failed to obtain anonymous token ({response.status_code})")
        self.token = token
        return token

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return cls.AVAILABLE_MODELS

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    client = RewindAI()
    print("Models:", client.models.list()[:5])
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "Say hi in one word."}],
        stream=False,
    )
    print("Response:", resp.choices[0].message.content if resp.choices[0].message else None)
