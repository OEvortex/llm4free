import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http import compat as requests

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


class Completions(BaseCompletions):
    def __init__(self, client: "TogetherAI"):
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
        proxies: Optional[Dict[str, str]] = None,
        stop: Optional[Union[str, List[str]]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        # Get API key if not already set
        if not self._client.headers.get("Authorization"):
            # If no API key is set, we can't proceed.
            # The user should have provided it in __init__.
            pass

        model_name = self._client.convert_model_name(model)
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if stop is not None:
            payload["stop"] = stop
        payload.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id, created_time, model_name, payload, timeout, proxies
            )
        else:
            return self._create_non_stream(
                request_id, created_time, model_name, payload, timeout, proxies
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
        try:
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
            )
            response.raise_for_status()
            prompt_tokens = count_tokens(
                [msg.get("content", "") for msg in payload.get("messages", [])]
            )
            completion_tokens = 0
            total_tokens = prompt_tokens

            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        line = line[6:]
                        if line.strip() == "[DONE]":
                            break
                        try:
                            chunk_data = json.loads(line)
                            if "choices" in chunk_data and chunk_data["choices"]:
                                delta = chunk_data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    completion_tokens += count_tokens(content)
                                    total_tokens = prompt_tokens + completion_tokens
                                    choice_delta = ChoiceDelta(
                                        content=content,
                                        role=delta.get("role", "assistant"),
                                        tool_calls=delta.get("tool_calls"),
                                    )
                                    choice = Choice(
                                        index=0,
                                        delta=choice_delta,
                                        finish_reason=None,
                                        logprobs=None,
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
                                        "estimated_cost": None,
                                    }
                                    yield chunk
                        except Exception:
                            continue

            # Final chunk with finish_reason="stop"
            delta = ChoiceDelta(content=None, role=None, tool_calls=None)
            choice = Choice(index=0, delta=delta, finish_reason="stop", logprobs=None)
            chunk = ChatCompletionChunk(
                id=request_id, choices=[choice], created=created_time, model=model
            )
            chunk.usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": None,
            }
            yield chunk
        except Exception as e:
            raise IOError(f"TogetherAI stream request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        try:
            payload_copy = payload.copy()
            payload_copy["stream"] = False
            response = self._client.session.post(
                self._client.api_endpoint,
                headers=self._client.headers,
                json=payload_copy,
                timeout=timeout or self._client.timeout,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
            )
            response.raise_for_status()
            data = response.json()

            full_text = ""
            finish_reason = "stop"
            if "choices" in data and data["choices"]:
                full_text = data["choices"][0]["message"]["content"]
                finish_reason = data["choices"][0].get("finish_reason", "stop")

            message = ChatCompletionMessage(role="assistant", content=full_text)
            choice = Choice(index=0, message=message, finish_reason=finish_reason)

            prompt_tokens = count_tokens(
                [msg.get("content", "") for msg in payload.get("messages", [])]
            )
            completion_tokens = count_tokens(full_text)
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

            completion = ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )
            return completion
        except Exception as e:
            raise IOError(f"TogetherAI non-stream request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "TogetherAI"):
        self.completions = Completions(client)


class TogetherAI(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for TogetherAI API.
    """

    required_auth = True
    AVAILABLE_MODELS = []

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Fetch available models from Together API."""
        if not api_key:
            return cls.AVAILABLE_MODELS

        try:
            # Use a temporary session for fetching models
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            response = requests.get(
                "https://api.together.xyz/v1/models", headers=headers, timeout=30
            )

            if response.status_code != 200:
                return cls.AVAILABLE_MODELS

            data = response.json()
            # Together API returns a list of model objects
            if isinstance(data, list):
                return [model["id"] for model in data if isinstance(model, dict) and "id" in model]

            return cls.AVAILABLE_MODELS

        except Exception:
            return cls.AVAILABLE_MODELS

    @classmethod
    def update_available_models(cls, api_key=None):
        """Update the available models list from Together API"""
        try:
            models = cls.get_models(api_key)
            if models:
                cls.AVAILABLE_MODELS = models
        except Exception:
            pass

    def __init__(
        self,
        api_key: Optional[str] = None,
        browser: str = "chrome",
        proxies: Optional[Dict[str, str]] = None,
    ):
        # Start background model fetch (non-blocking)
        self._start_background_model_fetch(api_key)

        super().__init__(proxies=proxies)
        self.timeout = 60
        self.api_endpoint = "https://api.together.xyz/v1/chat/completions"
        # Initialize LitAgent for consistent fingerprints across requests
        self._agent = LitAgent()
        self.headers = self._generate_consistent_fingerprint(browser=browser)

        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def _generate_consistent_fingerprint(self, browser: Optional[str] = None) -> Dict[str, str]:
        """
        Generate a consistent browser fingerprint using the instance's LitAgent.

        This method uses the same LitAgent instance to ensure consistent IP addresses
        and user agent across multiple requests in a conversation, preventing 404 errors
        caused by rapidly changing fingerprints.

        Args:
            browser (Optional[str]): The browser name to generate the fingerprint for.
                If not specified, a random browser is used.

        Returns:
            Dict[str, str]: A dictionary containing fingerprinting headers and values.
        """
        import random

        from llm4free.litagent.constants import BROWSERS, FINGERPRINTS

        # Get a user agent from the instance's agent
        if browser:
            browser = browser.lower()
            if browser in BROWSERS:
                user_agent = self._agent.browser(browser)
            else:
                user_agent = self._agent.random()
        else:
            user_agent = self._agent.random()

        accept_language = random.choice(FINGERPRINTS["accept_language"])
        accept = random.choice(FINGERPRINTS["accept"])
        platform = random.choice(FINGERPRINTS["platforms"])

        # Generate sec-ch-ua based on the user agent
        sec_ch_ua = ""
        sec_ch_ua_map = cast(Dict[str, str], FINGERPRINTS["sec_ch_ua"])
        for browser_name in sec_ch_ua_map:
            if browser_name in user_agent.lower():
                version = random.randint(*BROWSERS[browser_name])
                sec_ch_ua = sec_ch_ua_map[browser_name].format(version, version)
                break

        # Use the instance's agent for consistent IP rotation
        ip = self._agent.rotate_ip()
        fingerprint = {
            "user_agent": user_agent,
            "accept_language": accept_language,
            "accept": accept,
            "sec_ch_ua": sec_ch_ua,
            "platform": platform,
            "x-forwarded-for": ip,
            "x-real-ip": ip,
            "x-client-ip": ip,
            "forwarded": f"for={ip};proto=https",
            "x-forwarded-proto": "https",
            "x-request-id": self._agent.random_id(8)
            if hasattr(self._agent, "random_id")
            else "".join(random.choices("0123456789abcdef", k=8)),
        }

        return fingerprint

    def convert_model_name(self, model: str) -> str:
        """Convert model name - returns model if valid, otherwise default"""
        if model in self.AVAILABLE_MODELS:
            return model

        # Default to first available model if not found, or return the model itself if list is empty
        if self.AVAILABLE_MODELS:
            return self.AVAILABLE_MODELS[0]
        return model


if __name__ == "__main__":
    from rich import print

    client = TogetherAI(api_key="YOUR_API_KEY")
    messages = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm fine, thank you! How can I help you today?"},
        {"role": "user", "content": "Tell me a short joke."},
    ]

    # Non-streaming example
    response = client.chat.completions.create(
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        messages=messages,
        max_tokens=50,
        stream=False,
    )
    print("Non-streaming response:")
    print(response)

    # Streaming example
    print("\nStreaming response:")
    stream_gen = client.chat.completions.create(
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        messages=messages,
        max_tokens=50,
        stream=True,
    )

    for chunk in stream_gen:
        if chunk.choices[0].delta and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")
    print()
