"""OpenAI-compatible provider for anonymous ChatGPT (chatgpt.com).

The anonymous web client uses a browser-only flow:

1. Load ``https://chatgpt.com/`` so Cloudflare issues its cookies and the page
   loads the Sentinel SDK.
2. Ask the in-page ``SentinelSDK`` for a conversation requirement token
   (proof-of-work + Cloudflare Turnstile are solved inside the browser).
3. ``POST /unauth-mweb/conversation/prepare`` to obtain a conduit token.
4. ``POST /unauth-mweb/conversation/updates`` and consume the NDJSON stream.

All of the above runs through :class:`llm4free.browser_requests.cdp.CDPSession`
so no request-signing or Turnstile reverse-engineering is required here.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

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
    format_prompt,
)

BOLD = "\033[1m"
RED = "\033[91m"
RESET = "\033[0m"

CHATGPT_BASE_URL = "https://chatgpt.com/"
# A real Chrome UA is required: Cloudflare rejects the default HeadlessChrome UA.
CHATGPT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 180

# Console markers emitted by the in-page script.
_EVENT_PREFIX = "CGPT_EVENT:"
_ERROR_PREFIX = "CGPT_ERR:"
_DONE_MARKER = "CGPT_DONE"

# Reads only the console lines produced since the previous poll.
_CONSOLE_POLL_JS = (
    "(function(){"
    "var a=window.__llm4free_console||[];"
    "var i=window.__cgpt_cursor||0;"
    "window.__cgpt_cursor=a.length;"
    "return a.slice(i).join('\\n');"
    "})()"
)


class ChatGPTReversed:
    """Lightweight facade over the anonymous ChatGPT browser flow.

    The upstream anonymous endpoint always serves ChatGPT's default model, so
    every entry in :attr:`AVAILABLE_MODELS` is accepted for API compatibility
    and routed to that default.
    """

    AVAILABLE_MODELS = [
        "auto",
        "gpt-5-1",
        "gpt-5-1-instant",
        "gpt-5-1-thinking",
        "gpt-5",
        "gpt-5-instant",
        "gpt-5-thinking",
        "gpt-4",
        "gpt-4.1",
        "gpt-4-1",
        "gpt-4.1-mini",
        "gpt-4-1-mini",
        "gpt-4.5",
        "gpt-4-5",
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o1-mini",
        "o3-mini",
        "o3-mini-high",
        "o4-mini",
        "o4-mini-high",
    ]

    def __init__(self, model: str = "auto", timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the reversed client.

        Args:
            model: Model name from :attr:`AVAILABLE_MODELS`. The anonymous
                endpoint serves its default model regardless of this value.
            timeout: Maximum seconds to wait for a complete answer.
        """
        if model not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid model: {model}. Choose from: {self.AVAILABLE_MODELS}"
            )
        self.model = model
        self.timeout = timeout

    def initialize(self) -> None:
        """Backwards-compatible no-op; the browser session is created lazily."""
        return None

    def complete(self, message: str, model: Optional[str] = None) -> str:
        """Return a complete answer for ``message``.

        Args:
            message: The user prompt.
            model: Optional model override.

        Returns:
            The assistant response as plain text.
        """
        selected_model = model or self.model
        if selected_model not in self.AVAILABLE_MODELS:
            raise ValueError(
                f"Invalid model: {selected_model}. Choose from: {self.AVAILABLE_MODELS}"
            )
        return "".join(_stream_conversation(message, self.timeout))


def _build_prompt(messages: List[Dict[str, Any]]) -> str:
    """Flatten OpenAI-style messages into a single prompt for the web client."""
    if not messages:
        raise ValueError("ChatGPT requires at least one message")
    if len(messages) == 1 and messages[0].get("role") == "user":
        return str(messages[0].get("content") or "")
    return format_prompt(messages, include_system=True)


