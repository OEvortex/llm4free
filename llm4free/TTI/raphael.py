import base64
import json
import random
import time
import uuid
from typing import Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

RESOLUTIONS: dict[str, str] = {
    "square": "1:1",
    "portrait": "3:4",
    "landscape": "4:3",
}

ASPECT_MAP: dict[str, str] = {
    "1:1": "1:1",
    "square": "1:1",
    "3:4": "3:4",
    "portrait": "3:4",
    "4:3": "4:3",
    "landscape": "4:3",
    "16:9": "16:9",
    "9:16": "9:16",
}

QUALITY_MAP: dict[str, str] = {
    "low": "low",
    "standard": "low",
    "high": "standard",
    "hd": "high",
}

RESOLUTION_TIER_MAP: dict[str, str] = {
    "0.5k": "0.5k",
    "512": "0.5k",
    "1k": "1k",
    "1024": "1k",
    "2k": "2k",
}


def _parse_aspect(size: str) -> str:
    if size in ASPECT_MAP:
        return ASPECT_MAP[size]
    if "x" in size:
        parts = size.split("x")
        w, h = int(parts[0]), int(parts[1])
        if w == h:
            return "1:1"
        if w > h:
            return "4:3" if w / h < 1.6 else "16:9"
        return "3:4" if h / w < 1.6 else "9:16"
    return "1:1"


def _parse_quality(quality: str) -> str:
    return QUALITY_MAP.get(quality.lower(), "low")


def _parse_resolution(size: str) -> str:
    if size in RESOLUTION_TIER_MAP:
        return RESOLUTION_TIER_MAP[size]
    if "x" in size:
        parts = size.split("x")
        max_dim = max(int(parts[0]), int(parts[1]))
        if max_dim <= 512:
            return "0.5k"
        if max_dim <= 1024:
            return "1k"
        return "2k"
    return "0.5k"


MODELS: list[str] = [
    "raphael-basic",
    "raphael-2",
    "gpt-image-2",
    "nano-banana-2",
    "nano-banana-pro",
    "seedream-5",
]

MODEL_ALIASES: dict[str, str] = {
    "raphael-2.0": "raphael-basic",
    "raphael": "raphael-basic",
    "gpt-image": "gpt-image-2",
    "gptimage": "gpt-image-2",
    "nano-banana": "nano-banana-2",
    "nano-banana-pro": "nano-banana-pro",
    "nano-banana-2": "nano-banana-2",
    "seedream": "seedream-5",
    "seedream-5.0": "seedream-5",
    "flux": "flux",
}


def _resolve_model(model: str) -> str:
    key = model.lower().strip()
    return MODEL_ALIASES.get(key, key)


class Images(BaseImages):
    def __init__(self, client: "RaphaelAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "raphael-basic",
        prompt: str,
        n: int = 1,
        size: str = "512x512",
        response_format: str = "url",
        user: Optional[str] = None,
        style: str = "",
        aspect_ratio: str = "",
        timeout: Optional[int] = None,
        image_format: str = "png",
        seed: Optional[int] = None,
        convert_format: bool = False,
        **kwargs,
    ) -> ImageResponse:
        effective_timeout = timeout or 120
        agent = LitAgent()
        images: list[bytes] = []
        urls: list[str] = []
        session = self._client.session

        aspect = _parse_aspect(aspect_ratio or size)
        quality = _parse_quality(kwargs.get("quality", "low"))
        resolution = _parse_resolution(size)

        for _ in range(n):
            payload = {
                "prompt": prompt,
                "entry_type": "ai-image",
                "aspect": aspect,
                "isSafeContent": True,
                "autoTranslate": False,
                "model_id": _resolve_model(model),
                "number_of_images": 1,
                "highQuality": quality == "high",
                "fastMode": False,
                "size": aspect,
                "quality": quality,
                "resolution": resolution,
                "turnstileToken": None,
                "client_request_id": str(uuid.uuid4()),
            }

            try:
                resp = session.post(
                    "https://raphael.app/api/generate-image",
                    json=payload,
                    timeout=effective_timeout,
                    impersonate="chrome",
                )
            except CurlError as e:
                raise RuntimeError(f"Failed to generate image: {e}")

            if resp.status_code == 429:
                data = resp.json()
                error_code = data.get("error", {}).get("code", "")
                if error_code == "ANON_DAILY_LIMIT":
                    raise RuntimeError(
                        "Daily anonymous generation limit reached (2/day). "
                        "Use signed-in cookies or try again tomorrow."
                    )
                raise RuntimeError(f"Rate limited: {data}")

            if resp.status_code == 401:
                data = resp.json()
                raise RuntimeError(
                    f"Authentication required: {data.get('error', {}).get('message', 'Login needed')}"
                )

            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" in content_type or "text/plain" in content_type:
                image_url = self._parse_stream(resp.text)
            else:
                data = resp.json()
                image_url = data.get("url") or (
                    data.get("data", {}).get("url") if isinstance(data.get("data"), dict) else None
                )

            if not image_url:
                raise RuntimeError(f"No image URL in response: {resp.text[:200]}")

            try:
                dl_resp = session.get(
                    image_url,
                    timeout=effective_timeout,
                    impersonate="chrome",
                )
                dl_resp.raise_for_status()
                img_bytes = dl_resp.content
            except CurlError as e:
                raise RuntimeError(f"Failed to download image: {e}")

            images.append(img_bytes)

            if response_format == "url":
                uploaded_url = upload_image_with_fallback(
                    img_bytes, image_format, agent, effective_timeout
                )
                if not uploaded_url:
                    raise RuntimeError("Failed to upload image: all hosting services exhausted")
                urls.append(uploaded_url)

        result_data: list[ImageData] = []
        if response_format == "url":
            for u in urls:
                result_data.append(ImageData(url=u))
        elif response_format == "b64_json":
            for img in images:
                b64 = base64.b64encode(img).decode("utf-8")
                result_data.append(ImageData(b64_json=b64))

        return ImageResponse(created=int(time.time()), data=result_data)

    @staticmethod
    def _parse_stream(text: str) -> Optional[str]:
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                url = obj.get("url")
                if url:
                    return url
            except (json.JSONDecodeError, KeyError):
                continue
        return None


class RaphaelAI(TTICompatibleProvider):
    required_auth: bool = True
    working: bool = True

    AVAILABLE_MODELS = MODELS[:]

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        **kwargs,
    ):
        if session:
            self.session = session
        else:
            self.session = requests.Session()
            self.session.headers.update(
                {
                    "accept": "*/*",
                    "accept-language": "en-US,en;q=0.9",
                    "user-agent": LitAgent().random(),
                }
            )
        self.images = Images(self)

    @classmethod
    def from_browser(
        cls,
        url: str = "https://raphael.app/text-to-image",
        headed: bool = False,
        harvest_timeout: int = 120,
    ) -> "RaphaelAI":
        from llm4free.Extra.cookie_harvester import CookieHarvester

        ch = CookieHarvester(headed=headed, timeout=harvest_timeout)
        ch.harvest(url, wait=10.0, domain_filter=["raphael.app"])
        session = ch.to_requests_session()
        return cls(session=session)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    provider = RaphaelAI.from_browser(headed=True)
    response = provider.images.create(
        model="raphael-basic",
        prompt="a beautiful mountain landscape at sunset",
        size="portrait",
        response_format="url",
        n=1,
        timeout=120,
    )
    print(response)
