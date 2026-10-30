"""CDP-backed, no-auth DeepInfra provider.

DeepInfra's serverless ``/v1/inference/...`` route is strictly API-key gated
(401 "missing API key"). The web chat product (``https://deepinfra.com/chat``)
instead authenticates anonymous inference with a Cloudflare Turnstile token
sent as the ``X-DeepInfra-Turnstile`` header — no API key required.

This provider reproduces that browser-only flow over
:class:`llm4free.browser_requests.cdp.CDPSession` using the stealth-Chrome
native engine (the only engine that resolves Turnstile here):

1. Load ``https://deepinfra.com/chat`` so the Turnstile script and a
   Cloudflare-cleared context are present.
2. Render + execute a Turnstile widget (the site's public ``sitekey``) to mint
   a short-lived proof token.
3. ``fetch`` the OpenAI-compatible ``/v1/openai/chat/completions`` endpoint
   from inside the page (``credentials: 'omit'`` so the CORS preflight for the
   custom header succeeds) with ``X-DeepInfra-Turnstile`` /
   ``X-Deepinfra-Source: web-page``.
4. Relay the SSE stream back through the browser and parse it into
   OpenAI-style chunks.

Discovered from live traffic (see ``docs/Prompts/reverse.md``): the endpoint,
the ``X-DeepInfra-Turnstile`` auth, and the ``credentials: 'omit'`` CORS
requirement are all verified against the running site.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Tuple

from llm4free.browser_requests.cdp import CDPSession
from llm4free.browser_requests.proxy_auth import resolve_proxy_str
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

CHAT_URL = "https://deepinfra.com/chat"
INFER_URL = "https://api.deepinfra.com/v1/openai/chat/completions"

# Public Cloudflare Turnstile sitekey embedded in deepinfra.com (not a secret;
# it only identifies the widget). Overridable via env if the site rotates it.
TURNSTILE_SITEKEY = os.environ.get(
    "LLM4FREE_DEEPINFRA_SITEKEY", "0x4AAAAAADlBNBTRb73O02Vo"
)

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017"
DEFAULT_TIMEOUT = 180

# Models served by the anonymous chat endpoint. The verified default always
# works; the others are the chat dropdown's current lineup and may rotate.
AVAILABLE_MODELS = [
    DEFAULT_MODEL,
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "deepseek-ai/DeepSeek-V3.1",
    "Qwen/Qwen2.5-72B-Instruct",
]


def _resolve_proxy(proxy: Any) -> Optional[str]:
    """Normalize a proxy argument to a single URL string (or ``None``).

    Accepts a URL string, a ``{"http"/"https": url}`` dict, or any object
    exposing ``get()`` + ``proxies`` (e.g.
    :class:`llm4free.Extra.proxy_manager.ProxyManager`), in which case the
    next proxy from its rotation is used.
    """
    if proxy is None:
        return None
    getter = getattr(proxy, "get", None)
    if callable(getter) and hasattr(proxy, "proxies"):
        return resolve_proxy_str(getter())
    return resolve_proxy_str(proxy)


def _build_script(model: str, messages: List[Dict[str, Any]], params: Dict[str, Any]) -> str:
    """In-page script: mint a Turnstile token, then stream the SSE fetch.

    The returned promise resolves once the request is initiated; a detached
    reader keeps pushing decoded chunks onto ``window.__di.out``.
    """
    body = {"model": model, "messages": messages, "stream": True}
    body.update(params)
    return (
        "(async () => {\n"
        "  window.__di = {out: [], done: false, err: null, status: null, cur: 0};\n"
        f"  const sitekey = {json.dumps(TURNSTILE_SITEKEY)};\n"
        f"  const url = {json.dumps(INFER_URL)};\n"
        f"  const body = {json.dumps(json.dumps(body))};\n"
        "  try {\n"
        "    let token = '';\n"
        "    const holder = document.createElement('div');\n"
        "    holder.style.cssText = 'position:fixed;left:-9999px;top:0';\n"
        "    document.body.appendChild(holder);\n"
        "    const id = window.turnstile.render(holder, {\n"
        "      sitekey: sitekey,\n"
        "      callback: (t) => { window.__di_tok = t; },\n"
        "      'error-callback': () => { window.__di_tok = '__ERR__'; },\n"
        "      appearance: 'always',\n"
        "    });\n"
        "    try { window.turnstile.execute(id); } catch (e) {}\n"
        "    for (let i = 0; i < 25; i++) {\n"
        "      await new Promise((r) => setTimeout(r, 800));\n"
        "      token = window.__di_tok || '';\n"
        "      if (token && token.length > 20) break;\n"
        "    }\n"
        "    if (!token || token.length < 20 || token === '__ERR__') {\n"
        "      window.__di.err = 'turnstile token unavailable';\n"
        "      window.__di.done = true;\n"
        "      return 'notoken';\n"
        "    }\n"
        "    const resp = await fetch(url, {\n"
        "      method: 'POST', credentials: 'omit', mode: 'cors',\n"
        "      headers: {\n"
        "        'Content-Type': 'application/json',\n"
        "        'accept': 'text/event-stream',\n"
        "        'X-DeepInfra-Turnstile': token,\n"
        "        'X-Deepinfra-Source': 'web-page',\n"
        "      },\n"
        "      body: body,\n"
        "    });\n"
        "    window.__di.status = resp.status;\n"
        "    if (!resp.ok) {\n"
        "      window.__di.err = 'http ' + resp.status + ' ' + (await resp.text()).slice(0, 300);\n"
        "      window.__di.done = true;\n"
        "      return 'http' + resp.status;\n"
        "    }\n"
        "    const rd = resp.body.getReader();\n"
        "    const dc = new TextDecoder();\n"
        "    (async () => {\n"
        "      try {\n"
        "        while (true) {\n"
        "          const { done, value } = await rd.read();\n"
        "          if (done) break;\n"
        "          window.__di.out.push(dc.decode(value, { stream: true }));\n"
        "        }\n"
        "      } catch (e) { window.__di.err = String(e); }\n"
        "      finally { window.__di.done = true; }\n"
        "    })();\n"
        "    return 'started';\n"
        "  } catch (e) {\n"
        "    window.__di.err = String((e && e.stack) || e);\n"
        "    window.__di.done = true;\n"
        "    return 'error';\n"
        "  }\n"
        "})();"
    )


_POLL_JS = (
    "(function(){var d=window.__di||{out:[],done:true};"
    "var i=d.cur||0;var s=(d.out||[]).slice(i).join('');d.cur=(d.out||[]).length;"
    "return JSON.stringify({chunk:s,done:d.done,err:d.err,status:d.status});})()"
)

# Diagnostic snapshot when the flow fails to start — explains *why* (proxy or
# Cloudflare block vs a code error) instead of surfacing a bare sentinel.
_DIAG_JS = (
    "(function(){var d=window.__di||{};"
    "return JSON.stringify({"
    "href:location.href,title:document.title,"
    "turnstile:typeof window.turnstile,err:d.err,status:d.status});})()"
)


class _SSEParser:
    """Incremental OpenAI SSE parser fed with raw text fragments."""

    def __init__(self) -> None:
        self._buf = ""
        self.done = False
        self.usage: Dict[str, Any] = {}
        self.finish_reason: Optional[str] = None

    def feed(self, text: str) -> Generator[str, None, None]:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                self.done = True
                return
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = data.get("usage")
            if usage:
                self.usage = usage
            choices = data.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason"):
                self.finish_reason = choice["finish_reason"]
            content = (choice.get("delta") or {}).get("content")
            if content:
                yield content


async def _run_browser(
    model: str,
    messages: List[Dict[str, Any]],
    params: Dict[str, Any],
    timeout: int,
    output: "queue.Queue[Tuple[str, Optional[Any]]]",
    proxy: Optional[str] = None,
) -> None:
    """Drive the stealth browser once and push deltas/errors onto ``output``."""
    session = CDPSession(headless=True, launch_stealth_chrome=True, proxy=proxy)
    try:
        await session.start()
        await session.navigate(CHAT_URL)
        await asyncio.sleep(2.5)
        # Human-ish pointer warmup keeps the Turnstile challenge from failing.
        for x, y in ((120, 200), (400, 300), (600, 480)):
            await session.mouse_move(x, y)
            await asyncio.sleep(0.2)

        # The Turnstile <script> loads asynchronously; over a slow proxy the
        # page can render before ``window.turnstile`` exists. Wait for it so we
        # don't fail with "cannot read 'render' of undefined".
        for _ in range(40):  # up to ~10s
            if (await session.evaluate_js("typeof window.turnstile")) == "object":
                break
            await asyncio.sleep(0.25)

        started = await session.evaluate_js_stdin(_build_script(model, messages, params))
        if started != "started":
            diag = await session.evaluate_js(_DIAG_JS)
            output.put(
                ("error", f"DeepInfra browser flow failed to start ({started!r}) {diag}")
            )
            return

        parser = _SSEParser()
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
                return
            if state.get("done"):
                break
            await asyncio.sleep(0.4)
        else:
            output.put(("error", f"timed out after {timeout}s waiting for DeepInfra"))
            return

        output.put(("usage", parser.usage))
        output.put(("done", None))
    except Exception as exc:  # pragma: no cover - defensive
        output.put(("error", str(exc)))
    finally:
        try:
            await session.close()
        except Exception:
            pass


def _stream_deltas(
    model: str,
    messages: List[Dict[str, Any]],
    params: Dict[str, Any],
    timeout: int,
    proxy: Optional[str] = None,
) -> Generator[Tuple[str, Any], None, None]:
    """Yield ``("delta", text)`` then ``("usage", dict)`` items from the browser."""
    output: "queue.Queue[Tuple[str, Optional[Any]]]" = queue.Queue()

    def worker() -> None:
        try:
            asyncio.run(_run_browser(model, messages, params, timeout, output, proxy))
        except Exception as exc:  # pragma: no cover - defensive
            output.put(("error", str(exc)))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        try:
            kind, value = output.get(timeout=timeout + 60)
        except queue.Empty as exc:
            raise IOError("DeepInfra browser request timed out") from exc
        if kind == "delta":
            yield ("delta", value)
        elif kind == "usage":
            yield ("usage", value or {})
        elif kind == "error":
            raise IOError(f"DeepInfra request failed: {value}")
        elif kind == "done":
            break


class Completions(BaseCompletions):
    def __init__(self, client: "DeepInfra") -> None:
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
        proxy: Any = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion via DeepInfra's anonymous Turnstile route.

        Args:
            model: Model id served by the chat endpoint (defaults to the
                verified ``deepseek-ai/DeepSeek-V4.1-Flash-1017``).
            messages: OpenAI-style conversation messages.
            max_tokens: Forwarded as ``max_new_tokens``.
            stream: Return a chunk generator when ``True``.
            temperature: Sampling temperature.
            top_p: Nucleus sampling.
            timeout: Max seconds to wait for the browser flow.
            proxy: Route the browser request through this proxy. Accepts a URL
                (``http://user:pass@host:port``), a ``{"http"/"https": url}``
                dict, or a ``ProxyManager`` (rotated per call). Overrides the
                client-level proxy; falls back to it when omitted.
            proxies: Alias of ``proxy`` for interface compatibility.
            **kwargs: Extra body parameters forwarded to the endpoint.
        """
        selected = model or self._client.default_model
        if not messages:
            raise ValueError("DeepInfra requires at least one message")

        effective_proxy = _resolve_proxy(proxy) or _resolve_proxy(proxies)
        if not effective_proxy:
            effective_proxy = self._client.effective_proxy()

        params: Dict[str, Any] = {}
        if max_tokens is not None:
            params["max_new_tokens"] = max_tokens
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p
        params.update(kwargs)

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        actual_timeout = timeout or self._client.timeout

        if stream:
            return self._create_stream(
                request_id, created_time, selected, messages, params, actual_timeout,
                effective_proxy,
            )
        return self._create_non_stream(
            request_id, created_time, selected, messages, params, actual_timeout,
            effective_proxy,
        )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        params: Dict[str, Any],
        timeout: int,
        proxy: Optional[str] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        usage: Dict[str, Any] = {}
        for kind, value in _stream_deltas(model, messages, params, timeout, proxy):
            if kind == "usage":
                usage = value
                continue
            chunk = ChatCompletionChunk(
                id=request_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=value, role="assistant"),
                        finish_reason=None,
                    )
                ],
                created=created_time,
                model=model,
            )
            chunk.usage = usage or None
            yield chunk
        final = ChatCompletionChunk(
            id=request_id,
            choices=[Choice(index=0, delta=ChoiceDelta(content=None), finish_reason="stop")],
            created=created_time,
            model=model,
        )
        final.usage = usage or None
        yield final

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        params: Dict[str, Any],
        timeout: int,
        proxy: Optional[str] = None,
    ) -> ChatCompletion:
        parts: List[str] = []
        usage: Dict[str, Any] = {}
        for kind, value in _stream_deltas(model, messages, params, timeout, proxy):
            if kind == "usage":
                usage = value
            else:
                parts.append(value)
        content = "".join(parts)

        prompt_tokens = usage.get("prompt_tokens") or count_tokens(format_prompt(messages))
        completion_tokens = usage.get("completion_tokens") or count_tokens(content)
        total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)

        return ChatCompletion(
            id=request_id,
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            created=created_time,
            model=model,
            usage=CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
        )


