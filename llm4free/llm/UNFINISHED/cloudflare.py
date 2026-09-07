"""
Cloudflare AI Playground Chat Provider
======================================

A Cloudflare ``playground.ai.cloudflare.com`` chat provider ported from gpt4free
(PR #3483) for use in llm4free.

This provider drives a real Chrome browser through the async Chrome DevTools
Protocol (CDP) client :class:`CDPSession` to transparently pass the Cloudflare
challenge / "Just a moment..." interstitial. Once the page is verified it opens
an in-page WebSocket to the Cloudflare Agents runtime and pipes streamed tokens
out via ``console.log`` calls, which are captured through a console buffer that
the CDP session polls (the agent-browser backend has no live CDP event stream).

Because :meth:`Completions.create` must stay synchronous (llm4free providers
expose a synchronous ``chat.completions.create``), the async CDP flow is wrapped
in :func:`asyncio.run`.

Example:
    client = Cloudflare()
    response = client.chat.completions.create(
        model="llama-3.3-70b",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(response.choices[0].message.content)
"""

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Generator,
    List,
    Optional,
    Union,
)

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
from llm4free.browser_requests.cdp import CDPSession

# Cloudflare AI Playground endpoint.
URL = "https://playground.ai.cloudflare.com"

# Fixed placeholder agent id used by the playground WebSocket endpoint.
AGENT_ID = "00000000-0000-0000-0000-000000000000"

# Default model used when the caller does not specify one.
DEFAULT_MODEL = "llama-3.3-70b"

# Models exposed by the Cloudflare AI Playground.
AVAILABLE_MODELS = [
    "llama-3.3-70b",
    "@cf/meta/llama-3.3-70b-instruct",
    "llama-3.1-8b",
    "qwen2.5-7b",
    "gemma-2-9b",
]

# JavaScript template that opens an in-page WebSocket to the Cloudflare Agents
# runtime and streams tokens via console.log. The ``{MODEL}`` and ``{MESSAGES}``
# placeholders are substituted at runtime with str.replace(). Braces inside the
# template are kept verbatim because no f-string / .format() is used.
JS_TEMPLATE = """
(async () => {
    const model = "{MODEL}";
    const messages = {MESSAGES};
    const pk = crypto.randomUUID();
    const ws = new WebSocket(
        "wss://playground.ai.cloudflare.com/agents/playground/__AGENT_ID__?_pk=" + pk + "&model=" + encodeURIComponent(model)
    );
    ws.onopen = () => {
        ws.send(JSON.stringify({
            type: "cf_agent_stream_resume_request",
            session_id: pk,
        }));
        ws.send(JSON.stringify({
            type: "cf_agent_identity",
            agent_id: "__AGENT_ID__",
        }));
        ws.send(JSON.stringify({
            type: "cf_agent_state",
            state: {
                model: model,
                temperature: 1,
                stream: true,
                system: "You are a helpful assistant.",
                useExternalProvider: false,
            },
        }));
        ws.send(JSON.stringify({
            type: "cf_agent_mcp_servers",
            servers: [],
        }));
        ws.send(JSON.stringify({
            type: "cf_agent_stream_resume_none",
        }));
        setTimeout(() => {
            ws.send(JSON.stringify({
                type: "cf_agent_use_chat_request",
                init: {
                    method: "POST",
                    headers: { "content-type": "application/json" },
                    body: JSON.stringify({
                        messages: messages,
                        trigger: "submit-message",
                    }),
                },
            }));
        }, 1000);
    };
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === "text-delta" && typeof data.delta === "string") {
                console.log("CF_CHUNK: " + data.delta);
            } else if (data.type === "done") {
                console.log("CF_DONE");
                ws.close();
            } else if (data.type === "error") {
                console.log("CF_ERROR: " + (data.error || "unknown error"));
                ws.close();
            }
        } catch (e) {
            console.log("CF_ERROR: " + e.message);
        }
    };
    ws.onerror = (event) => {
        console.log("CF_ERROR: websocket error");
    };
})();
"""


