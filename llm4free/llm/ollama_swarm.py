"""
OllamaSwarm — OpenAI-compatible variant.

Self-contained Ollama swarm discovery + OpenAI-compatible chat interface.

Usage::

    from llm4free.llm.ollama_swarm import OllamaSwarm
    client = OllamaSwarm()
    resp = client.chat.completions.create(
        model="qwen3:14b",
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
    "http://117.50.171.144:11434",
    "http://133.4.188.2:11434",
    "http://136.243.60.49:11434",
    "http://152.53.93.215:11434",
    "http://158.101.214.195:11434",
    "http://163.172.212.132:11434",
    "http://165.1.76.13:11434",
    "http://168.235.74.31:11434",
    "http://193.237.153.60:11434",
    "http://193.237.205.200:11434",
    "http://199.79.202.22:11434",
    "http://2.59.170.202:11434",
    "http://20.246.91.177:11434",
    "http://210.59.176.82:11434",
    "http://211.23.87.144:11434",
    "http://213.136.76.182:11434",
    "http://220.135.48.55:11434",
    "http://31.70.86.211:11434",
    "http://38.180.104.127:11434",
    "http://45.145.42.104:11434",
    "http://47.79.39.175:11434",
    "http://51.178.49.219:11434",
    "http://52.201.213.145:11434",
    "http://54.36.111.107:11434",
    "http://57.128.123.135:11434",
    "http://62.45.168.106:11434",
    "http://64.156.70.180:11434",
    "http://64.176.39.95:11434",
    "http://82.135.28.45:11434",
    "http://82.165.174.61:11434",
    "http://83.86.59.188:11434",
    "http://84.22.103.64:11434",
    "http://85.214.43.150:11434",
    "http://85.214.44.11:11434",
    "http://90.149.239.71:11434",
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
    """Probe a server for available models using /v1/models or /api/tags."""
    with requests.Session() as s:
        try:
            # Try OpenAI-compatible /v1/models endpoint first
            r = s.get(f"{url}/v1/models", timeout=_PROBE_TIMEOUT)
            if r.ok:
                data = r.json()
                models = []
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if (
                        model_id
                        and "/attacker/" not in model_id
                        and not model_id.startswith("model-b")
                    ):
                        models.append(model_id)
                if models:
                    return url, models
        except Exception:
            pass

        try:
            # Fallback to Ollama-native /api/tags endpoint
            r = s.get(f"{url}/api/tags", timeout=_PROBE_TIMEOUT)
            r.raise_for_status()
            models = [
                m.get("name", "")
                for m in r.json().get("models", [])
                if "/attacker/" not in m.get("name", "") and not m.get("name", "").startswith("model-b")
            ]
            if models:
                return url, models
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
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        model = self._client.convert_model_name(model)
        prompt = self._client._last_user_text(messages)
        request_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_time = int(time.time())
        if stream:
            return self._create_stream(request_id, created_time, model, prompt, timeout, proxies)
        return self._create_non_stream(request_id, created_time, model, prompt, timeout, proxies)

    def _post_to(self, server_url: str, model: str, prompt: str, timeout: int):
        url = f"{server_url}/v1/chat/completions"
        return self._client.session.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
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
        prompt: str,
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> Generator[ChatCompletionChunk, None, None]:
        completion_tokens = 0
        finish_reason = None

        yielded = False
        for server_url in self._client.servers_for(model):
            try:
                response = self._post_to(server_url, model, prompt, timeout or self._client.timeout)
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
        prompt: str,
        timeout: Optional[int],
        proxies: Optional[Dict[str, str]],
    ) -> ChatCompletion:
        full_text = ""
        yielded = False
        for server_url in self._client.servers_for(model):
            try:
                response = self._post_to(server_url, model, prompt, timeout or self._client.timeout)
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
            prompt_tokens = self._client._safe_count(prompt)
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
        if not model:
            return next(iter(self._model_to_servers), "*")
        if model in self._model_to_servers or "*" in self._model_to_servers:
            return model
        return model

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
    for _m in ["beam:cloud", "tinyllama:latest", "qwen2.5:0.5b"]:
        try:
            response = client.chat.completions.create(
                model=_m,
                messages=[{"role": "user", "content": "Tell me a joke"}],
            )
            if isinstance(response, ChatCompletion):
                message = response.choices[0].message
                print(_m, "->", (message.content if message and message.content else "")[:80])
        except Exception as e:
            print(_m, "ERR", e)
