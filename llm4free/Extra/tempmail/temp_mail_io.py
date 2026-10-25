"""
TempMail.io Provider Implementation
Based on temp-mail.io API
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .base import AsyncTempMailProvider, TempMailProvider


@dataclass
class DomainModel:
    """Domain model for TempMail.io API"""

    name: str
    type: str
    forward_available: str
    forward_max_seconds: str


@dataclass
class CreateEmailResponseModel:
    """Response model for email creation in TempMail.io API"""

    email: str
    token: str


@dataclass
class MessageResponseModel:
    """Message model for TempMail.io API"""

    attachments: Optional[List[Any]]
    body_html: Optional[str]
    body_text: Optional[str]
    cc: Optional[str]
    created_at: str
    email_from: Optional[str]
    id: str
    subject: Optional[str]
    email_to: Optional[str]


class TempMailIOAsync(AsyncTempMailProvider):
    """
    TempMail.io API client for temporary email services
    Implements the AsyncTempMailProvider interface
    """

    def __init__(self):
        """Initialize TempMail.io Async client"""
        self._session = None
        self.email = None
        self.token = None

    async def initialize(self):
        """Initialize the aiohttp session"""
        self._session = aiohttp.ClientSession(
            base_url="https://api.internal.temp-mail.io",
            headers={
                "Host": "api.internal.temp-mail.io",
                "User-Agent": "okhttp/4.5.0",
                "Connection": "close",
            },
        )
        return self

    async def close(self) -> None:
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        """Context manager entry"""
        return await self.initialize()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()
        return None

    async def get_domains(self) -> List[DomainModel]:
        """Get available domains"""
        if not self._session:
            await self.initialize()

        if not self._session:
            return []

        try:
            async with self._session.get("/api/v3/domains") as response:
                response_json = await response.json()
                return [
                    DomainModel(
                        domain["name"],
                        domain["type"],
                        domain["forward_available"],
                        domain["forward_max_seconds"],
                    )
                    for domain in response_json["domains"]
                ]
        except Exception:
            return []

    async def create_email(
        self, alias: Optional[str] = None, domain: Optional[str] = None
    ) -> Tuple[str, str]:
        """Create a new temporary email"""
        if not self._session:
            await self.initialize()

        if not self._session:
            return "", ""

        try:
            async with self._session.post(
                "/api/v3/email/new", data={"name": alias, "domain": domain}
            ) as response:
                response_json = await response.json()
                self.email = response_json["email"]
                self.token = response_json["token"]
                return str(self.email), str(self.token)
        except Exception:
            return "", ""

    async def delete_email(self) -> bool:
        """Delete a temporary email"""
        if not self._session:
            await self.initialize()

        if not self._session or not self.email or not self.token:
            return False

        try:
            async with self._session.delete(
                f"/api/v3/email/{self.email}", data={"token": self.token}
            ) as response:
                success = response.status == 200
                if success:
                    self.email = None
                    self.token = None
                return success
        except Exception:
            return False

    async def get_messages(self) -> List[Dict]:
        """Get messages for a temporary email"""
        if not self._session:
            await self.initialize()

        if not self._session or not self.email:
            return []

        try:
            async with self._session.get(f"/api/v3/email/{self.email}/messages") as response:
                response_json = await response.json()
                if len(response_json) == 0:
                    return []

                messages = []
                for message in response_json:
                    msg_dict = {
                        "msg_id": message["id"],
                        "from": message["from"],
                        "to": message["to"],
                        "subject": message["subject"] if "subject" in message else "",
                        "body": message["body_text"] or message["body_html"],
                        "hasAttachments": bool(
                            message["attachments"] and len(message["attachments"]) > 0
                        ),
                        "createdAt": message["created_at"],
                    }
                    messages.append(msg_dict)
                return messages
        except Exception:
            return []


class TempMailIO(TempMailProvider):
    """
    Synchronous implementation for TempMail.io API
    Implements the TempMailProvider interface
    """

    def __init__(self, auto_create=False):
        """
        Initialize TempMail.io client

        Args:
            auto_create: Automatically create an email upon initialization
        """
        from llm4free.browser_requests._http.compat import Session

        self.session = Session()
        self.session.headers.update(
            {
                "Host": "api.internal.temp-mail.io",
                "User-Agent": "okhttp/4.5.0",
                "Connection": "close",
            }
        )
        self.base_url = "https://api.internal.temp-mail.io"
        self.email = None
        self.token = None
        self.messages_count = 0

        if auto_create:
            self.create_account()

    def get_domains(self) -> List[DomainModel]:
        """Get available domains"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/domains")
            response.raise_for_status()
            response_json = response.json()
            return [
                DomainModel(
                    domain["name"],
                    domain["type"],
                    domain["forward_available"],
                    domain["forward_max_seconds"],
                )
                for domain in response_json["domains"]
            ]
        except Exception:
            return []

    def create_account(self) -> bool:
        """Create a new temporary email account"""
        try:
            response = self.session.post(f"{self.base_url}/api/v3/email/new", data={})
            response.raise_for_status()
            response_json = response.json()
            self.email = response_json["email"]
            self.token = response_json["token"]
            return True
        except Exception:
            return False

    def get_messages(self) -> List[Dict]:
        """Get all messages in the inbox"""
        if not self.email:
            return []

        try:
            response = self.session.get(f"{self.base_url}/api/v3/email/{self.email}/messages")
            response.raise_for_status()
            response_json = response.json()
            if len(response_json) == 0:
                return []

            messages = []
            for message in response_json:
                msg_dict = {
                    "msg_id": message["id"],
                    "from": message["from"] if "from" in message else "",
                    "to": message["to"] if "to" in message else "",
                    "subject": message["subject"] if "subject" in message else "",
                    "body": message["body_text"] or message["body_html"] or "",
                    "hasAttachments": bool(
                        message.get("attachments") and len(message["attachments"]) > 0
                    ),
                    "createdAt": message["created_at"],
                }
                messages.append(msg_dict)
            return messages
        except Exception:
            return []

    def check_new_messages(self) -> List[Dict]:
        """Check for new messages and return only the new ones"""
        messages = self.get_messages()
        if not messages:
            return []

        if len(messages) > self.messages_count:
            new_msg_count = len(messages) - self.messages_count
            new_messages = messages[:new_msg_count]
            self.messages_count = len(messages)
            return new_messages

        self.messages_count = len(messages)
        return []

    def delete_account(self) -> bool:
        """Delete the current temporary email account"""
        if not self.email or not self.token:
            return False

        try:
            response = self.session.delete(
                f"{self.base_url}/api/v3/email/{self.email}", data={"token": self.token}
            )
            response.raise_for_status()
            success = response.status_code == 200
            if success:
                self.email = None
                self.token = None
                self.messages_count = 0
            return success
        except Exception:
            return False

    def get_account_info(self) -> Dict:
        """Get current account information"""
        if not self.email or not self.token:
            return {}

        return {"email": self.email, "token": self.token}
