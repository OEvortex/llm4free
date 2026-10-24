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
    def __init__(self, client: "Cerebras"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 40000,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        top_p: Optional[float] = 0.8,
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
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                stream=True,
                timeout=timeout or self._client.timeout,
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
            print(f"Error during Cerebras stream request: {e}")
            raise IOError(f"Cerebras request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
    ) -> ChatCompletion:
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))
        try:
            response = self._client.session.post(
                self._client.base_url,
                headers=self._client.headers,
                json=payload,
                timeout=timeout or self._client.timeout,
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
            print(f"Error during Cerebras non-stream request: {e}")
            raise IOError(f"Cerebras request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Cerebras"):
        self.completions = Completions(client)


class Cerebras(OpenAICompatibleProvider):
    required_auth = True
    AVAILABLE_MODELS = []

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Fetch available models from Cerebras API."""
        if not api_key:
            raise Exception("API key required to fetch models")

        try:
            # Use a temporary curl_cffi session for this class method
            temp_session = Session()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            response = temp_session.get(
                "https://api.cerebras.ai/v1/models", headers=headers, impersonate="chrome120"
            )

            if response.status_code != 200:
                raise Exception(f"Failed to fetch models: HTTP {response.status_code}")

            data = response.json()
            if "data" in data and isinstance(data["data"], list):
                return [model["id"] for model in data["data"]]
            raise Exception("Invalid response format from API")

        except (CurlError, Exception) as e:
            raise Exception(f"Failed to fetch models: {str(e)}")

    def __init__(self, browser: str = "chrome", api_key: Optional[str] = None):
        if not api_key:
            raise ValueError("API key is required for Cerebras")
        # Defer model fetch to background to avoid blocking initialization
        # The API requires api_key for fetching models, passed via background worker
        self._start_background_model_fetch(api_key=api_key)
        self.timeout = None
        self.base_url = "https://api.cerebras.ai/v1/chat/completions"
        self.session = Session()
        agent = LitAgent()
        fingerprint = agent.generate_fingerprint(browser)
        self.headers = {
            "Accept": fingerprint["accept"],
            "Accept-Language": fingerprint["accept_language"],
            "Content-Type": "application/json",
            "User-Agent": fingerprint.get("user_agent", ""),
            "Sec-CH-UA": fingerprint.get("sec_ch_ua", ""),
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{fingerprint.get("platform", "")}"',
            "Authorization": f"Bearer {api_key}",
        }
        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    # Requires API key
    client = Cerebras(api_key="csk-***************************")
    response = client.chat.completions.create(
        model="qwen-3-235b-a22b-instruct-2507",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        max_tokens=1000,
        stream=False,
    )
    if isinstance(response, ChatCompletion):
        if response.choices[0].message and response.choices[0].message.content:
            print(response.choices[0].message.content)