def _build_js(model: str, messages: List[Dict[str, Any]]) -> str:
    """Build the in-page WebSocket driver JavaScript for a request.

    Args:
        model: The Cloudflare model name to query.
        messages: The conversation messages payload.

    Returns:
        A ready-to-evaluate JavaScript string.
    """
    payload = [
        {
            "role": m["role"],
            "parts": [{"type": "text", "text": m["content"]}],
            "id": str(uuid.uuid4()),
        }
        for m in messages
    ]
    return (
        JS_TEMPLATE.replace("{MODEL}", model)
        .replace("{MESSAGES}", json.dumps(payload))
        .replace("__AGENT_ID__", AGENT_ID)
    )


async def _generate_async(
    model: str,
    messages: List[Dict[str, Any]],
    stream: bool,
) -> "AsyncGenerator[ChatCompletionChunk, None]":
    """Run the Cloudflare Playground chat flow over an async CDP session.

    Passes the Cloudflare challenge, opens the in-page agent WebSocket, and
    yields :class:`ChatCompletionChunk` objects. When ``stream`` is ``False``
    the chunks are collected by :meth:`Completions.create` and re-assembled
    into a single :class:`ChatCompletion`.

    Args:
        model: The Cloudflare model name to query.
        messages: The conversation messages.
        stream: Whether the caller requested streaming (controls whether the
            token chunks are yielded live; the generator always yields chunks).

    Yields:
        :class:`ChatCompletionChunk` objects for each streamed delta plus a
        final chunk with ``finish_reason="stop"``.

    Raises:
        RuntimeError: If the Cloudflare challenge cannot be bypassed or the
            in-page WebSocket reports an error.
    """
    request_id = f"chatcmpl-{uuid.uuid4().hex}"
    created_time = int(time.time())

    session = CDPSession(headless=False)
    full_content = ""
    completion_tokens = 0

    try:
        await session.start()
        await session.navigate(URL)

        # Wait for the Cloudflare challenge to clear (up to ~30s).
        await asyncio.sleep(5)
        cleared = False
        for _ in range(25):
            title = await session.evaluate_js("document.title") or ""
            body = await session.evaluate_js(
                "document.body ? document.body.innerHTML : ''"
            ) or ""
            if (
                "Just a moment" not in title
                and "Attention Required" not in title
                and "cf-browser-verification" not in body
            ):
                cleared = True
                break
            await asyncio.sleep(1)

        if not cleared:
            raise RuntimeError(
                "Cloudflare challenge could not be bypassed for "
                f"{URL}"
            )

        # Capture console.log output so we can poll for streamed tokens. The
        # agent-browser backend has no live CDP event stream, so the in-page
        # script pipes tokens out via console.log and we read them back.
        await session.install_console_capture()
        await session.evaluate_js(_build_js(model, messages))

        while True:
            try:
                line = await session.poll_console("CF_", timeout=30)
            except asyncio.TimeoutError:
                break

            if line is None:
                break

            if line.startswith("CF_ERROR: "):
                raise RuntimeError(line[len("CF_ERROR: ") :])
            if "CF_DONE" in line:
                break
            if line.startswith("CF_CHUNK: "):
                delta_text = line[len("CF_CHUNK: ") :]
                if not delta_text:
                    continue
                full_content += delta_text
                completion_tokens = count_tokens(full_content)

                delta = ChoiceDelta(content=delta_text, role="assistant")
                choice = Choice(index=0, delta=delta, finish_reason=None)
                chunk = ChatCompletionChunk(
                    id=request_id,
                    choices=[choice],
                    created=created_time,
                    model=model,
                )
                chunk.usage = {
                    "prompt_tokens": count_tokens(format_prompt(messages)),
                    "completion_tokens": completion_tokens,
                    "total_tokens": count_tokens(format_prompt(messages))
                    + completion_tokens,
                }
                yield chunk

        prompt_tokens = count_tokens(format_prompt(messages))
        total_tokens = prompt_tokens + completion_tokens

        # Final chunk with finish_reason="stop".
        delta = ChoiceDelta(content=None)
        choice = Choice(index=0, delta=delta, finish_reason="stop")
        final_chunk = ChatCompletionChunk(
            id=request_id,
            choices=[choice],
            created=created_time,
            model=model,
        )
        final_chunk.usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        yield final_chunk
    finally:
        await session.close()