class Chat(BaseChat):
    def __init__(self, client: "DeepInfra") -> None:
        self.completions = Completions(client)


class DeepInfra(OpenAICompatibleProvider):
    """Anonymous, CDP-backed DeepInfra provider (no API key required).

    Usage:
        client = DeepInfra()
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V4.1-Flash-1017",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)

    Through a proxy (the browser's traffic, including the in-page inference
    ``fetch``, egresses via it)::

        from llm4free.Extra.proxy_manager import ProxyManager
        pm = ProxyManager(auto_fetch=True)   # Urban VPN rotation
        client = DeepInfra(proxy=pm)          # rotates per request
    """

    required_auth = False
    default_model = DEFAULT_MODEL
    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(
        self,
        api_key: Optional[str] = None,
        browser: str = "chrome",
        timeout: int = DEFAULT_TIMEOUT,
        tools: Optional[List] = None,
        proxies: Optional[Dict[str, str]] = None,
        proxy: Any = None,
    ) -> None:
        """Initialize the DeepInfra client.

        Args:
            api_key: Unused; accepted for interface compatibility.
            browser: Fingerprint hint (the browser engine is always stealth Chrome).
            timeout: Max seconds per browser request.
            tools: Optional tools registered with the provider.
            proxies: Proxy alias for interface compatibility (a
                ``{"http"/"https": url}`` dict).
            proxy: Default proxy for every browser request. Accepts a URL
                (``http://user:pass@host:port``), a ``{"http"/"https": url}``
                dict, or a ``ProxyManager`` (rotated per request). Can be
                overridden per call via ``create(proxy=...)``.
        """
        super().__init__(api_key=api_key, tools=tools, proxies=proxies)
        self.timeout = timeout
        self._proxy = proxy if proxy is not None else proxies
        self.chat = Chat(self)

    def effective_proxy(self) -> Optional[str]:
        """Resolve the client-level proxy to a URL string (rotating once)."""
        return _resolve_proxy(self._proxy)

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Return the model ids accepted by the anonymous chat endpoint."""
        del api_key
        return list(cls.AVAILABLE_MODELS)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print as rprint

    client = DeepInfra()
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "How many r are in strawberry? Answer briefly."}],
        stream=False,
        max_tokens=128,
    )
    if isinstance(resp, ChatCompletion) and resp.choices:
        msg = resp.choices[0].message
        if msg and msg.content:
            rprint(msg.content)
