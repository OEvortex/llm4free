import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi import requests

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
    def __init__(self, client: "Zenmux"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = 1024,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        tools: Optional[List[Union[Dict[str, Any], Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        payload: Dict[str, Any] = {
            "messages": messages,
            "model": model,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if tools:
            payload["tools"] = self.format_tool_calls(tools)
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
                if not line:
                    continue
                if isinstance(line, bytes):
                    try:
                        line = line.decode("utf-8")
                    except Exception:
                        continue
                if line.startswith("data: "):
                    json_str = line[6:]
                else:
                    json_str = line
                if json_str == "[DONE]":
                    break
                try:
                    data = json.loads(json_str)
                    choice_data = data.get("choices", [{}])[0]
                    delta_data = choice_data.get("delta", {})
                    finish_reason = choice_data.get("finish_reason")
                    usage_data = data.get("usage", {})
                    if usage_data:
                        prompt_tokens = usage_data.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage_data.get("completion_tokens", completion_tokens)
                        total_tokens = usage_data.get("total_tokens", total_tokens)
                    content_piece = None
                    role = None
                    tool_calls = None
                    if delta_data:
                        content_piece = delta_data.get("content") or delta_data.get("text")
                        role = delta_data.get("role")
                        tool_calls = delta_data.get("tool_calls")
                    else:
                        message_d = choice_data.get("message", {})
                        role = message_d.get("role")
                        content_piece = message_d.get("content") or message_d.get("text")
                        tool_calls = message_d.get("tool_calls")
                    if content_piece:
                        completion_tokens += 1
                        total_tokens = prompt_tokens + completion_tokens
                    delta = ChoiceDelta(content=content_piece, role=role, tool_calls=tool_calls)
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
            print(f"Error during Zenmux stream request: {e}")
            raise IOError(f"Zenmux request failed: {e}") from e

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
            print(f"Error during Zenmux non-stream request: {e}")
            raise IOError(f"Zenmux request failed: {e}") from e


class Chat(BaseChat):
    def __init__(self, client: "Zenmux"):
        self.completions = Completions(client)


class Zenmux(OpenAICompatibleProvider):
    required_auth = True
    AVAILABLE_MODELS = [
        "z-ai/glm-4.6v-flash",
    ]

    def __init__(self, browser: str = "chrome", api_key: Optional[str] = None):
        self.timeout = None
        self.base_url = "https://zenmux.ai/api/v1/chat/completions"
        self.session = requests.Session()
        agent = LitAgent()
        fingerprint = agent.generate_fingerprint(browser)
        self.headers = {
            "Accept": fingerprint["accept"],
            "Accept-Language": fingerprint["accept_language"],
            "Content-Type": "application/json",
            "DNT": "1",
            "Origin": "https://zenmux.ai",
            "Referer": "https://zenmux.ai/",
            "Priority": "u=1, i",
            "Sec-CH-UA": fingerprint.get("sec_ch_ua")
            or '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{fingerprint["platform"]}"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Sec-GPC": "1",
            "User-Agent": fingerprint.get("user_agent"),
        }
        if api_key is not None:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.session.headers.update(self.headers)
        self.chat = Chat(self)
        try:
            self.update_available_models(api_key)
        except Exception:
            pass

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            }
            try:
                from curl_cffi.requests import Session as CurlSession

                curl_available = True
            except Exception:
                CurlSession = None
                curl_available = False
            try:
                from llm4free.litagent import LitAgent

                agent = LitAgent()
                fingerprint = agent.generate_fingerprint("chrome")
                headers.update(
                    {
                        "Accept": fingerprint.get("accept", headers["Accept"]),
                        "Accept-Language": fingerprint.get("accept_language", "en-US,en;q=0.9"),
                        "User-Agent": fingerprint.get("user_agent", headers["User-Agent"]),
                        "Sec-CH-UA": fingerprint.get("sec_ch_ua")
                        or '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
                        "Sec-CH-UA-Mobile": "?0",
                        "Sec-CH-UA-Platform": f'"{fingerprint.get("platform", "Windows")}"',
                    }
                )
            except Exception:
                pass
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            if curl_available and CurlSession is not None:
                session = CurlSession()
                response = session.get(
                    "https://zenmux.ai/api/v1/models",
                    headers=headers,
                    impersonate="chrome110",
                    timeout=10,
                )
            else:
                response = requests.get(
                    "https://zenmux.ai/api/v1/models", headers=headers, timeout=10
                )
            if getattr(response, "status_code", None) and response.status_code != 200:
                return cls.AVAILABLE_MODELS
            data = response.json()

            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                parsed = []
                for entry in data["data"]:
                    if isinstance(entry, str):
                        parsed.append(entry)
                    elif isinstance(entry, dict) and "id" in entry and isinstance(entry["id"], str):
                        parsed.append(entry["id"])
                if parsed:
                    return parsed

            def _parse(data_obj):
                models = []
                if isinstance(data_obj, list):
                    for item in data_obj:
                        if isinstance(item, str):
                            models.append(item)
                        elif isinstance(item, dict):
                            for key in ("id", "model", "name"):
                                if key in item and isinstance(item[key], str):
                                    models.append(item[key])
                                    break
                            else:
                                for v in item.values():
                                    if isinstance(v, str):
                                        models.append(v)
                                        break
                elif isinstance(data_obj, dict):
                    for key in ("data", "models", "result"):
                        if key in data_obj:
                            models.extend(_parse(data_obj[key]))
                    for k, v in data_obj.items():
                        if isinstance(v, dict):
                            models.append(k)
                return models

            models = _parse(data)
            models = [m for m in dict.fromkeys(models) if m]
            return models if models else cls.AVAILABLE_MODELS
        except Exception:
            return cls.AVAILABLE_MODELS

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        try:
            models = cls.get_models(api_key)
            if models:
                cls.AVAILABLE_MODELS = models
        except Exception:
            pass

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(self.AVAILABLE_MODELS)
