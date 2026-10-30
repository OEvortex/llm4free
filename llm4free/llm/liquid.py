"""Liquid Playground (https://playground.liquid.ai) provider.

Uses the site's internal chat API with browser session cookies.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from llm4free.browser_requests._http import compat as requests

from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    count_tokens,
    format_prompt,
)

BASE_URL = "https://playground.liquid.ai"
MODELS = {
    "lfm2.5-24b-a2b": "lfm2.5-24b-a2b-20261027",
    "lfm2.5-24b-a2b-20261027": "lfm2.5-24b-a2b-20261027",
    "lfm3-1.7b": "lfm3-1.7b-20250904",
    "lfm3-1.7b-20250904": "lfm3-1.7b-20250904",
    "lfm3-2.9b": "lfm3-2.9b-20250904",
    "lfm3-2.9b-20250904": "lfm3-2.9b-20250904",
    "lfm3-8b": "lfm3-8b-20250904",
    "lfm3-8b-20250904": "lfm3-8b-20250904",
    "lfm3-3b": "lfm3-3b-20250904",
    "lfm3-3b-20250904": "lfm3-3b-20250904",
    "lfm3-vl-2b": "lfm3-vl-2b",
    "lfm3-vl-3b": "lfm3-vl-3b",
    "lfm3-vl-8b": "lfm3-vl-8b",
    "lfm3-audio-2b": "lfm3-audio-2b",
    "lfm3-omni-2b": "lfm3-omni-2b",
    "lfm2.5-1.2b": "lfm2.5-1.2b-20251007",
    "lfm2.5-1.2b-20251007": "lfm2.5-1.2b-20251007",
    "lfm2.5-1.2b-jp": "lfm2.5-1.2b-jp-20251007",
    "lfm2.5-1.2b-jp-20251007": "lfm2.5-1.2b-jp-20251007",
    "lfm2.5-3b": "lfm2.5-3b-20251007",
    "lfm2.5-3b-20251007": "lfm2.5-3b-20251007",
    "lfm2.5-vl-3b": "lfm2.5-vl-3b-20251007",
    "lfm2.5-vl-3b-20251007": "lfm2.5-vl-3b-20251007",
    "lfm2.5-12b-a2b": "lfm2.5-12b-a2b-20251001",
    "lfm2.5-12b-a2b-20251001": "lfm2.5-12b-a2b-20251001",
}
AVAILABLE_MODELS = list(MODELS.keys())
DEFAULT_MODEL = "lfm2.5-24b-a2b"

_cached_session = None
_cached_user_id = None

FALLBACK_COOKIES = (
    "__Host-authjs.csrf-token=0f384ca202347cd47eb24a4cb3374a8545c7d7a563585ec3bbafa76edc5053a6%7C05c1a31371c162147fdfddcf6745c3034d5b71961409a7a57c6fe59bfcae502b; "
    "_ga=GA1.1.89583887.1793329932; "
    "__Secure-authjs.callback-url=https%3A%2F%2Fplayground.liquid.ai%2Fsign-in%3FcallbackUrl%3D%252Fchat; "
    "_ga_YR3K1FLCF0=GS2.1.s1793329931$o1$g1$t1793329946$j45$l0$h0; "
    "__Secure-authjs.session-token=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwia2lkIjoia2RkNmpSdVJINmFoR3pDRHd0b1dMcldNTGoyb3Byc2pON3djUGd1cnhZUko3eVVKZS01Z1hob1VpSzhXZnlpXzI0LUZvT0tkcmtTQTdrYktaaFU3UWcifQ..TXJKpufamNXOlk-INacglQ.dMTmTJL67FA7M3KuZuUav0ArzAlY2HKIbuQk4m8Fgl8lXVYNEU6TK9ekK0V1dpUDgkwpu7zKTViAQhECVgP_9gcP8EaHAS0LGO_pf6P0s_zV_ermvjLg_ggH_UJuzeo5PHP1QJONgOEcljTc8l8Tw6DCAD1YUScd4yf9_ZETlRIW3y6fR4nx8hviMawfilsl0de1vc6AA3bOy8ETLmBAcCW53LHfkL9P3X-WNawRgijgOZ34I16tHPbsE6zIiWlZ0YkKhVn4MdW6fT9EfZ9PfRN1Efx-YKp2-QdUn2bEfFtRCi88KIlUnoAD7N5Wel2Z7QqBMsjnLlLsSGcBWVFQ1FPvN_DA3y-jx-wNRlzxEw6E8wkw2sUD3mSWEVuBWnVv7Vm-OB4IWE5jZ214vq5_kA.mwbZH90SquT3webINCSkgWfPVJjX1odPioMi0xScOlE"
)


def _get_session_cookies():
    global _cached_session
    if _cached_session is not None:
        return _cached_session
    try:
        s = requests.Session()
        s.headers.update({"Cookie": FALLBACK_COOKIES, "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"})
        _cached_session = s
        return _cached_session
    except Exception:
        return requests.Session()


def _cookie_header() -> str:
    try:
        s = _get_session_cookies()
        cookies = s.cookies.get_dict()
        if cookies:
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
    except Exception:
        pass
    return FALLBACK_COOKIES


def _get_user_id() -> Optional[str]:
    global _cached_user_id
    if _cached_user_id:
        return _cached_user_id
    try:
        s = _get_session_cookies()
        cookie_header = _cookie_header()
        r = s.get(f"{BASE_URL}/api/auth/session", headers={"Cookie": cookie_header, "Referer": f"{BASE_URL}/chat"}, timeout=30)
        if r.ok:
            data = r.json()
            if isinstance(data, dict):
                uid = data.get("user", {}).get("id")
                if uid:
                    _cached_user_id = uid
                    return uid
    except Exception:
        pass
    return "cmvuecg510006jr08vptpv4tl"


class Completions(BaseCompletions):
    def __init__(self, client: "Liquid"):
        self._client = client

    def create(self, *, model=None, messages=None, stream=False, **kwargs):
        model = model or self._client.default_model
        model_slug = MODELS.get(model, model)
        messages = messages or []
        try:
            prompt = format_prompt(messages)
        except Exception:
            prompt = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)

        s = _get_session_cookies()
        cookie_header = _cookie_header()
        user_id = _get_user_id()
        payload = {"userId": user_id} if user_id else {}
        r = s.post(
            f"{BASE_URL}/api/chats",
            headers={
                "Content-Type": "application/json",
                "Cookie": cookie_header,
                "Referer": f"{BASE_URL}/chat",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            },
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        chat_id = r.json().get("newChat", {}).get("id") or r.json().get("id")

        resp = s.post(
            f"{BASE_URL}/api/chats/{chat_id}/messages/stream",
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Cookie": cookie_header,
                "Referer": f"{BASE_URL}/chat",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            },
            json={
                "content": prompt,
                "modelSlug": model_slug,
                "parentMessageId": None,
                "addons": [],
                "mode": "completion",
                "imageUuids": [],
            },
            timeout=180,
            stream=True,
        )
        resp.raise_for_status()

        content = resp.text
        out = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("0:"):
                try:
                    s2 = json.loads(line[2:])
                    if isinstance(s2, str):
                        out.append(s2)
                except Exception:
                    try:
                        s3 = line[2:]
                        if s3.startswith('"') and s3.endswith('"'):
                            s3 = json.loads(s3)
                        out.append(s3)
                    except Exception:
                        pass
                continue
        final = "".join(out).strip()
        if not final and "</think>" in content:
            final = content.split("</think>")[-1].strip()
        if not final:
            final = content

        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())
        if stream:
            def gen():
                yield ChatCompletionChunk(
                    id=request_id,
                    created=created_time,
                    model=model,
                    choices=[ChoiceDelta(index=0, delta=ChoiceDelta.MessageDelta(content=final), finish_reason=None)],
                )
                yield ChatCompletionChunk(
                    id=request_id,
                    created=created_time,
                    model=model,
                    choices=[ChoiceDelta(index=0, delta=ChoiceDelta.MessageDelta(content=""), finish_reason="stop")],
                )
            return gen()

        return ChatCompletion(
            id=request_id,
            created=created_time,
            model=model,
            choices=[Choice(index=0, message=ChatCompletionMessage(role="assistant", content=final), finish_reason="stop")],
            usage=CompletionUsage(
                prompt_tokens=count_tokens(prompt),
                completion_tokens=count_tokens(final),
                total_tokens=count_tokens(prompt) + count_tokens(final),
            ),
        )


class Chat(BaseChat):
    def __init__(self, client: "Liquid"):
        self.completions = Completions(client)


class Liquid(OpenAICompatibleProvider):
    AVAILABLE_MODELS = AVAILABLE_MODELS

    def __init__(self, api_key=None, **kwargs):
        self.default_model = DEFAULT_MODEL
        self.chat = Chat(self)
        self.api_key = api_key

    @property
    def models(self):
        return SimpleModelList(AVAILABLE_MODELS)

    @classmethod
    def get_models(cls):
        return AVAILABLE_MODELS


if __name__ == "__main__":
    c = Liquid()
    try:
        r = c.chat.completions.create(model="lfm2.5-24b-a2b", messages=[{"role": "user", "content": "Hello, how are you?"}], stream=False)
        print(r.choices[0].message.content)
    except Exception as e:
        print(e)
        raise
