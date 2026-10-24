"""Opera Aria — OpenAI-compatible variant backed by a browser (CDP) session.

All network traffic (the anonymous 3-step OAuth signup, access-token refresh
and the streaming ``a-chat`` requests) is executed *inside* a real browser via
:class:`llm4free.browser_requests.cdp.CDPSession` (the ``agent-browser`` CLI
backend). The in-page scripts perform the ``fetch`` calls and stream results
back to Python through a ``console.log`` buffer, the same technique used by
:mod:`llm4free.llm.chatgpt` and :mod:`llm4free.llm.akashgpt`.

Streaming/non-streaming exposure matches the OpenAI client surface:

    from llm4free.llm.opera_aria import OperaAria
    client = OperaAria()
    resp = client.chat.completions.create(
        model="aria",
        messages=[{"role": "user", "content": "Tell me a joke"}],
    )
    print(resp.choices[0].message.content)

Requirements: ``npm i -g agent-browser && agent-browser install``

Wire protocol summary:

* OAuth: ``client_credentials`` -> anonymous signup -> ``auth_token`` grant.
  The rotation-safe ``refresh_token`` is kept per client instance.
* Chat: v1 (``aria-legacy``) or v2 (``aria``) endpoint, server-sent events,
  one SSE ``event:``/``data:`` pair per message; the SSE parsing happens in
  the page and each extracted text fragment is forwarded to Python.

Bugs fixed relative to the previous curl_cffi implementation:

* Streaming never flipped ``is_first_request``/``conversation_id`` follow-up
  state for multi-turn continuity — now handled on the shared event path.
* The per-chunk ``usage`` dicts were built and then thrown away; usage is now
  attached to the final ``stop`` chunk.
* ``get_access_token()`` could recurse without bound when the token endpoint
  kept returning nothing — bounded to a single re-signup retry.
* The ``skip_next`` SSE heuristic skipped exactly one following line, so a
  ``thinking_status`` event without a trailing data line leaked the skip into
  the next unrelated event; the browser now parses SSE per-event instead.
* An empty prompt silently produced an empty request; it now raises.
"""

import asyncio
import base64
import concurrent.futures
import json
import logging
import os
import queue
import threading
import time
import urllib.parse
import uuid
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

from llm4free.browser_requests.cdp import CDPSession
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
    Tool,
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

logger = logging.getLogger(__name__)

__all__ = ["OperaAria"]

# ──────────────────────────────────────────────────────────────────────
#  Console markers shared between the in-page scripts and Python
# ──────────────────────────────────────────────────────────────────────

MARK_STATUS = "ARIA_ST:"  # HTTP status of the completed request
MARK_BODY = "ARIA_BODY:"  # base64-encoded full response body (auth calls)
MARK_END = "ARIA_END:"  # auth request finished
MARK_FAIL = "ARIA_FAIL:"  # base64-encoded error message
MARK_CHUNK = "ARIA_CHUNK:"  # base64-encoded streamed text fragment
MARK_CID = "ARIA_CID:"  # conversation id extracted from the SSE event
MARK_IMG = "ARIA_IMG:"  # base64-encoded generated-image URL
MARK_DONE = "ARIA_DONE:"  # stream finished

_CONSOLE_SETUP_JS = r"""
(() => {
  if (!window.__llm4free_console) {
    window.__llm4free_console = [];
    const orig = window.console.log.bind(window.console);
    window.console.log = function () {
      try {
        window.__llm4free_console.push(Array.prototype.map.call(arguments, String).join(' '));
      } catch (e) {}
      orig.apply(window.console, arguments);
    };
  }
})();
"""

_CONSOLE_CLEAR_JS = "if (window.__llm4free_console) { window.__llm4free_console.length = 0; }"

# Same-origin POST with a JSON response body (OAuth endpoints).
_HTTP_FETCH_JS = r"""
(async () => {
  const b64d = (s) => decodeURIComponent(escape(atob(s)));
  const b64e = (s) => btoa(unescape(encodeURIComponent(s)));
  try {
    const endpoint = b64d('__ENDPOINT_B64__');
    const headers = JSON.parse(b64d('__HEADERS_B64__'));
    const bodyB64 = '__BODY_B64__';
    const init = { method: 'POST', headers: headers };
    if (bodyB64) init.body = b64d(bodyB64);
    const res = await fetch(endpoint, init);
    const text = await res.text();
    console.log('__ST__' + res.status);
    console.log('__BODY__' + b64e(text));
    console.log('__END__');
  } catch (e) {
    console.log('__FAIL__' + b64e(String((e && e.message) || e)));
  }
})();
"""

