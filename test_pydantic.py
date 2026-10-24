
from llm4free.llm.pydantic_imports import BaseModel, StrictInt, StrictStr
from typing import Optional

class ChoiceDelta(BaseModel):
    content: Optional[StrictStr] = None

class Choice(BaseModel):
    index: StrictInt
    delta: ChoiceDelta = ChoiceDelta()

c = Choice(index=0)
print('default:', repr(c))
c2 = Choice(index=0, delta=ChoiceDelta(content="hello"))
print('with delta:', repr(c2))
c3 = Choice(index=0, delta=None)
print('with delta=None:', repr(c3))
