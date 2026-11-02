import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional

from llm4free.browser_requests.cdp import CDPSession

from llm4free.llm.base import BaseChat, BaseCompletions, OpenAICompatibleProvider, SimpleModelList
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
)

VENICE_BASE_URL = "https://venice.ai/"
CHAT_ENDPOINT = "https://outerface.venice.ai/api/inference/chat/agents/venice"
ATTESTATION_ENDPOINT = "https://outerface.venice.ai/api/app/user/client_attestation/mint"
MODELS_URL = "https://api.venice.ai/api/v1/models"

# Working text chat models from the Venice catalog (authless guest API)
AVAILABLE_MODELS = [
    "zai-org-glm-5",
    "zai-org-glm-5-1",
    "zai-org-glm-5-2",
    "z-ai-glm-5-turbo",
    "z-ai-glm-5-3",
    "z-ai-glm-5-3-flash",
]


_CONSOLE_POLL_JS = (
    "(function(){"
    "var a=window.__llm4free_console||[];"
    "var i=window.__venice_cursor||0;"
    "window.__venice_cursor=a.length;"
    "return a.slice(i).join('\\n');"
    "})()"
)

_EVENT_PREFIX = "VENICE_EVENT:"
_ERROR_PREFIX = "VENICE_ERR:"
_DONE_MARKER = "VENICE_DONE"

# Persistent session
_venice_session = None
_venice_session_lock = threading.Lock()
_venice_initialized = False


def _build_venice_script(messages: List[Dict[str, Any]]) -> str:
    """Build the in-page script to chat via Venice's guest API."""
    venice_messages = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue
        if role in ("user", "assistant"):
            venice_messages.append(
                {
                    "content": [
                        {
                            "annotations": [],
                            "text": content if content is not None else "",
                            "type": "output_text",
                        }
                    ],
                    "id": f"msg_{uuid.uuid4().hex[:12]}",
                    "role": role,
                    "status": "completed",
                    "type": "message",
                }
            )
    
    payload = {
        "clientTools": [
            {
                "description": "Asks the user to approve spending credits on paid usage. Venice calls this itself; never call it.",
                "inputSchema": {"properties": {}, "type": "object"},
                "name": "approve_paid_usage",
            }
        ],
        "input": {"messages": venice_messages},
    }
    
    script = f"""
(async () => {{
  const log = (m) => console.log(m);
  try {{
    // Get attestation
    const attResp = await fetch('{ATTESTATION_ENDPOINT}', {{
      method: 'POST',
      credentials: 'include',
      headers: {{
        'Content-Type': 'application/json',
        'x-venice-version': 'interface@20261101.080644+ab7a027',
        'x-venice-locale': 'en',
        'x-venice-middleface-version': '0.1.1190',
        'x-venice-request-timestamp-ms': Date.now().toString(),
        'Referer': '{VENICE_BASE_URL}'
      }},
      body: JSON.stringify({{"count": 5, "env": {{"nativeIntegrityOk": true, "reactStateHash": "b0447632072f076aa8a159db137c2e7e787cfc3212f58bb72e26611cef138b8b", "sentryVersion": "10.50.0", "unexpectedGlobalsCount": 666, "webdriver": true}}}})
    }});
    let token = null;
    if (attResp.ok) {{
      const attData = await attResp.json();
      if (attData.tokens && attData.tokens.length > 0) token = attData.tokens[0].token;
      else if (attData.token) token = attData.token;
    }}
    
    const headers = {{
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'x-venice-version': 'interface@20261101.080644+ab7a027',
      'x-venice-locale': 'en',
      'x-venice-middleface-version': '0.1.1190',
      'x-venice-request-timestamp-ms': Date.now().toString(),
      'Referer': '{VENICE_BASE_URL}'
    }};
    if (token) headers['x-venice-client-attestation'] = token;
    
    const resp = await fetch('{CHAT_ENDPOINT}', {{
      method: 'POST',
      credentials: 'include',
      headers: headers,
      body: JSON.stringify({json.dumps(payload)})
    }});
    
    if (!resp.ok) {{
      log('{_ERROR_PREFIX}' + resp.status + ' ' + (await resp.text()).slice(0, 300));
      return;
    }}
    
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {{
      const {{done, value}} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {{stream: true}});
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';
      for (const line of lines) {{
        if (line.trim()) log('{_EVENT_PREFIX}' + line);
      }}
    }}
    if (buffer.trim()) log('{_EVENT_PREFIX}' + buffer);
    log('{_DONE_MARKER}');
  }} catch (err) {{
    log('{_ERROR_PREFIX}' + (err && err.stack ? err.stack : String(err)));
  }}
}})();
"""
    return script


