import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    TypedDict,
    Union,
    cast,
    overload,
)

from curl_cffi import requests
from litprinter import ic

from llm4free.AIbase import ModelList, SimpleModelList

# Import the utils for response structures
from llm4free.llm.utils import ChatCompletion, ChatCompletionChunk
from llm4free.model_fetcher import BackgroundModelFetcher

DEFAULT_TIMEOUT = (10.0, 30.0)  # (connect, read) in seconds


# Define tool-related structures
class ToolDefinition(TypedDict):
    """Definition of a tool that can be called by the AI"""

    type: str
    function: Dict[str, Any]


class FunctionParameters(TypedDict):
    """Parameters for a function"""

    type: str
    properties: Dict[str, Dict[str, Any]]
    required: List[str]


class FunctionDefinition(TypedDict):
    """Definition of a function that can be called by the AI"""

    name: str
    description: str
    parameters: FunctionParameters


@dataclass
class Tool:
    """Tool class that can be passed to the provider"""

    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]]
    required_params: Optional[List[str]] = None
    implementation: Optional[Callable] = None

    def to_dict(self) -> ToolDefinition:
        """Convert to OpenAI tool definition format"""
        function_def = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required_params or list(self.parameters.keys()),
            },
        }

        return {"type": "function", "function": function_def}

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool with the given arguments"""
        if not self.implementation:
            return f"Tool '{self.name}' does not have an implementation."

        try:
            return self.implementation(**arguments)
        except Exception as e:
            ic.configureOutput(prefix="ERROR| ")
            ic(f"Error executing tool '{self.name}': {str(e)}")
            return f"Error executing tool '{self.name}': {str(e)}"


class BaseCompletions(ABC):
    @overload
    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: Literal[True],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Generator[ChatCompletionChunk, None, None]: ...

    @overload
    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        stream: Literal[False] = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> ChatCompletion: ...

    @overload
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
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]: ...

    @abstractmethod
    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],  # Changed to Any to support complex message structures
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,  # Support for tool definitions
        tool_choice: Optional[
            Union[str, Dict[str, Any]]
        ] = None,  # Support for tool_choice parameter
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """
        Abstract method to create chat completions with tool support.

        Args:
            model: The model to use for completion
            messages: List of message dictionaries
            max_tokens: Maximum number of tokens to generate
            stream: Whether to stream the response
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            tools: List of tool definitions available for the model to use
            tool_choice: Control over which tool the model should use
            **kwargs: Additional model-specific parameters

        Returns:
            Either a completion object or a generator of completion chunks if streaming
        """
        raise NotImplementedError

    def format_tool_calls(self, tools: List[Union[Tool, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Convert tools to the format expected by the provider"""
        formatted_tools = []

        for tool in tools:
            if isinstance(tool, Tool):
                formatted_tools.append(tool.to_dict())
            elif isinstance(tool, dict):
                # Assume already formatted correctly
                formatted_tools.append(tool)
            else:
                ic.configureOutput(prefix="WARNING| ")
                ic(f"Skipping invalid tool type: {type(tool)}")

        return cast(List[Dict[str, Any]], formatted_tools)

    def process_tool_calls(
        self, tool_calls: List[Dict[str, Any]], available_tools: Dict[str, Tool]
    ) -> List[Dict[str, Any]]:
        """
        Process tool calls and execute the relevant tools.

        Args:
            tool_calls: List of tool calls from the model
            available_tools: Dictionary mapping tool names to their implementations

        Returns:
            List of results from executing the tools
        """
        results = []

        for call in tool_calls:
            try:
                function_call = call.get("function", {})
                tool_name = function_call.get("name")
                arguments_str = function_call.get("arguments", "{}")

                # Parse arguments
                try:
                    if isinstance(arguments_str, str):
                        arguments = json.loads(arguments_str)
                    else:
                        arguments = arguments_str
                except json.JSONDecodeError:
                    results.append(
                        {
                            "tool_call_id": call.get("id"),
                            "result": f"Error: Could not parse arguments JSON: {arguments_str}",
                        }
                    )
                    continue

                # Execute the tool if available
                if tool_name in available_tools:
                    tool_result = available_tools[tool_name].execute(arguments)
                    results.append({"tool_call_id": call.get("id"), "result": str(tool_result)})
                else:
                    results.append(
                        {
                            "tool_call_id": call.get("id"),
                            "result": f"Error: Tool '{tool_name}' not found.",
                        }
                    )
            except Exception as e:
                ic.configureOutput(prefix="ERROR| ")
                ic(f"Error processing tool call: {str(e)}")
                results.append(
                    {
                        "tool_call_id": call.get("id", "unknown"),
                        "result": f"Error processing tool call: {str(e)}",
                    }
                )

        return results

    _TOOL_INVOKE_RE = re.compile(
        r"<invoke>\s*<tool_name>(.*?)</tool_name>\s*<parameters>(.*?)</parameters>\s*</invoke>",
        re.DOTALL,
    )

    def format_tools_for_prompt(self, tools: Optional[List[Tool]] = None) -> str:
        """Format tool definitions as an XML instruction block for the prompt.

        Injects tool definitions as XML instructions so the model knows how
        to call tools using the ``<invoke>`` format.
        """
        tool_list = tools or []
        if not tool_list:
            return ""

        parts = [
            "# Tools",
            "",
            "You may call one or more functions to assist with the user query.",
            "",
            "For each function call, output EXACTLY the following XML block:",
            "",
            "<invoke>",
            "  <tool_name>$TOOL_NAME</tool_name>",
            "  <parameters>$JSON_ARGUMENTS</parameters>",
            "</invoke>",
            "",
            "Where `$JSON_ARGUMENTS` is a valid JSON object of arguments.",
            "Output one `<invoke>...</invoke>` block per tool call.",
            "If no tool is needed, respond normally without any `<invoke>` blocks.",
            "",
            "Here are the available tools:",
            "",
        ]

        for tool in tool_list:
            parts.append(f"## {tool.name}")
            parts.append(f"Description: {tool.description}")
            parts.append("Parameters:")
            if tool.parameters:
                for pname, pinfo in tool.parameters.items():
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    req = tool.required_params is None or pname in (tool.required_params or [])
                    tag = " (required)" if req else " (optional)"
                    parts.append(f"  - {pname} ({ptype}){tag}: {pdesc}")
            else:
                parts.append("  (none)")
            parts.append("")

        return "\n".join(parts)

    @staticmethod
    def extract_tool_calls(text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse ``<invoke>`` XML blocks from LLM response text.

        Returns:
            A list of ``{"name": ..., "arguments": ...}`` dicts, or ``None``
            when the response contains no tool calls.
        """
        calls: List[Dict[str, Any]] = []
        for match in BaseCompletions._TOOL_INVOKE_RE.finditer(text):
            name = match.group(1).strip()
            raw_args = match.group(2).strip()
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
            calls.append({"name": name, "arguments": args})
        return calls or None

    @staticmethod
    def format_tool_results_xml(results: List[Dict[str, Any]]) -> str:
        """Format tool results as ``<tool_result>`` XML blocks."""
        parts: List[str] = []
        for r in results:
            parts.append(
                f"<tool_result>\n"
                f"  <tool_name>{r['tool_name']}</tool_name>\n"
                f"  <result>{r['result']}</result>\n"
                f"</tool_result>"
            )
        return "\n".join(parts)

    def _run_non_native_tool_loop(
        self,
        original_create: Callable[..., Any],
        *,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Inject tool definitions as XML prompt, call the model once, and
        return a native OpenAI-format ``ChatCompletion`` with ``tool_calls``
        populated — exactly like a native tool-supporting provider would.

        The caller is responsible for executing the tools and making a
        follow-up call to get the final answer (standard OpenAI pattern).

        Args:
            original_create: The provider's actual ``create()`` method.
            model: Model name.
            messages: Conversation messages.
            tools: Tool definitions.
            stream: Disabled when tools are present.
            **kwargs: Extra arguments forwarded to ``original_create``.
        """
        # Parse tools into Tool objects
        from llm4free.llm.utils import ToolCall, ToolFunction

        tool_objects: List[Tool] = []
        for t in tools or []:
            if isinstance(t, Tool):
                tool_objects.append(t)
            elif isinstance(t, dict):
                fn = t.get("function", t)
                tool_objects.append(
                    Tool(
                        name=fn.get("name", "unknown"),
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}).get("properties", {}),
                        required_params=fn.get("parameters", {}).get("required"),
                    )
                )

        if stream:
            ic("stream=True is ignored in non-native tool loop")
            stream = False

        # Inject tool definitions into the first system message (or prepend one)
        tool_block = self.format_tools_for_prompt(tool_objects)
        working_messages = list(messages)
        if tool_block:
            if working_messages and working_messages[0].get("role") == "system":
                working_messages = list(working_messages)
                working_messages[0] = {
                    **working_messages[0],
                    "content": tool_block + "\n\n" + (working_messages[0].get("content") or ""),
                }
            else:
                working_messages = [{"role": "system", "content": tool_block}, *working_messages]

        response = original_create(
            model=model,
            messages=working_messages,
            stream=False,
            tools=None,
            **kwargs,
        )

        text = ""
        if hasattr(response, "choices") and response.choices:
            msg = response.choices[0].message
            text = msg.content if hasattr(msg, "content") else (msg.get("content") or "")
        elif isinstance(response, dict):
            text = (response.get("choices") or [{}])[0].get("message", {}).get("content", "")

        calls = self.extract_tool_calls(text)
        if not calls:
            return response

        # Build native ToolCall list
        tool_calls: List[ToolCall] = []
        for call in calls:
            tool_calls.append(
                ToolCall(
                    id=f"call_{uuid.uuid4().hex}",
                    type="function",
                    function=ToolFunction(
                        name=call["name"],
                        arguments=json.dumps(call["arguments"]),
                    ),
                )
            )

        # Return a new ChatCompletion with native tool_calls format
        import copy

        from llm4free.llm.utils import ChatCompletion, ChatCompletionMessage, Choice

        orig_choice = response.choices[0]
        new_message = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=tool_calls,
        )
        new_choice = Choice(
            index=0,
            message=new_message,
            finish_reason="tool_calls",
            logprobs=getattr(orig_choice, "logprobs", None),
        )
        return ChatCompletion(
            id=getattr(response, "id", f"chatcmpl-{uuid.uuid4().hex}"),
            choices=[new_choice],
            created=getattr(response, "created", int(time.time())),
            model=getattr(response, "model", model),
            usage=getattr(response, "usage", None),
            system_fingerprint=getattr(response, "system_fingerprint", None),
        )


