import base64
import re
from typing import Any, List, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
from urllib.parse import quote as curl_utils

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageData, ImageResponse

SEARCH_BASE = "https://lexica.art"
IMAGE_CDN = "https://image.lexica.art"
RSC_BUILD_HASH = "1"

RSC_HEADERS = {
    "RSC": "1",
    "Next-Url": "/",
    "Next-Router-State-Tree": (
        '["",{"loginModal":["children",{"children":["[...catchAll]",'
        '{"children":["__PAGE__",{}]}]}],"promptModal":["children",'
        '{"children":["[...catchAll]",{"children":["__PAGE__",{}]}]}],'
        '"children":["__PAGE__",{}]},null,null,true]'
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://lexica.art/",
}

IMAGE_ID_RE = re.compile(r'"id":"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})","promptid"')

SIZE_VARIANT_MAP = {
    "1024x1024": "md2_webp",
    "1024x576": "md2_webp",
    "576x1024": "md2_webp",
    "1024x768": "md2_webp",
    "768x1024": "md2_webp",
    "1152x768": "md2_webp",
    "768x1152": "md2_webp",
    "full": "full_webp",
}


def _resolve_variant(size: str, image_format: str) -> str:
    variant = SIZE_VARIANT_MAP.get((size or "").strip().lower(), "md2_webp")
    if image_format == "jpeg":
        variant = variant.replace("_webp", "")
    return variant


class Images(BaseImages):
    def __init__(self, client: "Lexica"):
        self._client = client

    def _search(self, prompt: str, timeout: int, session: requests.Session) -> List[str]:
        url = f"{SEARCH_BASE}/?q={curl_utils.quote(prompt)}&_rsc={RSC_BUILD_HASH}"
        try:
            resp = session.get(
                url,
                headers=RSC_HEADERS,
                timeout=timeout,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except CurlError as e:
            raise RuntimeError(f"Lexica search request failed: {e}")

        ids = IMAGE_ID_RE.findall(resp.text)
        seen: set[str] = set()
        unique: List[str] = []
        for image_id in ids:
            if image_id not in seen:
                seen.add(image_id)
                unique.append(image_id)
        return unique

    def create(
        self,
        *,
        model: str = "lexica",
        prompt: str,
        n: int = 1,
        size: str = "1024x1024",
        response_format: str = "url",
        user: Optional[str] = None,
        style: str = "none",
        aspect_ratio: str = "1:1",
        timeout: Optional[int] = None,
        image_format: str = "png",
        seed: Optional[int] = None,
        convert_format: bool = False,
        **kwargs,
    ) -> ImageResponse:
        effective_timeout = timeout or 60
        session = self._client.session
        prompt_text = (prompt or "").strip()
        if not prompt_text:
            raise ValueError("prompt is required")

        image_ids = self._search(prompt_text, effective_timeout, session)
        if not image_ids:
            raise RuntimeError("Lexica returned no images for the given prompt")

        variant = _resolve_variant(size, image_format)
        selected = image_ids[: max(1, n)]

        result_data: List[ImageData] = []
        for image_id in selected:
            image_url = f"{IMAGE_CDN}/{variant}/{image_id}"
            if response_format == "url":
                result_data.append(ImageData(url=image_url))
            elif response_format == "b64_json":
                try:
                    dl = session.get(
                        image_url,
                        timeout=effective_timeout,
                        impersonate="chrome",
                    )
                    dl.raise_for_status()
                    b64 = base64.b64encode(dl.content).decode("utf-8")
                    result_data.append(ImageData(b64_json=b64))
                except CurlError as e:
                    raise RuntimeError(f"Failed to download image {image_id}: {e}")
            else:
                raise ValueError("response_format must be 'url' or 'b64_json'")

        return ImageResponse(data=result_data)


class Lexica(TTICompatibleProvider):
    required_auth: bool = False
    working: bool = True

    AVAILABLE_MODELS = ["lexica"]

    def __init__(self, session: Optional[requests.Session] = None, **kwargs):
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

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = Lexica()
    response = client.images.create(
        model="lexica",
        prompt="a cute cat wearing a hat, studio lighting",
        response_format="url",
        n=3,
    )
    print(response)
