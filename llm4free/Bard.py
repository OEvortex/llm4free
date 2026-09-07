import asyncio
import json
import os
import random
import re
import string
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession
from pydantic import BaseModel, field_validator
from requests.exceptions import HTTPError, RequestException, Timeout
from rich.console import Console

from llm4free.requests import get_args_from_cdp

console = Console()


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
        model_header (dict): Additional headers required for the model.
        advanced_only (bool): Whether the model is available only for advanced users.
    """

    UNSPECIFIED = ("unspecified", {}, False)
    GEMINI_3_0_PRO = (
        "gemini-3.0-pro",
        {
            "x-goog-ext-525001261-jspb": '[1,null,null,null,"e6fa609c3fa255c0",null,null,0,[4],null,null,2]'
        },
        False,
    )
    GEMINI_3_0_FLASH = (
        "gemini-3.0-flash",
        {
            "x-goog-ext-525001261-jspb": '[1,null,null,null,"56fdd199312815e2",null,null,0,[4],null,null,2]'
        },
        False,
    )
    GEMINI_3_0_FLASH_THINKING = (
        "gemini-3.0-flash-thinking",
        {
            "x-goog-ext-525001261-jspb": '[1,null,null,null,"e051ce1aa80aa576",null,null,0,[4],null,null,2]'
        },
        False,
    )

    def __init__(self, name: str, header: Dict[str, str], advanced_only: bool):
        """
        Initialize a Model enum member.

        Args:
            name (str): Model name.
            header (dict): Model-specific headers.
            advanced_only (bool): If True, model is for advanced users only.
        """
        self.model_name = name
        self.model_header = header
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


def _extract_bard_cookies(cookies: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Extract ``__Secure-1PSID`` and ``__Secure-1PSIDTS`` from CDP cookies.

    Args:
        cookies: Cookie list returned by :func:`llm4free.requests.get_args_from_cdp`.

    Returns:
        Tuple of ``(__Secure-1PSID, __Secure-1PSIDTS)`` values.

    Raises:
        ValueError: If either required cookie is missing.
    """
    secure_1psid = None
    secure_1psidts = None
    for cookie in cookies:
        name = cookie.get("name", "")
        if name.upper() == "__SECURE-1PSID":
            secure_1psid = cookie.get("value")
        elif name.upper() == "__SECURE-1PSIDTS":
            secure_1psidts = cookie.get("value")

    if not secure_1psid or not secure_1psidts:
        raise ValueError(
            "Required cookies (__Secure-1PSID or __Secure-1PSIDTS) not found in CDP cookies."
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
    ) -> "Chatbot":
        """Create a :class:`Chatbot` using CDP-harvested Gemini cookies.

        Opens a browser via :func:`llm4free.requests.get_args_from_cdp`,
        navigates to ``https://gemini.google.com``, and extracts the required
        ``__Secure-1PSID`` / ``__Secure-1PSIDTS`` cookies automatically.

        Args:
            proxy: Optional proxy URL or dict forwarded to the CDP browser.
            timeout: Request timeout for Gemini API calls.
            model: Default model enum member.
            impersonate: Browser profile for ``curl_cffi`` requests.
            cdp_timeout: Max seconds to wait for the Gemini page to load.

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
    ]

    def __init__(
        self,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ):
        headers = Headers.GEMINI.value.copy()
        if model != Model.UNSPECIFIED:
            headers.update(model.model_header)
        self._reqid = int("".join(random.choices(string.digits, k=7)))
        self.proxy = proxy
        self.impersonate = impersonate

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

        self.session: AsyncSession = AsyncSession(
            headers=headers,
            cookies={"__Secure-1PSID": secure_1psid, "__Secure-1PSIDTS": secure_1psidts},
            proxies=cast(Any, self.proxies_dict if self.proxies_dict else None),
            timeout=timeout,
            impersonate=cast(Any, self.impersonate if self.impersonate else None),
        )

        self.timeout = timeout
        self.model = model
        self.SNlM0e = None

    @classmethod
    async def create(
        cls,
        secure_1psid: str,
        secure_1psidts: str,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
    ) -> "AsyncChatbot":
        """
        Factory method to create and initialize an AsyncChatbot instance.
        Fetches the necessary SNlM0e value asynchronously.
        """
        instance = cls(secure_1psid, secure_1psidts, proxy, timeout, model, impersonate)
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
    async def create_from_cdp(
        cls,
        proxy: Optional[Union[str, Dict[str, str]]] = None,
        timeout: int = 20,
        model: Model = Model.UNSPECIFIED,
        impersonate: str = "chrome110",
        cdp_timeout: int = 120,
    ) -> "AsyncChatbot":
        """Create an :class:`AsyncChatbot` using CDP-harvested Gemini cookies.

        Opens a browser via :func:`llm4free.requests.get_args_from_cdp`,
        navigates to ``https://gemini.google.com``, and extracts the required
        ``__Secure-1PSID`` / ``__Secure-1PSIDTS`` cookies automatically.

        Args:
            proxy: Optional proxy URL or dict forwarded to the CDP browser.
            timeout: Request timeout for Gemini API calls.
            model: Default model enum member.
            impersonate: Browser profile for ``curl_cffi`` requests.
            cdp_timeout: Max seconds to wait for the Gemini page to load.

        Returns:
            A ready-to-use :class:`AsyncChatbot` instance.
        """
        cdp_args = await get_args_from_cdp(
            url="https://gemini.google.com",
            proxy=proxy if isinstance(proxy, str) else None,
            timeout=cdp_timeout,
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
                            self.session.headers.update(self.model.model_header)
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

            snlm0e_match = re.search(r'["\']SNlM0e["\']\s*:\s*["\'](.*?)["\']', resp.text)
            if not snlm0e_match:
                error_message = "SNlM0e value not found in response."
                if resp.status_code == 429:
                    error_message += " Rate limit likely exceeded."
                else:
                    error_message += (
                        f" Response status: {resp.status_code}. Check cookie validity and network."
                    )
                raise ValueError(error_message)

            if not self.secure_1psidts and "PSIDTS" not in self.session.cookies:
                try:
                    await self.__rotate_cookies()
                except Exception as e:
                    console.log(f"[yellow]Warning: Could not refresh PSIDTS cookie: {e}[/yellow]")

            return snlm0e_match.group(1)

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
        if self.SNlM0e is None:
            raise RuntimeError("AsyncChatbot not properly initialized. Call AsyncChatbot.create()")

        params = {
            "bl": "boq_assistant-bard-web-server_20240625.13_p0",
            "_reqid": str(self._reqid),
            "rt": "c",
        }

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

        if image_upload_id:
            message_struct = [
                [message],
                [[[image_upload_id, 1]]],
                [self.conversation_id, self.response_id, self.choice_id],
            ]
        else:
            message_struct = [
                [message],
                None,
                [self.conversation_id, self.response_id, self.choice_id],
            ]

        data = {
            "f.req": json.dumps(
                [None, json.dumps(message_struct, ensure_ascii=False)], ensure_ascii=False
            ),
            "at": self.SNlM0e,
        }

        resp = None
        try:
            resp = await self.session.post(
                Endpoint.GENERATE.value,
                params=params,
                data=data,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            if resp is None:
                raise ValueError("Failed to get response from Gemini API")

            lines = resp.text.splitlines()
            if len(lines) < 3:
                raise ValueError(
                    f"Unexpected response format. Status: {resp.status_code}. Content: {resp.text[:200]}..."
                )

            chat_data_line = None
            for line in lines:
                if line.startswith(")]}'"):
                    chat_data_line = line[4:].strip()
                    break
                elif line.startswith("["):
                    chat_data_line = line
                    break

            if not chat_data_line:
                chat_data_line = lines[3] if len(lines) > 3 else lines[-1]
                if chat_data_line.startswith(")]}'"):
                    chat_data_line = chat_data_line[4:].strip()

            response_json = json.loads(chat_data_line)

            body = None
            body_index = 0

            for part_index, part in enumerate(response_json):
                try:
                    if isinstance(part, list) and len(part) > 2:
                        main_part = json.loads(part[2])
                        if main_part and len(main_part) > 4 and main_part[4]:
                            body = main_part
                            body_index = part_index
                            break
                except (IndexError, TypeError, json.JSONDecodeError):
                    continue

            if not body:
                return self._error_response("Failed to parse response body. No valid data found.")

            try:
                content = ""
                if len(body) > 4 and len(body[4]) > 0 and len(body[4][0]) > 1:
                    content = body[4][0][1][0] if len(body[4][0][1]) > 0 else ""

                conversation_id = (
                    body[1][0] if len(body) > 1 and len(body[1]) > 0 else self.conversation_id
                )
                response_id = body[1][1] if len(body) > 1 and len(body[1]) > 1 else self.response_id

                factualityQueries = body[3] if len(body) > 3 else None
                textQuery = body[2][0] if len(body) > 2 and body[2] else ""

                choices = []
                if len(body) > 4:
                    for candidate in body[4]:
                        if (
                            len(candidate) > 1
                            and isinstance(candidate[1], list)
                            and len(candidate[1]) > 0
                        ):
                            choices.append({"id": candidate[0], "content": candidate[1][0]})

                choice_id = choices[0]["id"] if choices else self.choice_id

                images = []

                if len(body) > 4 and len(body[4]) > 0 and len(body[4][0]) > 4 and body[4][0][4]:
                    for img_data in body[4][0][4]:
                        try:
                            img_url = img_data[0][0][0]
                            img_alt = img_data[2] if len(img_data) > 2 else ""
                            img_title = img_data[1] if len(img_data) > 1 else "[Image]"
                            images.append({"url": img_url, "alt": img_alt, "title": img_title})
                        except (IndexError, TypeError):
                            console.log(
                                "[yellow]Warning: Could not parse image data structure (format 1).[/yellow]"
                            )
                            continue

                generated_images = []
                if len(body) > 4 and len(body[4]) > 0 and len(body[4][0]) > 12 and body[4][0][12]:
                    try:
                        if body[4][0][12][7] and body[4][0][12][7][0]:
                            for img_index, img_data in enumerate(body[4][0][12][7][0]):
                                try:
                                    img_url = img_data[0][3][3]
                                    img_title = f"[Generated Image {img_index + 1}]"
                                    img_alt = (
                                        img_data[3][5][0]
                                        if len(img_data[3]) > 5 and len(img_data[3][5]) > 0
                                        else ""
                                    )
                                    generated_images.append(
                                        {"url": img_url, "alt": img_alt, "title": img_title}
                                    )
                                except (IndexError, TypeError):
                                    continue

                            if not generated_images:
                                for part_index, part in enumerate(response_json):
                                    if part_index <= body_index:
                                        continue
                                    try:
                                        img_part = json.loads(part[2])
                                        if img_part[4][0][12][7][0]:
                                            for img_index, img_data in enumerate(
                                                img_part[4][0][12][7][0]
                                            ):
                                                try:
                                                    img_url = img_data[0][3][3]
                                                    img_title = f"[Generated Image {img_index + 1}]"
                                                    img_alt = (
                                                        img_data[3][5][0]
                                                        if len(img_data[3]) > 5
                                                        and len(img_data[3][5]) > 0
                                                        else ""
                                                    )
                                                    generated_images.append(
                                                        {
                                                            "url": img_url,
                                                            "alt": img_alt,
                                                            "title": img_title,
                                                        }
                                                    )
                                                except (IndexError, TypeError):
                                                    continue
                                            break
                                    except (IndexError, TypeError, json.JSONDecodeError):
                                        continue
                    except (IndexError, TypeError):
                        pass

                if len(generated_images) == 0 and len(body) > 4 and len(body[4]) > 0:
                    try:
                        candidate = body[4][0]
                        if len(candidate) > 22 and candidate[22]:
                            import re

                            content = (
                                candidate[22][0]
                                if isinstance(candidate[22], list) and len(candidate[22]) > 0
                                else str(candidate[22])
                            )
                            urls = re.findall(r"https?://[^\s]+", content)
                            for i, url in enumerate(urls):
                                if url[-1] in [".", ",", ")", "]", "}", '"', "'"]:
                                    url = url[:-1]
                                generated_images.append(
                                    {"url": url, "title": f"[Generated Image {i + 1}]", "alt": ""}
                                )
                    except (IndexError, TypeError) as e:
                        console.log(
                            f"[yellow]Warning: Could not parse alternative image structure: {e}[/yellow]"
                        )

                if len(images) == 0 and len(generated_images) == 0 and content:
                    try:
                        import re

                        urls = re.findall(
                            r"(https?://[^\s]+\.(jpg|jpeg|png|gif|webp))", content.lower()
                        )

                        google_urls = re.findall(
                            r"(https?://lh\d+\.googleusercontent\.com/[^\s]+)", content
                        )

                        general_urls = re.findall(r"(https?://[^\s]+)", content)

                        all_urls = []
                        if urls:
                            all_urls.extend([url_tuple[0] for url_tuple in urls])
                        if google_urls:
                            all_urls.extend(google_urls)

                        if not all_urls and general_urls:
                            all_urls = general_urls

                        if all_urls:
                            for i, url in enumerate(all_urls):
                                if url[-1] in [".", ",", ")", "]", "}", '"', "'"]:
                                    url = url[:-1]
                                images.append(
                                    {"url": url, "title": f"[Image in Content {i + 1}]", "alt": ""}
                                )
                            console.log(
                                f"[green]Found {len(all_urls)} potential image URLs in content.[/green]"
                            )
                    except Exception as e:
                        console.log(
                            f"[yellow]Warning: Error extracting URLs from content: {e}[/yellow]"
                        )

                all_images = images + generated_images

                results: AskResponse = {
                    "content": content,
                    "conversation_id": conversation_id,
                    "response_id": response_id,
                    "factualityQueries": factualityQueries,
                    "textQuery": textQuery,
                    "choices": choices,
                    "images": all_images,
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
