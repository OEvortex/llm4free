"""PI.ai (Pi) — OpenAI-compatible provider over a browser (CDP) session.

All network traffic (conversation start, streaming chat, and the optional
TTS download) is executed *inside* a real Chrome page via
:class:`llm4free.browser_requests.cdp.CDPSession` (the ``agent-browser`` CLI
backend), the same technique used by :mod:`llm4free.llm.chatgpt`,
:mod:`llm4free.llm.akashgpt` and :mod:`llm4free.llm.opera_aria`. Running
from a real page means Cloudflare cookies/fingerprints are genuine and no
hand-rolled ``__cf_bm`` header is needed.

Reverse-engineered wire contract (captured live from https://pi.ai/talk):

    # 1. Open https://pi.ai/talk — the bootstrap registers cookies and an
    #    implicit conversation; it clears the Cloudflare interstitial.
    #
    # 2. Create/reselect a conversation (full state incl. sids + voices):
    #    curl -X POST "https://pi.ai/api/chat/start" \\
    #      -H "Content-Type: application/json" \\
    #      -H "X-Api-Version: 3" \\
    #      -H "Origin: https://pi.ai" -H "Referer: https://pi.ai/talk" \\
    #      -d '{}'
    #    -> {"conversations":[{"sid":"..."}], "mainConversation":{...}, ...}
    #
    # 3. Chat (SSE, incremental deltas):
    #    curl -N -X POST "https://pi.ai/api/v2/chat" \\
    #      -H "Content-Type: application/json" \\
    #      -H "Accept: text/event-stream" \\
    #      -H "Origin: https://pi.ai" -H "Referer: https://pi.ai/talk" \\
    #      -d '{"text":"Hello!","conversation":"<sid>"}'
    #    -> text/event-stream pairs:
    #       event: received / data: {"sid":"...","sentAt":"..."}   (user msg ack)
    #       event: message  / data: {"sid":"...","sentAt":"..."}   (assistant sid)
    #       event: partial  / data: {"text":"delta..." [, "conversationId"]}  (repeat)
    #
    # 4. TTS (optional, ``voice=True``):
    #    curl "https://pi.ai/api/chat/voice?mode=eager&voice=voice3&messageSid=<assistant sid>"
    #    -> audio/mpeg bytes

Streaming/non-streaming exposure matches the OpenAI client surface:

    from llm4free.llm.pi import PiAI
    client = PiAI()
    resp = client.chat.completions.create(
        model="inflection_3_pi",
        messages=[{"role": "user", "content": "Tell me a joke"}],
    )
    print(resp.choices[0].message.content)

Requirements: ``npm i -g agent-browser && agent-browser install``.

Headless Cloudflare Turnstile: agent-browser is launched with the
*shipped* ``launch.mutate`` stealth plugin
(``llm4free/browser_requests/agent_browser_stealth_plugin.py``, registered
automatically via ``AGENT_BROWSER_PLUGINS``) which applies
``--disable-blink-features=AutomationControlled``, a clean
(non-``HeadlessChrome``) user agent, and a ``navigator.webdriver`` mask
init script. The challenge then resolves by itself in seconds, fully
headless. Edge cases can fall back to ``stealth_chrome=True`` (connect to
a real Chrome with anti-automation flags) or ``headless=False``.

Bugs fixed relative to the previous curl_cffi implementation:

* Dead endpoints: ``self.primary_url`` pointed at ``/api/chat``, which no
  longer serves chat; real endpoint is ``POST /api/v2/chat`` and SSE
  ``event:``/``partial`` semantics are parsed properly now.
* A hand-forged ``__cf_bm`` cookie (``uuid4().hex``) was attached — always
  invalid, now replaced by the real browser session's cookies.
* ``start_conversation()`` ran eagerly in ``__init__`` and made the
  constructor hit the network (and fail hard offline); it is lazy now.
* ``tiktoken`` unavailability crashed ``count_tokens`` inside streaming;
  it now falls back to the character-based estimator.
* The assistant-side TTS key was found by regexing all sids and picking
  the second one; it is now taken straight from the ``event: message``.
* Stream chunks carried per-chunk ``role``/usage noise; final ``stop``
  chunk now carries the usage summary like other providers.
"""

import asyncio
import base64
import concurrent.futures
import json
import logging
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

from llm4free import exceptions
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

logger = logging.getLogger(__name__)

__all__ = ["PiAI"]

