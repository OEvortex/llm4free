import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union, cast

from llm4free.llm.pydantic_imports import BaseModel, Field, StrictInt, StrictStr

# --- OpenAI Response Structure Mimics ---
# Moved here for reusability across different OpenAI-compatible providers


class DictLikeMixin:
    """
    Mixin class that provides dict-like access methods for Pydantic models.
    This allows models to be accessed like dictionaries while maintaining
    type safety and IDE autocomplete support.
    """

    def __getitem__(self, key):
        """Allow dict-like access."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Allow dict-like assignment."""
        setattr(self, key, value)

    def keys(self):
        """Return dict-like keys."""
        return self.__dict__.keys()

    def values(self):
        """Return dict-like values."""
        return self.__dict__.values()

    def items(self):
        """Return dict-like items."""
        return self.__dict__.items()

    def get(self, key, default=None):
        """Dict-like get method with default value."""
        return getattr(self, key, default)


class ToolCallType(str, Enum):
    """Type of tool call."""

    FUNCTION = "function"


class FunctionCall(BaseModel):
    """Function call specification."""

    name: StrictStr
    arguments: StrictStr


class ToolFunction(BaseModel):
    """Function specification in a tool."""

    name: StrictStr
    arguments: StrictStr


class ToolCall(BaseModel):
    """Tool call specification."""

    id: StrictStr
    type: StrictStr
    function: ToolFunction


class CompletionUsage(BaseModel):
    """Token usage information."""

    prompt_tokens: StrictInt
    completion_tokens: StrictInt
    total_tokens: StrictInt
    prompt_tokens_details: Optional[Dict[str, Any]] = None


class ChoiceDelta(BaseModel, DictLikeMixin):
    """Delta content in streaming response - OpenAI SDK compatible."""

    content: Optional[StrictStr] = None
    function_call: Optional[FunctionCall] = None
    role: Optional[StrictStr] = None
    tool_calls: Optional[List[ToolCall]] = None
    reasoning_content: Optional[StrictStr] = None  # For reasoning models
    reasoning: Optional[StrictStr] = None  # For reasoning models


class ChatCompletionMessage(BaseModel, DictLikeMixin):
    """Chat message in completion response."""

    role: StrictStr
    content: Optional[StrictStr] = None
    function_call: Optional[FunctionCall] = None
    tool_calls: Optional[List[ToolCall]] = None
    reasoning_content: Optional[StrictStr] = None  # For reasoning models (OpenAI o1 style)
    reasoning: Optional[StrictStr] = None  # For reasoning models (alternative field)


class Choice(BaseModel, DictLikeMixin):
    """Choice in completion response - OpenAI SDK compatible."""

    index: StrictInt
    message: Optional[ChatCompletionMessage] = None
    delta: ChoiceDelta = Field(default_factory=ChoiceDelta)
    finish_reason: Optional[StrictStr] = None
    logprobs: Optional[Dict[str, Any]] = None


class ModelData(BaseModel):
    """OpenAI model info response."""

    id: StrictStr
    object: StrictStr = "model"
    created: StrictInt = int(time.time())
    owned_by: StrictStr = "llm4free"
    permission: Optional[List[Dict[str, Any]]] = None
    root: Optional[StrictStr] = None
    parent: Optional[StrictStr] = None


class ModelList(BaseModel):
    """OpenAI model list response."""

    data: List[ModelData]
    object: StrictStr = "list"


# @dataclass
# class EmbeddingData(BaseModel):
#     """Single embedding data."""
#     embedding: List[float]
#     index: int
#     object: str = "embedding"

# @dataclass
# class EmbeddingResponse(BaseModel):
#     """OpenAI embeddings response."""
#     data: List[EmbeddingData]
#     model: str
#     usage: CompletionUsage
#     object: str = "list"

# @dataclass
# class FineTuningJob(BaseModel):
#     """OpenAI fine-tuning job."""
#     id: str
#     model: str
#     created_at: int
#     status: str
#     training_file: str
#     hyperparameters: Dict[str, Any]
#     object: str = "fine_tuning.job"
#     finished_at: Optional[int] = None
#     validation_file: Optional[str] = None
#     trained_tokens: Optional[int] = None
#     result_files: Optional[List[str]] = None
#     organization_id: Optional[str] = None

# @dataclass
# class FineTuningJobList(BaseModel):
#     """OpenAI fine-tuning job list response."""
#     data: List[FineTuningJob]
#     object: str = "list"
#     has_more: bool = False

# @dataclass
# class File(BaseModel):
#     """OpenAI file."""
#     id: str
#     bytes: int
#     created_at: int
#     filename: str
#     purpose: str
#     object: str = "file"
#     status: str = "uploaded"
#     status_details: Optional[str] = None

# @dataclass
# class FileList(BaseModel):
#     """OpenAI file list response."""
#     data: List[File]
#     object: str = "list"

# @dataclass
# class DeletedObject(BaseModel):
#     """OpenAI deleted object response."""
#     id: str
#     object: str = "deleted_object"
#     deleted: bool = True

# @dataclass
# class ImageData(BaseModel):
#     """OpenAI generated image."""
#     url: Optional[str] = None
#     b64_json: Optional[str] = None
#     revised_prompt: Optional[str] = None

