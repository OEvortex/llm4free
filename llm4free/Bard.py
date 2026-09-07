import asyncio
import hashlib
import json
import os
import random
import re
import string
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, TypedDict, Union, cast
from urllib.parse import quote_plus, unquote_plus

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, field_validator
from requests.exceptions import HTTPError, RequestException, Timeout
from rich.console import Console

from llm4free.browser_requests import get_args_from_cdp

console = Console()

# Patterns from g4f Gemini provider for parsing page metadata
XSRF_PATTERN = re.compile(r'SNlM0e(?:\\?"|"):\\?"(.*?)(?:\\?"|")')
BUILD_LABEL_PATTERN = re.compile(r"boq_assistant-bard-web-server_[A-Za-z0-9_.-]+")
SID_PATTERN = re.compile(r'FdrFJe(?:\\?"|"):\\?"([\d-]+)(?:\\?"|")')
PUSH_ID_PATTERN = re.compile(r'qKIAYe(?:\\?"|"):\\?"(.*?)(?:\\?"|")')

# Model registry aligned with g4f's known Gemini models
MODELS = {
    "gemini-3.6-flash": {"mode": 1},
    "gemini-3.5-flash": {"mode": 1},
    "gemini-3.5-flash-lite": {"mode": 6},
    "gemini-3.1-pro": {"mode": 3},
    "gemini-2.5-flash": {"mode": 1},
    "gemini-2.5-pro": {"mode": 3},
    "gemini-2.0-flash": {"mode": 1},
    "gemini-2.0-pro": {"mode": 3},
    "gemini-1.5-flash": {"mode": 1},
    "gemini-1.5-pro": {"mode": 3},
}

MODEL_ALIASES = {
    "gemini-2.0": "gemini-3.6-flash",
    "gemini-2.0-flash": "gemini-3.6-flash",
    "gemini-2.0-flash-thinking": "gemini-3.6-flash",
    "gemini-2.0-flash-thinking-with-apps": "gemini-3.6-flash",
    "gemini-2.5-flash": "gemini-3.6-flash",
    "gemini-2.5-pro": "gemini-3.1-pro",
    "gemini-3.1-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.5-flash": "gemini-3.6-flash",
    "gemini-3.5-flash-thinking": "gemini-3.6-flash",
    "gemini-3.6-flash-thinking": "gemini-3.6-flash",
    "gemini-auto": "gemini-3.6-flash",
    "gemini-3.5-flash-thinking-lite": "gemini-3.5-flash-lite",
    "gemini-3.5-flash-lite-thinking": "gemini-3.5-flash-lite",
    "gemini-flash-lite": "gemini-3.5-flash-lite",
    **{key: key for key in MODELS.keys()},
}


def _make_sapisid_hash(cookies: Dict[str, str]) -> Optional[str]:
    """Create SAPISIDHASH authorization header from cookies."""
    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-1PAPISID")
    if not sapisid:
        return None
    timestamp = int(time.time())
    digest = hashlib.sha1(
        f"{timestamp} {sapisid} https://gemini.google.com".encode()
    ).hexdigest()
    return f"SAPISIDHASH {timestamp}_{digest}"


def _iter_wrb_payloads(value: Any) -> Iterator[str]:
    """Iterate over WRB payloads in a nested response structure."""
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, list) or not item:
            continue
        first = item[0]
        if isinstance(first, str) and first.startswith("wrb.fr"):
            # Authenticated format: "wrb.fr,[...]" or "wrb.fr,[...]"
            payload = first[len("wrb.fr"):]
            if payload.startswith(","):
                payload = payload[1:]
            if payload:
                yield payload
                return
            # Anonymous format: ["wrb.fr", null, "[...]"]
            if len(item) > 2 and isinstance(item[2], str):
                yield item[2]
                return
        yield from _iter_wrb_payloads(item)


def _extract_response_content(response_part: list) -> Optional[str]:
    """Extract text content from a response part."""
    try:
        parts = response_part[4]
    except (IndexError, TypeError):
        return None
    if not isinstance(parts, list):
        return None
    snapshots = []
    for part in parts:
        if not isinstance(part, list) or len(part) <= 1:
            continue
        values = part[1]
        if isinstance(values, str):
            snapshots.append(values)
        elif isinstance(values, list):
            snapshots.extend(value for value in values if isinstance(value, str))
    return snapshots[-1] if snapshots else None


def _extract_response_part(value: Any) -> Optional[list]:
    """Extract the best response part from WRB payloads."""
    response_parts = []
    for payload in _iter_wrb_payloads(value):
        try:
            response_part = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if isinstance(response_part, list):
            response_parts.append(response_part)
    for response_part in reversed(response_parts):
        if _extract_response_content(response_part) is not None:
            return response_part
    return response_parts[-1] if response_parts else None


class AskResponse(TypedDict):
    content: str
    conversation_id: str
    response_id: str
    factualityQueries: Optional[List[Any]]
    textQuery: str
    choices: List[Dict[str, Union[str, List[str]]]]
    images: List[Dict[str, str]]
    error: bool


class Endpoint(Enum):
    """
    Enum for Google Gemini API endpoints.

    Attributes:
        INIT (str): URL for initializing the Gemini session.
        GENERATE (str): URL for generating chat responses.
        ROTATE_COOKIES (str): URL for rotating authentication cookies.
        UPLOAD (str): URL for uploading files/images.
    """

    INIT = "https://gemini.google.com/app"
    GENERATE = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"
    ROTATE_COOKIES = "https://accounts.google.com/RotateCookies"
    UPLOAD = "https://content-push.googleapis.com/upload"


