import inspect
import json
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, TypeAlias, Union

from litprinter import ic

# Type alias to allow both dict and SearchResponse for last_response
ResponseType: TypeAlias = Union[Dict[str, Any], "SearchResponse"]
# Backward-compatible alias for existing code
Response = ResponseType


# ──────────────────────────────────────────────────────────────────────
#  Response wrapper
# ──────────────────────────────────────────────────────────────────────


class SearchResponse:
    """Wrapper class for search API responses.

    Attributes:
        text: The text content of the response.
    """

    def __init__(self, text: str):
        self.text = text

    def __str__(self):
        return self.text

    def __repr__(self):
        return self.text


class AIProviderError(Exception):
    pass


# ──────────────────────────────────────────────────────────────────────
#  Model list helpers
# ──────────────────────────────────────────────────────────────────────


class ModelList(ABC):
    @abstractmethod
    def list(self) -> List[str]:
        """Return a list of available models."""
        raise NotImplementedError


class SimpleModelList(ModelList):
    def __init__(self, models: List[str]):
        self._models = models

    def list(self) -> List[str]:
        return self._models


# ──────────────────────────────────────────────────────────────────────
#  Tool definition
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Tool:
    """Tool definition for function calling.

    Attributes:
        name: The tool/function name.
        description: What the tool does.
        parameters: Parameter definitions as ``{name: {type, description, ...}}``.
        required_params: Required parameter names.  Defaults to all parameters.
        implementation: Optional callable that executes the tool.

    Example::

        >>> def get_weather(city: str) -> str:
        ...     return f"Weather in {city}: Sunny, 75F"
        >>> tool = Tool(
        ...     name="get_weather",
        ...     description="Get current weather for a city",
        ...     parameters={"city": {"type": "string", "description": "City name"}},
        ...     implementation=get_weather,
        ... )
        >>> tool.execute({"city": "London"})
        'Weather in London: Sunny, 75F'
    """

    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required_params: Optional[List[str]] = None
    implementation: Optional[Callable[..., Any]] = None

    # -- serialisation -------------------------------------------------- #

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI-compatible tool definition format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required_params or list(self.parameters.keys()),
                },
            },
        }

    # -- execution ------------------------------------------------------ #

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool with the given arguments."""
        if not self.implementation:
            return f"Tool '{self.name}' does not have an implementation."
        try:
            return self.implementation(**arguments)
        except Exception as e:
            return f"Error executing tool '{self.name}': {e}"


# ──────────────────────────────────────────────────────────────────────
#  Provider base class
# ──────────────────────────────────────────────────────────────────────


class Provider(ABC):
    """Base class for all normal (non-OpenAI-compatible) LLM4Free providers.

    Subclasses must implement :meth:`ask` and :meth:`get_message`.

    The :meth:`chat` method is **not** abstract — it provides an automatic
    tool-calling loop out of the box.  When *tools* are supplied it:

    1. Injects tool definitions into the prompt (XML format).
    2. Calls :meth:`ask` to get the raw response.
    3. Extracts ``<invoke>`` blocks from the response.
    4. Executes matching tools and feeds ``<tool_result>`` back.
    5. Repeats until the model returns plain text (up to *max_tool_rounds*).
    """

    required_auth: bool = False
    conversation: Any

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)

        chat = cls.__dict__.get("chat")
        if chat is None:
            return

        wrapped_params = ("tools", "tool_choice", "max_tool_rounds")
        try:
            chat_params = set(inspect.signature(chat).parameters)
        except (TypeError, ValueError):
            chat_params = set()

        if chat_params.intersection(wrapped_params):
            return

        @wraps(chat)
        def wrapped_chat(self, *args: Any, **kwargs: Any) -> Any:
            tools = kwargs.get("tools")
            tool_choice = kwargs.get("tool_choice")
            if tools or tool_choice is not None or self.available_tools:
                return Provider.chat(self, *args, **kwargs)
            return chat(self, *args, **kwargs)

        setattr(cls, "chat", wrapped_chat)

    def __init__(self, *args: Any, **kwargs: Any):
        self._last_response: ResponseType = {}
        self.conversation: Any = None
        self.available_tools = {}

    @property
    def available_tools(self) -> Dict[str, Tool]:
        tools = self.__dict__.get("_available_tools")
        if tools is None:
            tools = {}
            self.__dict__["_available_tools"] = tools
        return tools

    @available_tools.setter
    def available_tools(self, value: Dict[str, Tool]) -> None:
        self.__dict__["_available_tools"] = value

    # -- last_response property ----------------------------------------- #

    @property
    def last_response(self) -> ResponseType:
        return self._last_response

    @last_response.setter
    def last_response(self, value: ResponseType):
        self._last_response = value

    # ══════════════════════════════════════════════════════════════════ #
    #  Tool helpers  (used by chat() and can be used directly)
    # ══════════════════════════════════════════════════════════════════ #

    def register_tools(self, tools: List[Tool]) -> None:
        """Register tools available for function calling."""
        for tool in tools:
            self.available_tools[tool.name] = tool

    # ── XML prompt formatting ────────────────────────────────────────── #

    _TOOL_INVOKE_RE = re.compile(
        r"<invoke>\s*<tool_name>(.*?)</tool_name>\s*<parameters>(.*?)</parameters>\s*</invoke>",
        re.DOTALL,
    )

    def format_tools_for_prompt(self, tools: Optional[List[Tool]] = None) -> str:
        """Format tool definitions as an XML instruction block for the prompt.

        This tells the model *how* to call tools using the ``<invoke>`` XML
        format.  The model is instructed to output one or more ``<invoke>``
        blocks when it wants to use a tool, and to respond normally otherwise.
        """
        tool_list = tools or list(self.available_tools.values())
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
            "Emit the block directly: do not wrap it in `<tool_call>`, markdown",
            "fences, or any other tags, and do not add commentary inside it.",
            "If no tool is needed, respond normally without any `<invoke>` blocks.",
            "",
            "Example:",
            '<invoke><tool_name>TOOL_NAME</tool_name><parameters>{"argument": "value"}</parameters></invoke>',
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

    # ── XML parsing ──────────────────────────────────────────────────── #

    def extract_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse ``<invoke>`` blocks from LLM response text.

        Returns:
            A list of ``{"name": ..., "arguments": ...}`` dicts, or ``None``
            when the response contains no tool calls.
        """
        calls: List[Dict[str, Any]] = []
        for match in self._TOOL_INVOKE_RE.finditer(text):
            name = match.group(1).strip()
            raw_args = match.group(2).strip()
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                args = {}
            calls.append({"name": name, "arguments": args})
        return calls or None

    # ── Execution ────────────────────────────────────────────────────── #

    def process_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tool calls and return result dicts.

        Each result dict has keys: ``tool_name``, ``arguments``, ``result``.
        """
        results: List[Dict[str, Any]] = []
        for call in tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    results.append(
                        {
                            "tool_name": name,
                            "arguments": args,
                            "result": f"Error: could not parse arguments: {args}",
                        }
                    )
                    continue
            if name in self.available_tools:
                result = self.available_tools[name].execute(args)
            else:
                result = f"Error: tool '{name}' not found."
            results.append(
                {
                    "tool_name": name,
                    "arguments": args,
                    "result": str(result),
                }
            )
        return results

    @staticmethod
    def format_tool_results_xml(results: List[Dict[str, Any]]) -> str:
        """Format tool results as ``<tool_result>`` XML blocks.

        This is the text you would append to the conversation so the model
        can see tool outputs and continue.
        """
        parts: List[str] = []
        for r in results:
            parts.append(
                f"<tool_result>\n"
                f"  <tool_name>{r['tool_name']}</tool_name>\n"
                f"  <result>{r['result']}</result>\n"
                f"</tool_result>"
            )
        return "\n".join(parts)

    # ══════════════════════════════════════════════════════════════════ #
    #  The auto tool-calling loop  (used inside chat)
    # ══════════════════════════════════════════════════════════════════ #

    def run_tool_loop(
        self,
        prompt: str,
        *,
        tools: Optional[List[Tool]] = None,
        max_rounds: int = 5,
        stream: bool = False,
        raw: bool = False,
        optimizer: Optional[str] = None,
        conversationally: bool = False,
        **ask_kwargs: Any,
    ) -> Any:
        """Run the full tool-calling loop and return the final text response.

        This is the method :meth:`chat` delegates to when *tools* are present.

        Flow (mirrors the OpenAI Response API)::

            1. Inject tool definitions into the prompt
            2. Call ``ask()``  →  get raw response
            3. Parse ``<invoke>`` blocks from the response
            4. If none found →  return the text as final answer
            5. Execute tools →  format ``<tool_result>`` blocks
            6. Append results to prompt →  go to step 2
            7. Repeat up to *max_rounds*
        """
        # Merge per-request tools with instance tools
        if tools:
            self.register_tools(tools)

        tool_list = list(self.available_tools.values())
        tool_block = self.format_tools_for_prompt(tool_list)

        # Streaming + tools is not supported in the auto-loop because we
        # need to inspect the full response before continuing.
        if stream:
            ic("stream=True is ignored when tools are present (auto-loop)")
            stream = False

        conversation = getattr(self, "conversation", None)
        conversation_prompt = conversation.gen_complete_prompt(prompt) if conversation else prompt
        if tool_block:
            conversation_prompt = tool_block + "\n\n" + conversation_prompt

        response: Any = None
        for _ in range(max_rounds):
            response = self.ask(
                conversation_prompt,
                stream=False,
                raw=raw,
                optimizer=optimizer,
                conversationally=conversationally,
                **ask_kwargs,
            )
            text = self.get_message(response)
            calls = self.extract_tool_calls(text)

            if not calls:
                # No tool calls — this is the final answer
                return response

            # Execute tools
            results = self.process_tool_calls(calls)

            # Feed results back
            result_xml = self.format_tool_results_xml(results)
            conversation_prompt += f"\n\n{text}\n\n{result_xml}"

            # Track in structured conversation history
            if conversation and hasattr(conversation, "add_tool_call_result"):
                for r in results:
                    conversation.add_tool_call_result(r["tool_name"], r["arguments"], r["result"])

        # Exhausted max_rounds — return last response
        return response if response is not None else ""

    # ══════════════════════════════════════════════════════════════════ #
    #  Public chat interface
    # ══════════════════════════════════════════════════════════════════ #

    def chat(
        self,
        prompt: str,
        stream: bool = False,
        optimizer: Optional[str] = None,
        conversationally: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Generate a response, automatically handling tool calls.

        When *tools* are supplied the method runs an internal loop:
        call model → parse ``<invoke>`` → execute tools → feed
        ``<tool_result>`` back → repeat until the model returns plain text.

        When *tools* is ``None`` it falls back to a simple ``ask()`` +
        ``get_message()`` call (the legacy behaviour).

        Args:
            prompt: User prompt.
            stream: Stream the response (disabled when tools are present).
            optimizer: Prompt optimizer name.
            conversationally: Use optimizer conversationally.
            tools: Tools the model can call.
            tool_choice: Reserved for future use.
            max_tool_rounds: Maximum tool-calling iterations.
            **kwargs: Forwarded to ``ask()`` (e.g. ``raw``).
        """
        raw = kwargs.pop("raw", False)
        tools = kwargs.pop("tools", None)
        kwargs.pop("tool_choice", None)
        max_tool_rounds = kwargs.pop("max_tool_rounds", 5)

        if tools or self.available_tools:
            # --- auto tool-calling path -------------------------------- #
            result = self.run_tool_loop(
                prompt,
                tools=tools,
                max_rounds=max_tool_rounds,
                stream=False,
                raw=raw,
                optimizer=optimizer,
                conversationally=conversationally,
                **kwargs,
            )
            return result if raw else self.get_message(result)

        # --- legacy (no tools) path ------------------------------------ #
        if stream:

            def _stream() -> Generator[Any, None, None]:
                ask_result = self.ask(
                    prompt,
                    stream=True,
                    raw=raw,
                    optimizer=optimizer,
                    conversationally=conversationally,
                    **kwargs,
                )
                if isinstance(ask_result, Generator):
                    for chunk in ask_result:
                        yield chunk if raw else self.get_message(chunk)
                else:
                    # Non-streaming result returned even when stream=True
                    yield ask_result if raw else self.get_message(ask_result)

            return _stream()

        result = self.ask(
            prompt,
            stream=False,
            raw=raw,
            optimizer=optimizer,
            conversationally=conversationally,
            **kwargs,
        )
        return result if raw else self.get_message(result)

    # ══════════════════════════════════════════════════════════════════ #
    #  Abstract methods  (subclasses must implement)
    # ══════════════════════════════════════════════════════════════════ #

    @abstractmethod
    def ask(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        optimizer: Optional[str] = None,
        conversationally: bool = False,
        **kwargs: Any,
    ) -> Union[Response, Generator[Response, None, None]]:
        """Make a raw API call and return the provider-specific response."""
        raise NotImplementedError

    @abstractmethod
    def get_message(self, response: Any) -> str:
        """Extract the text message from a raw response."""
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────
#  TTS / STT / Search base classes  (unchanged)
# ──────────────────────────────────────────────────────────────────────