# @dataclass
# class ImageResponse(BaseModel):
#     """OpenAI image generation response."""
#     data: List[ImageData]
#     created: int = int(time.time())


class ChatCompletion(BaseModel):
    """Chat completion response - OpenAI SDK compatible."""

    model: StrictStr
    choices: List[Choice]
    id: StrictStr = Field(default_factory=lambda: f"chatcmpl-{str(uuid.uuid4())}")
    created: StrictInt = Field(default_factory=lambda: int(time.time()))
    object: StrictStr = "chat.completion"
    system_fingerprint: Optional[StrictStr] = None
    usage: Optional[CompletionUsage] = None

    def __getitem__(self, key):
        """Allow dict-like access."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Allow dict-like assignment."""
        setattr(self, key, value)

    def keys(self):
        """Return dict-like keys."""
        return self.__dict__.keys()

    def values(self):
        """Return dict-like values."""
        return self.__dict__.values()

    def items(self):
        """Return dict-like items."""
        return self.__dict__.items()

    def get(self, key, default=None):
        """Dict-like get method with default value."""
        return getattr(self, key, default)


class ChatCompletionChunk(BaseModel):
    """Streaming chat completion response chunk - OpenAI SDK compatible."""

    model: StrictStr
    choices: List[Choice]
    id: StrictStr = Field(default_factory=lambda: f"chatcmpl-{str(uuid.uuid4())}")
    created: StrictInt = Field(default_factory=lambda: int(time.time()))
    object: StrictStr = "chat.completion.chunk"
    system_fingerprint: Optional[StrictStr] = None
    usage: Optional[Dict[str, Any]] = None  # Add usage field for streaming chunks

    def __getitem__(self, key):
        """Allow dict-like access."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Allow dict-like assignment."""
        setattr(self, key, value)

    def keys(self):
        """Return dict-like keys."""
        return self.__dict__.keys()

    def values(self):
        """Return dict-like values."""
        return self.__dict__.values()

    def items(self):
        """Return dict-like items."""
        return self.__dict__.items()

    def get(self, key, default=None):
        """Dict-like get method with default value."""
        return getattr(self, key, default)


# --- Helper Functions ---


def format_prompt(
    messages: List[Dict[str, Any]],
    add_special_tokens: bool = False,
    do_continue: bool = False,
    include_system: bool = True,
) -> str:
    """
    Format a series of messages into a single string, optionally adding special tokens.

    Args:
        messages: A list of message dictionaries, each containing 'role' and 'content'.
        add_special_tokens: Whether to add special formatting tokens.
        do_continue: If True, don't add the final "Assistant:" prompt.
        include_system: Whether to include system messages in the formatted output.

    Returns:
        A formatted string containing all messages.
    """

    # Helper function to convert content to string
    def to_string(value) -> str:
        if isinstance(value, str):
            return value
        elif isinstance(value, dict):
            if "text" in value:
                return value.get("text", "")
            return ""
        elif isinstance(value, list):
            return "".join([to_string(v) for v in value])
        return str(value)

    # If there's only one message and no special tokens needed, just return its content
    if not add_special_tokens and len(messages) <= 1:
        return to_string(messages[0]["content"])

    # Filter and process messages
    processed_messages = [
        (message["role"], to_string(message["content"]))
        for message in messages
        if include_system or message.get("role") != "system"
    ]

    # Format each message as "Role: Content"
    formatted = "\n".join(
        [
            f"{role.capitalize()}: {content}"
            for role, content in processed_messages
            if content.strip()
        ]
    )

    # Add final prompt for assistant if needed
    if do_continue:
        return formatted

    return f"{formatted}\nAssistant:"


def get_system_prompt(messages: List[Dict[str, Any]]) -> str:
    """
    Extract and concatenate all system messages.

    Args:
        messages: A list of message dictionaries.

    Returns:
        A string containing all system messages concatenated with newlines.
    """
    return "\n".join([m["content"] for m in messages if m["role"] == "system"])


def get_last_user_message(messages: List[Dict[str, Any]]) -> str:
    """
    Get the content of the last user message in the conversation.

    Args:
        messages: A list of message dictionaries.

    Returns:
        The content of the last user message as a string.
    """
    for message in reversed(messages):
        if message["role"] == "user":
            if isinstance(message["content"], str):
                return message["content"]
            # Handle complex content structures
            if isinstance(message["content"], dict) and "text" in message["content"]:
                return message["content"]["text"]
            if isinstance(message["content"], list):
                text_parts = []
                for part in message["content"]:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                return "".join(text_parts)
    return ""


# --- Token Counter ---


def count_tokens(text_or_messages: Any) -> int:
    """
    Count tokens in a string or a list of messages using tiktoken.

    Args:
        text_or_messages: A string or a list of messages (string or any type).

    Returns:
        int: Number of tokens.
    """
    import tiktoken

    if isinstance(text_or_messages, str):
        enc = tiktoken.encoding_for_model("gpt-4o")
        return len(enc.encode(text_or_messages))
    elif isinstance(text_or_messages, list):
        enc = tiktoken.encoding_for_model("gpt-4o")
        total = 0
        for m in text_or_messages:
            if isinstance(m, str):
                total += len(enc.encode(m))
            else:
                total += len(enc.encode(str(m)))
        return total
    else:
        return 0
