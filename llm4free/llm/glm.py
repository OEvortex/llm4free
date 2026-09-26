"""OpenAI-compatible provider for anonymous GLM chat on z.ai."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union, cast
from urllib.parse import urlencode

from curl_cffi import requests

from llm4free.browser_requests.cdp import CDPSession, find_agent_browser
from llm4free.llm.base import BaseChat, BaseCompletions, OpenAICompatibleProvider, SimpleModelList
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    count_tokens,
)

GLM_BASE_URL = "https://chat.z.ai"
GLM_AUTH_URL = f"{GLM_BASE_URL}/api/v1/auths/"
GLM_MODELS_URL = f"{GLM_BASE_URL}/api/models"
GLM_CHAT_URL = f"{GLM_BASE_URL}/api/v2/chat/completions"
GLM_NEW_CHAT_URL = f"{GLM_BASE_URL}/api/v1/chats/new"
GLM_FE_VERSION = "prod-fe-1.1.69"
GLM_QUERY_VERSION = "0.0.1"
GLM_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
GLM_DEFAULT_MODEL = "GLM-5.3-Flash"
GLM_MAX_CAPTCHA_RETRIES = 2
AVAILABLE_MODELS = [
    "GLM-5.3-Flash",
    "GLM-5.3",
    "GLM-5.2",
    "GLM-5-Turbo",
    "GLM-5V-Turbo",
    "GLM-4.7",
    "GLM-4.6V",
    "GLM-4.5-Air",
    "GLM-4.5",
    "GLM-4.1V-9B-Thinking",
    "Z1-Rumination",
    "Z1-32B",
    "GLM-4-32B",
]
MODEL_IDS = {
    "GLM-5.3-Flash": "x-preview-l",
    "GLM-5.3": "glm-5.3",
    "GLM-5.2": "glm-5.2",
    "GLM-5-Turbo": "GLM-5-Turbo",
    "GLM-5V-Turbo": "GLM-5v-Turbo",
    "GLM-4.7": "glm-4.7",
    "GLM-4.6V": "glm-4.6v",
    "GLM-4.5-Air": "0727-106B-API",
    "GLM-4.5": "0727-360B-API",
    "GLM-4.1V-9B-Thinking": "GLM-4.1V-Thinking-FlashX",
    "Z1-Rumination": "deep-research",
    "Z1-32B": "zero",
    "GLM-4-32B": "glm-4-air-250414",
}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# ── Aliyun captcha recovery ──────────────────────────────────────────────

CAPTCHA_CONFIG = {"region": "sgp", "prefix": "no8xfe", "sceneId": "didk33e0"}
CAPTCHA_TOKEN_TTL_SECONDS = 45
CAPTCHA_SOLVE_RETRIES = 3
CAPTCHA_SDK_PATH = Path(__file__).with_name("AliyunCaptcha.js.txt")
CAPTCHA_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}, loadTimes: () => ({}), csi: () => ({}), app: {}};
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
"""
_captcha_token: Optional[str] = None
_captcha_token_expires_at = 0.0
_captcha_solve_lock: Optional[asyncio.Lock] = None


def _captcha_is_available() -> bool:
    """Return whether agent-browser and the bundled captcha SDK are available."""
    try:
        find_agent_browser()
    except RuntimeError:
        return False
    return CAPTCHA_SDK_PATH.is_file()


def _get_captcha_solve_lock() -> asyncio.Lock:
    """Return the process-wide lock used to serialize captcha solves."""
    global _captcha_solve_lock
    if _captcha_solve_lock is None:
        _captcha_solve_lock = asyncio.Lock()
    return _captcha_solve_lock


def invalidate_captcha_token() -> None:
    """Discard the cached captcha token after a server rejection."""
    global _captcha_token, _captcha_token_expires_at
    _captcha_token = None
    _captcha_token_expires_at = 0.0