async def _wait_for_challenge(session: CDPSession, attempts: int = 15) -> None:
    """Wait for a Cloudflare interstitial to clear."""
    for _ in range(attempts):
        try:
            title = await session.get_title()
        except Exception:
            title = ""
        if "just a moment" not in (title or "").lower() and "cloudflare" not in (title or "").lower():
            return
        try:
            await session.bypass_turnstile()
        except Exception:
            pass
        await asyncio.sleep(1)


async def _ensure_session() -> CDPSession:
    global _venice_session, _venice_initialized
    if _venice_session is not None and _venice_initialized:
        try:
            # Check if session is still alive
            await _venice_session.get_title()
            return _venice_session
        except Exception:
            try:
                await _venice_session.close()
            except Exception:
                pass
            _venice_session = None
            _venice_initialized = False
    
    with _venice_session_lock:
        if _venice_session is not None and _venice_initialized:
            try:
                await _venice_session.get_title()
                return _venice_session
            except Exception:
                try:
                    await _venice_session.close()
                except Exception:
                    pass
                _venice_session = None
                _venice_initialized = False
        
        session = CDPSession(headless=True)
        await session.start()
        await session.navigate(VENICE_BASE_URL)
        await _wait_for_challenge(session)
        await session.install_console_capture()
        await session.evaluate_js("window.__venice_cursor = 0;")
        await session.evaluate_js("window.__llm4free_console = [];")
        _venice_session = session
        _venice_initialized = True
        return session


async def _run_browser(
    messages: List[Dict[str, Any]],
    timeout: int,
    output: "queue.Queue",
) -> None:
    try:
        session = await _ensure_session()
        await session.evaluate_js("window.__venice_cursor = 0;")
        await session.evaluate_js_stdin(_build_venice_script(messages))

        deadline = time.time() + timeout
        current = ""
        while time.time() < deadline:
            try:
                chunk = await session.evaluate_js(_CONSOLE_POLL_JS)
            except Exception:
                await asyncio.sleep(0.5)
                continue
            if isinstance(chunk, str) and chunk:
                for line in chunk.split("\n"):
                    if not line:
                        continue
                    if line.startswith(_ERROR_PREFIX):
                        output.put(("error", line[len(_ERROR_PREFIX) :].strip()))
                        return
                    if line.startswith(_DONE_MARKER):
                        output.put(("done", None))
                        return
                    if not line.startswith(_EVENT_PREFIX):
                        continue
                    raw = line[len(_EVENT_PREFIX) :]
                    if not raw.strip():
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    # Try to extract content
                    content = None
                    if isinstance(data.get("content"), str):
                        content = data["content"]
                    elif isinstance(data.get("delta"), dict):
                        if isinstance(data["delta"].get("content"), str):
                            content = data["delta"]["content"]
                        elif isinstance(data["delta"].get("text"), str):
                            content = data["delta"]["text"]
                    elif isinstance(data.get("output"), dict):
                        out = data["output"]
                        if isinstance(out.get("content"), str):
                            content = out["content"]
                        elif isinstance(out.get("text"), str):
                            content = out["text"]
                        elif isinstance(out.get("message"), dict) and isinstance(out["message"].get("content"), str):
                            content = out["message"]["content"]
                    elif isinstance(data.get("choices"), list) and data["choices"]:
                        choice = data["choices"][0]
                        if isinstance(choice.get("delta"), dict):
                            if isinstance(choice["delta"].get("content"), str):
                                content = choice["delta"]["content"]
                            elif isinstance(choice["delta"].get("text"), str):
                                content = choice["delta"]["text"]
                        elif isinstance(choice.get("message"), dict) and isinstance(choice["message"].get("content"), str):
                            content = choice["message"]["content"]
                    elif isinstance(data.get("text"), str):
                        content = data["text"]
                    elif isinstance(data.get("message"), dict) and isinstance(data["message"].get("content"), str):
                        content = data["message"]["content"]
                    
                    if content:
                        if content.startswith(current):
                            delta = content[len(current) :]
                        elif current and content:
                            delta = content
                        else:
                            delta = content
                        current = content
                        if delta:
                            output.put(("delta", delta))
            await asyncio.sleep(0.3)

        output.put(("error", f"timed out after {timeout}s waiting for Venice"))
    except Exception as exc:
        output.put(("error", str(exc)))
        # Reset session on error
        global _venice_session, _venice_initialized
        if _venice_session:
            try:
                await _venice_session.close()
            except Exception:
                pass
            _venice_session = None
            _venice_initialized = False