# Streaming POST of the a-chat payload; the SSE stream is parsed in-page and
# every extracted fragment is reported via the console markers.
_STREAM_FETCH_JS = r"""
(async () => {
  const b64d = (s) => decodeURIComponent(escape(atob(s)));
  const b64e = (s) => btoa(unescape(encodeURIComponent(s)));
  const isV1 = __IS_V1__;
  try {
    const endpoint = b64d('__ENDPOINT_B64__');
    const headers = JSON.parse(b64d('__HEADERS_B64__'));
    const payload = b64d('__BODY_B64__');
    const res = await fetch(endpoint, { method: 'POST', headers: headers, body: payload });
    if (!res.ok) {
      const text = await res.text();
      console.log('__FAIL__' + b64e('http ' + res.status + ' ' + text.slice(0, 800)));
      return;
    }
    console.log('__ST__' + res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let curEvent = null;
    for (;;) {
      const r = await reader.read();
      if (r.done) break;
      buf += decoder.decode(r.value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const raw of lines) {
        const line = raw.replace(/\r$/, '');
        if (!line) { curEvent = null; continue; }
        if (line.startsWith('event:')) { curEvent = line.slice(6).trim(); continue; }
        if (!line.startsWith('data:')) continue;
        const ds = line.slice(5).trim();
        if (!ds || ds === '[DONE]' || ds === 'null') continue;
        if (curEvent === 'thinking_status') continue;
        let obj;
        try { obj = JSON.parse(ds); } catch (e) { continue; }
        if (isV1) {
          if (typeof obj.message === 'string' && obj.message) {
            console.log('__CHUNK__' + b64e(obj.message));
          }
          if (typeof obj.conversation_id === 'string' && obj.conversation_id) {
            console.log('__CID__' + obj.conversation_id);
          }
        } else {
          if (obj && typeof obj.response === 'object' && obj.response) {
            const rpc = obj.response;
            if (rpc.content_type === 'image' && typeof rpc.image_url === 'string' && rpc.image_url) {
              console.log('__IMG__' + b64e(rpc.image_url));
            } else if (typeof rpc.message === 'string' && rpc.message) {
              console.log('__CHUNK__' + b64e(rpc.message));
            }
          }
          if (obj && typeof obj.metadata === 'object' && obj.metadata
              && typeof obj.metadata.conversation_id === 'string' && obj.metadata.conversation_id) {
            console.log('__CID__' + obj.metadata.conversation_id);
          }
        }
      }
    }
    console.log('__DONE__');
  } catch (e) {
    console.log('__FAIL__' + b64e(String((e && e.message) || e)));
  }
})();
"""

_CONSOLE_LEN_JS = "(window.__llm4free_console||[]).length"


def _console_lines_js(cursor: int) -> str:
    """Expression that returns the un-consumed console buffer lines."""
    return "(window.__llm4free_console||[]).slice(" + str(cursor) + ").join('\\n')"


# ──────────────────────────────────────────────────────────────────────
#  base64 / prompt helpers
# ──────────────────────────────────────────────────────────────────────


def _encode_text_b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _encode_json_b64(obj: Any) -> str:
    return _encode_text_b64(json.dumps(obj))


def _decode_text_b64(value: str) -> str:
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("OperaAria: failed to decode base64 payload: %s", e)
        return value


def _approx_tokens(text: str) -> int:
    """Fallback token estimator when ``tiktoken`` is unavailable.

    Rough heuristic: ~4 characters per token. Used purely for the ``usage``
    accounting fields in the OpenAI-compat response.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _message_content_text(content: Any) -> str:
    """Flatten an OpenAI message content field into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # OpenAI "content parts" format: [{"type": "text", "text": "..."}]
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


# ──────────────────────────────────────────────────────────────────────
#  Browser worker (background thread owning the CDPSession + event loop)
# ──────────────────────────────────────────────────────────────────────