async def _solve_captcha_once(headless: bool = True) -> str:
    """Solve one Aliyun challenge in a browser page served on the z.ai origin."""
    if not CAPTCHA_SDK_PATH.is_file():
        raise RuntimeError(f"Bundled Aliyun captcha SDK is missing: {CAPTCHA_SDK_PATH}")
    sdk = CAPTCHA_SDK_PATH.read_text(encoding="utf-8")
    session = CDPSession(headless=headless)
    init_script = tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", encoding="utf-8", delete=False
    )
    try:
        init_script.write(CAPTCHA_STEALTH_SCRIPT)
        init_script.close()
        await session._run("open", "--init-script", init_script.name, timeout=30)
        session._started = True
        await session._run(
            "network",
            "route",
            "https://chat.z.ai/*",
            "--body",
            "<!doctype html><html><head></head><body>"
            '<div id="captcha-element"></div><button id="captcha-button"></button>'
            "</body></html>",
            "--resource-type",
            "document",
            timeout=30,
        )
        await session._run("open", "https://chat.z.ai/", timeout=30)
        await asyncio.sleep(3)
        origin = await session.evaluate_js("location.origin")
        if origin != "https://chat.z.ai":
            raise RuntimeError(f"Unable to establish z.ai origin in captcha browser: {origin}")
        await session.evaluate_js_stdin(sdk)
        config = json.dumps(CAPTCHA_CONFIG)
        expression = f"""
new Promise((resolve, reject) => {{
  const cfg = {config};
  const timeout = setTimeout(() => reject(new Error('Captcha solve timed out')), 40000);
  if (typeof window.initAliyunCaptcha !== 'function') {{
    reject(new Error('Aliyun captcha SDK failed to initialize'));
    return;
  }}
  window.AliyunCaptchaConfig = {{region: cfg.region, prefix: cfg.prefix}};
  window.initAliyunCaptcha({{
    SceneId: cfg.sceneId, mode: 'popup', region: cfg.region, prefix: cfg.prefix,
    language: 'en', element: '#captcha-element', button: '#captcha-button',
    captchaLogoImg: '', showErrorTip: false,
    success: (token) => {{ clearTimeout(timeout); resolve(token); }},
    fail: (error) => {{ clearTimeout(timeout); reject(new Error(JSON.stringify(error))); }},
    getInstance: (instance) => instance.startTracelessVerification()
  }});
}})
"""
        token = await session.evaluate_js(expression)
        if not isinstance(token, str) or not token:
            raise RuntimeError(f"Aliyun captcha returned an invalid token: {token!r}")
        return token
    finally:
        await session.close()
        Path(init_script.name).unlink(missing_ok=True)


async def _get_captcha_verify_param_async() -> str:
    """Return a cached token or solve a fresh captcha challenge."""
    global _captcha_token, _captcha_token_expires_at
    if _captcha_token and _captcha_token_expires_at > time.time():
        return _captcha_token
    async with _get_captcha_solve_lock():
        if _captcha_token and _captcha_token_expires_at > time.time():
            return _captcha_token
        if not _captcha_is_available():
            raise RuntimeError(
                "GLM requires captcha verification. Install agent-browser with: "
                "npm i -g agent-browser && agent-browser install"
            )
        last_error: Optional[Exception] = None
        for attempt in range(1, CAPTCHA_SOLVE_RETRIES + 1):
            try:
                token = await _solve_captcha_once(headless=attempt > 1)
                _captcha_token = token
                _captcha_token_expires_at = time.time() + CAPTCHA_TOKEN_TTL_SECONDS
                return token
            except Exception as error:
                last_error = error
                if attempt < CAPTCHA_SOLVE_RETRIES:
                    await asyncio.sleep(attempt)
        raise RuntimeError(
            f"GLM captcha solving failed after {CAPTCHA_SOLVE_RETRIES} attempts: {last_error}"
        )


