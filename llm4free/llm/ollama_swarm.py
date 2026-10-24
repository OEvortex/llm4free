"""
OllamaSwarm — OpenAI-compatible variant.

Self-contained Ollama swarm discovery + OpenAI-compatible chat interface.

Usage::

    from llm4free.llm.ollama_swarm import OllamaSwarm
    client = OllamaSwarm()
    resp = client.chat.completions.create(
        model="beam:cloud",
        messages=[{"role": "user", "content": "Tell me a joke"}],
    )
    print(resp.choices[0].message.content)
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import requests
from requests import RequestException

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

BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"

DEFAULT_TTFT_TIMEOUT = 10.0

_DEFAULT_SEED_SERVERS: List[str] = [
    "http://116.203.177.162:11434",
    "http://193.237.205.200:11434",
    "http://117.50.171.144:11434",
]

_FOFA_API = "https://fofa.info/api/v1/search/all"
_FOFA_QUERY = 'port="11434" && body="Ollama"'
_FOFA_FIELDS = "ip,port"
_PROBE_TIMEOUT = 5
_PROBE_WORKERS = 20


def _cache_dir() -> Path:
    p = Path.home() / ".cache" / "llm4free" / "ollama_swarm" / date.today().strftime("%Y-%m-%d")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _seed_file() -> Path:
    return _cache_dir().parent / "user_servers.json"


def _models_cache_file() -> Path:
    return _cache_dir() / "models.json"


def _get_candidate_servers(seed_servers: Optional[List[str]] = None) -> List[str]:
    seeds: List[str] = (
        list(seed_servers) if seed_servers is not None else list(_DEFAULT_SEED_SERVERS)
    )
    user = _seed_file()
    if user.exists():
        try:
            with open(user, "r") as f:
                extra = json.load(f)
            if isinstance(extra, list):
                seeds.extend(extra)
        except Exception:
            pass
    return seeds


def _fofa_discover(max_results: int = 50) -> List[str]:
    email = os.environ.get("FOFA_EMAIL", "")
    key = os.environ.get("FOFA_KEY", "")
    if not email or not key:
        return []
    try:
        qbase64 = base64.b64encode(_FOFA_QUERY.encode()).decode()
        params = {
            "email": email,
            "key": key,
            "qbase64": qbase64,
            "page": 1,
            "size": min(max_results, 100),
            "fields": _FOFA_FIELDS,
        }
        with requests.Session() as s:
            r = s.get(_FOFA_API, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            return []
        results = data.get("results", [])
        endpoints: List[str] = []
        for item in results:
            if isinstance(item, list) and len(item) >= 2:
                ip, port = item[0], item[1]
                endpoints.append(f"http://{ip}:{port}")
            elif isinstance(item, dict):
                ip = item.get("ip", "")
                port = item.get("port", 11434)
                if ip:
                    endpoints.append(f"http://{ip}:{port}")
        return endpoints
    except Exception:
        return []


def _probe_server(url: str) -> Optional[Tuple[str, List[str]]]:
    """Probe a server for available beam model."""
    with requests.Session() as s:
        try:
            # Check OpenAI-compatible /v1/models endpoint
            r = s.get(f"{url}/v1/models", timeout=_PROBE_TIMEOUT)
            if r.ok:
                data = r.json()
                models = [
                    m.get("id", "")
                    for m in data.get("data", [])
                    if m.get("id") in ("beam:cloud", "beam")
                ]
                if models:
                    return url, ["beam:cloud"]
        except Exception:
            pass

        try:
            # Fallback to Ollama-native /api/tags endpoint
            r = s.get(f"{url}/api/tags", timeout=_PROBE_TIMEOUT)
            if r.ok:
                models = [
                    m.get("name", "")
                    for m in r.json().get("models", [])
                    if m.get("name") in ("beam:cloud", "beam")
                ]
                if models:
                    return url, ["beam:cloud"]
        except Exception:
            return None
    return None


def discover_servers(seed_servers: Optional[List[str]] = None) -> Dict[str, List[str]]:
    cached = _models_cache_file()
    if cached.exists():
        try:
            with open(cached, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass

    candidates: List[str] = _get_candidate_servers(seed_servers)
    for url in _fofa_discover():
        if url not in candidates:
            candidates.append(url)

    alive: Dict[str, List[str]] = {}
    with ThreadPoolExecutor(max_workers=_PROBE_WORKERS) as pool:
        futures = {pool.submit(_probe_server, url): url for url in candidates}
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                url, models = res
                alive[url] = models

    if alive:
        try:
            with open(cached, "w") as f:
                json.dump(alive, f)
        except Exception:
            pass

    return alive


def build_model_index(servers: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for server, models in servers.items():
        for m in models:
            out.setdefault(m, []).append(server)
    return out


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class Completions(BaseCompletions):
    def __init__(self, client: "OllamaSwarm"):
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
        model = self._client.convert_model_name(model)
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())
        if stream:
            return self._create_stream(request_id, created_time, model, messages, timeout, proxies)
        return self._create_non_stream(request_id, created_time, model, messages, timeout, proxies)

    def _post_to(self, server_url: str, model: str, messages: List[Dict[str, Any]], timeout: int):
        url = f"{server_url}/v1/chat/completions"
        return self._client.session.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                **({"max_tokens": self._client.max_tokens} if self._client.max_tokens else {}),
            },
            stream=True,
            timeout=timeout or self._client.timeout,
        )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> Generator[ChatCompletionChunk, None, None]:
        completion_tokens = 0
        finish_reason = None

        yielded = False
        for server_url in self._client.servers_for(model):
            try:
                response = self._post_to(server_url, model, messages, timeout or self._client.timeout)
                if not response.ok:
                    continue
            except (RequestException, Exception):
                continue

            try:
                for raw_line in response.iter_lines():
                    if raw_line is None:
                        continue
                    if isinstance(raw_line, bytes):
                        raw_line = raw_line.decode("utf-8", errors="replace")
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload_str = line[5:].strip()
                    if payload_str in ("[DONE]", ""):
                        if completion_tokens:
                            break
                        continue
                    try:
                        evt = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue

                    choice = (evt.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    finish = choice.get("finish_reason")

                    if text:
                        completion_tokens += self._client._safe_count(text)
                        chunk = ChoiceDelta(content=text, role="assistant", tool_calls=None)
                        ch = Choice(index=0, delta=chunk, finish_reason=None, logprobs=None)
                        c = ChatCompletionChunk(
                            id=request_id,
                            choices=[ch],
                            created=created_time,
                            model=model,
                            system_fingerprint=None,
                        )
                        yielded = True
                        yield c
                    elif finish and finish not in (None, "null"):
                        finish_reason = finish
                        break

                self._client._promote(model, server_url)
                if finish_reason is None:
                    finish_reason = "stop"
                delta = ChoiceDelta(content=None, role=None, tool_calls=None)
                ch = Choice(index=0, delta=delta, finish_reason=finish_reason, logprobs=None)
                stop_chunk = ChatCompletionChunk(
                    id=request_id,
                    choices=[ch],
                    created=created_time,
                    model=model,
                    system_fingerprint=None,
                )
                yield stop_chunk
                return

            except (RequestException, Exception):
                if yielded:
                    raise
                continue

        raise IOError(f"OllamaSwarm: no server in the swarm accepted model {model!r}")

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> ChatCompletion:
        full_text = ""
        yielded = False
        for server_url in self._client.servers_for(model):
            try:
                response = self._post_to(server_url, model, messages, timeout or self._client.timeout)
                if not response.ok:
                    continue
            except (RequestException, Exception):
                continue

            try:
                for raw_line in response.iter_lines():
                    if raw_line is None:
                        continue
                    if isinstance(raw_line, bytes):
                        raw_line = raw_line.decode("utf-8", errors="replace")
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload_str = line[5:].strip()
                    if payload_str in ("[DONE]", ""):
                        if full_text:
                            break
                        continue
                    try:
                        evt = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    choice = (evt.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        full_text += text
                        yielded = True
                    finish = choice.get("finish_reason")
                    if finish and finish not in (None, "null"):
                        break
            except Exception:
                if yielded:
                    raise
                continue

            self._client._promote(model, server_url)
            prompt_tokens = sum(
                self._client._safe_count(str(m.get("content", ""))) for m in messages
            )
            completion_tokens = self._client._safe_count(full_text)
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            message = ChatCompletionMessage(role="assistant", content=full_text)
            choice = Choice(index=0, message=message, finish_reason="stop", logprobs=None)
            return ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
                system_fingerprint=None,
            )

        raise IOError(f"OllamaSwarm: no server in the swarm accepted model {model!r}")


class Chat(BaseChat):
    def __init__(self, client: "OllamaSwarm"):
        self.completions = Completions(client)


class OllamaSwarm(OpenAICompatibleProvider):
    required_auth = False

    def __init__(
        self,
        timeout: int = 60,
        seed_servers: Optional[List[str]] = None,
        skip_discovery: bool = False,
    ):
        self.timeout = timeout
        self.proxies: Optional[Dict[str, str]] = None
        if skip_discovery:
            assert seed_servers, "skip_discovery=True requires an explicit seed_servers=[...] list"
            self._servers: Dict[str, List[str]] = {s: ["*"] for s in seed_servers}
        else:
            self._servers = discover_servers(seed_servers=seed_servers)
        self._model_to_servers: Dict[str, List[str]] = build_model_index(self._servers)
        if not self._model_to_servers and seed_servers:
            self._servers = {s: ["*"] for s in seed_servers}
            self._model_to_servers = {"*": list(seed_servers)}

        self.session = requests.Session()
        self.max_tokens: Optional[int] = None
        self.chat = Chat(self)

    def convert_model_name(self, model: str) -> str:
        return "beam:cloud"

    @staticmethod
    def _last_user_text(messages: List[Dict[str, str]]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    def servers_for(self, model: str) -> List[str]:
        return list(self._model_to_servers.get(model) or self._model_to_servers.get("*") or [])

    def _promote(self, model: str, server_url: str) -> None:
        if model in self._model_to_servers:
            self._model_to_servers[model] = [server_url] + [
                s for s in self._model_to_servers[model] if s != server_url
            ]

    def _safe_count(self, text: str) -> int:
        return _approx_tokens(text)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(list(self._model_to_servers.keys()))


if __name__ == "__main__":
    client = OllamaSwarm()
    response = client.chat.completions.create(
        model="beam:cloud",
        messages=[{"role": "user", "content": "Tell me a joke"}],
    )
    if isinstance(response, ChatCompletion):
        message = response.choices[0].message
        print("beam:cloud ->", message.content if message and message.content else "")
