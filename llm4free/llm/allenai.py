"""CDP-backed AllenAI Playground provider (https://playground.allenai.org).

The playground's chat API requires a reCAPTCHA Enterprise token (action:
``prompt_submission``) sent as a multipart/form-data field. Pure HTTP cannot
mint that token, so this provider drives a real Chrome via CDP, executes the
captcha challenge in-page, then fetches the streaming endpoint from the same
origin.

Response format: newline-delimited JSON objects. Content deltas arrive as
``{"chunkType":"delta","content":"text",...}`` lines; the final assembled
response has ``"chunkType":"final"``.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Tuple

from llm4free.browser_requests.cdp import CDPSession
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
    format_prompt,
)

CHAT_URL = "https://playground.allenai.org"
API_ENDPOINT = "https://prod-api.playground.apps.allenai.org/v5/threads/chat"
RECAPTCHA_SITEKEY = "6Lf7tM0sAAAAANuUHdCL9nZ82_WuBX-z9yf0E_ij"
CAPTCHA_ACTION = "prompt_submission"

DEFAULT_MODEL = "olmo-3.1-32b-instruct"
DEFAULT_TIMEOUT = 120

MODELS: Dict[str, str] = {
    "olmo-3.1-32b-instruct": "Olmo-3.1-32B-Instruct",
    "olmo-3.1-32b-think": "Olmo-3.1-32B-Think",
    "olmo-3.1-32b": "Olmo-3.1-32B-Instruct",
    "olmo-3-7b-instruct": "Olmo-3-7B-Instruct",
    "olmo-3-7b-think": "Olmo-3-7B-Think",
    "olmo-3-7b": "Olmo-3-7B-Instruct",
    "olmo-2-1124-13b-instruct": "cs-OLMo-2-1124-13B-Instruct",
    "olmo-2-13b": "cs-OLMo-2-1124-13B-Instruct",
    "olmo-2-0325-32b-instruct": "cs-OLMo-2-0325-32B-Instruct",
    "olmo-2-32b": "cs-OLMo-2-0325-32B-Instruct",
    "olmo-2-1124-7b-instruct": "cs-OLMo-2-1124-7B-Instruct",
    "olmo-2-7b": "cs-OLMo-2-1124-7B-Instruct",
    "olmo-2-0425-1b-instruct": "cs-OLMo-2-0425-1B-Instruct",
    "olmo-2-1b": "cs-OLMo-2-0425-1B-Instruct",
    "tulu-3-405b": "cs-Llama-3.1-Tulu-3-70B",
    "tulu-3-405b-instruct": "cs-Llama-3.1-Tulu-3-70B",
    "tulu-3-70b": "cs-Llama-3.1-Tulu-3-70B",
    "llama-3.1-tulu-3-70b": "cs-Llama-3.1-Tulu-3-70B",
    "tulu-3-8b": "cs-Llama-3.1-Tulu-3.1-8B",
    "tulu-3-1-8b": "cs-Llama-3.1-Tulu-3.1-8B",
    "molmo-2-8b": "molmo2-8b",
    "olmocr-2": "olmocr-2-7b-1025",
}
AVAILABLE_MODELS = list(MODELS.keys())

_BUILD_SCRIPT_TEMPLATE = """\
(async () => {
  window.__ai = {out: [], done: false, err: null, status: null, cur: 0};
  try {
    let token = '';
    if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) {
      window.__ai.err = 'grecaptcha.enterprise not loaded';
      window.__ai.done = true;
      return 'nocaptcha';
    }
    await new Promise((resolve) => grecaptcha.enterprise.ready(resolve));
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        token = await Promise.race([
          grecaptcha.enterprise.execute(SITEKEY_JS, {action: ACTION_JS}),
          new Promise((_, rej) => setTimeout(() => rej(new Error('cap-timeout')), 12000)),
        ]);
        if (token && token.length > 20) break;
      } catch (e) { /* headless never resolves -> retry then fall back */ }
      await new Promise((r) => setTimeout(r, 1200));
    }
    if (!token || token.length < 20) {
      window.__ai.err = 'captcha token unavailable';
      window.__ai.done = true;
      return 'notoken';
    }
    const fd = new FormData();
    fd.append('content', CONTENT_JS);
    fd.append('captchaToken', token);
    fd.append('host', 'ai2_model_hub');
    fd.append('model', MODEL_ID_JS);
    fd.append('role', 'user');
    fd.append('enableToolCalling', 'false');
    fd.append('bypassSafetyCheck', 'false');
    fd.append('extraParameters', '{}');
    fd.append('temperature', String(TEMP_JS));
    fd.append('topP', String(TOPP_JS));
    fd.append('maxTokens', String(MAXTOK_JS));
    fd.append('n', '1');
    const resp = await fetch(ENDPOINT_JS, {
      method: 'POST',
      headers: { 'X-Anonymous-User-ID': ANON_ID_JS },
      body: fd,
    });
    window.__ai.status = resp.status;
    if (!resp.ok) {
      const txt = await resp.text();
      window.__ai.err = 'http ' + resp.status + ' ' + txt.slice(0, 400);
      window.__ai.done = true;
      return 'http' + resp.status;
    }
    const rd = resp.body.getReader();
    const dc = new TextDecoder();
    (async () => {
      try {
        while (true) {
          const { done, value } = await rd.read();
          if (done) break;
          window.__ai.out.push(dc.decode(value, { stream: true }));
        }
      } catch (e) { window.__ai.err = String(e); }
      finally { window.__ai.done = true; }
    })();
    return 'started';
  } catch (e) {
    window.__ai.err = String((e && e.stack) || e);
    window.__ai.done = true;
    return 'error';
  }
})();"""

_POLL_JS = (
    "(function(){var d=window.__ai||{out:[],done:true};"
    "var i=d.cur||0;var s=(d.out||[]).slice(i).join('');d.cur=(d.out||[]).length;"
    "return JSON.stringify({chunk:s,done:d.done,err:d.err,status:d.status});})()"
)

_ACCEPT_TOS_JS = """\
(async () => {
  const cbs = document.querySelectorAll('input[type="checkbox"]');
  for (const cb of cbs) { if (!cb.checked) cb.click(); }
  const btn = Array.from(document.querySelectorAll('button')).find(
    b => b.textContent.includes('Accept terms')
  );
  if (btn) { btn.click(); await new Promise(r => setTimeout(r, 1500)); }
  return 'done';
})()"""

_WAIT_RECAPTCHA_JS = (
    "(typeof grecaptcha !== 'undefined' && grecaptcha.enterprise"
    " && typeof grecaptcha.enterprise.execute === 'function')"
    " ? 'ready' : 'loading'"
)


def _build_script(
    content: str,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    anonymous_user_id: str,
) -> str:
    return (
        _BUILD_SCRIPT_TEMPLATE
        .replace("SITEKEY_JS", json.dumps(RECAPTCHA_SITEKEY))
        .replace("ACTION_JS", json.dumps(CAPTCHA_ACTION))
        .replace("CONTENT_JS", json.dumps(content))
        .replace("MODEL_ID_JS", json.dumps(model_id))
        .replace("TEMP_JS", json.dumps(temperature))
        .replace("TOPP_JS", json.dumps(top_p))
        .replace("MAXTOK_JS", json.dumps(max_tokens))
        .replace("ENDPOINT_JS", json.dumps(API_ENDPOINT))
        .replace("ANON_ID_JS", json.dumps(anonymous_user_id))
    )


class _NDJSONParser:
    """Incremental parser for AllenAI's newline-delimited JSON stream."""

    def __init__(self) -> None:
        self._buf = ""
        self.done = False
        self.full_content = ""

    def feed(self, text: str) -> Generator[str, None, None]:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk_type = data.get("chunkType")
            if chunk_type == "start":
                content = data.get("content") or ""
                if content:
                    self.full_content += content
                    yield content
            elif chunk_type == "delta":
                content = data.get("content") or ""
                if content:
                    self.full_content += content
                    yield content
            elif chunk_type == "final":
                final_content = data.get("content") or ""
                if final_content and not self.full_content:
                    yield final_content
                self.done = True