def _conversation_script(prompt: str) -> str:
    """Build the in-page script that performs the whole anonymous flow."""
    script = r"""
(async () => {
  const log = (m) => console.log(m);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  try {
    const prompt = __PROMPT__;

    // Wait for the page's Sentinel SDK (it is injected after hydration).
    let waited = 0;
    while (typeof window.SentinelSDK === 'undefined' && waited < 60000) {
      await sleep(500);
      waited += 500;
    }
    if (typeof window.SentinelSDK === 'undefined') {
      log('CGPT_ERR:SentinelSDK unavailable (Cloudflare/challenge not passed)');
      return;
    }

    // Ask the SDK for proof-of-work + Turnstile-backed requirements.
    let req = null;
    for (let attempt = 0; attempt < 5 && !req; attempt++) {
      try {
        await window.SentinelSDK.init('conversation');
        const raw = await window.SentinelSDK.token('conversation');
        if (raw) {
          const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
          if (parsed && parsed.c && parsed.p && parsed.t) req = parsed;
        }
      } catch (err) {
        log('CGPT_WARN:token attempt failed: ' + err);
      }
      if (!req) await sleep(1200);
    }
    if (!req) {
      log('CGPT_ERR:Sentinel requirements token unavailable');
      return;
    }

    const sessionId = crypto.randomUUID();
    const operationId = crypto.randomUUID();
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const timezoneOffset = new Date().getTimezoneOffset();
    const contextual = JSON.stringify({
      app_name: 'chatgpt.com',
      has_web_push_capabilities: true,
      is_dark_mode: false,
      web_push_notification_permission: 'default',
      page_height: window.innerHeight,
      page_width: window.innerWidth,
      pixel_ratio: window.devicePixelRatio || 1,
      screen_height: window.screen.height,
      screen_width: window.screen.width,
      time_since_loaded: Math.round(performance.now() / 1000),
    });
    const conversationState = JSON.stringify({
      messages: [],
      parentMessageId: 'client-created-root',
      safety: { dismissedInterventionIds: [] },
      userMessageCount: 0,
    });
    const retryOwner = JSON.stringify({ mode: 'anonymous', sessionEpoch: null });

    const prepareBody = new URLSearchParams({
      conversationRetryOwner: retryOwner,
      conversationState: conversationState,
      clientContextualInfo: contextual,
      timezone: timezone,
      timezoneOffsetMinutes: String(timezoneOffset),
    });
    const prepare = await fetch(
      '/unauth-mweb/conversation/prepare?lightweight_authenticated=0',
      {
        method: 'POST',
        credentials: 'include',
        headers: {
          'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
          'oai-session-id': sessionId,
          'x-web-mobile-prepare-state': 'none',
          'x-web-mobile-prepare-reason': 'context_change',
        },
        body: prepareBody.toString(),
      }
    );
    if (!prepare.ok) {
      log('CGPT_ERR:prepare ' + prepare.status + ' ' + (await prepare.text()).slice(0, 300));
      return;
    }
    const prepared = await prepare.json();

    const updatesBody = new URLSearchParams({
      conversationState: conversationState,
      messageMetadata: '',
      'oai-session-id': sessionId,
      imageAttachments: '[]',
      pendingImageUploads: '[]',
      prompt: prompt,
      clientContextualInfo: contextual,
      imageSaveData: 'off',
      imageEffectiveType: '4g',
      timezone: timezone,
      timezoneOffsetMinutes: String(timezoneOffset),
      conversationRetryOwner: retryOwner,
      workOrigin: '',
      workModel: '',
      workEffort: '',
      workTier: '',
      assistantMessageId: 'pending-' + crypto.randomUUID(),
      userMessageId: crypto.randomUUID(),
      chatRequirementsToken: req.c,
      proofToken: req.p,
      turnstileToken: req.t,
      telemetryToken: '',
      timingToken: '[1,null]',
    });
    const updates = await fetch(
      '/unauth-mweb/conversation/updates?lightweight_authenticated=0&operationId=' + operationId,
      {
        method: 'POST',
        credentials: 'include',
        headers: {
          accept: 'application/vnd.openai.conversation-source+ndjson',
          'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
          'oai-session-id': sessionId,
          'x-conduit-token': prepared.conduit_token || '',
          'x-oai-turn-trace-id': crypto.randomUUID(),
          'x-web-mobile-prepare-state': 'success',
          'x-web-mobile-conversation-renderer': 'octane',
          'x-web-mobile-conversation-source': '2',
          'x-web-mobile-conversation-stream-protocol': '2',
          'x-openai-beacon-google-auth': '1',
        },
        body: updatesBody.toString(),
      }
    );
    if (!updates.ok) {
      log('CGPT_ERR:updates ' + updates.status + ' ' + (await updates.text()).slice(0, 300));
      return;
    }

    const reader = updates.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.trim()) log('CGPT_EVENT:' + line);
      }
    }
    if (buffer.trim()) log('CGPT_EVENT:' + buffer);
    log('CGPT_DONE');
  } catch (err) {
    log('CGPT_ERR:' + (err && err.stack ? err.stack : String(err)));
  }
})();
"""
    return script.replace("__PROMPT__", json.dumps(prompt))


