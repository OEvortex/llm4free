import re
import time
import uuid
from typing import Any, Dict, Generator, List, Optional, Union

import requests

from llm4free.litagent import LitAgent

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


def remove_stats(content: str) -> str:
    return re.split(r"<\|stats\|>", content, maxsplit=1)[0].rstrip()


MODELS = {"llama3.1-8B": "llama3.1-8B"}
AVAILABLE_MODELS = list(MODELS.keys())


class Completions(BaseCompletions):
    def __init__(self, client: "ChatJimmy"):
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        model = model or self._client.default_model
        model_name = MODELS.get(model, model)
        messages = messages or []
        payload_messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        resp = requests.post(
            "https://chatjimmy.ai/api/chat",
            headers=LitAgent().generate_fingerprint(),
            json={
                "messages": payload_messages,
                "chatOptions": {"selectedModel": model_name, "systemPrompt": "", "topK": 8},
                "attachment": None,
            },
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()

        raw = resp.text
        content = remove_stats(raw)

        if stream:
            def gen():
                chunk_size = 48
                buf = content
                while buf:
                    part = buf[:chunk_size]
                    buf = buf[chunk_size:]
                    if not part.strip():
                        continue
                    yield ChatCompletionChunk(
                        id=request_id,
                        choices=[Choice(index=0, delta=ChoiceDelta(content=part, role="assistant"), finish_reason=None)],
                        created=created_time,
                        model=model,
                    )
                yield ChatCompletionChunk(
                    id=request_id,
                    choices=[Choice(index=0, delta=ChoiceDelta(content=None, role=None), finish_reason="stop")],
                    created=created_time,
                    model=model,
                )
            return gen()

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
    def __init__(self, client: "ChatJimmy"):
        self.completions = Completions(client)


class ChatJimmy(OpenAICompatibleProvider):
    required_auth = False
    AVAILABLE_MODELS = AVAILABLE_MODELS
    default_model = "llama3.1-8B"

    def __init__(self, timeout: int = 60, **kwargs):
        super().__init__(**kwargs)
        self.timeout = timeout
        self.chat = Chat(self)

    @classmethod
    def get_models(cls, api_key=None):
        return cls.AVAILABLE_MODELS

    @property
    def models(self):
        return SimpleModelList(type(self).AVAILABLE_MODELS)

if __name__ == "__main__":
    from rich import print
    client = ChatJimmy()
    result = client.chat.completions.create(
        model=client.default_model,
        messages=[{"role": "user", "content": "HI"}],
        stream=True,
    )
    for chunk in result:
        print(chunk, end="", flush=True)