class Completions(BaseCompletions):
    """Cloudflare Playground chat completions interface."""

    def __init__(self, client: "Cloudflare"):
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
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """Create a chat completion with the Cloudflare AI Playground.

        Mimics ``openai.chat.completions.create``. The underlying CDP browser
        flow is asynchronous and is executed synchronously via ``asyncio.run``.

        Args:
            model: The Cloudflare model name (e.g. ``llama-3.3-70b``).
            messages: List of conversation message dicts.
            max_tokens: Optional max tokens (unused by the playground).
            stream: Whether to stream the response token-by-token.
            temperature: Optional sampling temperature (unused by the playground).
            top_p: Optional nucleus sampling (unused by the playground).
            timeout: Optional timeout in seconds (unused by the playground).
            proxies: Optional proxy configuration (unused by the playground).
            **kwargs: Extra provider-specific parameters.

        Returns:
            A :class:`ChatCompletion` when ``stream`` is ``False``, otherwise a
            generator of :class:`ChatCompletionChunk` objects.
        """
        target_model = model or DEFAULT_MODEL

        # _generate_async is an *async generator*; asyncio.run cannot consume
        # one directly. Drive it on a dedicated event loop in a background
        # thread and relay chunks through a queue so we can yield them from
        # this synchronous method (true streaming) or collect them.
        def _drive() -> "Generator[ChatCompletionChunk, None, None]":
            out: "queue.Queue[Any]" = queue.Queue()
            stop = object()

            def _worker() -> None:
                loop = asyncio.new_event_loop()
                try:
                    async def _consume() -> None:
                        async for chunk in _generate_async(
                            target_model, messages, stream=stream
                        ):
                            out.put(chunk)
                    loop.run_until_complete(_consume())
                except Exception as exc:  # surface failures to the consumer
                    out.put(exc)
                finally:
                    loop.close()
                out.put(stop)

            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            while True:
                item = out.get()
                if item is stop:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item

        if stream:
            return _drive()

        # Non-streaming: collect the async chunks and assemble a single
        # ChatCompletion from the final chunk's usage and accumulated text.
        chunks: List[ChatCompletionChunk] = list(_drive())
        full_content = ""
        for chunk in chunks:
            if (
                chunk.choices
                and chunk.choices[0].delta is not None
                and chunk.choices[0].delta.content
            ):
                full_content += chunk.choices[0].delta.content

        final = chunks[-1] if chunks else None
        usage_data = (final.usage if final is not None else None) or {
            "prompt_tokens": count_tokens(format_prompt(messages)),
            "completion_tokens": count_tokens(full_content),
            "total_tokens": count_tokens(format_prompt(messages))
            + count_tokens(full_content),
        }
        message = ChatCompletionMessage(role="assistant", content=full_content)
        choice = Choice(index=0, message=message, finish_reason="stop")
        usage = CompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return ChatCompletion(
            id=final.id if final is not None else f"chatcmpl-{uuid.uuid4().hex}",
            choices=[choice],
            created=final.created if final is not None else int(time.time()),
            model=target_model,
            usage=usage,
        )


class Chat(BaseChat):
    """Cloudflare Playground chat interface."""

    def __init__(self, client: "Cloudflare"):
        self.completions = Completions(client)


class Cloudflare(OpenAICompatibleProvider):
    """OpenAI-compatible client for the Cloudflare AI Playground.

    Uses the async CDP client to bypass the Cloudflare challenge and streams
    tokens through an in-page WebSocket. Because it launches a real browser, it
    is disabled by default in the unified client (``active_by_default=False``).

    Usage:
        client = Cloudflare()
        response = client.chat.completions.create(
            model="llama-3.3-70b",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        print(response.choices[0].message.content)
    """

    required_auth = False
    active_by_default = False

    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(self, tools: Optional[List] = None, proxies: Optional[Dict[str, str]] = None):
        """Initialize the Cloudflare Playground client.

        Args:
            tools: Optional list of tools to register with the provider.
            proxies: Optional proxy configuration dict.
        """
        super().__init__(api_key=None, tools=tools, proxies=proxies)
        self.url = URL
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = Cloudflare()
    print("NON-STREAMING RESPONSE:")
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
    )
    print(response)
    print("\nSTREAMING RESPONSE:")
    stream_response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
        stream=True,
    )
    for chunk in stream_response:
        print(chunk)
