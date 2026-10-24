"""ChatBotChatApp provider (https://chatbotchatapp.com).

Wraps the site's public web front-end behind the OpenAI-compatible interface.

Request flow:
1. GET / to obtain the session cookies, the CSRF meta token, and the page ``ypp`` value.
2. POST /api/get-timestamp to obtain the server timestamp.
3. POST /api with a signed payload; the response is an SSE stream.

The request ``id`` is an MD5 over the timestamp, nonce, the hashed message
content, and a fixed client token:

    md5("timestamp" + ts + "nonce" + nonce + "messages" + content
        + "keyToken" + "XXXXXXYYY" + "vv1")
"""

import hashlib
import json
import re
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

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

BASE_URL = "https://chatbotchatapp.com"

# Model selectors exposed by the site's model picker. "auto" sends no model.
AVAILABLE_MODELS = [
    "auto",
    "model-gpt-5",
    "model-minimax-m3",
    "model-chatgpt-4",
    "model-chatgpt-3-5",
    "model-pixtral",
]

# Literal client token used by the site when signing requests.
_SIGNING_TOKEN = "XXXXXXYYY"

_CSRF_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')
_YPP_RE = re.compile(r'const\s+ypp\s*=\s*"([^"]+)"')


def _iter_json_objects(text: str) -> Generator[Dict[str, Any], None, None]:
    """Yield every concatenated JSON object in an SSE data payload."""
    decoder = json.JSONDecoder()
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        try:
            obj, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            yield obj
        index = end