async def _wait_for_ready(session: CDPSession, attempts: int = 120) -> bool:
    """Poll until reCAPTCHA Enterprise loads, accepting the ToS dialog as it appears.

    Replaces fixed warm-up sleeps with a condition check each pass, so the
    flow advances the moment the page is ready rather than on a timer.
    """
    for _ in range(attempts):
        try:
            await session.evaluate_js(_ACCEPT_TOS_JS)
            if (await session.evaluate_js(_WAIT_RECAPTCHA_JS)) == "ready":
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def _attempt(
    headless: bool,
    content: str,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout: int,
    output: "queue.Queue[Tuple[str, Any]]",
    proxy: Optional[str],
) -> Optional[str]:
    """Run one browser attempt; push deltas/errors, return a short status string.

    Returns ``"ok"`` when the stream finished, a status sentinel (e.g.
    ``"notoken"``) when the captcha never resolved, or ``"error"`` for fatal
    failures already reported on ``output``.
    """
    session = CDPSession(headless=headless, launch_stealth_chrome=True, proxy=proxy)
    try:
        await session.start()
        await session.navigate(CHAT_URL)

        if not await _wait_for_ready(session):
            return "nocaptcha"

        anon_id = str(uuid.uuid4())
        started = await session.evaluate_js_stdin(
            _build_script(content, model_id, temperature, top_p, max_tokens, anon_id)
        )

        if started == "nocaptcha" or started == "notoken":
            return started
        if started != "started":
            diag = await session.evaluate_js(
                "(function(){var d=window.__ai||{};"
                "return JSON.stringify({href:location.href,err:d.err,status:d.status});})()"
            )
            output.put(("error", f"AllenAI browser flow failed ({started!r}): {diag}"))
            return "error"

        parser = _NDJSONParser()
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = await session.evaluate_js(_POLL_JS)
            try:
                state = json.loads(raw or "{}")
            except json.JSONDecodeError:
                state = {}
            for delta in parser.feed(state.get("chunk") or ""):
                output.put(("delta", delta))
            if parser.done:
                break
            if state.get("err"):
                output.put(("error", str(state["err"])))
                return "error"
            if state.get("done"):
                break
            await asyncio.sleep(0.3)
        else:
            output.put(("error", f"timed out after {timeout}s waiting for AllenAI"))
            return "error"

        output.put(("done", None))
        return "ok"
    except Exception as exc:
        output.put(("error", str(exc)))
        return "error"
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def _run_browser(
    content: str,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout: int,
    output: "queue.Queue[Tuple[str, Any]]",
    proxy: Optional[str] = None,
) -> None:
    """Drive stealth Chrome with automatic headless->headful fallback.

    reCAPTCHA Enterprise only mints a token in a session with a real display,
    so a pure headless attempt is tried first and, if it cannot produce a
    token, the flow transparently retries headful (works under Xvfb). Only
    pre-stream failures trigger the retry, so already-delivered output is
    never duplicated.
    """
    for headless in (True, False):
        status = await _attempt(
            headless, content, model_id, temperature, top_p, max_tokens,
            timeout, output, proxy,
        )
        if status == "ok" or status == "error":
            return
        # "nocaptcha"/"notoken": captcha can't resolve in this mode -> next attempt.
    output.put(("error", "AllenAI: reCAPTCHA token unavailable (headless and headful)"))