def _stream_conversation(messages: List[Dict[str, Any]], timeout: int = 180) -> Generator[str, None, None]:
    output: "queue.Queue" = queue.Queue()

    def worker() -> None:
        try:
            asyncio.run(_run_browser(messages, timeout, output))
        except Exception as exc:
            output.put(("error", str(exc)))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        try:
            kind, value = output.get(timeout=timeout + 60)
        except queue.Empty as exc:
            raise IOError("Venice browser request timed out") from exc
        if kind == "delta" and value:
            yield value
        elif kind == "error":
            raise IOError(f"Venice request failed: {value}")
        elif kind == "done":
            break


class Completions(BaseCompletions):
    def __init__(self, client: "Venice"):
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
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        del max_tokens, temperature, top_p, proxies, kwargs
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        actual_timeout = timeout or self._client.timeout

        if stream:
            return self._create_stream(request_id, created_time, model, messages, actual_timeout)
        return self._create_non_stream(request_id, created_time, model, messages, actual_timeout)

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: int,
    ) -> Generator[ChatCompletionChunk, None, None]:
        for delta_text in _stream_conversation(messages, timeout):
            yield ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=delta_text, role="assistant"),
                        finish_reason=None,
                    )
                ],
                created=created_time,
                model=model,
            )
        yield ChatCompletionChunk(
            id=request_id,
            choices=[Choice(index=0, delta=ChoiceDelta(content=None), finish_reason="stop")],
            created=created_time,
            model=model,
        )

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        timeout: int,
    ) -> ChatCompletion:
        content = "".join(_stream_conversation(messages, timeout))
        message = ChatCompletionMessage(role="assistant", content=content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        usage = CompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "Venice"):
        self.completions = Completions(client)


class Venice(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for the Venice API.

    Uses the guest/unauthenticated endpoint via browser session.
    """

    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = "zai-org-glm-5"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 180,
        proxies: Optional[Dict[str, str]] = None,
    ):
        super().__init__(proxies=proxies)
        self.timeout = timeout
        self.api_key = api_key
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        try:
            if api_key:
                from llm4free.browser_requests._http.compat import Session
                temp_session = Session()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                response = temp_session.get(
                    MODELS_URL,
                    headers=headers,
                    impersonate="chrome110",
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and isinstance(data.get("data"), list):
                        models = [m["id"] for m in data["data"] if isinstance(m, dict) and "id" in m]
                        if models:
                            cls.AVAILABLE_MODELS = models
                            return models
        except Exception:
            pass
        return list(cls.AVAILABLE_MODELS)

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
        return SimpleModelList(list(type(self).AVAILABLE_MODELS))

if __name__ == "__main__":
    client = Venice()
    resp = client.chat.completions.create(
        model="zai-org-glm-5",
        messages=[{"role": "user", "content": "Hello, Venice!"}],
        stream=False,
    )
    print(resp)