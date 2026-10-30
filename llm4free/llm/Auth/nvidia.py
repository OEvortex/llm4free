import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, cast

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
    count_tokens,
)


class Completions(BaseCompletions):
    def __init__(self, client: "Nvidia"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 2048,
        stream: bool = False,
        temperature: Optional[float] = 0.7,
        top_p: Optional[float] = 0.9,
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
                proxies=proxies
                impersonate="chrome120",
            )
            response.raise_for_status()

            prompt_tokens = count_tokens(
                [msg.get("content", "") for msg in payload.get("messages", [])]
            )
            completion_tokens = 0
            total_tokens = 0

            # Manual parsing similar to DeepInfra/Groq OpenAI compatible providers
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

                            content = delta_data.get("content")
                            if content:
                                completion_tokens += count_tokens(content)
                                total_tokens = prompt_tokens + completion_tokens

                            delta = ChoiceDelta(
                                content=content,
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
            raise IOError(f"Nvidia stream request failed: {e}") from e

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
                proxies=proxies
                impersonate="chrome120",
            )
            response.raise_for_status()
            data = response.json()

            choices_data = data.get("choices", [])
            usage_data = data.get("usage", {})

            choices = []
            for choice_d in choices_data:
                message_d = choice_d.get("message", {})
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
                id=data.get("id", request_id),
                choices=choices,
                created=data.get("created", created_time),
                model=data.get("model", model),
                usage=usage,
            )
            return completion
        except Exception as e:
            raise IOError(f"Nvidia non-stream request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Nvidia"):
        self.completions = Completions(client)


class Nvidia(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for Nvidia NIM API.
    """

    required_auth = True
    AVAILABLE_MODELS = []

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Fetch available models from Nvidia API."""
        url = "https://integrate.api.nvidia.com/v1/models"
        try:
            # Use a temporary curl_cffi session for this class method
            temp_session = Session()
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = temp_session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "data" in data:
                    return [model["id"] for model in data["data"] if "id" in model]
            return cls.AVAILABLE_MODELS
        except Exception:
            return cls.AVAILABLE_MODELS

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        """Update the available models list from Nvidia API dynamically."""
        try:
            models = cls.get_models(api_key)
            if models and len(models) > 0:
                cls.AVAILABLE_MODELS = models
        except Exception:
            # Fallback to default models list if fetching fails
            pass

    def __init__(self, api_key: str, browser: str = "chrome", timeout: int = 30):
        if not api_key:
            raise ValueError("API key is required for Nvidia")

        # Start background model fetch (non-blocking)
        self._start_background_model_fetch(api_key)

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.session = Session()

        if LitAgent:
            agent = LitAgent()
            fingerprint = agent.generate_fingerprint(browser)
        else:
            fingerprint = {
                "accept_language": "en-US,en;q=0.9",
                "user_agent": LitAgent().random(),
            }

        self.headers = {
            "Accept": "application/json",
            "Accept-Language": fingerprint["accept_language"],
            "Content-Type": "application/json",
            "User-Agent": fingerprint.get("user_agent", ""),
            "Authorization": f"Bearer {api_key}",
        }
        self.session.headers.update(self.headers)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    # Example usage:
    # client = Nvidia(api_key="nvapi-...")
    # response = client.chat.completions.create(
    #     model="meta/llama-3.3-70b-instruct",
    #     messages=[{"role": "user", "content": "Hello!"}]
    # )
    # if isinstance(response, ChatCompletion):
    #     if response.choices[0].message and response.choices[0].message.content:
    #         print(response.choices[0].message.content)
    pass