class _WorkerThread(threading.Thread):
    """Background thread that owns an asyncio loop and its ``CDPSession``."""

    def __init__(self, backend: "_BrowserBackend") -> None:
        super().__init__(name="llm4free-opera-aria-cdp", daemon=True)
        self._backend = backend
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.session: Optional[CDPSession] = None
        self.ready = threading.Event()
        self.start_error: Optional[BaseException] = None

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        session = CDPSession(
            headless=self._backend.headless,
            user_data_dir=self._backend.user_data_dir,
        )
        self.session = session
        try:
            loop.run_until_complete(session.start())
        except BaseException as e:
            self.start_error = e
            self.session = None
            self.ready.set()
            loop.close()
            self.loop = None
            return
        self.ready.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(session.close())
            except BaseException as e:
                logger.debug("OperaAria: browser session close failed: %s", e)
            finally:
                loop.close()


class _BrowserBackend:
    """Owns the browser worker and runs the in-page network coroutines."""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
    ) -> None:
        self.headless = headless
        self.user_data_dir = user_data_dir
        self._worker: Optional[_WorkerThread] = None
        self._lock = threading.Lock()
        self._closed = False

    @property
    def session(self) -> Optional[CDPSession]:
        """The live browser session, or ``None`` when the worker is not running."""
        worker = self._worker
        if worker is None or not worker.is_alive():
            return None
        return worker.session

    def worker(self) -> _WorkerThread:
        """Lazily start (or return) the browser worker thread."""
        with self._lock:
            if self._closed:
                raise RuntimeError("OperaAria browser backend has been closed")
            if self._worker is None:
                self._worker = _WorkerThread(self)
                self._worker.start()
            worker = self._worker
        if not worker.ready.wait(timeout=120):
            raise RuntimeError("OperaAria browser worker did not become ready in 120s")
        if worker.start_error is not None:
            raise RuntimeError(
                f"OperaAria: failed to start the browser session: {worker.start_error}"
            ) from worker.start_error
        if worker.loop is None or worker.session is None or not worker.is_alive():
            raise RuntimeError("OperaAria browser worker is not running")
        return worker

    def call(self, coro_factory: Callable[[], Any], timeout: Optional[float] = None) -> Any:
        """Schedule a coroutine on the worker loop and wait for its result."""
        worker = self.worker()
        loop = worker.loop
        if loop is None:
            raise RuntimeError("OperaAria browser worker is not running")
        fut = asyncio.run_coroutine_threadsafe(coro_factory(), loop)
        try:
            return fut.result(timeout=timeout)
        except (TimeoutError, concurrent.futures.TimeoutError):
            fut.cancel()
            raise

    def stop(self) -> None:
        """Shut the browser session and its worker thread down."""
        with self._lock:
            worker = self._worker
            self._worker = None
            self._closed = True
        if worker is None or not worker.is_alive():
            return
        if worker.loop is not None:
            worker.loop.call_soon_threadsafe(worker.loop.stop)
            worker.join(timeout=60)

    # ── coroutines run on the worker loop ─────────────────────────

    async def _prepare_page(self, page_url: str) -> None:
        """Navigate to ``page_url`` (same-origin as the upcoming fetch) and
        install a guarded ``console.log`` capture buffer."""
        if self.session is None:
            raise RuntimeError("OperaAria browser worker is not running")
        try:
            await self.session.navigate(page_url)
        except RuntimeError as e:
            logger.warning("OperaAria: navigate failed for %s: %s", page_url, e)
        try:
            await self.session.evaluate_js(_CONSOLE_SETUP_JS)
            await self.session.evaluate_js(_CONSOLE_CLEAR_JS)
        except RuntimeError as e:
            logger.warning("OperaAria: console capture setup failed: %s", e)

    async def _console_len(self) -> int:
        if self.session is None:
            return 0
        try:
            value = await self.session.evaluate_js(_CONSOLE_LEN_JS)
        except RuntimeError:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _console_lines(self, cursor: int) -> List[str]:
        """Return the un-consumed buffered console lines."""
        if self.session is None:
            return []
        try:
            chunk = await self.session.evaluate_js(_console_lines_js(cursor))
        except RuntimeError as e:
            logger.warning("OperaAria: console read failed: %s", e)
            return []
        if not isinstance(chunk, str) or not chunk:
            return []
        return chunk.split("\n")

    async def http_request(
        self,
        url: str,
        headers: Dict[str, str],
        body_b64: Optional[str],
        timeout: float = 90.0,
    ) -> Dict[str, Any]:
        """Same-origin POST from the browser; returns ``{"status", "text"}``.

        Args:
            url: Absolute endpoint URL; the page is navigated to its origin
                first so the ``fetch`` is not blocked by CORS.
            headers: Request headers (browser-controlled forbidden headers
                such as ``Origin``/``User-Agent`` are supplied by the page).
            body_b64: Base64-encoded request body, or ``None``.
            timeout: Maximum seconds to wait for completion.

        Returns:
            Dict with the HTTP ``status`` and the decoded body ``text``.

        Raises:
            IOError: The fetch failed inside the browser.
            TimeoutError: The request did not complete in time.
        """
        if self.session is None:
            raise RuntimeError("OperaAria browser worker is not running")
        parts = urllib.parse.urlsplit(url)
        await self._prepare_page(f"{parts.scheme}://{parts.netloc}/")
        js = (
            _HTTP_FETCH_JS.replace("__ENDPOINT_B64__", _encode_text_b64(url))
            .replace("__HEADERS_B64__", _encode_json_b64(headers))
            .replace("__BODY_B64__", body_b64 or "")
            .replace("__ST__", MARK_STATUS)
            .replace("__BODY__", MARK_BODY)
            .replace("__END__", MARK_END)
            .replace("__FAIL__", MARK_FAIL)
        )
        try:
            # May block until the promise resolves or the CLI eval timeout
            # fires; either way the script keeps running in the page.
            await self.session.evaluate_js(js)
        except RuntimeError as e:
            logger.debug("OperaAria: fetch dispatch returned: %s", e)

        cursor = await self._console_len()
        deadline = time.time() + timeout
        status: Optional[int] = None
        body_text: Optional[str] = None
        while time.time() < deadline:
            lines = await self._console_lines(cursor)
            cursor += len(lines)
            for line in lines:
                if line.startswith(MARK_STATUS):
                    try:
                        status = int(line[len(MARK_STATUS):].strip())
                    except ValueError:
                        status = 0
                elif line.startswith(MARK_BODY):
                    body_text = _decode_text_b64(line[len(MARK_BODY):])
                elif line.startswith(MARK_END):
                    return {"status": status or 0, "text": body_text or ""}
                elif line.startswith(MARK_FAIL):
                    raise IOError(f"OperaAria: fetch failed: {_decode_text_b64(line[len(MARK_FAIL):])}")
            await asyncio.sleep(0.25)
        raise TimeoutError(f"OperaAria: {url} did not complete within {timeout}s")

    async def stream_chat(
        self,
        endpoint: str,
        headers: Dict[str, str],
        payload_b64: str,
        is_v1: bool,
        timeout: float,
        push: Callable[[str, Any], None],
    ) -> None:
        """Stream one a-chat request, forwarding events to ``push``.

        Events pushed: ``("text", fragment)``, ``("image", url)``,
        ``("cid", conversation_id)``. Propagates :class:`IOError` /
        :class:`TimeoutError` failures to the awaiting caller.
        """
        if self.session is None:
            raise RuntimeError("OperaAria browser worker is not running")
        parts = urllib.parse.urlsplit(endpoint)
        await self._prepare_page(f"{parts.scheme}://{parts.netloc}/")
        js = (
            _STREAM_FETCH_JS.replace("__IS_V1__", "true" if is_v1 else "false")
            .replace("__ENDPOINT_B64__", _encode_text_b64(endpoint))
            .replace("__HEADERS_B64__", _encode_json_b64(headers))
            .replace("__BODY_B64__", payload_b64)
            .replace("__ST__", MARK_STATUS)
            .replace("__CHUNK__", MARK_CHUNK)
            .replace("__CID__", MARK_CID)
            .replace("__IMG__", MARK_IMG)
            .replace("__DONE__", MARK_DONE)
            .replace("__FAIL__", MARK_FAIL)
        )
        try:
            await self.session.evaluate_js(js)
        except RuntimeError as e:
            logger.debug("OperaAria: stream dispatch returned: %s", e)

        cursor = await self._console_len()
        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = await self._console_lines(cursor)
            cursor += len(lines)
            for line in lines:
                if line.startswith(MARK_CHUNK):
                    push("text", _decode_text_b64(line[len(MARK_CHUNK):]))
                elif line.startswith(MARK_IMG):
                    push("image", _decode_text_b64(line[len(MARK_IMG):]))
                elif line.startswith(MARK_CID):
                    push("cid", line[len(MARK_CID):].strip())
                elif line.startswith(MARK_DONE):
                    return
                elif line.startswith(MARK_FAIL):
                    raise IOError(f"OperaAria request failed: {_decode_text_b64(line[len(MARK_FAIL):])}")
            await asyncio.sleep(0.3)
        raise TimeoutError(f"OperaAria: stream did not finish within {timeout}s")