def _stream_deltas(
    content: str,
    model_id: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout: int,
    proxy: Optional[str] = None,
) -> Generator[str, None, None]:
    """Yield text deltas from the browser-driven AllenAI stream."""
    output: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

    def worker() -> None:
        try:
            asyncio.run(_run_browser(
                content, model_id, temperature, top_p, max_tokens, timeout, output, proxy
            ))
        except Exception as exc:
            output.put(("error", str(exc)))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        try:
            kind, value = output.get(timeout=timeout + 60)
        except queue.Empty as exc:
            raise IOError("AllenAI browser request timed out") from exc
        if kind == "delta":
            yield value
        elif kind == "error":
            raise IOError(f"AllenAI request failed: {value}")
        elif kind == "done":
            break


class Completions(BaseCompletions):
    def __init__(self, client: "AllenAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = DEFAULT_MODEL,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        proxy: Any = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        if not messages:
            raise ValueError("AllenAI requires at least one message")

        model = model or DEFAULT_MODEL
        model_id = MODELS.get(model.lower(), model)
        if model_id not in set(MODELS.values()):
            raise ValueError(f"Model {model!r} not supported by AllenAI")

        content = format_prompt(messages, add_special_tokens=True)
        temp = temperature if temperature is not None else 0.6
        tp = top_p if top_p is not None else 0.95
        mt = max_tokens if max_tokens is not None else 30720
        effective_timeout = timeout or self._client.timeout

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        if stream:
            return self._create_stream(
                request_id, created_time, model, content, model_id,
                temp, tp, mt, effective_timeout, proxy or proxies,
            )
        return self._create_non_stream(
            request_id, created_time, model, content, model_id, messages,
            temp, tp, mt, effective_timeout, proxy or proxies,
        )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        content: str,
        model_id: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout: int,
        proxy: Any,
    ) -> Generator[ChatCompletionChunk, None, None]:
        first = True
        try:
            for delta_text in _stream_deltas(
                content, model_id, temperature, top_p, max_tokens, timeout,
                proxy=proxy,
            ):
                role = "assistant" if first else None
                first = False
                choice = Choice(
                    index=0,
                    delta=ChoiceDelta(content=delta_text, role=role),
                    finish_reason=None,
                )
                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[choice],
                    created=created_time,
                    model=model,
                )
        except IOError:
            raise

        final_choice = Choice(
            index=0,
            delta=ChoiceDelta(content=None, role=None),
            finish_reason="stop",
        )
        yield ChatCompletionChunk(
            id=request_id,
            choices=[final_choice],
            created=created_time,
            model=model,
        )

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        content: str,
        model_id: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        top_p: float,
        max_tokens: int,
        timeout: int,
        proxy: Any,
    ) -> ChatCompletion:
        parts: List[str] = []
        for delta_text in _stream_deltas(
            content, model_id, temperature, top_p, max_tokens, timeout,
            proxy=proxy,
        ):
            parts.append(delta_text)
        full_content = "".join(parts)

        message = ChatCompletionMessage(role="assistant", content=full_content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        prompt_tokens = count_tokens(content)
        completion_tokens = count_tokens(full_content)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "AllenAI"):
        self.completions = Completions(client)


