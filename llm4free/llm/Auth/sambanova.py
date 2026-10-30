"""
Sambanova OpenAI-compatible provider.
https://api.sambanova.ai/v1/chat/completions
"""

import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from llm4free.browser_requests._http.exceptions import CurlError
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
)


class Completions(BaseCompletions):
    def __init__(self, client: "Sambanova"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 4096,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        top_p: Optional[float] = 0.9,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        payload.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(request_id, created_time, model, payload, timeout, proxies)
        else:
            return self._create_non_stream(
                request_id, created_time, model, payload, timeout, proxies
            )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Implementation for streaming chat completions."""
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                proxies=proxies
                impersonate="chrome120",
            )
            response.raise_for_status()

            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0

            for line in response.iter_lines(decode_unicode=True):
                if line:
                    if line.startswith("data: "):
                        json_str = line[6:]
                        if json_str == "[DONE]":
                            break
                        try:
                            data = json.loads(json_str)
                            choices = data.get("choices")
                            if not choices and choices is not None:
                                continue
                            choice_data = choices[0] if choices else {}
                            delta_data = choice_data.get("delta", {})
                            finish_reason = choice_data.get("finish_reason")

                            # Update usage if available
                            usage_data = data.get("usage", {})
                            if usage_data:
                                prompt_tokens = usage_data.get("prompt_tokens", prompt_tokens)
                                completion_tokens = usage_data.get(
                                    "completion_tokens", completion_tokens
                                )
                                total_tokens = usage_data.get("total_tokens", total_tokens)

                            if delta_data.get("content"):
                                completion_tokens += 1
                                total_tokens = prompt_tokens + completion_tokens

                            delta = ChoiceDelta(
                                content=delta_data.get("content"),
                                role=delta_data.get("role"),
                                tool_calls=delta_data.get("tool_calls"),
                            )
                            choice = Choice(
                                index=choice_data.get("index", 0),
                                delta=delta,
                                finish_reason=finish_reason,
                                logprobs=choice_data.get("logprobs"),
                            )
                            chunk = ChatCompletionChunk(
                                id=request_id,
                                choices=[choice],
                                created=created_time,
                                model=model,
                                system_fingerprint=data.get("system_fingerprint"),
                            )
                            chunk.usage = {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "total_tokens": total_tokens,
                                "estimated_cost": None,
                            }
                            yield chunk

                        except json.JSONDecodeError:
                            continue

            # Final chunk with finish_reason="stop"
            delta = ChoiceDelta(content=None, role=None, tool_calls=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop", logprobs=None)
            chunk = ChatCompletionChunk(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                system_fingerprint=None,
            )
            chunk.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": None,
            }
            yield chunk

        except CurlError as e:
            raise IOError(f"Sambanova stream request failed (CurlError): {e}") from e
        except Exception as e:
            raise IOError(f"Sambanova stream request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        """Implementation for non-streaming chat completions."""
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                timeout=timeout or self._client.timeout,
                proxies=proxies
                impersonate="chrome120",
            )
            response.raise_for_status()
            data = response.json()

            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message")
                if not message_d and "delta" in choice_d:
                    # Handle streaming-style response in non-stream mode
                    delta = choice_d["delta"]
                    message_d = {
                        "role": delta.get("role", "assistant"),
                        "content": delta.get("content", ""),
                    }
                if not message_d:
                    message_d = {"role": "assistant", "content": ""}

                message = ChatCompletionMessage(
                    role=message_d.get("role", "assistant"), content=message_d.get("content", "")
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

            completion = ChatCompletion(
                id=request_id,
                choices=choices,
                created=created_time,
                model=data.get("model", model),
                usage=usage,
            )
            return completion

        except CurlError as e:
            raise IOError(f"Sambanova non-stream request failed (CurlError): {e}") from e
        except Exception as e:
            raise IOError(f"Sambanova non-stream request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Sambanova"):
        self.completions = Completions(client)


class Sambanova(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for Sambanova API.
    Requires API key from https://cloud.sambanova.ai/
    """

    required_auth = True

    AVAILABLE_MODELS = []

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Fetch available models from Sambanova API."""
        if not api_key:
            raise ValueError("API key is required to fetch models.")

        try:
            temp_session = Session()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            response = temp_session.get(
                "https://api.sambanova.ai/v1/models", headers=headers, impersonate="chrome120"
            )

            if response.status_code == 200:
                data = response.json()
                if "data" in data and isinstance(data["data"], list):
                    return [model["id"] for model in data["data"] if "id" in model]

            return cls.AVAILABLE_MODELS

        except Exception:
            return cls.AVAILABLE_MODELS

    def __init__(self, api_key: str, timeout: int = 60, browser: str = "chrome"):
        """
        Initialize the Sambanova OpenAI-compatible client.

        Args:
            api_key: Your Sambanova API key (required)
            timeout: Request timeout in seconds
            browser: Browser type for fingerprinting
        """
        if not api_key:
            raise ValueError("API key is required for Sambanova")

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.sambanova.ai/v1/chat/completions"

        self.session = Session()

        # Generate browser fingerprint
        if LitAgent:
            agent = LitAgent()
            fingerprint = agent.generate_fingerprint(browser)
            self.headers = {
                "Accept": fingerprint.get("accept", "*/*"),
                "Accept-Language": fingerprint.get("accept_language", "en-US,en;q=0.9"),
                "Content-Type": "application/json",
                "User-Agent": fingerprint.get("user_agent", ""),
                "Sec-CH-UA": fingerprint.get("sec_ch_ua", ""),
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": f'"{fingerprint.get("platform", "Windows")}"',
                "Authorization": f"Bearer {api_key}",
            }
        else:
            self.headers = {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

        self.session.headers.update(self.headers)

        # Update models list dynamically
        self.update_available_models(api_key)

        # Initialize chat interface
        self.chat = Chat(self)

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        """Update the available models list from Sambanova API."""
        if api_key:
            models = cls.get_models(api_key)
            if models:
                cls.AVAILABLE_MODELS = models

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    # Example usage - requires API key
    import os

    api_key = os.environ.get("SAMBANOVA_API_KEY", "")
    if not api_key:
        print("Set SAMBANOVA_API_KEY environment variable to test")
    else:
        client = Sambanova(api_key=api_key)
        print(f"Available models: {client.models.list()}")

        # Test non-streaming
        response = client.chat.completions.create(
            model="Meta-Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": "Hello!"}],
            max_tokens=100,
            stream=False,
        )
        if isinstance(response, ChatCompletion):
            message = response.choices[0].message if response.choices else None
            print(f"Response: {message.content if message else ''}")
        else:
            print(f"Response: {response}")

        # Test streaming
        print("\nStreaming response:")
        stream_resp = client.chat.completions.create(
            model="Meta-Llama-3.1-8B-Instruct",
            messages=[{"role": "user", "content": "Say hello briefly"}],
            max_tokens=100,
            stream=True,
        )
        if hasattr(stream_resp, "__iter__") and not isinstance(
            stream_resp, (str, bytes, ChatCompletion)
        ):
            for chunk in stream_resp:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    print(delta.content, end="", flush=True)
        else:
            print(stream_resp)
        print()