# ──────────────────────────────────────────────────────────────────────
#  Per-instance auth state
# ──────────────────────────────────────────────────────────────────────


class _OperaAriaState:
    """Client-bound OAuth + conversation state.

    Captures the long-lived ``refresh_token`` (rotated only when the OAuth
    server invalidates it), the short-lived ``access_token`` and its expiry,
    the per-session encryption key carried by the v1/v2 payloads, and the
    ``conversation_id`` used to keep follow-up turns in the same thread.
    """

    def __init__(self, refresh_token: Optional[str] = None) -> None:
        self.refresh_token = refresh_token
        self.access_token: Optional[str] = None
        self.expires_at: float = 0.0
        self.conversation_id: Optional[str] = None
        self.is_first_request: bool = True
        self.encryption_key = base64.b64encode(os.urandom(32)).decode("utf-8")

    def is_token_expired(self) -> bool:
        return time.time() >= self.expires_at

    def update_token(self, access_token: str, expires_in: int) -> None:
        self.access_token = access_token
        self.expires_at = time.time() + max(1, int(expires_in)) - 60


# ──────────────────────────────────────────────────────────────────────
#  OpenAI-compat completions class
# ──────────────────────────────────────────────────────────────────────


class Completions(BaseCompletions):
    def __init__(self, client: "OperaAria"):
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
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Any:
        """Mimics ``openai.chat.completions.create``.

        Opera Aria's wire format only carries a single ``query`` string, so
        the last user message is used as the query (with other messages as a
        plain-text fallback) and everything else is dropped.

        Returns:
            A :class:`ChatCompletion` when ``stream=False``, otherwise a
            generator of :class:`ChatCompletionChunk` objects.
        """
        model = self._client.convert_model_name(model)
        version = self._client._api_version(model)
        prompt = self._client._last_user_text(messages)
        if not prompt:
            raise ValueError(
                "OperaAria requires at least one message with plain-text content"
            )

        request_id = f"chatcmpl-{self._client._uuid()}"
        created_time = int(time.time())

        access_token = self._client.get_access_token()
        headers = self._client._build_headers(access_token, version)
        payload = self._client._build_payload(prompt, version)
        payload_b64 = _encode_json_b64(payload)
        effective_timeout = float(timeout or self._client.timeout)

        events = self._iter_events(version, headers, payload_b64, effective_timeout)
        if stream:
            return self._stream_response(events, request_id, created_time, model, prompt)
        return self._complete_response(events, request_id, created_time, model, prompt)

    # ── event plumbing (shared by streaming and non-streaming) ────

    def _iter_events(
        self,
        version: str,
        headers: Dict[str, str],
        payload_b64: str,
        timeout: float,
    ) -> Generator[Tuple[str, Any], None, None]:
        """Yield ``("text"|"image"|"cid", value)`` events for one request.

        Runs the browser streaming coroutine on the backend worker thread
        and pumps results through a queue so callers (in the user's thread)
        receive true streaming updates.
        """
        client = self._client
        backend = client.backend
        endpoint = client._api_endpoint(version)
        q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

        def _consume(event: str, value: Any = None) -> None:
            q.put((event, value))

        def _runner() -> None:
            try:
                worker = backend.worker()
                loop = worker.loop
                if loop is None:
                    raise RuntimeError("OperaAria browser worker is not running")
                fut = asyncio.run_coroutine_threadsafe(
                    backend.stream_chat(
                        endpoint,
                        headers,
                        payload_b64,
                        version == "v1",
                        timeout,
                        _consume,
                    ),
                    loop,
                )
            except Exception as e:
                _consume("error", e)
                return
            try:
                fut.result()
            except BaseException as e:
                _consume("error", e)
            finally:
                _consume("done", None)

        threading.Thread(target=_runner, name="llm4free-opera-aria-stream", daemon=True).start()

        # Wall-clock guard: a bit of slack on top of the network timeout so
        # a stall surfaces as TimeoutError instead of hanging forever.
        deadline = time.time() + timeout + 30
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"OperaAria: response did not finish within {timeout:.0f}s")
            try:
                event, value = q.get(timeout=min(remaining, 30.0))
            except queue.Empty:
                continue
            if event == "done":
                return
            if event == "error":
                raise IOError(f"OperaAria request failed: {value}") from (
                    value if isinstance(value, BaseException) else None
                )
            yield event, value

    def _stream_response(
        self,
        events: Generator[Tuple[str, Any], None, None],
        request_id: str,
        created_time: int,
        model: str,
        prompt: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        prompt_tokens = self._client._safe_count(prompt)
        completion_tokens = 0
        try:
            for event, value in events:
                if event == "text":
                    chunk_text: str = value
                elif event == "image":
                    chunk_text = f"[image: {value}]"
                elif event == "cid" and value:
                    self._client._state.conversation_id = value
                    continue
                else:
                    continue
                completion_tokens += self._client._safe_count(chunk_text)
                yield ChatCompletionChunk(
                    id=request_id,
                    created=created_time,
                    model=model,
                    system_fingerprint=None,
                    choices=[
                        Choice(
                            index=0,
                            delta=ChoiceDelta(
                                content=chunk_text,
                                role="assistant",
                                tool_calls=None,
                            ),
                            finish_reason=None,
                            logprobs=None,
                        )
                    ],
                )
        except Exception as e:
            raise IOError(f"OperaAria request failed: {e}") from e

        self._client._state.is_first_request = False
        # Final stop chunk — OpenAI reports usage on the last chunk.
        yield ChatCompletionChunk(
            id=request_id,
            created=created_time,
            model=model,
            system_fingerprint=None,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                    logprobs=None,
                )
            ],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost": None,
            },
        )

    def _complete_response(
        self,
        events: Generator[Tuple[str, Any], None, None],
        request_id: str,
        created_time: int,
        model: str,
        prompt: str,
    ) -> ChatCompletion:
        parts: List[str] = []
        for event, value in events:
            if event == "text":
                parts.append(value)
            elif event == "image":
                parts.append(f"[image: {value}]")
            elif event == "cid" and value:
                self._client._state.conversation_id = value

        self._client._state.is_first_request = False

        full_text = "".join(parts)
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