class Headers(Enum):
    """
    Enum for HTTP headers used in Gemini API requests.

    Attributes:
        GEMINI (dict): Headers for Gemini chat requests.
        ROTATE_COOKIES (dict): Headers for rotating cookies.
        UPLOAD (dict): Headers for file/image upload.
    """

    GEMINI = {
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "Host": "gemini.google.com",
        "Origin": "https://gemini.google.com",
        "Referer": "https://gemini.google.com/",
        "X-Same-Domain": "1",
    }
    ROTATE_COOKIES = {
        "Content-Type": "application/json",
    }
    UPLOAD = {"Push-ID": "feeds/mcudyrk2a4khkz"}


class Model(Enum):
    """
    Enum for available Gemini model configurations.

    Attributes:
        model_name (str): Name of the model.
        mode (int): Model mode value used in request[79].
        advanced_only (bool): Whether the model is available only for advanced users.
    """

    UNSPECIFIED = ("unspecified", 0, False)
    GEMINI_3_6_FLASH = ("gemini-3.6-flash", 1, False)
    GEMINI_3_5_FLASH = ("gemini-3.5-flash", 1, False)
    GEMINI_3_5_FLASH_LITE = ("gemini-3.5-flash-lite", 6, False)
    GEMINI_3_1_PRO = ("gemini-3.1-pro", 3, False)
    GEMINI_2_5_FLASH = ("gemini-2.5-flash", 1, False)
    GEMINI_2_5_PRO = ("gemini-2.5-pro", 3, False)
    GEMINI_2_0_FLASH = ("gemini-2.0-flash", 1, False)
    GEMINI_2_0_PRO = ("gemini-2.0-pro", 3, False)
    GEMINI_1_5_FLASH = ("gemini-1.5-flash", 1, False)
    GEMINI_1_5_PRO = ("gemini-1.5-pro", 3, False)

    def __init__(self, name: str, mode: int, advanced_only: bool):
        """
        Initialize a Model enum member.

        Args:
            name (str): Model name.
            mode (int): Model mode value for request field 79.
            advanced_only (bool): If True, model is for advanced users only.
        """
        self.model_name = name
        self.mode = mode
        self.advanced_only = advanced_only

    @classmethod
    def from_name(cls, name: str):
        """
        Get a Model enum member by its model name.

        Args:
            name (str): Name of the model.

        Returns:
            Model: Corresponding Model enum member.

        Raises:
            ValueError: If the model name is not found.
        """
        for model in cls:
            if model.model_name == name:
                return model
        raise ValueError(
            f"Unknown model name: {name}. Available models: {', '.join([model.model_name for model in cls])}"
        )

    @classmethod
    def resolve(cls, name: str) -> "Model":
        """Resolve a model name to a Model enum, falling back to UNSPECIFIED."""
        try:
            return cls.from_name(name)
        except ValueError:
            return cls.UNSPECIFIED


async def upload_file(
    file: Union[bytes, str, Path],
    proxy: Optional[Union[str, Dict[str, str]]] = None,
    impersonate: str = "chrome110",
) -> str:
    """
    Uploads a file to Google's Gemini server using curl_cffi and returns its identifier.

    Args:
        file (bytes | str | Path): File data in bytes or path to the file to be uploaded.
        proxy (str | dict, optional): Proxy URL or dictionary for the request.
        impersonate (str, optional): Browser profile for curl_cffi to impersonate. Defaults to "chrome110".

    Returns:
        str: Identifier of the uploaded file.

    Raises:
        HTTPError: If the upload request fails.
        RequestException: For other network-related errors.
        FileNotFoundError: If the file path does not exist.
    """
    if not isinstance(file, bytes):
        file_path = Path(file)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found at path: {file}")
        with open(file_path, "rb") as f:
            file_content = f.read()
    else:
        file_content = file

    proxies_dict = None
    if isinstance(proxy, str):
        proxies_dict = {"http": proxy, "https": proxy}
    elif isinstance(proxy, dict):
        proxies_dict = proxy

    try:
        async with AsyncSession(
            proxies=cast(Any, proxies_dict),
            impersonate=cast(Any, impersonate),
            headers=Headers.UPLOAD.value,
        ) as client:
            response = await client.post(
                url=Endpoint.UPLOAD.value,
                files={"file": file_content},
            )
            response.raise_for_status()
            return response.text
    except HTTPError as e:
        console.log(f"[red]HTTP error during file upload: {e.response.status_code} {e}[/red]")
        raise
    except (RequestException, CurlError) as e:
        console.log(f"[red]Network error during file upload: {e}[/red]")
        raise


def load_cookies(cookie_path: str) -> Tuple[str, str]:
    """
    Loads authentication cookies from a JSON file.

    Args:
        cookie_path (str): Path to the JSON file containing cookies.

    Returns:
        tuple[str, str]: Tuple containing __Secure-1PSID and __Secure-1PSIDTS cookie values.

    Raises:
        Exception: If the file is not found, invalid, or required cookies are missing.
    """
    try:
        with open(cookie_path, "r", encoding="utf-8") as file:
            cookies = json.load(file)
        session_auth1 = next(
            (item["value"] for item in cookies if item["name"].upper() == "__SECURE-1PSID"), None
        )
        session_auth2 = next(
            (item["value"] for item in cookies if item["name"].upper() == "__SECURE-1PSIDTS"), None
        )

        if not session_auth1 or not session_auth2:
            raise ValueError("Required cookies (__Secure-1PSID or __Secure-1PSIDTS) not found.")

        return session_auth1, session_auth2
    except FileNotFoundError:
        raise Exception(f"Cookie file not found at path: {cookie_path}")
    except json.JSONDecodeError:
        raise Exception("Invalid JSON format in the cookie file.")
    except StopIteration as e:
        raise Exception(f"{e} Check the cookie file format and content.")
    except Exception as e:
        raise Exception(f"An unexpected error occurred while loading cookies: {e}")


