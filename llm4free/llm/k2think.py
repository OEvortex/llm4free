import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

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
)


class Completions(BaseCompletions):
    def __init__(self, client: "K2Think"):
        self._client = client

    @staticmethod
    def _strip_thinking(text: str) -> str:
        marker = "</think>"
        idx = text.rfind(marker)
        if idx != -1:
            return text[idx + len(marker) :].lstrip()
        return text

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
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())

        payload = {
            "stream": stream,
            "model": model,
            "messages": messages,
            "params": {},
            "features": {"web_search": False},
        }

        if stream:
            return self._handle_streaming_response(
                request_id, created_time, model, payload, timeout, proxies
            )
        else:
            return self._handle_non_streaming_response(
                request_id, created_time, model, payload, timeout, proxies
            )

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
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
            )
            response.raise_for_status()

            full_content = ""
            sent_length = 0

            for line in response.iter_lines(decode_unicode=False):
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue

                json_str = line[6:]
                if json_str == "[DONE]":
                    break

                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                if "done" in data and data.get("done"):
                    final_content = data.get("content", full_content)
                    cleaned = self._strip_thinking(final_content)
                    if len(cleaned) > sent_length:
                        new_text = cleaned[sent_length:]
                        sent_length = len(cleaned)
                        delta = ChoiceDelta(content=new_text, role="assistant")
                        choice = Choice(index=0, delta=delta, finish_reason=None)
                        yield ChatCompletionChunk(
                            id=request_id,
                            choices=[choice],
                            created=created_time,
                            model=model,
                        )
                    break

                if "content" in data:
                    full_content = data["content"]

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
                json=payload,
                stream=False,
                timeout=timeout or self._client.timeout,
            )
            response.raise_for_status()

            data = response.json()
            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message")
                if not message_d:
                    message_d = {"role": "assistant", "content": ""}

                raw_content = message_d.get("content", "")
                cleaned_content = self._strip_thinking(raw_content)

                message = ChatCompletionMessage(
                    role=message_d.get("role", "assistant"),
                    content=cleaned_content,
                )
                choice = Choice(
                    index=choice_d.get("index", 0),
                    message=message,
                    finish_reason=choice_d.get("finish_reason", "stop"),
                )
                choices.append(choice)

            usage = CompletionUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return ChatCompletion(
                id=request_id,
                choices=choices,
                created=created_time,
                model=data.get("model", model),
                usage=usage,
            )

        except Exception as e:
            raise IOError(f"K2Think request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "K2Think"):
        self.completions = Completions(client)


class K2Think(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for K2Think AI API.

    Usage:
        client = K2Think()
        response = client.chat.completions.create(
            model="MBZUAI-IFM/K2-Think-v2",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    AVAILABLE_MODELS = [
        "MBZUAI-IFM/K2-Think-v2",
    ]

    def __init__(self, timeout: int = 30, proxies: dict = {}, browser: str = "chrome"):
        """
        Initialize the K2Think client.

        Args:
            timeout: Request timeout in seconds
            proxies: Proxy configuration for requests
            browser: Browser name for LitAgent to generate User-Agent
        """
        self.timeout = timeout
        self.proxies = proxies
        self.chat_endpoint = "https://www.k2think.ai/api/guest/chat/completions"

        # Initialize session with curl_cffi
        self.session = Session()

        # Set up browser fingerprinting
        self.agent = LitAgent()
        self.fingerprint = self.agent.generate_fingerprint(browser)

        # Set headers
        self.session.headers.update(
            {
                "Accept": self.fingerprint["accept"],
                "Accept-Language": self.fingerprint["accept_language"],
                "Content-Type": "application/json",
                "Origin": "https://www.k2think.ai",
                "Referer": "https://www.k2think.ai/guest",
                "User-Agent": self.fingerprint.get("user_agent", ""),
                "Sec-CH-UA": self.fingerprint.get("sec_ch_ua", ""),
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": f'"{self.fingerprint.get("platform", "")}"',
            }
        )

        # Set proxies if provided
        if proxies:
            self.session.proxies.update(cast(Any, proxies))

        # Initialize chat property
        self.chat = Chat(self)

    def refresh_identity(self, browser: Optional[str] = None):
        """
        Refreshes the browser identity fingerprint.

        Args:
            browser: Specific browser to use for the new fingerprint
        """
        browser = browser or self.fingerprint.get("browser_type", "chrome")
        self.fingerprint = self.agent.generate_fingerprint(browser)

        self.session.headers.update(
            {
                "Accept": self.fingerprint["accept"],
                "Accept-Language": self.fingerprint["accept_language"],
            }
        )

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
        model="MBZUAI-IFM/K2-Think-v2",
        messages=messages,
        stream=False,
    )
    if isinstance(response, ChatCompletion) and response.choices:
        msg = response.choices[0].message
        if msg:
            print(msg.content)

    print("\n=== Streaming ===")
    stream = client.chat.completions.create(
        model="MBZUAI-IFM/K2-Think-v2",
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