def get_captcha_verify_param() -> str:
    """Return a cached or newly solved Aliyun captcha token."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_get_captcha_verify_param_async())
    raise RuntimeError("GLM captcha solving cannot be called from an active event loop")


class CaptchaRequiredError(RuntimeError):
    """Raised when z.ai requires an Aliyun captcha verification token."""


class _StreamEvent:
    """Normalized event emitted by the z.ai SSE parser."""

    def __init__(
        self,
        kind: str,
        value: str = "",
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.kind = kind
        self.value = value
        self.usage = usage


class Completions(BaseCompletions):
    """OpenAI-compatible chat completions for z.ai GLM."""

    def __init__(self, client: "GLM") -> None:
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
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """Create a GLM completion using the OpenAI-compatible interface."""
        del max_tokens, temperature, top_p
        if not messages:
            raise ValueError("GLM requires at least one message")
        if proxies:
            self._client.session.proxies.update(cast(Any, proxies))
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created = int(time.time())
        options: Dict[str, Any] = {
            "model": self._client.resolve_model(model),
            "requested_model": model,
            "messages": messages,
            "timeout": timeout,
            "web_search": bool(kwargs.get("web_search", False)),
            "reasoning_effort": kwargs.get("reasoning_effort"),
        }
        if stream:
            return self._stream(request_id, created, options)
        return self._complete(request_id, created, options)

    def _complete(self, request_id: str, created: int, options: Dict[str, Any]) -> ChatCompletion:
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        usage_data: Optional[Dict[str, Any]] = None
        for event in self._client.iter_events(**options):
            if event.kind == "content":
                content_parts.append(event.value)
            elif event.kind == "reasoning":
                reasoning_parts.append(event.value)
            elif event.kind == "usage" and event.usage:
                usage_data = event.usage
        content = "".join(content_parts)
        message = ChatCompletionMessage(
            role="assistant",
            content=content,
            reasoning_content="".join(reasoning_parts) or None,
        )
        choice = Choice(index=0, message=message, finish_reason="stop")
        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created,
            model=options["requested_model"],
            usage=self._client.build_usage(options["messages"], content, usage_data),
        )

    def _stream(
        self,
        request_id: str,
        created: int,
        options: Dict[str, Any],
    ) -> Generator[ChatCompletionChunk, None, None]:
        for event in self._client.iter_events(**options):
            if event.kind == "usage" and event.usage:
                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[],
                    created=created,
                    model=options["requested_model"],
                    usage=event.usage,
                )
                continue
            if event.kind not in ("content", "reasoning"):
                continue
            delta = ChoiceDelta(
                content=event.value if event.kind == "content" else None,
                reasoning_content=event.value if event.kind == "reasoning" else None,
            )
            yield ChatCompletionChunk(
                id=request_id,
                choices=[Choice(index=0, delta=delta, finish_reason=None)],
                created=created,
                model=options["requested_model"],
            )
        yield ChatCompletionChunk(
            id=request_id,
            choices=[Choice(index=0, delta=ChoiceDelta(), finish_reason="stop")],
            created=created,
            model=options["requested_model"],
        )


class Chat(BaseChat):
    def __init__(self, client: "GLM") -> None:
        self.completions = Completions(client)


class GLM(OpenAICompatibleProvider):
    """OpenAI-compatible client for anonymous GLM models at chat.z.ai."""

    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(self, timeout: int = 60, proxies: Optional[Dict[str, str]] = None) -> None:
        super().__init__(api_key=None, proxies=proxies)
        self.timeout = timeout
        self.api_endpoint = GLM_CHAT_URL
        self.session = requests.Session(impersonate="chrome")
        self.session.proxies.update(cast(Any, self.proxies))
        self._token: Optional[str] = None
        self._user_id = ""
        self._user_name = "User"
        self._model_map = dict(MODEL_IDS)
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    @staticmethod
    def _compute_signature(request_id: str, timestamp: str, user_id: str) -> str:
        params = {"requestId": request_id, "timestamp": timestamp, "user_id": user_id}
        source = ",".join(f"{key}={params[key]}" for key in sorted(params))
        return hmac.new(b"", source.encode(), hashlib.sha256).hexdigest()

    def _build_url_params(self) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        now = datetime.now().astimezone()
        offset_value = now.utcoffset()
        offset = offset_value.total_seconds() if offset_value is not None else 0
        return {
            "timestamp": timestamp,
            "requestId": str(uuid.uuid4()),
            "user_id": self._user_id,
            "version": GLM_QUERY_VERSION,
            "platform": "web",
            "token": self._token or "",
            "user_agent": GLM_USER_AGENT,
            "language": "en-US",
            "languages": "en-US,en",
            "timezone": "Africa/Cairo",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "screen_resolution": "1920x1080",
            "viewport_height": "947",
            "viewport_width": "1920",
            "viewport_size": "1920x1080",
            "color_depth": "30",
            "pixel_ratio": "1",
            "current_url": f"{GLM_BASE_URL}/",
            "pathname": "/",
            "host": "chat.z.ai",
            "hostname": "chat.z.ai",
            "protocol": "https:",
            "search": "",
            "hash": "",
            "referrer": "",
            "title": "",
            "timezone_offset": str(-int(offset // 60)),
            "local_time": now.strftime("%m/%d/%Y, %I:%M:%S %p"),
            "utc_time": datetime.now(timezone.utc).isoformat(),
            "is_mobile": "false",
            "is_touch": "false",
            "max_touch_points": "0",
            "browser_name": "chrome",
            "os_name": "linux",
            "signature_timestamp": timestamp,
        }

    @staticmethod
    def _build_variables(user_name: str) -> Dict[str, str]:
        now = datetime.now().astimezone()
        return {
            "{{USER_NAME}}": user_name or "User",
            "{{USER_LOCATION}}": "Unknown",
            "{{CURRENT_DATETIME}}": now.strftime("%Y-%m-%d %H:%M:%S"),
            "{{CURRENT_DATE}}": now.strftime("%Y-%m-%d"),
            "{{CURRENT_TIME}}": now.strftime("%H:%M:%S"),
            "{{CURRENT_WEEKDAY}}": WEEKDAYS[now.weekday()],
            "{{CURRENT_TIMEZONE}}": "Africa/Cairo",
            "{{USER_LANGUAGE}}": "en-US",
        }

    def _build_headers(self, signature: str) -> Dict[str, str]:
        return {
            "authorization": f"Bearer {self._token}",
            "content-type": "application/json",
            "accept-language": "en-US",
            "x-fe-version": GLM_FE_VERSION,
            "referer": "",
            "user-agent": GLM_USER_AGENT,
            "x-region": "overseas",
            "accept": "*/*",
            "x-signature": signature,
            "origin": GLM_BASE_URL,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
        }

    def _ensure_auth(self, timeout: int) -> None:
        if self._token:
            return
        response = self.session.get(GLM_AUTH_URL, timeout=timeout, impersonate="chrome")
        if response.status_code != 200:
            raise RuntimeError(f"GLM authentication failed with HTTP {response.status_code}")
        data = response.json()
        self._token = data.get("token")
        if not self._token:
            raise RuntimeError("GLM authentication response did not include a token")
        self._user_id = str(data.get("id", ""))
        self._user_name = data.get("name") or data.get("nickname") or "User"
        self._refresh_models(timeout)

    def _refresh_models(self, timeout: int) -> None:
        response = self.session.get(
            GLM_MODELS_URL,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=timeout,
            impersonate="chrome",
        )
        if response.status_code != 200:
            return
        discovered: Dict[str, str] = {}
        for item in response.json().get("data", []):
            name, model_id = item.get("name"), item.get("id")
            if isinstance(name, str) and isinstance(model_id, str):
                discovered[name] = model_id
        if discovered:
            self._model_map = discovered
            type(self).AVAILABLE_MODELS = list(discovered)

    def resolve_model(self, model: str) -> str:
        """Resolve a public model name, case-insensitive name, or upstream model ID."""
        self._ensure_auth(self.timeout)
        if model in self._model_map:
            return self._model_map[model]
        for name, model_id in self._model_map.items():
            if model.lower() in (name.lower(), model_id.lower()):
                return model_id
        return self._model_map.get(GLM_DEFAULT_MODEL, "x-preview-l")

    def _create_chat(self, model: str, timeout: int) -> str:
        chat_id = str(uuid.uuid4())
        is_glm5 = "glm-5" in model.lower()
        payload = {
            "chat": {
                "id": chat_id,
                "title": "New Chat",
                "models": [model],
                "params": {},
                "history": {"messages": {}, "currentId": None},
                "tags": [],
                "flags": [],
                "features": [],
                "mcp_servers": [],
                "enable_thinking": is_glm5 or "glm-4" in model.lower(),
                "reasoning_effort": "max" if is_glm5 else "",
                "auto_web_search": False,
                "message_version": 1,
                "extra": {},
                "timestamp": int(time.time() * 1000),
                "type": "default",
            }
        }
        response = self.session.post(
            GLM_NEW_CHAT_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            timeout=timeout,
            impersonate="chrome",
        )
        if response.status_code != 200:
            raise RuntimeError(f"GLM chat creation failed with HTTP {response.status_code}")
        data = response.json()
        return data.get("id") or data.get("chat", {}).get("id") or chat_id

    def _build_completion_payload(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        web_search: bool,
        reasoning_effort: Optional[str],
        captcha_token: str,
    ) -> Dict[str, Any]:
        prompt = "\n".join(
            str(message.get("content", ""))
            for message in messages
            if isinstance(message.get("content"), str)
        )[:500]
        is_glm5 = "glm-5" in model.lower()
        return {
            "stream": True,
            "model": model,
            "messages": messages,
            "signature_prompt": prompt,
            "params": {},
            "extra": {},
            "variables": self._build_variables(self._user_name),
            "chat_id": self._create_chat(model, self.timeout),
            "id": str(uuid.uuid4()),
            "current_user_message_id": str(uuid.uuid4()),
            "current_user_message_parent_id": None,
            "background_tasks": {"title_generation": True, "tags_generation": True},
            "captcha_verify_param": captcha_token,
            "features": {
                "image_generation": False,
                "web_search": web_search,
                "auto_web_search": False,
                "preview_mode": True,
                "flags": [],
                "vlm_tools_enable": False,
                "vlm_web_search_enable": False,
                "vlm_website_mode": False,
                "enable_thinking": bool(reasoning_effort and reasoning_effort != "none"),
                "reasoning_effort": "max" if is_glm5 else "",
            },
        }

    def _post_completion(self, payload: Dict[str, Any], timeout: int) -> requests.Response:
        params = self._build_url_params()
        signature = self._compute_signature(
            params["requestId"],
            params["timestamp"],
            self._user_id,
        )
        response = self.session.post(
            f"{GLM_CHAT_URL}?{urlencode(params)}",
            data=json.dumps(payload, separators=(",", ":")),
            headers=self._build_headers(signature),
            stream=True,
            timeout=timeout,
            impersonate="chrome",
        )
        if response.status_code >= 400:
            detail = response.text[:1000]
            if response.status_code == 403 and "captcha" in detail.lower():
                raise CaptchaRequiredError(detail)
            raise RuntimeError(f"GLM completion failed with HTTP {response.status_code}: {detail}")
        return response

    def iter_events(
        self,
        *,
        model: str,
        requested_model: str,
        messages: List[Dict[str, Any]],
        timeout: Optional[int],
        web_search: bool,
        reasoning_effort: Optional[str],
    ) -> Generator[_StreamEvent, None, None]:
        """Yield normalized content, reasoning, and usage events."""
        del requested_model
        effective_timeout = timeout or self.timeout
        self._ensure_auth(effective_timeout)
        resolved = self.resolve_model(model)
        captcha_token = ""
        for attempt in range(GLM_MAX_CAPTCHA_RETRIES + 1):
            payload = self._build_completion_payload(
                resolved,
                messages,
                web_search,
                reasoning_effort,
                captcha_token,
            )
            try:
                response = self._post_completion(payload, effective_timeout)
                yield from self._parse_stream(response)
                return
            except CaptchaRequiredError:
                if attempt >= GLM_MAX_CAPTCHA_RETRIES:
                    raise RuntimeError("GLM captcha verification failed after 3 attempts")
                invalidate_captcha_token()
                captcha_token = get_captcha_verify_param()

    @staticmethod
    def _parse_stream(response: requests.Response) -> Generator[_StreamEvent, None, None]:
        for raw_line in response.iter_lines():
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            line = str(raw_line).strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "chat:completion":
                continue
            data = event.get("data", {})
            error = data.get("error")
            if error:
                code = str(error.get("code") or error.get("error_code") or "")
                if "CAPTCHA" in code.upper():
                    raise CaptchaRequiredError(str(error.get("detail") or code))
                raise RuntimeError(f"GLM stream error: {json.dumps(error)}")
            phase = data.get("phase", "")
            delta = data.get("delta_content", "")
            if phase == "thinking" and delta:
                cleaned = str(delta).split("</summary>\n>")[-1]
                if cleaned:
                    yield _StreamEvent("reasoning", cleaned)
            elif phase == "answer":
                edit_content = data.get("edit_content")
                if edit_content:
                    content = str(edit_content).split("\n</details>\n")[-1]
                else:
                    content = str(delta)
                if content:
                    yield _StreamEvent("content", content)
            elif phase == "other" and data.get("usage"):
                yield _StreamEvent("usage", usage=data["usage"])
            elif phase == "done":
                return

    @staticmethod
    def build_usage(
        messages: List[Dict[str, Any]],
        content: str,
        usage_data: Optional[Dict[str, Any]],
    ) -> CompletionUsage:
        try:
            prompt_count = count_tokens(messages)
        except ModuleNotFoundError:
            prompt_count = sum(len(str(message.get("content", ""))) // 4 for message in messages)
        try:
            completion_count = count_tokens(content)
        except ModuleNotFoundError:
            completion_count = len(content) // 4
        prompt_tokens = int((usage_data or {}).get("prompt_tokens") or prompt_count)
        completion_tokens = int((usage_data or {}).get("completion_tokens") or completion_count)
        total_tokens = int(
            (usage_data or {}).get("total_tokens") or (prompt_tokens + completion_tokens)
        )
        return CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


if __name__ == "__main__":
    client = GLM()
    result = client.chat.completions.create(
        model=GLM_DEFAULT_MODEL,
        messages=[{"role": "user", "content": "Say hello in one word."}],
        stream=False,
    )
    if isinstance(result, ChatCompletion) and result.choices[0].message:
        print(result.choices[0].message.content)