def _extract_bard_cookies(cookies: Dict[str, str]) -> Tuple[str, str]:
    """Extract ``__Secure-1PSID`` and ``__Secure-1PSIDTS`` from CDP cookies.

    Args:
        cookies: Cookie dict returned by :func:`llm4free.browser_requests.get_args_from_cdp`.

    Returns:
        Tuple of ``(__Secure-1PSID, __Secure-1PSIDTS)`` values.

    Raises:
        ValueError: If either required cookie is missing.
    """
    secure_1psid = cookies.get("__Secure-1PSID")
    secure_1psidts = cookies.get("__Secure-1PSIDTS")
    if not secure_1psid or not secure_1psidts:
        raise ValueError(
            "Required cookies (__Secure-1PSID or __Secure-1PSIDTS) not found in CDP cookies. "
            "If using a Chrome profile, make sure you're already logged into gemini.google.com."
        )
    return secure_1psid, secure_1psidts


class Chatbot:
    """
    Synchronous wrapper for the AsyncChatbot class.

    This class provides a synchronous interface to interact with Google Gemini,
    handling authentication, conversation management, and message sending.

    Attributes:
        loop (asyncio.AbstractEventLoop): Event loop for running async tasks.
        secure_1psid (str): Authentication cookie.
        secure_1psidts (str): Authentication cookie.
        async_chatbot (AsyncChatbot): Underlying asynchronous chatbot instance.
    """

    def __init__(
        self,
        cookie_path: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ):
        try:
            self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        self.secure_1psid, self.secure_1psidts = load_cookies(cookie_path)
        self.async_chatbot = self.loop.run_until_complete(
            AsyncChatbot.create(
                self.secure_1psid, self.secure_1psidts, proxy, timeout, model, impersonate
            )
        )

    def save_conversation(self, file_path: str, conversation_name: str):
        return self.loop.run_until_complete(
            self.async_chatbot.save_conversation(file_path, conversation_name)
        )

    def load_conversations(self, file_path: str) -> List[Dict]:
        return self.loop.run_until_complete(self.async_chatbot.load_conversations(file_path))

    def load_conversation(self, file_path: str, conversation_name: str) -> bool:
        return self.loop.run_until_complete(
            self.async_chatbot.load_conversation(file_path, conversation_name)
        )

    def ask(self, message: str, image: Optional[Union[bytes, str, Path]] = None) -> AskResponse:
        return self.loop.run_until_complete(self.async_chatbot.ask(message, image=image))

    @classmethod
    def from_cdp(
        cls,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        cdp_timeout: int = 120,
        profile_name: Optional[str] = None,
    ) -> "Chatbot":
        """Create a :class:`Chatbot` using CDP-harvested Gemini cookies.

        Opens a browser via :func:`llm4free.browser_requests.get_args_from_cdp`,
        navigates to ``https://gemini.google.com``, and extracts the required
        ``__Secure-1PSID`` / ``__Secure-1PSIDTS`` cookies automatically.

        Args:
            proxy: Optional proxy URL or dict forwarded to the CDP browser.
            timeout: Request timeout for Gemini API calls.
            model: Default model enum member.
            impersonate: Browser profile for ``curl_cffi`` requests.
            cdp_timeout: Max seconds to wait for the Gemini page to load.
            profile_name: Optional Chrome profile name or path to reuse login state.
                On this system, available profiles include ``"Profile 1"``
                and ``"Profile 2"``. When omitted, an isolated temporary
                browser state is used and Google login cookies may be missing.

        Returns:
            A ready-to-use :class:`Chatbot` instance.
        """
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        cdp_args = loop.run_until_complete(
            get_args_from_cdp(
                url="https://gemini.google.com",
                proxy=proxy if isinstance(proxy, str) else None,
                timeout=cdp_timeout,
                user_data_dir=profile_name,
            )
        )
        secure_1psid, secure_1psidts = _extract_bard_cookies(cdp_args["cookies"])

        instance = cls.__new__(cls)
        instance.loop = loop
        instance.secure_1psid = secure_1psid
        instance.secure_1psidts = secure_1psidts
        instance.async_chatbot = loop.run_until_complete(
            AsyncChatbot.create(
                secure_1psid, secure_1psidts, proxy, timeout, model, impersonate
            )
        )
        return instance

    @classmethod
    def from_cookies(
        cls,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ) -> "Chatbot":
        """Create a :class:`Chatbot` directly from Gemini auth cookies.

        This is the fastest path when you already have valid
        ``__Secure-1PSID`` and ``__Secure-1PSIDTS`` values.

        Returns:
            A ready-to-use :class:`Chatbot` instance.
        """
        instance = cls.__new__(cls)
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        instance.loop = loop
        instance.secure_1psid = secure_1psid
        instance.secure_1psidts = secure_1psidts
        instance.async_chatbot = loop.run_until_complete(
            AsyncChatbot.create(
                secure_1psid, secure_1psidts, proxy, timeout, model, impersonate
            )
        )
        return instance

    @classmethod
    def from_anonymous(
        cls,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ) -> "Chatbot":
        """Create a :class:`Chatbot` for anonymous usage without Google login.

        This mode uses Gemini's unauthenticated API. No cookies are required,
        but responses may be limited compared to authenticated mode.

        Returns:
            A ready-to-use :class:`Chatbot` instance.
        """
        instance = cls.__new__(cls)
        try:
            loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        instance.loop = loop
        instance.secure_1psid = ""
        instance.secure_1psidts = ""
        instance.async_chatbot = loop.run_until_complete(
            AsyncChatbot.create_anonymous(
                proxy=proxy,
                timeout=timeout,
                model=model,
                impersonate=impersonate,
            )
        )
        return instance


