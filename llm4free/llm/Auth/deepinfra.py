import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

from curl_cffi import CurlError
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
    def __init__(self, client: "DeepInfra"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 2049,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
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
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
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
        except Exception as e:
            print(f"Error during DeepInfra stream request: {e}")
            raise IOError(f"DeepInfra request failed: {e}") from e

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
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                timeout=timeout or self._client.timeout,
                proxies=proxies,  # ty:ignore[invalid-argument-type]
            )
            response.raise_for_status()
            data = response.json()
            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})
            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message")
                if not message_d and "delta" in choice_d:
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
        except Exception as e:
            print(f"Error during DeepInfra non-stream request: {e}")
            raise IOError(f"DeepInfra request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "DeepInfra"):
        self.completions = Completions(client)


class DeepInfra(OpenAICompatibleProvider):
    """
    DeepInfra OpenAI-compatible provider.

    DeepInfra provides OpenAI-compatible API for LLM models.
    API Documentation: https://deepinfra.com/docs/openai_api
    """

    required_auth = True
    AVAILABLE_MODELS = [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3-8B-Instruct",
        "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
        "deepseek-ai/DeepSeek-V3.1",
        "Qwen/Qwen2.5-72B-Instruct",
    ]

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Fetch available models from DeepInfra API.

        Args:
            api_key (str, optional): DeepInfra API key.

        Returns:
            list: List of available model IDs
        """
        if not api_key:
            return cls.AVAILABLE_MODELS

        try:
            # Use a temporary curl_cffi session for this class method
            temp_session = Session()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            response = temp_session.get(
                "https://api.deepinfra.com/v1/openai/models",
                headers=headers,
                impersonate="chrome110",
            )

            if response.status_code == 200:
                data = response.json()
                if "data" in data and isinstance(data["data"], list):
                    return [model["id"] for model in data["data"] if "id" in model]

        except (CurlError, Exception):
            pass

        # Fallback to default models list if fetching fails
        return cls.AVAILABLE_MODELS

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        """Update the available models list from DeepInfra API"""
        try:
            models = cls.get_models(api_key)
            if models and len(models) > 0:
                cls.AVAILABLE_MODELS = models
        except Exception:
            # Fallback to default models list if fetching fails
            pass

    def __init__(self, api_key: str, browser: str = "chrome"):
        """Initialize DeepInfra client.

        Args:
            api_key (str): DeepInfra API key (required).
            browser (str, optional): Browser type for fingerprint. Defaults to "chrome".
        """
        # Non-blocking background fetch of available models from API
        # Models will be cached after fetch completes
        self._start_background_model_fetch(api_key=api_key)

        self.timeout = None
        self.base_url = "https://api.deepinfra.com/v1/openai/chat/completions"
        self.session = Session()

        # Initialize LitAgent for browser fingerprint
        agent = LitAgent()
        fingerprint = agent.generate_fingerprint(browser)

        # Minimal headers for DeepInfra API
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": fingerprint["user_agent"],
        }

        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    import os

    api_key = os.environ.get("DEEPINFRA_API_KEY", "your-api-key-here")
    client = DeepInfra(api_key=api_key)
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        max_tokens=1000,
        stream=False,
    )
    if isinstance(response, ChatCompletion):
        if response.choices[0].message and response.choices[0].message.content:
            print(response.choices[0].message.content)
