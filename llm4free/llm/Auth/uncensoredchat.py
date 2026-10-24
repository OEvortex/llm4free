"""
UncensoredChat - AI Chat via uncensored.chat

Uncensored.chat is a free, uncensored AI chat platform with character-based
roleplay and storytelling. This provider uses the OpenAI-compatible API at
/api/v1/chat/completions with a Bearer token API key.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi import CurlError, requests

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
)

CHARACTERS: Dict[str, Dict[str, Any]] = {
    "assistant": {
        "id": None,
        "name": "Assistant",
        "slug": "assistant",
    },
    "gigachad": {
        "id": 87,
        "name": "GigaChad",
        "slug": "gigachad",
    },
    "donald-trump": {
        "id": 601,
        "name": "Donald Trump",
        "slug": "donald-trump",
    },
    "mental-health": {
        "id": 943,
        "name": "Mental Health AI",
        "slug": "mental-health",
    },
    "jeffrey-epstein": {
        "id": 1007,
        "name": "Jeffrey Epstein",
        "slug": "jeffrey-epstein",
    },
    "sydney-sweeney": {
        "id": 249,
        "name": "Sydney Sweeney",
        "slug": "sydney-sweeney",
    },
    "steve-jobs": {
        "id": 113,
        "name": "Steve Jobs",
        "slug": "steve-jobs",
    },
    "ana-de-amars": {
        "id": 247,
        "name": "Ana de Amars",
        "slug": "ana-de-amars",
    },
    "mahatma-gandhi": {
        "id": 196,
        "name": "Mahatma Gandhi",
        "slug": "mahatma-gandhi",
    },
    "marie-curie": {
        "id": 123,
        "name": "Marie Curie",
        "slug": "marie-curie",
    },
    "cleopatra": {
        "id": 144,
        "name": "Cleopatra",
        "slug": "cleopatra",
    },
}


class Completions(BaseCompletions):
    def __init__(self, client: "UncensoredChat"):
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
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        character = self._client.convert_model_name(model)
        char_info = CHARACTERS.get(character, CHARACTERS["assistant"])

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        payload: Dict[str, Any] = {
            "model": char_info["slug"],
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p

        if stream:
            return self._create_stream(request_id, created_time, model, payload, timeout, proxies)
        else:
            return self._create_non_stream(
                request_id, created_time, model, payload, timeout, proxies
            )

    def _make_request(
        self,
        payload: Dict[str, Any],
        stream: bool,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ):
        headers = {
            "Authorization": f"Bearer {self._client.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        session = self._client.session
        try:
            response = session.post(
                self._client.api_endpoint,
                json=payload,
                headers=headers,
                stream=stream,
                timeout=timeout or self._client.timeout,
                impersonate="chrome131",
            )
            response.raise_for_status()
            return response
        except CurlError as e:
            raise IOError(f"UncensoredChat request failed: {e}") from e

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        payload["stream"] = True
        response = self._make_request(payload, stream=True, timeout=timeout, proxies=proxies)

        for raw_line in response.iter_lines():
            if raw_line is None:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("data: "):
                data_str = line[6:]
            elif line.startswith("data:"):
                data_str = line[5:]
            else:
                continue

            data_str = data_str.strip()
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason")
                content = delta.get("content")

                if content:
                    delta_obj = ChoiceDelta(content=content)
                    c = Choice(index=0, delta=delta_obj, finish_reason=None)
                    chunk = ChatCompletionChunk(
                        id=request_id,
                        choices=[c],
                        created=created_time,
                        model=model,
                    )
                    yield chunk

                if finish_reason:
                    delta_obj = ChoiceDelta(content=None)
                    c = Choice(index=0, delta=delta_obj, finish_reason=finish_reason)
                    chunk = ChatCompletionChunk(
                        id=request_id,
                        choices=[c],
                        created=created_time,
                        model=model,
                    )
                    yield chunk
                    break
            except json.JSONDecodeError:
                continue

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        payload["stream"] = False
        response = self._make_request(payload, stream=False, timeout=timeout, proxies=proxies)
        data = response.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage_data = data.get("usage", {})

        usage = CompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        message = ChatCompletionMessage(role="assistant", content=content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "UncensoredChat"):
        self.completions = Completions(client)


class UncensoredChat(OpenAICompatibleProvider):
    """
    Free AI Chat via uncensored.chat (OpenAI-compatible API)

    Requires an API key from uncensored.chat (get one from your dashboard).
    Uses the OpenAI-compatible /api/v1/chat/completions endpoint.

    Usage:
        client = UncensoredChat(api_key="your-api-key")
        response = client.chat.completions.create(
            model="gigachad",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = True
    AVAILABLE_MODELS = list(CHARACTERS.keys())

    def __init__(
        self,
        api_key: Optional[str] = None,
        proxies: Optional[dict] = None,
        timeout: int = 60,
    ):
        self.api_endpoint = "https://uncensored.chat/api/v1/chat/completions"
        self.timeout = timeout
        self._api_key = api_key or ""
        self.proxies = proxies or {}
        self.session = requests.Session()
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))
        self.chat = Chat(self)

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str):
        self._api_key = value

    def convert_model_name(self, model: str) -> str:
        if model in CHARACTERS:
            return model
        for slug, info in CHARACTERS.items():
            if model.lower() in info["name"].lower():
                return slug
        return "assistant"

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    import sys

    print("-" * 80)
    print(f"{'Model':<50} {'Status':<10} {'Response'}")
    print("-" * 80)

    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    if not api_key:
        print("Usage: python uncensoredchat.py YOUR_API_KEY")
        sys.exit(1)

    for model in UncensoredChat.AVAILABLE_MODELS:
        try:
            client = UncensoredChat(api_key=api_key, timeout=120)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'Hello' in one word"}],
                stream=False,
            )
            if (
                isinstance(response, ChatCompletion)
                and response.choices
                and response.choices[0].message
                and response.choices[0].message.content
            ):
                status = "✓"
                display_text = response.choices[0].message.content.strip()
                display_text = display_text[:50] + "..." if len(display_text) > 50 else display_text
            else:
                status = "✗"
                display_text = "Empty or invalid response"
            print(f"{model:<50} {status:<10} {display_text}")
        except Exception as e:
            print(f"{model:<50} {'✗':<10} {str(e)[:80]}")
