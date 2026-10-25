"""
Mail.TM Provider Implementation
Based on mail.tm and mail.gw APIs
"""

import json
import random
from typing import Dict, List, Optional, Tuple

from llm4free.browser_requests._http.compat import Session

from ...scout import Scout
from .base import (
    EMAIL_LENGTH,
    PASSWORD_LENGTH,
    AsyncTempMailProvider,
    TempMailProvider,
    generate_random_string,
)


class MailTM(TempMailProvider):
    """
    Mail.TM API client for temporary email services
    Implements the synchronous TempMailProvider interface
    """

    def __init__(self, auto_create=False):
        """
        Initialize MailTM client

        Args:
            auto_create (bool): Automatically create an email upon initialization
        """
        self.url_bases = ["https://api.mail.tm", "https://api.mail.gw"]
        self.url_base = self.url_bases[random.randrange(2)]
        self.url_accounts = f"{self.url_base}/accounts"
        self.url_me = f"{self.url_base}/me"
        self.url_domain = f"{self.url_base}/domains"
        self.url_msg = f"{self.url_base}/messages"
        self.url_token = f"{self.url_base}/token"

        self.email = None
        self.password = None
        self.token = None
        self.account_id = None
        self.header = None
        self.messages_count = 0

        if auto_create:
            self.create_account()

    def get_domain(self) -> str:
        """Get available domain for email creation"""
        try:
            session = Session()
            resp = session.get(f"{self.url_domain}?page=1")
            resp.raise_for_status()
            ans = json.loads(str(resp.text))
            return ans["hydra:member"][0]["domain"]
        except Exception:
            return ""

    def create_account(self) -> bool:
        """Create a new temporary email account"""
        domain = self.get_domain()
        if not domain:
            return False

        # Generate random email and password
        self.email = generate_random_string(EMAIL_LENGTH) + "@" + domain
        self.password = generate_random_string(PASSWORD_LENGTH, include_digits=True)

        # Register the account
        myobj = {"address": self.email, "password": self.password}
        try:
            session = Session()
            resp = session.post(self.url_accounts, json=myobj)
            resp.raise_for_status()
            ans = json.loads(str(resp.text))
            self.account_id = ans["id"]

            # Get token
            self.get_token()
            return True if self.token else False

        except Exception:
            return False

    def get_token(self) -> str:
        """Get authentication token"""
        if not self.email or not self.password:
            return ""

        myobj = {"address": self.email, "password": self.password}
        try:
            session = Session()
            resp = session.post(self.url_token, json=myobj)
            resp.raise_for_status()
            ans = json.loads(str(resp.text))
            self.token = ans["token"]
            self.header = {"Authorization": "Bearer " + self.token}
            return self.token
        except Exception:
            return ""

    def get_message_detail(self, msg_id: str) -> str:
        """Get detailed content of a message"""
        if not self.header:
            return ""

        try:
            session = Session()
            resp = session.get(f"{self.url_msg}/{msg_id}", headers=self.header)
            resp.raise_for_status()
            ans = json.loads(str(resp.text))

            # Use Scout instead of BeautifulSoup for HTML parsing
            scout = Scout(ans["text"])

            # Extract text with Scout's get_text method
            return scout.get_text(strip=True)

        except Exception:
            return ""

    def get_messages(self) -> List[Dict]:
        """Get messages from the inbox"""
        if not self.header:
            return []

        try:
            session = Session()
            resp = session.get(f"{self.url_msg}?page=1", headers=self.header)
            resp.raise_for_status()
            ans = json.loads(str(resp.text))

            messages = []
            if ans["hydra:totalItems"] > 0:
                for x in ans["hydra:member"]:
                    msg_dict = {
                        "msg_id": x["id"],
                        "from": x["from"]["address"],
                        "subject": x["subject"],
                        "intro": x["intro"],
                        "hasAttachments": x["hasAttachments"],
                        "createdAt": x["createdAt"],
                        "body": self.get_message_detail(x["id"]),
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
        if not self.header or not self.account_id:
            return False

        try:
            session = Session()
            resp = session.delete(f"{self.url_accounts}/{self.account_id}", headers=self.header)
            resp.raise_for_status()
            self.email = None
            self.password = None
            self.token = None
            self.account_id = None
            self.header = None
            self.messages_count = 0
            return True
        except Exception:
            return False

    def get_account_info(self) -> Dict:
        """Get current account information"""
        if not self.header:
            return {}

        try:
            session = Session()
            resp = session.get(self.url_me, headers=self.header)
            resp.raise_for_status()
            return json.loads(str(resp.text))
        except Exception:
            return {}


class MailTMAsync(AsyncTempMailProvider):
    """
    Asynchronous Mail.TM API client for temporary email services
    Implements the AsyncTempMailProvider interface
    """

    def __init__(self):
        """Initialize MailTM Async client"""
        self.url_bases = ["https://api.mail.tm", "https://api.mail.gw"]
        self.url_base = self.url_bases[random.randrange(2)]
        self.url_accounts = f"{self.url_base}/accounts"
        self.url_me = f"{self.url_base}/me"
        self.url_domain = f"{self.url_base}/domains"
        self.url_msg = f"{self.url_base}/messages"
        self.url_token = f"{self.url_base}/token"

        self.session = None
        self.email = None
        self.password = None
        self.token = None
        self.account_id = None
        self.header = None

    async def initialize(self):
        """Initialize the session"""
        import aiohttp

        self.session = aiohttp.ClientSession()
        return self

    async def close(self) -> None:
        """Close the session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        """Context manager entry"""
        return await self.initialize()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()

    async def get_domain(self) -> str:
        """Get available domain for email creation"""
        if not self.session:
            await self.initialize()

        if not self.session:
            return ""

        try:
            async with self.session.get(f"{self.url_domain}?page=1") as resp:
                resp.raise_for_status()
                ans = await resp.json()
                return ans["hydra:member"][0]["domain"]
        except Exception:
            return ""

    async def create_email(
        self, alias: Optional[str] = None, domain: Optional[str] = None
    ) -> Tuple[str, str]:
        """Create a new email account"""
        if not self.session:
            await self.initialize()

        if not self.session:
            return "", ""

        if not domain:
            domain = await self.get_domain()
            if not domain:
                return "", ""

        # Generate random email address or use alias
        if alias:
            self.email = f"{alias}@{domain}"
        else:
            self.email = f"{generate_random_string(EMAIL_LENGTH)}@{domain}"

        # Generate password
        self.password = generate_random_string(PASSWORD_LENGTH, include_digits=True)

        # Register account
        data = {"address": self.email, "password": self.password}
        try:
            async with self.session.post(self.url_accounts, json=data) as resp:
                resp.raise_for_status()
                ans = await resp.json()
                self.account_id = ans["id"]

                # Get token
                token = await self._get_token()
                return self.email, token

        except Exception:
            return "", ""

    async def _get_token(self) -> str:
        """Get authentication token"""
        if not self.email or not self.password or not self.session:
            return ""

        data = {"address": self.email, "password": self.password}
        try:
            async with self.session.post(self.url_token, json=data) as resp:
                resp.raise_for_status()
                ans = await resp.json()
                self.token = ans["token"]
                self.header = {"Authorization": f"Bearer {self.token}"}
                return self.token
        except Exception:
            return ""

    async def get_message_detail(self, msg_id: str) -> str:
        """Get detailed content of a message"""
        if not self.header or not self.session:
            return ""

        try:
            async with self.session.get(f"{self.url_msg}/{msg_id}", headers=self.header) as resp:
                resp.raise_for_status()
                ans = await resp.json()

                # Use Scout instead of BeautifulSoup for HTML parsing
                scout = Scout(ans["text"])

                # Extract text with Scout's get_text method with improved options
                # Strip whitespace for cleaner output
                return scout.get_text(separator=" ", strip=True)

        except Exception:
            return ""

    async def get_messages(self) -> List[Dict]:
        """Get messages for a temporary email"""
        if not self.header or not self.session:
            return []

        try:
            async with self.session.get(f"{self.url_msg}?page=1", headers=self.header) as resp:
                resp.raise_for_status()
                ans = await resp.json()

                messages = []
                if ans["hydra:totalItems"] > 0:
                    for x in ans["hydra:member"]:
                        detail = await self.get_message_detail(x["id"])
                        msg_dict = {
                            "msg_id": x["id"],
                            "from": x["from"]["address"],
                            "subject": x["subject"],
                            "intro": x["intro"],
                            "hasAttachments": x["hasAttachments"],
                            "createdAt": x["createdAt"],
                            "body": detail,
                        }
                        messages.append(msg_dict)
                return messages
        except Exception:
            return []

    async def delete_email(self) -> bool:
        """Delete a temporary email"""
        if not self.header or not self.account_id or not self.session:
            return False

        try:
            async with self.session.delete(
                f"{self.url_accounts}/{self.account_id}", headers=self.header
            ) as resp:
                resp.raise_for_status()
                self.email = None
                self.password = None
                self.token = None
                self.account_id = None
                self.header = None
                return True
        except Exception:
            return False