class BaseChat(ABC):
    completions: BaseCompletions


class OpenAICompatibleProvider(ABC):
    """
    Abstract Base Class for providers mimicking the OpenAI Python client structure.
    Requires a nested 'chat.completions' structure with tool support.
    Users can provide their own proxies via the proxies parameter.
    """

    chat: BaseChat
    available_tools: Dict[str, Tool] = {}  # Dictionary of available tools
    supports_tools: bool = False  # Whether the provider supports tools
    supports_tool_choice: bool = False  # Whether the provider supports tool_choice
    required_auth: bool = False  # Whether the provider requires authentication

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)

        if cls.supports_tools:
            return

        orig_init = cls.__init__

        @wraps(orig_init)
        def _non_native_init(self, *args: Any, **kwargs: Any) -> None:
            orig_init(self, *args, **kwargs)
            completions = getattr(getattr(self, "chat", None), "completions", None)
            if completions is None:
                return
            original_create = completions.create

            @wraps(original_create)
            def _tool_aware_create(*a: Any, **kw: Any) -> Any:
                tools = kw.get("tools")
                if tools is not None:
                    kw.pop("tools", None)
                    # tool_choice is irrelevant in the XML loop
                    kw.pop("tool_choice", None)
                    return completions._run_non_native_tool_loop(
                        original_create,
                        *a,
                        tools=tools,
                        **kw,
                    )
                return original_create(*a, **kw)

            completions.create = _tool_aware_create

        cls.__init__ = _non_native_init  # type: ignore

    def __init__(
        self,
        api_key: Optional[str] = None,
        tools: Optional[List[Tool]] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ):
        self.available_tools = {}
        if tools:
            self.register_tools(tools)
        self.proxies = proxies or {}
        self.session = requests.Session()
        self.session.timeout = DEFAULT_TIMEOUT
        if self.proxies:
            self.session.proxies.update(cast(Any, self.proxies))
        # raise NotImplementedError  # <-- Commented out for metaclass test

    @property
    @abstractmethod
    def models(self) -> ModelList:
        """
        Property that returns an object with a .list() method returning available models.
        Subclasses must implement this property.
        """
        raise NotImplementedError

    def register_tools(self, tools: List[Tool]) -> None:
        """
        Register tools with the provider.

        Args:
            tools: List of Tool objects to register
        """
        for tool in tools:
            self.available_tools[tool.name] = tool

    def _start_background_model_fetch(self, api_key: Optional[str] = None) -> None:
        """Start non-blocking background fetch of available models.

        Fetches models from the provider's API in a background thread and caches
        the result. Immediately returns and allows initialization to continue.

        Args:
            api_key: Optional API key for authentication during model fetch.
        """
        # Use class name as provider identifier for caching
        provider_name = self.__class__.__name__

        # Define the fetch function that will run in the background
        def fetch_models() -> List[str]:
            """Fetch models via the classmethod and update cache/class var."""
            try:
                get_models_func = cast(
                    Callable[[Optional[str]], List[str]],
                    getattr(self.__class__, "get_models", None),
                )
                if get_models_func is not None:
                    models = get_models_func(api_key)
                    if models and isinstance(models, list):
                        # Also call update_available_models if available to update
                        # the class variable
                        update_func = cast(
                            Callable[[Optional[str]], None],
                            getattr(self.__class__, "update_available_models", None),
                        )
                        if update_func is not None:
                            update_func(api_key)
                        return models
            except Exception as e:
                ic(f"Failed to fetch models for {provider_name}: {e}")
            return []

        # Get current available models as fallback
        fallback_models = getattr(self.__class__, "AVAILABLE_MODELS", [])

        # Start async fetch
        fetcher = BackgroundModelFetcher()
        fetcher.fetch_async(
            provider_name=provider_name,
            fetch_func=fetch_models,
            fallback_models=list(fallback_models) if fallback_models else [],
        )

    def get_tool_by_name(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self.available_tools.get(name)

    def format_tool_response(
        self, messages: List[Dict[str, Any]], tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Format tool results as messages to be sent back to the provider.

        Args:
            messages: The original messages
            tool_results: Results from executing tools

        Returns:
            Updated message list with tool results
        """
        updated_messages = messages.copy()

        # Find the assistant message with tool calls
        for i, msg in enumerate(reversed(updated_messages)):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                # For each tool result, add a tool message
                for result in tool_results:
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": result["result"],
                    }
                    updated_messages.append(tool_message)
                break

        return updated_messages
