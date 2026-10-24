
from typing import overload, Literal, Union, Generator, List, Dict, Any, Optional
from pydantic import BaseModel

class ChoiceDelta(BaseModel):
    content: Optional[str] = None

class ChatCompletionMessage(BaseModel):
    role: str
    content: Optional[str] = None

class Choice(BaseModel):
    index: int
    message: Optional[ChatCompletionMessage] = None
    delta: Optional[ChoiceDelta] = None
    finish_reason: Optional[str] = None

class ChunkChoice(BaseModel):
    index: int
    delta: ChoiceDelta
    finish_reason: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    id: str
    choices: List[ChunkChoice]

class ChatCompletion(BaseModel):
    id: str
    choices: List[Choice]

class Completions:
    @overload
    def create(self, *, stream: Literal[True], **kwargs: Any) -> Generator[ChatCompletionChunk, None, None]: ...
    @overload
    def create(self, *, stream: Literal[False] = False, **kwargs: Any) -> ChatCompletion: ...
    @overload
    def create(self, *, stream: bool = False, **kwargs: Any) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]: ...
    def create(self, *, stream: bool = False, **kwargs: Any) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        if stream:
            return (ChatCompletionChunk(id="1", choices=[ChunkChoice(index=0, delta=ChoiceDelta(content="hi"))]) for _ in range(1))
        return ChatCompletion(id="1", choices=[])

c = Completions()
comp = c.create(stream=True)
for chunk in comp:
    print(chunk.choices[0].delta.content, end="", flush=True)

non_stream = c.create(stream=False)
print(non_stream.choices[0].message.content)
