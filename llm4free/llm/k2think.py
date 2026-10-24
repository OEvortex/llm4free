"""K2 Horizon (formerly K2 Think) provider.

The public playground moved from ``www.k2think.ai`` to ``chat.ifm.ai`` and the
guest API changed shape:

* request body requires a ``chat_id`` (a random UUID is accepted);
* the model is ``IFM/K2-Horizon-375B-A23B``;
* streaming responses send cumulative ``content`` events, where reasoning is
  wrapped in ``<details type="reasoning">`` blocks;
* non-streaming responses use the regular OpenAI ``choices[].message`` shape
  and expose reasoning separately in ``message.reasoning``.

The implementation below was verified against live traffic from the guest
playground.
"""

import json
import re
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
    ToolCall,
    ToolFunction,
)

# K2 Horizon streams its reasoning inside HTML-like <details> blocks.  During
# streaming the closing tag can arrive several events later, so strip both
# complete and still-open blocks.
_REASONING_DETAILS_RE = re.compile(
    r"<details\b[^>]*\btype\s*=\s*[\"']?reasoning[\"']?[^>]*>.*?</details\s*>",
    re.IGNORECASE | re.DOTALL,
)
_OPEN_REASONING_DETAILS_RE = re.compile(
    r"<details\b[^>]*\btype\s*=\s*[\"']?reasoning[\"']?[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)
_THINK_TAG_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_OPEN_THINK_TAG_RE = re.compile(r"<think\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL)

_MODEL_ALIASES = {
    "MBZUAI-IFM/K2-Think-v2": "IFM/K2-Horizon-375B-A23B",
    "MBZUAI-IFM/K2-Think": "IFM/K2-Horizon-375B-A23B",
    "K2-Think-v2": "IFM/K2-Horizon-375B-A23B",
    "K2-Think": "IFM/K2-Horizon-375B-A23B",
    "k2-think": "IFM/K2-Horizon-375B-A23B",
    "k2-think-v2": "IFM/K2-Horizon-375B-A23B",
    "k2": "IFM/K2-Horizon-375B-A23B",
}
_DEFAULT_MODEL = "IFM/K2-Horizon-375B-A23B"


def _strip_thinking(text: str) -> str:
    """Remove K2 Horizon reasoning markup from ``text``.

    The playground streams cumulative content that looks like::

        <details type="reasoning" done="true" duration="0">
        <summary>Thought for 0 seconds</summary>
        > ...
        </details>
        Hello!

    Only ``Hello!`` is part of the actual answer.
    """
    if not text:
        return ""

    cleaned = _REASONING_DETAILS_RE.sub("", text)
    cleaned = _OPEN_REASONING_DETAILS_RE.sub("", cleaned)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = _OPEN_THINK_TAG_RE.sub("", cleaned)
    return cleaned.lstrip()


def _normalize_model(model: str) -> str:
    """Map old K2 Think model names to the current K2 Horizon model."""
    if not model or model.lower() in {"default", "k2think", "k2-think"}:
        return _DEFAULT_MODEL
    return _MODEL_ALIASES.get(model, model)


class Completions(BaseCompletions):
    def __init__(self, client: "K2Think"):
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
        tools: Optional[List[Any]] = None,
        tool_choice: Optional[Any] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        features = kwargs.pop("features", None)
        if not isinstance(features, dict):
            features = {"web_search": bool(kwargs.pop("web_search", False))}

        params = kwargs.pop("params", None)
        chat_id = kwargs.pop("chat_id", None) or str(uuid.uuid4())

        payload: Dict[str, Any] = {
            "stream": stream,
            "model": _normalize_model(model),
            "chat_id": chat_id,
            "messages": messages,
            "params": params if isinstance(params, dict) else {},
            "features": features,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        if stream:
            return self._handle_streaming_response(
                request_id, created_time, payload["model"], payload, timeout, proxies
            )
        return self._handle_non_streaming_response(
            request_id, created_time, payload["model"], payload, timeout, proxies
        )

    def _request_kwargs(
        self,
        payload: Dict[str, Any],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
        *,
        stream: bool,
    ) -> Dict[str, Any]:
        request_kwargs: Dict[str, Any] = {
            "json": payload,
            "timeout": timeout or self._client.timeout,
            "headers": {"Accept": "text/event-stream" if stream else "application/json"},
        }
        if stream:
            request_kwargs["stream"] = True
        if proxies:
            request_kwargs["proxies"] = proxies
        return request_kwargs

    def _handle_streaming_response(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        try:
            response = self._client.session.post(
                self._client.chat_endpoint,
                **self._request_kwargs(payload, timeout, proxies, stream=True),
            )
            response.raise_for_status()

            full_content = ""
            sent_content = ""
            role_sent = False

            try:
                for raw_line in response.iter_lines(decode_unicode=False):
                    if not raw_line:
                        continue

                    line = (
                        raw_line.decode("utf-8", errors="replace")
                        if isinstance(raw_line, bytes)
                        else raw_line
                    ).strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # K2 Horizon emits cumulative content events.  Some
                    # OpenAI-compatible deployments emit deltas instead, so
                    # support both shapes.
                    choices = data.get("choices") or []
                    delta_text: Optional[str] = None
                    if choices:
                        delta = choices[0].get("delta") or {}
                        delta_text = delta.get("content")

                    if data.get("content") is not None:
                        full_content = data["content"]
                    elif delta_text:
                        full_content += delta_text

                    is_done = bool(data.get("done"))
                    if is_done and data.get("content") is not None:
                        full_content = data["content"]

                    cleaned = _strip_thinking(full_content)
                    if cleaned and cleaned != sent_content and cleaned.startswith(sent_content):
                        new_text = cleaned[len(sent_content) :]
                        sent_content = cleaned
                        if new_text:
                            delta = ChoiceDelta(
                                content=new_text,
                                role=None if role_sent else "assistant",
                            )
                            role_sent = True
                            choice = Choice(index=0, delta=delta, finish_reason=None)
                            yield ChatCompletionChunk(
                                id=request_id,
                                choices=[choice],
                                created=created_time,
                                model=model,
                            )

                    if is_done:
                        break
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

            # Final chunk with finish_reason="stop"
            delta = ChoiceDelta(content=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop")
            yield ChatCompletionChunk(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
            )

        except Exception as e:
            raise IOError(f"K2Think streaming request failed: {e}") from e

    def _handle_non_streaming_response(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        try:
            response = self._client.session.post(
                self._client.chat_endpoint,
                **self._request_kwargs(payload, timeout, proxies, stream=False),
            )
            response.raise_for_status()

            data = response.json()
            choices_data = data.get("choices") or []
            usage_data = data.get("usage") or {}

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message") or {}

                raw_content = message_d.get("content") or ""
                cleaned_content = _strip_thinking(raw_content)
                reasoning = message_d.get("reasoning") or message_d.get("reasoning_content")

                tool_calls = []
                for tool_call_d in message_d.get("tool_calls") or []:
                    function = tool_call_d.get("function") or {}
                    tool_calls.append(
                        ToolCall(
                            id=tool_call_d.get("id") or f"call_{uuid.uuid4().hex}",
                            type=tool_call_d.get("type", "function"),
                            function=ToolFunction(
                                name=function.get("name", ""),
                                arguments=function.get("arguments", "{}"),
                            ),
                        )
                    )

                message = ChatCompletionMessage(
                    role=message_d.get("role", "assistant"),
                    content=cleaned_content or None,
                    reasoning=reasoning or None,
                    reasoning_content=reasoning or None,
                    tool_calls=tool_calls or None,
                )
                choice = Choice(
                    index=choice_d.get("index", 0),
                    message=message,
                    finish_reason=choice_d.get("finish_reason") or "stop",
                )
                choices.append(choice)

            usage = CompletionUsage(
                prompt_tokens=usage_data.get("prompt_tokens") or 0,
                completion_tokens=usage_data.get("completion_tokens") or 0,
                total_tokens=usage_data.get("total_tokens") or 0,
                prompt_tokens_details=usage_data.get("prompt_tokens_details"),
            )

            return ChatCompletion(
                id=data.get("id") or request_id,
                choices=choices,
                created=int(data.get("created") or created_time),
                model=data.get("model") or model,
                usage=usage,
            )

        except Exception as e:
            raise IOError(f"K2Think request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "K2Think"):
        self.completions = Completions(client)


class K2Think(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for the K2 Horizon (K2 Think) guest API.

    Usage:
        client = K2Think()
        response = client.chat.completions.create(
            model="IFM/K2-Horizon-375B-A23B",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    AVAILABLE_MODELS = [
        "IFM/K2-Horizon-375B-A23B",
    ]

    def __init__(
        self,
        timeout: int = 30,
        proxies: Optional[Dict[str, str]] = None,
        browser: str = "chrome",
    ):
        """
        Initialize the K2Think client.

        Args:
            timeout: Request timeout in seconds
            proxies: Proxy configuration for requests
            browser: Browser name for LitAgent to generate User-Agent
        """
        self.timeout = timeout
        self.proxies: Dict[str, str] = proxies or {}
        self.chat_endpoint = "https://chat.ifm.ai/api/guest/chat/completions"

        # curl_cffi with a browser TLS fingerprint passes Cloudflare the same
        # way the real playground does.
        self.session = Session(impersonate="chrome")

        # Set up browser fingerprinting
        self.agent = LitAgent()
        self.fingerprint = self.agent.generate_fingerprint(browser)
        self.session.headers.update(self._build_headers())

        # Set proxies if provided
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))

        # Initialize chat property
        self.chat = Chat(self)

    def _build_headers(self) -> Dict[str, str]:
        """Build the headers sent by the K2 Horizon playground."""
        return {
            "Accept": "application/json",
            "Accept-Language": self.fingerprint["accept_language"],
            "Content-Type": "application/json",
            "Origin": "https://chat.ifm.ai",
            "Referer": "https://chat.ifm.ai/guest",
            "User-Agent": self.fingerprint.get("user_agent", ""),
            "Sec-CH-UA": self.fingerprint.get("sec_ch_ua", ""),
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{self.fingerprint.get("platform", "")}"',
        }

    def refresh_identity(self, browser: Optional[str] = None) -> Dict[str, Any]:
        """
        Refreshes the browser identity fingerprint.

        Args:
            browser: Specific browser to use for the new fingerprint
        """
        browser = browser or self.fingerprint.get("browser_type", "chrome")
        self.fingerprint = self.agent.generate_fingerprint(browser)
        self.session.headers.update(self._build_headers())
        return self.fingerprint

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


# Example usage
if __name__ == "__main__":
    client = K2Think()
    messages = [
        {"role": "user", "content": "Say hello in one word"},
    ]

    print("=== Non-streaming ===")
    response = client.chat.completions.create(
        model="IFM/K2-Horizon-375B-A23B",
        messages=messages,
        stream=False,
    )
    if isinstance(response, ChatCompletion) and response.choices:
        msg = response.choices[0].message
        if msg:
            print(msg.content)

    print("\n=== Streaming ===")
    stream = client.chat.completions.create(
        model="IFM/K2-Horizon-375B-A23B",
        messages=messages,
        stream=True,
    )
    if hasattr(stream, "__iter__"):
        for chunk in stream:
            if isinstance(chunk, ChatCompletionChunk) and chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    print(delta.content, end="", flush=True)
        print()