def _extract_text(payload: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Extract text from one NDJSON conversation event.

    Args:
        payload: A decoded event from the conversation source stream.

    Returns:
        ``("cumulative", text)`` when the event carries the full message so
        far, ``("delta", text)`` when it carries only a new fragment, or
        ``None`` when the event has no assistant text.
    """
    if payload.get("type") != "content":
        return None
    dil = payload.get("dil")
    if isinstance(dil, dict):
        constants = dil.get("constants")
        if isinstance(constants, dict) and isinstance(constants.get("0"), str):
            return "cumulative", constants["0"]
    markdown = payload.get("markdown")
    if isinstance(markdown, str) and markdown:
        return "delta", markdown
    return None


async def _wait_for_challenge(session: CDPSession, attempts: int = 15) -> None:
    """Wait for a Cloudflare interstitial to clear, nudging Turnstile if needed."""
    for _ in range(attempts):
        try:
            title = await session.get_title()
        except Exception:
            title = ""
        if "just a moment" not in (title or "").lower():
            return
        try:
            await session.bypass_turnstile()
        except Exception:
            pass
        await asyncio.sleep(1)


async def _run_browser(
    prompt: str,
    timeout: int,
    output: "queue.Queue[Tuple[str, Optional[str]]]",
) -> None:
    """Run the browser conversation and push deltas onto ``output``.

    Args:
        prompt: Flattened user prompt.
        timeout: Maximum seconds to wait for the stream to finish.
        output: Queue receiving ``("delta", text)``, ``("error", message)``
            and ``("done", None)`` items.
    """
    session = CDPSession(headless=True, user_agent=CHATGPT_USER_AGENT)
    try:
        await session.start()
        await session.navigate(CHATGPT_BASE_URL)
        await _wait_for_challenge(session)
        await session.install_console_capture()
        await session.evaluate_js("window.__cgpt_cursor = 0;")
        await session.evaluate_js_stdin(_conversation_script(prompt), timeout=120)

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
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    extracted = _extract_text(event)
                    if extracted is None:
                        continue
                    mode, text = extracted
                    if mode == "cumulative":
                        if text.startswith(current):
                            delta = text[len(current) :]
                        else:
                            delta = text
                        current = text
                    else:
                        delta = text
                        current += text
                    if delta:
                        output.put(("delta", delta))
            await asyncio.sleep(0.3)

        output.put(("error", f"timed out after {timeout}s waiting for ChatGPT"))
    except Exception as exc:
        output.put(("error", str(exc)))
    finally:
        try:
            await session.close()
        except Exception:
            pass


def _stream_conversation(prompt: str, timeout: int = DEFAULT_TIMEOUT) -> Generator[str, None, None]:
    """Yield assistant text deltas produced by a browser conversation."""
    output: "queue.Queue[Tuple[str, Optional[str]]]" = queue.Queue()

    def worker() -> None:
        try:
            asyncio.run(_run_browser(prompt, timeout, output))
        except Exception as exc:  # pragma: no cover - defensive
            output.put(("error", str(exc)))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    while True:
        try:
            kind, value = output.get(timeout=timeout + 60)
        except queue.Empty as exc:
            raise IOError("ChatGPT browser request timed out") from exc
        if kind == "delta" and value:
            yield value
        elif kind == "error":
            raise IOError(f"ChatGPT request failed: {value}")
        elif kind == "done":
            break


class Completions(BaseCompletions):
    def __init__(self, client: "ChatGPT") -> None:
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
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """Create a chat completion using the anonymous ChatGPT web client.

        Args:
            model: Model name (all names route to the anonymous default model).
            messages: OpenAI-style conversation messages.
            max_tokens: Ignored by the anonymous endpoint.
            stream: Return a chunk generator when ``True``.
            temperature: Ignored by the anonymous endpoint.
            top_p: Ignored by the anonymous endpoint.
            tools: Ignored here; enabled through the base provider's XML loop.
            tool_choice: Ignored by the anonymous endpoint.
            timeout: Maximum seconds to wait for the answer.
            proxies: Ignored; configure the browser network instead.
            **kwargs: Extra parameters accepted for interface compatibility.

        Returns:
            A :class:`ChatCompletion` or a generator of
            :class:`ChatCompletionChunk` objects.
        """
        del max_tokens, temperature, top_p, tools, tool_choice, proxies, kwargs
        if model not in ChatGPTReversed.AVAILABLE_MODELS:
            model = "auto"
        prompt = _build_prompt(messages)
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        actual_timeout = timeout or self._client.timeout

        if stream:
            return self._create_streaming(request_id, created_time, model, prompt, actual_timeout)
        return self._create_non_streaming(
            request_id, created_time, model, messages, prompt, actual_timeout
        )

    def _create_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        prompt: str,
        timeout: int,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Yield OpenAI-compatible chunks as the browser stream arrives."""
        for delta_text in _stream_conversation(prompt, timeout):
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
            choices=[
                Choice(index=0, delta=ChoiceDelta(content=None), finish_reason="stop")
            ],
            created=created_time,
            model=model,
        )

    def _create_non_streaming(
        self,
        request_id: str,
        created_time: int,
        model: str,
        messages: List[Dict[str, Any]],
        prompt: str,
        timeout: int,
    ) -> ChatCompletion:
        """Collect the browser stream into a single completion object."""
        content = "".join(_stream_conversation(prompt, timeout))
        prompt_tokens = count_tokens(format_prompt(messages))
        completion_tokens = count_tokens(content)
        usage = CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
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
            usage=usage,
        )


