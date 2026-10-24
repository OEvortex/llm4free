# This file marks the directory as a Python package.
# Static imports for all llm provider modules
#
# 2026-06-12: Ayle, Elmo, SonusAI, Meta were moved to
# llm4free/Provider/UNFINISHED/ (their upstreams went away).

# Base classes and utilities
from llm4free.llm.ai4chat import AI4Chat
from llm4free.llm.chatjimmy import ChatJimmy
from llm4free.llm.akashgpt import AkashGPT
from llm4free.llm.Auth import (
    Cerebras,
    DeepAI,
    DeepInfra,
    Groq,
    HuggingFace,
    Nvidia,
    OpenRouter,
    Sambanova,
    TogetherAI,
    TwoAI,
    Upstage,
    Zenmux,
)
from llm4free.llm.Auth.textpollinations import TextPollinations
from llm4free.llm.Auth.uncensoredchat import UncensoredChat
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    FunctionDefinition,
    FunctionParameters,
    OpenAICompatibleProvider,
    SimpleModelList,
    Tool,
    ToolDefinition,
)
from llm4free.llm.chatgpt import ChatGPT, ChatGPTReversed

# Provider implementations
from llm4free.llm.gemini import Gemini
from llm4free.llm.gptfree import GptFree
from llm4free.llm.ibm import IBM
from llm4free.llm.k2think import K2Think
from llm4free.llm.miklium import Miklium
from llm4free.llm.netwrck import Netwrck
from llm4free.llm.ollama_swarm import OllamaSwarm
from llm4free.llm.pi import PiAI
from llm4free.llm.toolbaz import Toolbaz
from llm4free.llm.typliai import TypliAI
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    FunctionCall,
    ModelData,
    ModelList,
    ToolCall,
    ToolCallType,
    ToolFunction,
    count_tokens,
    format_prompt,
    get_last_user_message,
    get_system_prompt,
)
from llm4free.llm.wisecat import WiseCat
from llm4free.llm.writecream import Writecream

# List of all exported names
__all__ = [
    # Base classes and utilities
    "OpenAICompatibleProvider",
    "SimpleModelList",
    "BaseChat",
    "BaseCompletions",
    "Tool",
    "ToolDefinition",
    "FunctionParameters",
    "FunctionDefinition",
    # Utils
    "ChatCompletion",
    "ChatCompletionChunk",
    "Choice",
    "ChoiceDelta",
    "ChatCompletionMessage",
    "CompletionUsage",
    "ToolCall",
    "ToolFunction",
    "FunctionCall",
    "ToolCallType",
    "ModelData",
    "ModelList",
    "format_prompt",
    "get_system_prompt",
    "get_last_user_message",
    "count_tokens",

    "DeepAI",


    "PiAI",
    "TogetherAI",
    "TwoAI",
    "AI4Chat",
    "AkashGPT",
    "Cerebras",
    "ChatGPT",
    "ChatGPTReversed",
    "DeepInfra",


    "Gemini",
    "GptFree",
    "IBM",
    "ChatJimmy",
    "K2Think",
    "Netwrck",
    "Nvidia",
    "OllamaSwarm",
    "OpenRouter",
    "TextPollinations",
    "Toolbaz",
    "Upstage",
    "WiseCat",
    "Writecream",
    "Zenmux",
    "Sambanova",
    "TypliAI",

    "UncensoredChat",
    # New free providers (no browser required)
    "Miklium",
    # NOTE: Cloudflare, DeepInfraFree, Perchance are in llm4free.llm.UNFINISHED
    # (browser-backed; Cloudflare Turnstile does not resolve headless).
]
