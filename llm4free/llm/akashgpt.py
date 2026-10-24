import json
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union

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

AVAILABLE_MODELS = [
    "openai-gpt-oss-120b",
    "Meta-Llama-3-3-70B-Instruct",
]


class Completions(BaseCompletions):
    def __init__(self, client: "AkashGPT"):
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
        if model not in AVAILABLE_MODELS:
            model = AVAILABLE_MODELS[0]
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        if stream:
            return self._stream(request_id, created_time, model, messages, timeout)
        return self._non_stream(request_id, created_time, model, messages, timeout)

    def _stream(self, request_id, created_time, model, messages, timeout):
        import asyncio
        import threading

        result = []

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def run():
                    session = CDPSession(headless=True)
                    try:
                        await session.start()
                        await session.navigate("https://chat.akash.network/")
                        try:
                            await session._run("wait", "--load", "networkidle", timeout=30)
                        except Exception:
                            pass
                        await session.install_console_capture()
                        payload = {
                            "id": uuid.uuid4().hex,
                            "messages": messages,
                            "model": model,
                            "temperature": 0.6,
                            "topP": 0.9,
                            "context": [],
                        }
                        js = """
                        (async () => {
                          try {
                            const res = await fetch('https://chat.akash.network/api/chat', {
                              method: 'POST',
                              headers: {'content-type': 'application/json'},
                              body: JSON.stringify(%s)
                            });
                            if(!res.ok) { console.log('AKASH_ERR:' + res.status); return; }
                            const reader = res.body.getReader();
                            const decoder = new TextDecoder();
                            let buf = '';
                            while(true) {
                              const {done, value} = await reader.read();
                              if(done) break;
                              buf += decoder.decode(value);
                              const lines = buf.split('\\n');
                              buf = lines.pop() || '';
                              for(const line of lines) {
                                if(!line.trim()) continue;
                                if(line.startsWith('0:')) {
                                  try {
                                    let c = line.slice(2);
                                    if(c.startsWith('"') && c.endsWith('"')) c = JSON.parse(c);
                                    console.log('AKASH_CHUNK:' + c);
                                  } catch(e) {}
                                }
                              }
                            }
                            console.log('AKASH_DONE');
                          } catch(e) { console.log('AKASH_ERR:' + e.toString()); }
                        })();
                        """ % json.dumps(payload)
                        await session.evaluate_js(js)
                        start = time.time()
                        seen = 0
                        while time.time() - start < (timeout or 90):
                            try:
                                buf = await session.evaluate_js("(window.__llm4free_console||[]).slice().join('\\n')")
                            except Exception:
                                break
                            if not isinstance(buf, str):
                                await asyncio.sleep(1)
                                continue
                            lines = buf.split("\n")
                            for line in lines[seen:]:
                                seen += 1
                                if not line:
                                    continue
                                if line.startswith("AKASH_ERR:"):
                                    raise IOError(f"AkashGPT request failed: {line}")
                                if line.startswith("AKASH_DONE"):
                                    break
                                if line.startswith("AKASH_CHUNK:"):
                                    content = line[len("AKASH_CHUNK:") :]
                                    result.append(ChatCompletionChunk(
                                        id=request_id,
                                        choices=[Choice(index=0, delta=ChoiceDelta(content=content, role="assistant"), finish_reason=None)],
                                        created=created_time,
                                        model=model,
                                    ))
                            if any(l.startswith("AKASH_DONE") or l.startswith("AKASH_ERR") for l in lines[seen-10:seen]):
                                break
                            await asyncio.sleep(0.5)
                        result.append(ChatCompletionChunk(
                            id=request_id,
                            choices=[Choice(index=0, delta=ChoiceDelta(content=None, role=None), finish_reason="stop")],
                            created=created_time,
                            model=model,
                        ))
                    finally:
                        await session.close()
                loop.run_until_complete(run())
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout or 90)
        return iter(result)

    def _non_stream(self, request_id, created_time, model, messages, timeout):
        chunks = list(self._stream(request_id, created_time, model, messages, timeout))
        content = ""
        for c in chunks:
            if c.choices and c.choices[0].delta and c.choices[0].delta.content:
                content += c.choices[0].delta.content
        prompt_tokens = count_tokens(format_prompt(messages))
        completion_tokens = count_tokens(content)
        return ChatCompletion(
            id=request_id,
            choices=[Choice(index=0, message=ChatCompletionMessage(role="assistant", content=content), finish_reason="stop")],
            created=created_time,
            model=model,
            usage=CompletionUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens),
        )


class Chat(BaseChat):
    def __init__(self, client: "AkashGPT"):
        self.completions = Completions(client)


class AkashGPT(OpenAICompatibleProvider):
    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = AVAILABLE_MODELS[0]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key=None):
        return cls.AVAILABLE_MODELS

    @property
    def models(self):
        return SimpleModelList(type(self).AVAILABLE_MODELS)

if __name__ == "__main__":
    from rich import print
    from llm4free.AIutel import timeIt

    @timeIt
    def main():
        akash = AkashGPT()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"},
        ]
        completion = akash.chat.completions.create(model="openai-gpt-oss-120b", messages=messages, stream=True)
        for chunk in completion:
            print(chunk.choices[0].delta.content or "", end="", flush=True)

    main()