class Chat(BaseChat):
    def __init__(self, client: "OperaAria"):
        self.completions = Completions(client)


# ──────────────────────────────────────────────────────────────────────
#  Public client
# ──────────────────────────────────────────────────────────────────────


class OperaAria(OpenAICompatibleProvider):
    """OpenAI-compatible client for Opera Aria over a browser (CDP) session.

    Every request — anonymous OAuth signup, token refresh and the streaming
    chat calls — is executed from inside a real Chrome page via the
    ``agent-browser``-backed :class:`~llm4free.browser_requests.cdp.CDPSession`,
    which also supplies genuine browser fingerprints (TLS, headers).

    Usage::

        client = OperaAria()
        response = client.chat.completions.create(
            model="aria",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)

        for chunk in client.chat.completions.create(model="aria",
                                                    messages=messages,
                                                    stream=True):
            print(chunk.choices[0].delta.content or "", end="")
    """

    required_auth = False

    # Endpoints
    API_ENDPOINT_V1 = "https://composer.opera-api.com/api/v1/a-chat"
    API_ENDPOINT_V2 = "https://composer.opera-api.com/api/v2/a-chat"
    TOKEN_ENDPOINT = "https://oauth2.opera-api.com/oauth2/v1/token/"
    SIGNUP_ENDPOINT = "https://auth.opera.com/account/v2/external/anonymous/signup"

    _USER_AGENT_V1 = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36 OPR/89.0.0.0"
    )
    _USER_AGENT_V2 = (
        "Mozilla/5.0 (Linux; U; Android 8.1.0; DRA-L21 Build/HUAWEIDRA-L21; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        "Chrome/138.0.7204.179 Mobile Safari/537.36 OPR/99.0.2254.81922"
    )

    AVAILABLE_MODELS = ["aria", "aria-legacy"]
    _MODEL_TO_VERSION = {"aria": "v2", "aria-legacy": "v1"}

    _FORM_AUTH_HEADERS = {
        "User-Agent": "okhttp/5.3.2",
        "Content-Type": "application/x-www-form-urlencoded",
        "x-requested-with": "XMLHttpRequest",
        "x-opera-client-cache": "1",
    }

    def __init__(
        self,
        timeout: int = 120,
        refresh_token: Optional[str] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        **kwargs: Any,
    ):
        self.timeout = timeout
        self.headless = headless
        self.user_data_dir = user_data_dir
        self._state = _OperaAriaState(refresh_token=refresh_token)
        self.backend = _BrowserBackend(headless=headless, user_data_dir=user_data_dir)
        super().__init__(**kwargs)
        # Authentication is lazy: the browser worker is spun up on the first
        # request so instantiating the client stays cheap.
        self.chat = Chat(self)

    # ── model helpers ──────────────────────────────────────────────

    def _uuid(self) -> str:
        return uuid.uuid4().hex

    def _safe_count(self, text: str) -> int:
        """Count tokens via ``tiktoken`` if installed, else the
        character-based fallback. Keeps the provider usable in slim
        installs that don't have the optional ``tiktoken`` dep."""
        try:
            return count_tokens(text)
        except (ImportError, ModuleNotFoundError, OSError):
            return _approx_tokens(text)

    def _api_version(self, model: str) -> str:
        return self._MODEL_TO_VERSION.get(model, "v2")

    def _api_endpoint(self, version: str) -> str:
        return self.API_ENDPOINT_V1 if version == "v1" else self.API_ENDPOINT_V2

    def convert_model_name(self, model: str) -> str:
        if not model:
            return "aria"
        return model if model in self.AVAILABLE_MODELS else "aria"

    @staticmethod
    def _last_user_text(messages: List[Dict[str, Any]]) -> str:
        """Opera Aria takes a single query string — pull the last user
        message; if no user message exists, fall back to joining every
        message's content so the query is never silently empty."""
        for m in reversed(messages or []):
            if isinstance(m, dict) and m.get("role") == "user":
                text = _message_content_text(m.get("content"))
                if text.strip():
                    return text
        fallback = "\n\n".join(
            text
            for m in (messages or [])
            if isinstance(m, dict)
            for text in [_message_content_text(m.get("content"))]
            if text.strip()
        )
        return fallback

    # ── request build helpers ─────────────────────────────────────

    @staticmethod
    def _timezone_offset_string() -> str:
        """Local UTC offset formatted like ``+02:00``."""
        gmtoff = time.localtime().tm_gmtoff or 0
        sign = "+" if gmtoff >= 0 else "-"
        total_minutes = abs(int(gmtoff)) // 60
        hours, minutes = divmod(total_minutes, 60)
        return f"{sign}{hours:02d}:{minutes:02d}"

    def _build_headers(self, access_token: str, version: str) -> Dict[str, str]:
        tz_offset = self._timezone_offset_string()
        if version == "v1":
            return {
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Origin": "opera-aria://ui",
                "User-Agent": self._USER_AGENT_V1,
                "X-Opera-Timezone": tz_offset,
                "X-Opera-UI-Language": "en",
            }
        return {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": "https://composer.opera-api.com",
            "Referer": "https://composer.opera-api.com/assets/aria/index.html",
            "User-Agent": self._USER_AGENT_V2,
            "X-Opera-Timezone": tz_offset,
            "X-Opera-UI-Language": "en",
            "X-Requested-With": "com.opera.mini.native",
        }

    def _build_payload(self, prompt: str, version: str) -> Dict[str, Any]:
        if version == "v1":
            data: Dict[str, Any] = {
                "query": prompt,
                "stream": True,
                "linkify": True,
                "linkify_version": 3,
                "sia": True,
                "media_attachments": [],
                "encryption": {"key": self._state.encryption_key},
            }
        else:
            data = {
                "query": prompt,
                "sia": True,
                "think_harder": False,
                "supported_features": [],
                "file_attachments": [],
                "encryption": {"key": self._state.encryption_key},
            }
        if not self._state.is_first_request and self._state.conversation_id:
            data["conversation_id"] = self._state.conversation_id
        return data

    # ── auth (browser-backed, mirrors the original 3-step flow) ───

    def _browser_http(
        self,
        url: str,
        headers: Dict[str, str],
        body: Optional[str],
    ) -> Tuple[Dict[str, Any], str]:
        """POST through the browser and return ``(json_data, raw_text)``.

        The browser worker pool is shared across auth + chat calls, so the
        OAuth round-trips ride the same session as the chat request.
        """
        timeout = float(self.timeout) + 30
        response = self.backend.call(
            lambda: self.backend.http_request(
                url,
                headers,
                _encode_text_b64(body) if body else None,
                timeout=timeout,
            ),
            timeout=timeout + 60,
        )
        status = int(response.get("status") or 0)
        text = str(response.get("text") or "")
        if status != 200:
            raise IOError(
                f"OperaAria: {url} returned HTTP {status}: {text[:200]}"
            )
        try:
            return json.loads(text), text
        except json.JSONDecodeError:
            raise IOError(f"OperaAria: {url} returned non-JSON body: {text[:200]}") from None

    def _post_form(
        self,
        url: str,
        data: Dict[str, str],
    ) -> Tuple[Dict[str, Any], str]:
        body = urllib.parse.urlencode(data)
        return self._browser_http(url, self._FORM_AUTH_HEADERS, body)

    def _generate_refresh_token(self) -> str:
        """Anonymous 3-step OAuth signup executed inside the browser.

        Returns:
            The long-lived ``refresh_token`` for the anonymous account.

        Raises:
            IOError: If any step fails or returns missing credentials.
        """
        r1 = self._post_form(
            self.TOKEN_ENDPOINT,
            {
                "client_id": "mini-client",
                "client_secret": (
                    "Pcc5NvlCrxl02pMw32kO6WrnhpS0pUZ95YrDP8XNKJJQvFht4wQDkFJ7v9x5hn7C"
                ),
                "grant_type": "client_credentials",
                "scope": "anonymous_account",
            },
        )
        anon_token = r1[0].get("access_token")
        if not anon_token:
            raise IOError(
                f"OperaAria: step-1 (client_credentials) returned no access_token: {r1[1][:200]}"
            )

        r2 = self._browser_http(
            self.SIGNUP_ENDPOINT,
            {
                **self._FORM_AUTH_HEADERS,
                "Authorization": f"Bearer {anon_token}",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
            },
            json.dumps({"client_id": "mini"}),
        )
        auth_token = r2[0].get("token")
        if not auth_token:
            raise IOError(
                f"OperaAria: step-2 (anonymous signup) returned no auth_token: {r2[1][:200]}"
            )

        r3 = self._post_form(
            self.TOKEN_ENDPOINT,
            {
                "auth_token": auth_token,
                "client_id": "mini",
                "grant_type": "auth_token",
                "scope": "shodan:aria",
            },
        )
        refresh_token = r3[0].get("refresh_token")
        if not refresh_token:
            raise IOError(
                f"OperaAria: step-3 (auth_token grant) returned no refresh_token: {r3[1][:200]}"
            )
        return refresh_token

    def _refresh_access_token(self) -> Dict[str, Any]:
        data, _text = self._post_form(
            self.TOKEN_ENDPOINT,
            {
                "client_id": "mini",
                "grant_type": "refresh_token",
                "refresh_token": self._state.refresh_token or "",
                "scope": "shodan:aria",
            },
        )
        return data

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing or re-signing up as needed.

        The re-signup fallback is bounded to exactly one attempt so a
        broken endpoint cannot trigger unbounded recursion.
        """
        state = self._state
        retried = False
        while True:
            if state.access_token and not state.is_token_expired():
                return state.access_token  # type: ignore[return-value]
            if not state.refresh_token:
                state.refresh_token = self._generate_refresh_token()
            data = self._refresh_access_token()
            token = data.get("access_token")
            if token:
                try:
                    expires_in = int(data.get("expires_in") or 3600)
                except (TypeError, ValueError):
                    expires_in = 3600
                state.update_token(token, expires_in)
                return token
            if retried:
                raise IOError(
                    "OperaAria: token refresh kept failing after one re-signup attempt"
                )
            logger.info("OperaAria: refresh token rejected; re-running anonymous signup")
            state.refresh_token = None
            retried = True

    # ── lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        """Shut the browser session down (idempotent)."""
        self.backend.stop()

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = OperaAria()
    try:
        response = client.chat.completions.create(
            model="aria",
            messages=[{"role": "user", "content": "Tell me a joke"}],
        )
        message = response.choices[0].message
        print(message.content if message else "")
    finally:
        client.close()