class Chat(BaseChat):
    def __init__(self, client: "ChatGPT") -> None:
        self.completions = Completions(client)


class ChatGPT(OpenAICompatibleProvider):
    """OpenAI-compatible client for anonymous ChatGPT.

    Usage:
        client = ChatGPT()
        response = client.chat.completions.create(
            model="auto",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    default_model = "auto"

    def __init__(
        self,
        api_key: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        proxies: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the ChatGPT client.

        Args:
            api_key: Unused; included for interface compatibility.
            tools: Optional list of tools registered with the provider.
            proxies: Unused; the browser handles its own networking.
            timeout: Maximum seconds to wait for a complete answer.
        """
        super().__init__(api_key=api_key, tools=tools, proxies=proxies)
        self.timeout = timeout
        self.chat = Chat(self)

    @property
    def AVAILABLE_MODELS(self) -> List[str]:
        return ChatGPTReversed.AVAILABLE_MODELS

    @classmethod
    def get_models(cls, api_key: Optional[str] = None) -> List[str]:
        """Return the model names accepted by this provider."""
        del api_key
        return list(ChatGPTReversed.AVAILABLE_MODELS)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(self.AVAILABLE_MODELS)


if __name__ == "__main__":
    from litprinter import ic

    client = ChatGPT()
    response = client.chat.completions.create(
        model="auto",
        messages=[
            {"role": "user", "content": "How many r are in strawberry? Answer briefly."}
        ],
        stream=True,
    )
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print()