def _content_to_text(content: Any) -> str:
    """Normalize OpenAI message content (str or list of parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts)
    return "" if content is None else str(content)


class Completions(BaseCompletions):
    def __init__(self, client: "ChatBotChatApp"):
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
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
            return self._stream(request_id, created_time, model, messages, timeout)

        content = ""
        for chunk in self._stream(request_id, created_time, model, messages, timeout):
            choice = chunk.choices[0]
            if choice.delta and choice.delta.content:
                content += choice.delta.content

        prompt_tokens = count_tokens(format_prompt(messages))
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

    def _stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: int,
    ) -> Generator[ChatCompletionChunk, None, None]:
        response = self._post_chat(model, messages, timeout)

        finished = False
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", "replace") if isinstance(raw_line, bytes) else raw_line
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue

            for event in _iter_json_objects(data):
                conversation_id = event.get("conversationId")
                if conversation_id:
                    self._client.last_conversation_id = conversation_id

                choices = event.get("choices") or event.get("candidates") or []
                for choice in choices:
                    content = choice.get("content") or {}
                    for part in content.get("parts") or []:
                        text = part.get("text")
                        if text:
                            yield ChatCompletionChunk(
                                id=request_id,
                                choices=[
                                    Choice(
                                        index=0,
                                        delta=ChoiceDelta(content=text, role="assistant"),
                                        finish_reason=None,
                                    )
                                ],
                                created=created_time,
                                model=model,
                            )

                    if choice.get("finishReason") in ("STOP", "MAX_TOKENS"):
                        finished = True

        if not finished:
            finished = True
        if finished:
            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=None, role=None),
                        finish_reason="stop",
                    )
                ],
                created=created_time,
                model=model,
            )

    def _build_payload(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: int,
    ) -> Dict[str, Any]:
        modal = None if model in ("auto", "") else model
        serialized = self._serialize_messages(messages, modal)

        csrf, ypp = self._client._ensure_session(timeout)
        timestamp = self._client._get_timestamp(csrf, ypp, timeout)

        nonce = str(uuid.uuid4())
        # The site signs a single message body, selected with timestamp modulo
        # the message count, not the whole conversation.
        signed_content = serialized[timestamp % len(serialized)]["content"]
        signature = (
            f"timestamp{timestamp}"
            f"nonce{nonce}"
            f"messages{signed_content}"
            f"keyToken{_SIGNING_TOKEN}"
            f"vv1"
        )
        request_id = hashlib.md5(signature.encode("utf-8")).hexdigest()

        return {
            "id": request_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "messages": serialized,
            "url": f"{BASE_URL}/",
            "modal": modal,
        }

    def _serialize_messages(
        self, messages: List[Dict[str, Any]], modal: Optional[str]
    ) -> List[Dict[str, Any]]:
        system_parts = [
            _content_to_text(m.get("content"))
            for m in messages
            if m.get("role") == "system" and _content_to_text(m.get("content"))
        ]
        preamble = "\n\n".join(system_parts)

        conversation = [m for m in messages if m.get("role") != "system"]
        if not conversation and preamble:
            conversation = [{"role": "user", "content": preamble}]

        now_ms = int(time.time() * 1000)
        serialized: List[Dict[str, Any]] = []
        preamble_pending = bool(preamble)

        for index, message in enumerate(conversation):
            role = message.get("role", "user")
            content = _content_to_text(message.get("content"))
            if role == "assistant":
                role = "model"
            elif role != "user":
                role = "user"

            if preamble_pending and role == "user":
                content = f"{preamble}\n\n{content}" if content else preamble
                preamble_pending = False

            serialized.append(
                {
                    "role": role,
                    "content": content,
                    "thoughts": "",
                    "attachments": "",
                    "toolNameHints": [],
                    "functionCall": "",
                    "dataAdd": "",
                    "timestamp": now_ms + index * 2 + (2 if role == "model" else 0),
                    "model": modal,
                }
            )

        return serialized or [
            {
                "role": "user",
                "content": "",
                "thoughts": "",
                "attachments": "",
                "toolNameHints": [],
                "functionCall": "",
                "dataAdd": "",
                "timestamp": now_ms,
                "model": modal,
            }
        ]

    def _post_chat(
        self, model: str, messages: List[Dict[str, Any]], timeout: int
    ) -> Any:
        for attempt in range(2):
            csrf, _ = self._client._ensure_session(timeout)
            payload = self._build_payload(model, messages, timeout)
            headers = self._client._request_headers()
            headers.update(
                {
                    "Accept": "text/event-stream",
                    "Content-Type": "text/plain;charset=UTF-8",
                    "X-CSRF-TOKEN": csrf,
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}/",
                }
            )
            response = self._client.session.post(
                f"{BASE_URL}/api",
                data=json.dumps(payload),
                headers=headers,
                stream=True,
                timeout=timeout,
                impersonate="chrome110",
            )
            if response.status_code in (419, 403) and attempt == 0:
                self._client._reset_session()
                continue
            if response.status_code == 429:
                response.close()
                raise IOError("ChatBotChatApp rate limit reached; try again later")
            response.raise_for_status()
            return response

        raise IOError("ChatBotChatApp session rejected the request")


class Chat(BaseChat):
    def __init__(self, client: "ChatBotChatApp"):
        self.completions = Completions(client)


class ChatBotChatApp(OpenAICompatibleProvider):
    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = "auto"

    def __init__(
        self,
        timeout: int = 120,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ):
        super().__init__(proxies=proxies, **kwargs)
        self.timeout = timeout
        self.user_agent = LitAgent().random()
        self._csrf: Optional[str] = None
        self._ypp: Optional[str] = None
        self.last_conversation_id: Optional[str] = None
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return cls.AVAILABLE_MODELS

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def _request_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{BASE_URL}/",
        }

    def _reset_session(self) -> None:
        self._csrf = None
        self._ypp = None

    def _ensure_session(self, timeout: int) -> tuple[str, str]:
        if self._csrf and self._ypp:
            return self._csrf, self._ypp

        response = self.session.get(
            f"{BASE_URL}/",
            headers=self._request_headers(),
            timeout=timeout,
            impersonate="chrome110",
        )
        response.raise_for_status()
        html = response.text

        csrf_match = _CSRF_RE.search(html)
        ypp_match = _YPP_RE.search(html)
        if not csrf_match or not ypp_match:
            raise IOError("ChatBotChatApp: failed to extract CSRF token or ypp value")

        self._csrf = csrf_match.group(1)
        self._ypp = ypp_match.group(1)
        return self._csrf, self._ypp

    def _get_timestamp(self, csrf: str, ypp: str, timeout: int) -> int:
        headers = self._request_headers()
        headers.update(
            {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRF-TOKEN": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
            }
        )
        response = self.session.post(
            f"{BASE_URL}/api/get-timestamp",
            data={"href": f"{BASE_URL}/", "ypp": ypp},
            headers=headers,
            timeout=timeout,
            impersonate="chrome110",
        )
        response.raise_for_status()
        payload = response.json()

        if not payload.get("status") or "timestamp" not in payload:
            raise IOError(f"ChatBotChatApp: timestamp handshake failed: {payload}")

        return int(payload["timestamp"])


if __name__ == "__main__":
    client = ChatBotChatApp()
    result = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Say hello in one word."}],
        stream=True,
    )
    for chunk in result:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    print()
    print("conversation:", client.last_conversation_id)