# ──────────────────────────────────────────────────────────────────────
#  Console markers shared between the in-page scripts and Python
# ──────────────────────────────────────────────────────────────────────

MARK_STATUS = "PI_ST:"  # the last HTTP status seen
MARK_JSON = "PI_JSON:"  # base64-encoded JSON body (chat/start response)
MARK_END = "PI_END:"  # request finished
MARK_FAIL = "PI_FAIL:"  # base64-encoded error message
MARK_CHUNK = "PI_CHUNK:"  # base64-encoded streamed text delta
MARK_MSID = "PI_MSID:"  # assistant message sid (TTS key)
MARK_PIECE = "PI_PIECE:"  # base64 voice-audio piece ``<index>:<payload>``
MARK_DONE = "PI_DONE:"  # stream finished

_PI_TALK_URL = "https://pi.ai/talk"

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

_CONSOLE_LEN_JS = "(window.__llm4free_console||[]).length"


def _console_lines_js(cursor: int) -> str:
    """Expression that returns the un-consumed console buffer lines."""
    return "(window.__llm4free_console||[]).slice(" + str(cursor) + ").join('\\n')"


# In-page script: POST /api/chat/start (X-Api-Version: 3 keeps the legacy
# full-state shape that includes ``conversations``).
_START_FETCH_JS = r"""
(async () => {
  const b64e = (s) => btoa(unescape(encodeURIComponent(s)));
  try {
    const res = await fetch('https://pi.ai/api/chat/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Api-Version': '3' },
      body: '{}',
    });
    const text = await res.text();
    console.log('__ST__' + res.status);
    console.log('__JSON__' + b64e(text));
    console.log('__END__');
  } catch (e) {
    console.log('__FAIL__' + b64e(String((e && e.message) || e)));
  }
})();
"""

# In-page script: POST /api/v2/chat with SSE parsing. Each ``event:``/``data:``
# pair is dispatched per-event (no leaky skip-next heuristics):
#   * ``event: message`` -> assistant sid marker (TTS key)
#   * ``event: partial`` -> incremental text delta marker
_STREAM_FETCH_JS = r"""
(async () => {
  const b64d = (s) => decodeURIComponent(escape(atob(s)));
  const b64e = (s) => btoa(unescape(encodeURIComponent(s)));
  try {
    const conversation = b64d('__CONV_B64__');
    const text = b64d('__TEXT_B64__');
    const body = {};
    if (text) body.text = text;
    if (conversation) body.conversation = conversation;
    const res = await fetch('https://pi.ai/api/v2/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const t = await res.text();
      console.log('__FAIL__' + b64e('http ' + res.status + ' ' + t.slice(0, 800)));
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
        let obj;
        try { obj = JSON.parse(ds); } catch (e) { continue; }
        if (curEvent === 'message' && typeof obj.sid === 'string' && obj.sid) {
          console.log('__MSID__' + obj.sid);
        } else if (curEvent === 'partial' && typeof obj.text === 'string' && obj.text) {
          console.log('__CHUNK__' + b64e(obj.text));
        }
        // ``received`` and unknown events carry no assistant-side payload.
      }
    }
    console.log('__DONE__');
  } catch (e) {
    console.log('__FAIL__' + b64e(String((e && e.message) || e)));
  }
})();
"""

# In-page script: GET /api/chat/voice -> base64 pieces on the console buffer.
_VOICE_FETCH_JS = r"""
(async () => {
  const b64d = (s) => decodeURIComponent(escape(atob(s)));
  const b64e = (s) => btoa(unescape(encodeURIComponent(s)));
  const bufToB64 = (buf) => {
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 32768) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    }
    return btoa(bin);
  };
  try {
    const url = b64d('__URL_B64__');
    const res = await fetch(url);
    if (!res.ok) {
      console.log('__FAIL__' + b64e('http ' + res.status));
      return;
    }
    const buf = await res.arrayBuffer();
    const b64 = bufToB64(buf);
    const PIECE = 480000;
    for (let i = 0, n = 0; i < b64.length; i += PIECE, n++) {
      console.log('__PIECE__' + n + ':' + b64.slice(i, i + PIECE));
    }
    console.log('__END__PIECECOUNT:' + Math.ceil(b64.length / PIECE));
  } catch (e) {
    console.log('__FAIL__' + b64e(String((e && e.message) || e)));
  }
})();
"""