class AllenAI(OpenAICompatibleProvider):
    """CDP-backed AllenAI Playground provider (reCAPTCHA-gated, no API key).

    Runs stealth Chrome and waits on page-readiness conditions (reCAPTCHA SDK
    loaded, ToS accepted) rather than fixed sleeps. A headless attempt runs
    first; because reCAPTCHA Enterprise only mints a token with a real
    display, the flow automatically retries headful (e.g. under Xvfb) when the
    headless session cannot produce a token.

    Usage:
        client = AllenAI()
        response = client.chat.completions.create(
            model="olmo-3.1-32b-instruct",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    supports_stream = True
    supports_system_message = True
    default_model = DEFAULT_MODEL
    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        proxies: Optional[Dict[str, str]] = None,
        proxy: Any = None,
    ):
        super().__init__(proxies=proxies)
        self.timeout = timeout
        self._proxy = proxy if proxy is not None else proxies
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        return AVAILABLE_MODELS

    @classmethod
    def get_model(cls, model: str) -> str:
        return MODELS.get(model.lower(), model)

    @classmethod
    def is_model_supported(cls, model: str) -> bool:
        return cls.get_model(model) in set(MODELS.values())


if __name__ == "__main__":
    client = AllenAI()
    print(f"Available models: {client.models.list()}")

    print("\n=== Non-Streaming ===")
    response = client.chat.completions.create(
        model="olmo-3.1-32b-instruct",
        messages=[{"role": "user", "content": "Say hello in exactly 3 words."}],
        stream=False,
    )
    if isinstance(response, ChatCompletion):
        msg = response.choices[0].message
        if msg and msg.content:
            print(msg.content)
