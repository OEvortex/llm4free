"""Authentication-required OpenAI-compatible providers."""

from llm4free.llm.Auth.cerebras import Cerebras
from llm4free.llm.Auth.deep_ai import DeepAI
from llm4free.llm.Auth.groq import Groq
from llm4free.llm.Auth.huggingface import HuggingFace
from llm4free.llm.Auth.nvidia import Nvidia
from llm4free.llm.Auth.openrouter import OpenRouter
from llm4free.llm.Auth.sambanova import Sambanova
from llm4free.llm.Auth.textpollinations import TextPollinations
from llm4free.llm.Auth.together_ai import TogetherAI
from llm4free.llm.Auth.two_ai import TwoAI
from llm4free.llm.Auth.upstage import Upstage
from llm4free.llm.Auth.zenmux import Zenmux

__all__ = [
    "DeepAI",
    "TogetherAI",
    "TwoAI",
    "Cerebras",
    "Groq",
    "HuggingFace",
    "Nvidia",
    "OpenRouter",
    "Sambanova",
    "TextPollinations",
    "Upstage",
    "Zenmux",
]