def _decode_text_b64(value: str) -> str:
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("PiAI: failed to decode base64 payload: %s", e)
        return value


def _approx_tokens(text: str) -> int:
    """Fallback token estimator when ``tiktoken`` is unavailable."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _encode_text_b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _encode_json_b64(obj: Any) -> str:
    return _encode_text_b64(json.dumps(obj))


# ──────────────────────────────────────────────────────────────────────
#  Browser worker (background thread owning the CDPSession + event loop)
# ──────────────────────────────────────────────────────────────────────


class _WorkerThread(threading.Thread):
    """Background thread that owns an asyncio loop and its ``CDPSession``."""

    def __init__(self, backend: "_BrowserBackend") -> None:
        super().__init__(name="llm4free-pi-cdp", daemon=True)
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
            port=self._backend.port if self._backend.stealth_chrome else None,
            launch_stealth_chrome=self._backend.stealth_chrome,
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
                logger.debug("PiAI: browser session close failed: %s", e)
            finally:
                loop.close()


class _BrowserBackend:
    """Owns the browser worker and runs the in-page network coroutines."""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        challenge_timeout: float = 60.0,
        stealth_chrome: bool = False,
        port: Optional[int] = None,
    ) -> None:
        """Initialize the browser backend.

        Args:
            headless: Headless default (``True``) works fine: agent-browser
                launches with the shipped ``launch.mutate`` stealth plugin
                (see ``agent_browser_stealth_plugin.py``) which clears the
                Cloudflare Turnstile challenge without any real Chrome.
            user_data_dir: Optional persistent browser profile name.
            challenge_timeout: Seconds to wait for the challenge to clear.
            stealth_chrome: Fallback: instead connect agent-browser to a
                real Chrome launched with anti-automation flags (only
                needed if the plugin route is unavailable).
            port: CDP port for the ``stealth_chrome`` fallback.
        """
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.challenge_timeout = challenge_timeout
        self.stealth_chrome = stealth_chrome
        self.port = port or 9222
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
                raise RuntimeError("PiAI browser backend has been closed")
            if self._worker is None:
                self._worker = _WorkerThread(self)
                self._worker.start()
            worker = self._worker
        if not worker.ready.wait(timeout=120):
            raise RuntimeError("PiAI browser worker did not become ready in 120s")
        if worker.start_error is not None:
            raise RuntimeError(
                f"PiAI: failed to start the browser session: {worker.start_error}"
            ) from worker.start_error
        if worker.loop is None or worker.session is None or not worker.is_alive():
            raise RuntimeError("PiAI browser worker is not running")
        return worker

    def call(self, coro_factory: Callable[[], Any], timeout: Optional[float] = None) -> Any:
        """Schedule a coroutine on the worker loop and wait for its result."""
        worker = self.worker()
        loop = worker.loop
        if loop is None:
            raise RuntimeError("PiAI browser worker is not running")
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

    async def _prepare_page(self) -> int:
        """Navigate to pi.ai/talk, clear any Cloudflare interstitial, and
        install a guarded ``console.log`` capture buffer.

        Returns:
            The console-buffer cursor snapshot (0 lines consumed so far) to
            hand to :meth:`start_conversation` / :meth:`stream_chat`.
        """
        if self.session is None:
            raise RuntimeError("PiAI browser worker is not running")
        try:
            await self.session.navigate(_PI_TALK_URL)
        except RuntimeError as e:
            logger.warning("PiAI: navigate failed for %s: %s", _PI_TALK_URL, e)

        # Wait out the Cloudflare interstitial ("Just a moment...").
        # With the stealth plugin active the challenge resolves by itself
        # within seconds, so clicking starts only as a late fallback —
        # premature clicks interrupt the in-flight solve.
        deadline = time.time() + self.challenge_timeout
        click_after = deadline - min(20.0, self.challenge_timeout * 0.4)
        while time.time() < deadline:
            try:
                title = await self.session.get_title()
            except RuntimeError:
                title = ""
            if "just a moment" not in (title or "").lower():
                break
            if time.time() >= click_after:
                try:
                    await self.session.bypass_turnstile()
                except RuntimeError:
                    pass
            await asyncio.sleep(1.5)
        try:
            title = await self.session.get_title()
        except RuntimeError:
            title = ""
        if "just a moment" in (title or "").lower():
            raise exceptions.FailedToGenerateResponseError(
                "PiAI: Cloudflare challenge did not clear in "
                f"{self.challenge_timeout:.0f}s (agent-browser stealth plugin "
                "did not activate - ensure the shipped "
                "agent_browser_stealth_plugin.py is registered via "
                "AGENT_BROWSER_PLUGINS, or try stealth_chrome=True / "
                "headless=False)"
            )

        try:
            await self.session.evaluate_js(_CONSOLE_SETUP_JS)
            await self.session.evaluate_js(_CONSOLE_CLEAR_JS)
        except RuntimeError as e:
            logger.warning("PiAI: console capture setup failed: %s", e)
        # Cursor snapshot happens right after the clear: any console line
        # produced from here on belongs to the caller's marker dispatch,
        # even when the in-page fetch completes within milliseconds.
        return await self._console_len()

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
        if self.session is None:
            return []
        try:
            chunk = await self.session.evaluate_js(_console_lines_js(cursor))
        except RuntimeError as e:
            logger.warning("PiAI: console read failed: %s", e)
            return []
        if not isinstance(chunk, str) or not chunk:
            return []
        return chunk.split("\n")

    async def start_conversation(self, timeout: float = 60.0) -> Dict[str, Any]:
        """In-page ``POST /api/chat/start``; returns the parsed JSON state."""
        if self.session is None:
            raise RuntimeError("PiAI browser worker is not running")
        cursor = await self._prepare_page()
        js = (
            _START_FETCH_JS.replace("__ST__", MARK_STATUS)
            .replace("__JSON__", MARK_JSON)
            .replace("__END__", MARK_END)
            .replace("__FAIL__", MARK_FAIL)
        )
        try:
            await self.session.evaluate_js(js)
        except RuntimeError as e:
            logger.debug("PiAI: start dispatch returned: %s", e)

        deadline = time.time() + timeout
        raw = ""
        while time.time() < deadline:
            lines = await self._console_lines(cursor)
            cursor += len(lines)
            for line in lines:
                if line.startswith(MARK_JSON):
                    raw = _decode_text_b64(line[len(MARK_JSON):])
                elif line.startswith(MARK_END):
                    if not raw:
                        raise exceptions.FailedToGenerateResponseError(
                            "PiAI: /api/chat/start returned an empty body"
                        )
                    try:
                        return json.loads(raw)
                    except json.JSONDecodeError as e:
                        raise exceptions.FailedToGenerateResponseError(
                            f"PiAI: /api/chat/start returned non-JSON: {raw[:200]}"
                        ) from e
                elif line.startswith(MARK_FAIL):
                    raise exceptions.FailedToGenerateResponseError(
                        f"PiAI: /api/chat/start failed: {_decode_text_b64(line[len(MARK_FAIL):])}"
                    )
            await asyncio.sleep(0.25)
        raise TimeoutError(f"PiAI: /api/chat/start did not complete within {timeout:.0f}s")

    async def stream_chat(
        self,
        conversation_id: Optional[str],
        prompt: str,
        timeout: float,
        push: Callable[[str, Any], None],
    ) -> None:
        """Stream one /api/v2/chat request, forwarding events to ``push``.

        Events pushed: ``("text", delta)`` and ``("msid", assistant_sid)``.
        The caller pushes a final ``("done", None)`` sentinel itself, so any
        exception propagates to it from ``fut.result()``.
        """
        if self.session is None:
            raise RuntimeError("PiAI browser worker is not running")
        cursor = await self._prepare_page()
        js = (
            _STREAM_FETCH_JS.replace("__CONV_B64__", _encode_text_b64(conversation_id or ""))
            .replace("__TEXT_B64__", _encode_text_b64(prompt))
            .replace("__ST__", MARK_STATUS)
            .replace("__MSID__", MARK_MSID)
            .replace("__CHUNK__", MARK_CHUNK)
            .replace("__DONE__", MARK_DONE)
            .replace("__FAIL__", MARK_FAIL)
        )
        try:
            await self.session.evaluate_js(js)
        except RuntimeError as e:
            logger.debug("PiAI: stream dispatch returned: %s", e)

        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = await self._console_lines(cursor)
            cursor += len(lines)
            for line in lines:
                if line.startswith(MARK_CHUNK):
                    push("text", _decode_text_b64(line[len(MARK_CHUNK):]))
                elif line.startswith(MARK_MSID):
                    push("msid", line[len(MARK_MSID):].strip())
                elif line.startswith(MARK_DONE):
                    return
                elif line.startswith(MARK_FAIL):
                    raise exceptions.FailedToGenerateResponseError(
                        f"PI.ai request failed: {_decode_text_b64(line[len(MARK_FAIL):])}"
                    )
            await asyncio.sleep(0.3)
        raise TimeoutError(f"PiAI: chat stream did not finish within {timeout:.0f}s")

    async def fetch_voice(
        self,
        voice_tag: str,
        message_sid: str,
        timeout: float = 120.0,
    ) -> bytes:
        """In-page ``GET /api/chat/voice``; returns the ``audio/mpeg`` bytes."""
        if self.session is None:
            raise RuntimeError("PiAI browser worker is not running")
        url = (
            "https://pi.ai/api/chat/voice?mode=eager&voice="
            + urllib.parse.quote(voice_tag)
            + "&messageSid="
            + urllib.parse.quote(message_sid)
        )
        cursor = await self._prepare_page()
        js = (
            _VOICE_FETCH_JS.replace("__URL_B64__", _encode_text_b64(url))
            .replace("__PIECE__", MARK_PIECE)
            .replace("__END__", MARK_END)
            .replace("__FAIL__", MARK_FAIL)
        )
        try:
            await self.session.evaluate_js(js)
        except RuntimeError as e:
            logger.debug("PiAI: voice dispatch returned: %s", e)

        deadline = time.time() + timeout
        pieces: Dict[int, str] = {}
        while time.time() < deadline:
            lines = await self._console_lines(cursor)
            cursor += len(lines)
            for line in lines:
                if line.startswith(MARK_PIECE):
                    rest = line[len(MARK_PIECE):]
                    index, _, payload = rest.partition(":")
                    try:
                        pieces[int(index)] = payload
                    except ValueError:
                        continue
                elif line.startswith(MARK_END):
                    if not pieces:
                        raise exceptions.FailedToGenerateResponseError(
                            "PiAI: voice endpoint returned no audio"
                        )
                    b64_parts = [piece for _, piece in sorted(pieces.items())]
                    return base64.b64decode("".join(b64_parts))
                elif line.startswith(MARK_FAIL):
                    raise exceptions.FailedToGenerateResponseError(
                        f"PiAI: voice request failed: {_decode_text_b64(line[len(MARK_FAIL):])}"
                    )
            await asyncio.sleep(0.3)
        raise TimeoutError(f"PiAI: voice download did not finish within {timeout:.0f}s")


# ──────────────────────────────────────────────────────────────────────
#  OpenAI-compat completions class
# ──────────────────────────────────────────────────────────────────────


class Completions(BaseCompletions):
    def __init__(self, client: "PiAI"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = 2048,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[Dict[str, str]] = None,
        voice: bool = False,
        voice_name: str = "voice3",
        output_file: str = "PiAI.mp3",
        **kwargs: Any,
    ) -> Any:
        """Mimics ``openai.chat.completions.create`` with Pi.ai specifics."""
        if voice and voice_name not in self._client.AVAILABLE_VOICES:
            raise ValueError(
                f"Voice '{voice_name}' not available. Choose from: "
                f"{list(self._client.AVAILABLE_VOICES.keys())}"
            )

        prompt = format_prompt(messages, do_continue=True, add_special_tokens=True)
        if not prompt.strip():
            raise ValueError("PiAI requires at least one message with plain-text content")

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        effective_timeout = float(timeout or self._client.timeout)

        if not self._client.conversation_id:
            self._client.start_conversation()

        events = self._iter_events(prompt, effective_timeout)
        if stream:
            return self._stream_response(
                events,
                request_id,
                created_time,
                model,
                prompt,
                voice,
                voice_name,
                output_file,
            )
        return self._complete_response(
            events,
            request_id,
            created_time,
            model,
            prompt,
            voice,
            voice_name,
            output_file,
        )

    # ── event plumbing (shared by streaming and non-streaming) ────

    def _iter_events(
        self,
        prompt: str,
        timeout: float,
    ) -> Generator[Tuple[str, Any], None, None]:
        """Yield ``("text"|"msid", value)`` events for one chat request."""
        client = self._client
        backend = client.backend
        conversation_id = client.conversation_id
        q: "queue.Queue[Tuple[str, Any]]" = queue.Queue()

        def _consume(event: str, value: Any = None) -> None:
            q.put((event, value))

        def _runner() -> None:
            try:
                worker = backend.worker()
                loop = worker.loop
                if loop is None:
                    raise RuntimeError("PiAI browser worker is not running")
                fut = asyncio.run_coroutine_threadsafe(
                    backend.stream_chat(conversation_id, prompt, timeout, _consume),
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

        threading.Thread(target=_runner, name="llm4free-pi-stream", daemon=True).start()

        # Wall-clock guard: slack on top of the network timeout so a stall
        # surfaces as TimeoutError instead of hanging forever.
        deadline = time.time() + timeout + 30
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"PiAI: response did not finish within {timeout:.0f}s")
            try:
                event, value = q.get(timeout=min(remaining, 30.0))
            except queue.Empty:
                continue
            if event == "done":
                return
            if event == "error":
                if isinstance(value, exceptions.FailedToGenerateResponseError):
                    raise value
                raise exceptions.FailedToGenerateResponseError(
                    f"PI.ai request failed: {value}"
                ) from (value if isinstance(value, BaseException) else None)
            yield event, value

    def _stream_response(
        self,
        events: Generator[Tuple[str, Any], None, None],
        request_id: str,
        created_time: int,
        model: str,
        prompt: str,
        voice: bool,
        voice_name: str,
        output_file: str,
    ) -> Generator[ChatCompletionChunk, None, None]:
        prompt_tokens = self._client._safe_count(prompt)
        completion_tokens = 0
        message_sid: Optional[str] = None
        try:
            for event, value in events:
                if event == "text":
                    completion_tokens += self._client._safe_count(value)
                    yield ChatCompletionChunk(
                        id=request_id,
                        created=created_time,
                        model=model,
                        choices=[
                            Choice(
                                index=0,
                                delta=ChoiceDelta(
                                    content=value,
                                    role="assistant",
                                ),
                                finish_reason=None,
                            )
                        ],
                    )
                elif event == "msid" and value:
                    message_sid = value
        except exceptions.FailedToGenerateResponseError:
            raise
        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(
                f"PI.ai request failed: {e}"
            ) from e

        # Final stop chunk with usage summary.
        yield ChatCompletionChunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(),
                    finish_reason="stop",
                )
            ],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

        if voice and message_sid:
            threading.Thread(
                target=self._client.download_audio_threaded,
                args=(voice_name, message_sid, output_file),
                daemon=True,
            ).start()

    def _complete_response(
        self,
        events: Generator[Tuple[str, Any], None, None],
        request_id: str,
        created_time: int,
        model: str,
        prompt: str,
        voice: bool = False,
        voice_name: str = "voice3",
        output_file: str = "PiAI.mp3",
    ) -> ChatCompletion:
        parts: List[str] = []
        message_sid: Optional[str] = None
        for event, value in events:
            if event == "text":
                parts.append(value)
            elif event == "msid" and value:
                message_sid = value

        full_content = "".join(parts)
        prompt_tokens = self._client._safe_count(prompt)
        completion_tokens = self._client._safe_count(full_content)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        message = ChatCompletionMessage(role="assistant", content=full_content)
        choice = Choice(index=0, message=message, finish_reason="stop")

        if voice and message_sid:
            threading.Thread(
                target=self._client.download_audio_threaded,
                args=(voice_name, message_sid, output_file),
                daemon=True,
            ).start()

        return ChatCompletion(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "PiAI"):
        self.completions = Completions(client)


# ──────────────────────────────────────────────────────────────────────
#  Public client
# ──────────────────────────────────────────────────────────────────────


class PiAI(OpenAICompatibleProvider):
    """PiAI provider following OpenAI-compatible interface, backed by a
    browser (CDP) session.

    Supports Pi.ai specific features like voice generation and conversation
    management. Every request runs from inside the real ``pi.ai/talk`` page,
    so Cloudflare cookies/fingerprints are genuine.

    Usage::

        client = PiAI()
        response = client.chat.completions.create(
            model="inflection_3_pi",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    AVAILABLE_MODELS = ["inflection_3_pi"]
    AVAILABLE_VOICES: Dict[str, str] = {
        "voice1": "voice1",
        "voice2": "voice2",
        "voice3": "voice3",
        "voice4": "voice4",
        "voice5": "voice5",
        "voice6": "voice6",
        "voice7": "voice7",
        "voice8": "voice8",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 120,
        proxies: Optional[Dict[str, str]] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        challenge_timeout: int = 60,
        **kwargs: Any,
    ):
        """Initialize PI.ai provider.

        Args:
            api_key: Not used for Pi.ai but kept for compatibility.
            timeout: Request timeout in seconds (chat streaming + TTS).
            proxies: Not supported by the browser backend (accepted for
                API parity; silently ignored).
            headless: Whether to run the browser headless. Defaults to
                ``True`` and works: the shipped agent-browser stealth
                plugin clears the Cloudflare Turnstile challenge. Pass
                ``False`` only as a manual fallback on desktop machines.
            user_data_dir: Optional persisted browser profile name.
            challenge_timeout: Seconds to wait for the Cloudflare
                interstitial to clear.
            **kwargs: Additional arguments forwarded to the base provider.
        """
        super().__init__(proxies=proxies, **kwargs)
        self.timeout = timeout
        self.challenge_timeout = challenge_timeout
        self.conversation_id: Optional[str] = None
        self.backend = _BrowserBackend(
            headless=headless,
            user_data_dir=user_data_dir,
            challenge_timeout=float(challenge_timeout),
        )
        # Authentication/cookies live in the real browser session; the
        # curl_cffi session from the base class is kept for API parity only.
        self.chat = Chat(self)

    # ── helpers ───────────────────────────────────────────────────

    def _safe_count(self, text: str) -> int:
        """Count tokens via ``tiktoken`` if installed, else approximate."""
        try:
            return count_tokens(text)
        except Exception:
            return _approx_tokens(text)

    # ── conversation lifecycle ────────────────────────────────────

    def start_conversation(self) -> str:
        """Initialize/resume a Pi conversation via the in-page browser call.

        Returns:
            The conversation sid.

        Raises:
            FailedToGenerateResponseError: If the endpoint fails or the
                response does not carry a conversation sid.
        """
        try:
            state = self.backend.call(
                lambda: self.backend.start_conversation(timeout=self.timeout + 30),
                timeout=self.timeout + 60,
            )
        except (RuntimeError, TimeoutError, concurrent.futures.TimeoutError) as e:
            raise exceptions.FailedToGenerateResponseError(
                f"Failed to start conversation: {e}"
            ) from e

        conversations = state.get("conversations") or []
        first = conversations[0] if isinstance(conversations, list) and conversations else {}
        sid = first.get("sid") if isinstance(first, dict) else None
        if not sid:
            main = state.get("mainConversation") or {}
            sid = main.get("sid") if isinstance(main, dict) else None
        if not sid:
            raise exceptions.FailedToGenerateResponseError(
                f"Unexpected response structure from start API: {json.dumps(state)[:300]}"
            )
        self.conversation_id = str(sid)
        return self.conversation_id

    def reset_conversation(self) -> str:
        """Drop the cached conversation id and start a fresh one."""
        self.conversation_id = None
        return self.start_conversation()

    # ── voice download (background thread) ────────────────────────

    def download_audio_threaded(self, voice_name: str, message_sid: str, output_file: str) -> None:
        """Download TTS audio for one assistant message and write it out.

        Runs inside the browser session; intended to be invoked from a
        background thread (see :meth:`Completions._stream_response`).
        """
        try:
            voice_tag = self.AVAILABLE_VOICES.get(voice_name, self.AVAILABLE_VOICES["voice3"])
            audio = self.backend.call(
                lambda: self.backend.fetch_voice(
                    voice_tag, message_sid, timeout=float(self.timeout) + 60
                ),
                timeout=self.timeout + 90,
            )
            if audio:
                with open(output_file, "wb") as file:
                    file.write(audio)
        except Exception as e:
            logger.warning("PiAI: voice download failed: %s", e)

    # ── lifecycle ─────────────────────────────────────────────────

    def close(self) -> None:
        """Shut the browser session down (idempotent)."""
        self.backend.stop()

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    client = PiAI()
    try:
        # Test streaming
        print("Testing streaming response:")
        stream = client.chat.completions.create(
            model="inflection_3_pi",
            messages=[{"role": "user", "content": "Hello! Say 'Hi' in one word."}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()

        # Test non-streaming
        print("\nTesting non-streaming response:")
        response = client.chat.completions.create(
            model="inflection_3_pi",
            messages=[{"role": "user", "content": "Tell me a short joke."}],
            stream=False,
        )
        message = response.choices[0].message
        if message and message.content:
            print(message.content)
        if response.usage:
            print(f"Usage: {response.usage}")
    finally:
        client.close()