class TTSProvider(ABC):
    @abstractmethod
    def tts(
        self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs: Any
    ) -> str:
        """Convert text to speech and save to a temporary file.

        Returns:
            Path to the generated audio file.
        """
        raise NotImplementedError

    def save_audio(
        self, audio_file: str, destination: Optional[str] = None, verbose: bool = False
    ) -> str:
        """Save audio to a specific destination."""
        import os
        import shutil
        import time

        source_path = Path(audio_file)
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        if destination is None:
            timestamp = int(time.time())
            destination = os.path.join(os.getcwd(), f"tts_audio_{timestamp}{source_path.suffix}")

        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.copy2(source_path, destination)

        if verbose:
            print(f"[debug] Audio saved to {destination}")
        return destination

    def stream_audio(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        instructions: Optional[str] = None,
        chunk_size: int = 1024,
        verbose: bool = False,
    ) -> Generator[bytes, None, None]:
        """Stream audio in chunks."""
        audio_file = self.tts(text, voice=voice, verbose=verbose)
        with open(audio_file, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk


class STTProvider(ABC):
    """Abstract base class for Speech-to-Text providers."""

    @abstractmethod
    def transcribe(self, audio_path: Union[str, Path], **kwargs: Any) -> Dict[str, Any]:
        """Transcribe audio file to text."""
        raise NotImplementedError

    @abstractmethod
    def transcribe_from_url(self, audio_url: str, **kwargs: Any) -> Dict[str, Any]:
        """Transcribe audio from URL to text."""
        raise NotImplementedError


class AISearch(ABC):
    """Abstract base class for AI-powered search providers."""

    @property
    def last_response(self) -> ResponseType:
        """Last response from search, can be dict or SearchResponse."""
        return self._last_response

    @last_response.setter
    def last_response(self, value: ResponseType):
        self._last_response = value

    @abstractmethod
    def search(
        self,
        prompt: str,
        stream: bool = False,
        raw: bool = False,
        **kwargs: Any,
    ) -> Union[
        SearchResponse,
        Generator[Union[Dict[str, str], SearchResponse], None, None],
        List[Any],
        Dict[str, Any],
        str,
    ]:
        """Search using the provider's API and get AI-generated responses."""
        raise NotImplementedError