class AsyncChatbot:
    """
    Asynchronous chatbot client for interacting with Google Gemini using curl_cffi.

    This class manages authentication, session state, conversation history,
    and sending/receiving messages (including images) asynchronously.

    Attributes:
        headers (dict): HTTP headers for requests.
        _reqid (int): Request identifier for Gemini API.
        SNlM0e (str): Session token required for API requests.
        conversation_id (str): Current conversation ID.
        response_id (str): Current response ID.
        choice_id (str): Current choice ID.
        proxy (str | dict | None): Proxy configuration.
        proxies_dict (dict | None): Proxy dictionary for curl_cffi.
        secure_1psid (str): Authentication cookie.
        secure_1psidts (str): Authentication cookie.
        session (AsyncSession): curl_cffi session for HTTP requests.
        timeout (int): Request timeout in seconds.
        model (Model): Selected Gemini model.
        impersonate (str): Browser profile for curl_cffi to impersonate.
    """

    __slots__ = [
        "headers",
        "_reqid",
        "SNlM0e",
        "conversation_id",
        "response_id",
        "choice_id",
        "proxy",
        "proxies_dict",
        "secure_1psidts",
        "secure_1psid",
        "session",
        "timeout",
        "model",
        "impersonate",
        "_bl",
        "_sid",
        "_upload_push_id",
        "anonymous",
    ]

    def __init__(
        self,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        anonymous: bool = False,
    ):
        headers = Headers.GEMINI.value.copy()
        self._reqid = int("".join(random.choices(string.digits, k=7)))
        self.proxy = proxy
        self.impersonate = impersonate
        self.anonymous = anonymous

        self.proxies_dict = None
        if isinstance(proxy, str):
            self.proxies_dict = {"http": proxy, "https": proxy}
        elif isinstance(proxy, dict):
            self.proxies_dict = proxy

        self.conversation_id = ""
        self.response_id = ""
        self.choice_id = ""
        self.secure_1psid = secure_1psid
        self.secure_1psidts = secure_1psidts

        # Metadata extracted from Gemini page init
        self._bl = "boq_assistant-bard-web-server_20240625.13_p0"
        self._sid = None
        self._upload_push_id = "feeds/mcudyrk2a4khkz"
        self.SNlM0e = None

        # For anonymous mode, don't set auth cookies
        cookies = {} if anonymous else {"__Secure-1PSID": secure_1psid, "__Secure-1PSIDTS": secure_1psidts}

        self.session: AsyncSession = AsyncSession(
            headers=headers,
            cookies=cookies,
            proxies=cast(Any, self.proxies_dict if self.proxies_dict else None),
            timeout=timeout,
            impersonate=cast(Any, self.impersonate if self.impersonate else None),
        )

        self.timeout = timeout
        self.model = model

    @classmethod
    async def create(
        cls,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        anonymous: bool = False,
    ) -> "AsyncChatbot":
        """
        Factory method to create and initialize an AsyncChatbot instance.
        Fetches the necessary SNlM0e value asynchronously unless in anonymous mode.

        Args:
            anonymous: If True, skip authentication and work without cookies.
        """
        instance = cls(secure_1psid, secure_1psidts, proxy, timeout, model, impersonate, anonymous)
        if not anonymous:
            try:
                instance.SNlM0e = await instance.__get_snlm0e()
            except Exception as e:
                console.log(
                    f"[red]Error during AsyncChatbot initialization (__get_snlm0e): {e}[/red]",
                    style="bold red",
                )
                await instance.session.close()
                raise
        return instance

    @classmethod
    async def create_anonymous(
        cls,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ) -> "AsyncChatbot":
        """Create an :class:`AsyncChatbot` for anonymous usage without cookies.

        This mode uses Gemini's unauthenticated API endpoint. No Google login
        is required, but responses may be limited compared to authenticated mode.

        Returns:
            A ready-to-use :class:`AsyncChatbot` instance.
        """
        return await cls.create(
            secure_1psid="",
            secure_1psidts="",
            proxy=proxy,
            timeout=timeout,
            model=model,
            impersonate=impersonate,
            anonymous=True,
        )

    @classmethod
    async def create_from_cdp(
        cls,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        cdp_timeout: int = 120,
        profile_name: Optional[str] = None,
    ) -> "AsyncChatbot":
        """Create an :class:`AsyncChatbot` using CDP-harvested Gemini cookies.

        Opens a browser via :func:`llm4free.browser_requests.get_args_from_cdp`,
        navigates to ``https://gemini.google.com``, and extracts the required
        ``__Secure-1PSID`` / ``__Secure-1PSIDTS`` cookies automatically.

        Args:
            proxy: Optional proxy URL or dict forwarded to the CDP browser.
            timeout: Request timeout for Gemini API calls.
            model: Default model enum member.
            impersonate: Browser profile for ``curl_cffi`` requests.
            cdp_timeout: Max seconds to wait for the Gemini page to load.
            profile_name: Optional Chrome profile name or path to reuse login state.
                On this system, available profiles include ``"Profile 1 (Vortex)"``
                and ``"Profile 2 (XETRO)"``. When omitted, an isolated temporary
                browser state is used and Google login cookies may be missing.

        Returns:
            A ready-to-use :class:`AsyncChatbot` instance.
        """
        cdp_args = await get_args_from_cdp(
            url="https://gemini.google.com",
            proxy=proxy if isinstance(proxy, str) else None,
            timeout=cdp_timeout,
            user_data_dir=profile_name,
        )
        secure_1psid, secure_1psidts = _extract_bard_cookies(cdp_args["cookies"])
        return await cls.create(
            secure_1psid, secure_1psidts, proxy, timeout, model, impersonate
        )

    def _error_response(self, message: str) -> AskResponse:
        """Helper to create a consistent error response."""
        return {
            "content": message,
            "conversation_id": getattr(self, "conversation_id", ""),
            "response_id": getattr(self, "response_id", ""),
            "factualityQueries": [],
            "textQuery": "",
            "choices": [],
            "images": [],
            "error": True,
        }

    async def save_conversation(self, file_path: str, conversation_name: str) -> None:
        conversations = await self.load_conversations(file_path)
        conversation_data = {
            "conversation_name": conversation_name,
            "_reqid": self._reqid,
            "conversation_id": self.conversation_id,
            "response_id": self.response_id,
            "choice_id": self.choice_id,
            "SNlM0e": self.SNlM0e,
            "model_name": self.model.model_name,
            "timestamp": datetime.now().isoformat(),
        }

        found = False
        for i, conv in enumerate(conversations):
            if conv.get("conversation_name") == conversation_name:
                conversations[i] = conversation_data
                found = True
                break
        if not found:
            conversations.append(conversation_data)

        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(conversations, f, indent=4, ensure_ascii=False)
        except IOError as e:
            console.log(f"[red]Error saving conversation to {file_path}: {e}[/red]")
            raise

    async def load_conversations(self, file_path: str) -> List[Dict]:
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            console.log(f"[red]Error loading conversations from {file_path}: {e}[/red]")
            return []

    async def load_conversation(self, file_path: str, conversation_name: str) -> bool:
        conversations = await self.load_conversations(file_path)
        for conversation in conversations:
            if conversation.get("conversation_name") == conversation_name:
                try:
                    self._reqid = conversation["_reqid"]
                    self.conversation_id = conversation["conversation_id"]
                    self.response_id = conversation["response_id"]
                    self.choice_id = conversation["choice_id"]
                    self.SNlM0e = conversation["SNlM0e"]
                    if "model_name" in conversation:
                        try:
                            self.model = Model.from_name(conversation["model_name"])
                        except ValueError as e:
                            console.log(
                                f"[yellow]Warning: Model '{conversation['model_name']}' from saved conversation not found. Using current model '{self.model.model_name}'. Error: {e}[/yellow]"
                            )

                    console.log(f"Loaded conversation '{conversation_name}'")
                    return True
                except KeyError as e:
                    console.log(
                        f"[red]Error loading conversation '{conversation_name}': Missing key {e}[/red]"
                    )
                    return False
        console.log(f"[yellow]Conversation '{conversation_name}' not found in {file_path}[/yellow]")
        return False

    async def __get_snlm0e(self) -> str:
        """Fetches the SNlM0e value required for API requests using curl_cffi."""
        if not self.secure_1psid:
            raise ValueError("__Secure-1PSID cookie is required.")

        try:
            resp = await self.session.get(Endpoint.INIT.value, timeout=self.timeout)
            resp.raise_for_status()

            if "Sign in to continue" in resp.text or "accounts.google.com" in str(resp.url):
                raise PermissionError(
                    "Authentication failed. Cookies might be invalid or expired. Please update them."
                )

            # Extract XSRF token using g4f's pattern for escaped JSON
            snlm0e_match = XSRF_PATTERN.search(resp.text)
            if not snlm0e_match:
                error_message = "SNlM0e value not found in response."
                if resp.status_code == 429:
                    error_message += " Rate limit likely exceeded."
                else:
                    error_message += (
                        f" Response status: {resp.status_code}. Check cookie validity and network."
                    )
                raise ValueError(error_message)

            self.SNlM0e = snlm0e_match.group(1)

            # Extract build label
            build_match = BUILD_LABEL_PATTERN.search(resp.text)
            if build_match:
                self._bl = build_match.group(0)

            # Extract upload push ID
            push_id_match = PUSH_ID_PATTERN.search(resp.text)
            if push_id_match:
                self._upload_push_id = push_id_match.group(1)

            # Extract SID
            sid_match = SID_PATTERN.search(resp.text)
            if sid_match:
                self._sid = sid_match.group(1)

            # Rotate cookies if PSIDTS is missing
            if not self.secure_1psidts and "PSIDTS" not in self.session.cookies:
                try:
                    await self.__rotate_cookies()
                except Exception as e:
                    console.log(f"[yellow]Warning: Could not refresh PSIDTS cookie: {e}[/yellow]")

            return self.SNlM0e

        except Timeout as e:
            raise TimeoutError(f"Request timed out while fetching SNlM0e: {e}") from e
        except (RequestException, CurlError) as e:
            raise ConnectionError(f"Network error while fetching SNlM0e: {e}") from e
        except Exception as e:
            if isinstance(e, HTTPError) and (
                e.response.status_code == 401 or e.response.status_code == 403
            ):
                raise PermissionError(
                    f"Authentication failed (status {e.response.status_code}). Check cookies. {e}"
                ) from e
            else:
                raise Exception(f"Error while fetching SNlM0e: {e}") from e

    async def __rotate_cookies(self) -> Optional[str]:
        """Rotates the __Secure-1PSIDTS cookie."""
        try:
            response = await self.session.post(
                Endpoint.ROTATE_COOKIES.value,
                headers=Headers.ROTATE_COOKIES.value,
                data='[000,"-0000000000000000000"]',
                timeout=self.timeout,
            )
            response.raise_for_status()

            if new_1psidts := response.cookies.get("__Secure-1PSIDTS"):
                self.secure_1psidts = new_1psidts
                self.session.cookies.set("__Secure-1PSIDTS", new_1psidts)
                return new_1psidts
        except Exception as e:
            console.log(f"[yellow]Cookie rotation failed: {e}[/yellow]")
            raise

    def _make_sapisid_hash(self) -> Optional[str]:
        """Create SAPISIDHASH authorization header from current cookies."""
        cookies = {
            "__Secure-1PSID": self.secure_1psid,
            "__Secure-1PSIDTS": self.secure_1psidts,
        }
        cookies.update(dict(self.session.cookies))
        return _make_sapisid_hash(cookies)

    def _get_model_headers(self) -> Dict[str, str]:
        """Get model-specific headers based on current model selection."""
        if self.model == Model.UNSPECIFIED:
            return {}
        mode = self.model.mode
        model_header = {
            "x-goog-ext-525001261-jspb": f"[1,null,null,null,null,null,null,0,[4],null,null,{mode}]"
        }
        return model_header

    def _build_request(
        self,
        prompt: str,
        language: str = "en",
        model: str = "gemini-3.6-flash",
        expanded_thinking: bool = False,
        conversation: Optional[Any] = None,
        uploads: Optional[List[List]] = None,
        tools: Optional[List] = None,
        request_uuid: Optional[str] = None,
    ) -> List[Any]:
        """Build the 97-element request structure for Gemini API."""
        image_list = (
            [[[image_url, 1], image_name] for image_url, image_name in uploads]
            if uploads
            else []
        )
        turn_index = (
            getattr(conversation, "turn_index", 0) if conversation is not None else 0
        )
        request = [None] * 97
        request[0] = [prompt, 0, None, image_list, None, None, 0]
        request[1] = [language]
        request[2] = [
            "" if conversation is None else getattr(conversation, "conversation_id", ""),
            "" if conversation is None else getattr(conversation, "response_id", ""),
            "" if conversation is None else getattr(conversation, "choice_id", ""),
            None,
            None,
            None,
            None,
            None,
            None,
            "",
        ]
        request[6] = [1]
        request[7] = 1
        if tools:
            request[9] = tools
        request[10] = 1
        request[11] = 0
        request[17] = [[turn_index]]
        request[18] = 0
        request[27] = 1
        request[30] = [4]
        request[41] = [1]
        request[53] = 0
        request[59] = request_uuid or str(uuid.uuid4())
        request[61] = []
        request[68] = 2
        # Resolve model mode from registry
        resolved_model = MODEL_ALIASES.get(model, model)
        mode = MODELS.get(resolved_model, {}).get("mode", 1)
        request[79] = mode
        request[80] = 2 if expanded_thinking else 1
        request[91] = 0
        # Gemini Web marks the first turn with 1 and follow-up turns with 0.
        request[96] = int(conversation is None)
        return request

    async def ask(
        self, message: str, image: Optional[Union[bytes, str, Path]] = None
    ) -> AskResponse:
        """
        Sends a message to Google Gemini and returns the response using curl_cffi.

        Parameters:
            message: str
                The message to send.
            image: Optional[Union[bytes, str, Path]]
                Optional image data (bytes) or path to an image file to include.

        Returns:
            dict: A dictionary containing the response content and metadata.
        """
        if not self.anonymous and self.SNlM0e is None:
            raise RuntimeError("AsyncChatbot not properly initialized. Call AsyncChatbot.create()")

        params = {
            "bl": self._bl,
            "_reqid": str(self._reqid),
            "rt": "c",
        }
        if self._sid:
            params["f.sid"] = self._sid

        image_upload_id = None
        if image:
            try:
                image_upload_id = await upload_file(
                    image, proxy=self.proxies_dict, impersonate=self.impersonate
                )
                console.log(f"Image uploaded successfully. ID: {image_upload_id}")
            except Exception as e:
                console.log(f"[red]Error uploading image: {e}[/red]")
                return self._error_response(f"Error uploading image: {e}")

        request_uuid = str(uuid.uuid4()).upper()
        uploads = []
        if image_upload_id:
            uploads = [[[image_upload_id, 1], "image"]]

        message_struct = self._build_request(
            message,
            language="en",
            model=self.model.model_name if self.model != Model.UNSPECIFIED else "gemini-2.0-flash",
            expanded_thinking=False,
            conversation=None,
            uploads=uploads,
            tools=None,
            request_uuid=request_uuid,
        )

        data = {
            "f.req": json.dumps([None, json.dumps(message_struct, ensure_ascii=False)], ensure_ascii=False),
        }
        if self.SNlM0e:
            data["at"] = self.SNlM0e

        request_headers = {}
        if self._sid:
            request_headers["Referer"] = "https://gemini.google.com/app"
        authorization = self._make_sapisid_hash()
        if authorization:
            request_headers["Authorization"] = authorization
        model_headers = self._get_model_headers()
        if model_headers:
            request_headers.update(model_headers)
            request_headers["x-goog-ext-525005358-jspb"] = f'["{request_uuid}",1]'

        resp = None
        try:
            resp = await self.session.post(
                Endpoint.GENERATE.value,
                params=params,
                data=data,
                headers=request_headers if request_headers else None,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            if resp is None:
                raise ValueError("Failed to get response from Gemini API")

            response_text = resp.text
            if not response_text or not response_text.strip():
                return self._error_response("Empty response from Gemini API")

            lines = response_text.splitlines()
            response_part = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(")]}'"):
                    line = line[4:].strip()
                try:
                    payload = json.loads(line)
                    if isinstance(payload, list):
                        candidate = _extract_response_part(payload)
                        if candidate is not None:
                            # Prefer response parts with actual content
                            if response_part is None:
                                response_part = candidate
                            content = _extract_response_content(candidate)
                            if content:
                                response_part = candidate
                                break
                except (json.JSONDecodeError, TypeError):
                    continue

            if response_part is None:
                return self._error_response("Failed to parse response body. No valid data found.")

            try:
                content = _extract_response_content(response_part) or ""

                conversation_id = (
                    response_part[1][0]
                    if len(response_part) > 1 and isinstance(response_part[1], list) and len(response_part[1]) > 0
                    else self.conversation_id
                )
                response_id = (
                    response_part[1][1]
                    if len(response_part) > 1 and isinstance(response_part[1], list) and len(response_part[1]) > 1
                    else self.response_id
                )

                factualityQueries = response_part[3] if len(response_part) > 3 else None
                textQuery = response_part[2][0] if len(response_part) > 2 and isinstance(response_part[2], list) and response_part[2] else ""

                choices = []
                if len(response_part) > 4 and isinstance(response_part[4], list):
                    for candidate in response_part[4]:
                        if (
                            isinstance(candidate, list)
                            and len(candidate) > 1
                            and isinstance(candidate[1], list)
                            and len(candidate[1]) > 0
                        ):
                            choices.append({"id": candidate[0], "content": candidate[1][0]})

                choice_id = choices[0]["id"] if choices else self.choice_id

                images = []
                if len(response_part) > 4 and isinstance(response_part[4], list) and len(response_part[4]) > 0:
                    candidate = response_part[4][0]
                    if isinstance(candidate, list) and len(candidate) > 4 and candidate[4]:
                        for img_data in candidate[4]:
                            try:
                                img_url = img_data[0][0][0]
                                img_alt = img_data[2] if len(img_data) > 2 else ""
                                img_title = img_data[1] if len(img_data) > 1 else "[Image]"
                                images.append({"url": img_url, "alt": img_alt, "title": img_title})
                            except (IndexError, TypeError):
                                continue

                results: AskResponse = {
                    "content": content,
                    "conversation_id": conversation_id,
                    "response_id": response_id,
                    "factualityQueries": factualityQueries,
                    "textQuery": textQuery,
                    "choices": choices,
                    "images": images,
                    "error": False,
                }

                self.conversation_id = conversation_id
                self.response_id = response_id
                self.choice_id = choice_id
                self._reqid += random.randint(1000, 9000)

                return results

            except (IndexError, TypeError) as e:
                console.log(f"[red]Error extracting data from response: {e}[/red]")
                return self._error_response(f"Error extracting data from response: {e}")

        except json.JSONDecodeError as e:
            console.log(f"[red]Error parsing JSON response: {e}[/red]")
            resp_text = resp.text[:200] if resp else "No response"
            return self._error_response(
                f"Error parsing JSON response: {e}. Response: {resp_text}..."
            )
        except Timeout as e:
            console.log(f"[red]Request timed out: {e}[/red]")
            return self._error_response(f"Request timed out: {e}")
        except HTTPError as e:
            console.log(f"[red]HTTP error {e.response.status_code}: {e}[/red]")
            return self._error_response(f"HTTP error {e.response.status_code}: {e}")
        except (RequestException, CurlError) as e:
            console.log(f"[red]Network error: {e}[/red]")
            return self._error_response(f"Network error: {e}")
        except Exception as e:
            console.log(
                f"[red]An unexpected error occurred during ask: {e}[/red]", style="bold red"
            )
            return self._error_response(f"An unexpected error occurred: {e}")


class Image(BaseModel):
    """
    Represents a single image object returned from Gemini.

    Attributes:
        url (str): URL of the image.
        title (str): Title of the image (default: "[Image]").
        alt (str): Optional description of the image.
        proxy (str | dict | None): Proxy used when saving the image.
        impersonate (str): Browser profile for curl_cffi to impersonate.
    """

    url: str
    title: str = "[Image]"
    alt: str = ""
    proxy: Optional[Union[str, Dict[str, str]]] = None
    impersonate: str = "chrome110"

    def __str__(self) -> str:
        return f"{self.title}({self.url}) - {self.alt}"

    def __repr__(self) -> Any:
        short_url = self.url if len(self.url) <= 50 else self.url[:20] + "..." + self.url[-20:]
        short_alt = self.alt[:30] + "..." if len(self.alt) > 30 else self.alt
        return f"Image(title='{self.title}', url='{short_url}', alt='{short_alt}')"

    async def save(
        self,
        path: str = "downloaded_images",
        filename: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        verbose: bool = False,
        skip_invalid_filename: bool = True,
    ) -> Optional[str]:
        """
        Save the image to disk using curl_cffi.
        Parameters:
            path: str, optional
                Directory to save the image (default "downloaded_images").
            filename: str, optional
                Filename to use; if not provided, inferred from URL.
            cookies: dict, optional
                Cookies used for the image request.
            verbose: bool, optional
                If True, outputs status messages (default False).
            skip_invalid_filename: bool, optional
                If True, skips saving if the filename is invalid.
        Returns:
            Absolute path of the saved image if successful; None if skipped.
        Raises:
            HTTPError if the network request fails.
            RequestException/CurlError for other network errors.
            IOError if file writing fails.
        """
        if not filename:
            try:
                from urllib.parse import unquote, urlparse

                parsed_url = urlparse(self.url)
                base_filename = os.path.basename(unquote(parsed_url.path))
                safe_filename = re.sub(r'[<>:"/\\|?*]', "_", base_filename)
                if safe_filename and len(safe_filename) > 0:
                    filename = safe_filename
                else:
                    filename = f"image_{random.randint(1000, 9999)}.jpg"
            except Exception:
                filename = f"image_{random.randint(1000, 9999)}.jpg"

        try:
            _ = Path(filename)
            max_len = 255
            if len(filename) > max_len:
                name, ext = os.path.splitext(filename)
                filename = name[: max_len - len(ext) - 1] + ext
        except (OSError, ValueError):
            if verbose:
                console.log(f"[yellow]Invalid filename generated: {filename}[/yellow]")
            if skip_invalid_filename:
                if verbose:
                    console.log("[yellow]Skipping save due to invalid filename.[/yellow]")
                return None
            filename = f"image_{random.randint(1000, 9999)}.jpg"
            if verbose:
                console.log(f"[yellow]Using fallback filename: {filename}[/yellow]")

        proxies_dict = None
        if isinstance(self.proxy, str):
            proxies_dict = {"http": self.proxy, "https": self.proxy}
        elif isinstance(self.proxy, dict):
            proxies_dict = self.proxy

        dest = None
        try:
            async with AsyncSession(
                cookies=cookies,
                proxies=cast(Any, proxies_dict),
                impersonate=cast(Any, self.impersonate),
            ) as client:
                if verbose:
                    console.log(f"Attempting to download image from: {self.url}")

                response = await client.get(self.url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                if "image" not in content_type and verbose:
                    console.log(
                        f"[yellow]Warning: Content type is '{content_type}', not an image. Saving anyway.[/yellow]"
                    )

                dest_path = Path(path)
                dest_path.mkdir(parents=True, exist_ok=True)
                dest = dest_path / filename

                dest.write_bytes(response.content)

                if verbose:
                    console.log(f"Image saved successfully as {dest.resolve()}")

                return str(dest.resolve())

        except HTTPError as e:
            console.log(
                f"[red]Error downloading image {self.url}: {e.response.status_code} {e}[/red]"
            )
            raise
        except (RequestException, CurlError) as e:
            console.log(f"[red]Network error downloading image {self.url}: {e}[/red]")
            raise
        except IOError as e:
            console.log(f"[red]Error writing image file to {dest}: {e}[/red]")
            raise
        except Exception as e:
            console.log(f"[red]An unexpected error occurred during image save: {e}[/red]")
            raise


class WebImage(Image):
    """
    Represents an image retrieved from web search results.

    Returned when asking Gemini to "SEND an image of [something]".
    """

    async def save(
        self,
        path: str = "downloaded_images",
        filename: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        verbose: bool = False,
        skip_invalid_filename: bool = True,
    ) -> Optional[str]:
        """
        Save the image to disk using curl_cffi.
        Parameters:
            path: str, optional
                Directory to save the image (default "downloaded_images").
            filename: str, optional
                Filename to use; if not provided, inferred from URL.
            cookies: dict, optional
                Cookies used for the image request.
            verbose: bool, optional
                If True, outputs status messages (default False).
            skip_invalid_filename: bool, optional
                If True, skips saving if the filename is invalid.
        Returns:
            Absolute path of the saved image if successful; None if skipped.
        Raises:
            HTTPError if the network request fails.
            RequestException/CurlError for other network errors.
            IOError if file writing fails.
        """
        return await super().save(path, filename, cookies, verbose, skip_invalid_filename)


class GeneratedImage(Image):
    """
    Represents an image generated by Google's AI image generator (e.g., ImageFX).

    Attributes:
        cookies (dict[str, str]): Cookies required for accessing the generated image URL,
            typically from the GeminiClient/Chatbot instance.
    """

    cookies: Dict[str, str]

    @field_validator("cookies")
    @classmethod
    def validate_cookies(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Ensures cookies are provided for generated images."""
        if not v or not isinstance(v, dict):
            raise ValueError("GeneratedImage requires a dictionary of cookies from the client.")
        return v

    async def save(
        self,
        path: str = "downloaded_images",
        filename: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        verbose: bool = False,
        skip_invalid_filename: bool = True,
        **kwargs,
    ) -> Optional[str]:
        """
        Save the generated image to disk.
        Parameters:
            filename: str, optional
                Filename to use. If not provided, a default name including
                a timestamp and part of the URL is used. Generated images
                are often in .png or .jpg format.
            Additional arguments are passed to Image.save.
        Returns:
            Absolute path of the saved image if successful, None if skipped.
        """
        if filename is None:
            ext = ".jpg" if ".jpg" in self.url.lower() else ".png"
            url_part = self.url.split("/")[-1][:10]
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{url_part}{ext}"

        return await super().save(
            path, filename, cookies or self.cookies, verbose, skip_invalid_filename
        )
