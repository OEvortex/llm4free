"""
Emailnator Provider Implementation
Synchronous provider for Emailnator.com
"""

from json import loads
from time import sleep
from typing import Dict, List, Optional

from llm4free.browser_requests._http.compat import Session

from llm4free.litagent import LitAgent

from .base import TempMailProvider


class EmailnatorProvider(TempMailProvider):
    def __init__(self):
        self.client = Session()
        self.client.get("https://www.emailnator.com/", timeout=6)
        self.cookies = self.client.cookies.get_dict()
        self.user_agent = LitAgent()
        xsrf_token = self.client.cookies.get("XSRF-TOKEN")
        self.client.headers = {
            "authority": "www.emailnator.com",
            "origin": "https://www.emailnator.com",
            "referer": "https://www.emailnator.com/",
            "user-agent": self.user_agent.random(),
            "x-xsrf-token": (xsrf_token[:-3] + "=") if xsrf_token else "",
        }
        self.email = None
        self._messages = []
        self._account_deleted = False

    def create_account(self) -> bool:
        response = self.client.post(
            "https://www.emailnator.com/generate-email",
            json={"email": ["plusGmail", "dotGmail"]},
        )
        self.email = loads(response.text)["email"][0]
        return bool(self.email)

    def get_messages(self) -> List[Dict]:
        # Wait for at least one message
        for _ in range(30):  # Wait up to 60 seconds
            sleep(2)
            mail_token = self.client.post(
                "https://www.emailnator.com/message-list", json={"email": self.email}
            )
            mail_token = loads(mail_token.text)["messageData"]
            if len(mail_token) > 1:
                break
        else:
            return []
        # Get message details
        messages = []
        for msg in mail_token[1:]:
            msg_id = msg["messageID"]
            mail_context = self.client.post(
                "https://www.emailnator.com/message-list",
                json={"email": self.email, "messageID": msg_id},
            )
            # The response is HTML, so we just store it as body
            messages.append(
                {
                    "msg_id": msg_id,
                    "from": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "body": mail_context.text,
                }
            )
        self._messages = messages
        return messages

    def check_new_messages(self) -> List[Dict]:
        current = self.get_messages()
        if not self._messages:
            return current
        # Return only new messages
        old_ids = {m["msg_id"] for m in self._messages}
        new_msgs = [m for m in current if m["msg_id"] not in old_ids]
        return new_msgs

    def delete_account(self) -> bool:
        # Emailnator does not support explicit account deletion, so just mark as deleted
        self._account_deleted = True
        return True

    def get_account_info(self) -> Dict:
        return {"email": self.email, "deleted": self._account_deleted}
