import base64
import time
from typing import Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

API_BASE = "https://draw.onefreeai.com"

MODEL_MAP: dict[str, str] = {
    "qwen_image_plus": "Qwen Image Plus",
    "flux_1_1_pro": "Flux 1.1 Pro",
    "flux_1_1_pro_ultra": "Flux 1.1 Pro Ultra",
    "nano_banana": "Nano Banana",
    "nano_banana_pro": "Nano Banana Pro",
}

SIZE_MAP: dict[str, str] = {
    "1:1": "1024x1024",
    "3:2": "1152x768",
    "2:3": "768x1152",
    "3:4": "768x1024",
    "4:3": "1024x768",
    "9:16": "576x1024",
    "16:9": "1024x576",
}


def _resolve_size(size: str) -> str:
    if size in SIZE_MAP:
        return SIZE_MAP[size]
    if size in SIZE_MAP.values():
        return size
    return "1024x1024"


def _resolve_model(model: str) -> str:
    key = model.lower().strip()
    return MODEL_MAP.get(key, model)


class Images(BaseImages):
    def __init__(self, client: "OneFreeAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "qwen_image_plus",
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
        effective_timeout = timeout or 120
        agent = LitAgent()
        images: list[bytes] = []
        urls: list[str] = []
        session = self._client.session

        resolved_model = _resolve_model(model)
        resolved_size = _resolve_size(size)
        prompt_text = (prompt or "").strip()

        for _ in range(n):
            fd = {
                "prompt": prompt_text,
                "size": resolved_size,
                "model": resolved_model,
                "influence": "20",
            }

            try:
                resp = session.post(
                    f"{API_BASE}/api/text2image.php",
                    data=fd,
                    timeout=effective_timeout,
                    impersonate="chrome",
                )
                resp.raise_for_status()
            except CurlError as e:
                raise RuntimeError(f"Failed to submit generation task: {e}")

            data = resp.json()
            task_id = data.get("task_id")
            if not task_id:
                raise RuntimeError(f"No task_id in response: {data}")

            image_url = self._poll_task(task_id, effective_timeout, session)

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

    def _poll_task(self, task_id: str, timeout: int, session: requests.Session) -> str:
        started = time.time()
        while time.time() - started < timeout:
            fd = {"task_id": task_id}
            try:
                resp = session.post(
                    f"{API_BASE}/api/text2image.php",
                    data=fd,
                    timeout=30,
                    impersonate="chrome",
                )
                resp.raise_for_status()
            except CurlError as e:
                raise RuntimeError(f"Poll request failed: {e}")

            data = resp.json()
            status = data.get("task_status") or data.get("status", "")

            if status == "SUCCEEDED":
                url = (
                    data.get("url")
                    or (data.get("result", {}).get("data", [{}])[0].get("url"))
                    or ""
                )
                if url:
                    return url
                raise RuntimeError(f"Task succeeded but no URL found: {data}")

            if status == "FAILED":
                raise RuntimeError(data.get("error") or "Generation failed")

            time.sleep(1.5)

        raise RuntimeError("Generation timed out")


class OneFreeAI(TTICompatibleProvider):
    required_auth: bool = False
    working: bool = True

    AVAILABLE_MODELS = list(MODEL_MAP.keys())

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

    client = OneFreeAI()
    response = client.images.create(
        model="qwen_image_plus",
        prompt="a beautiful sunset over mountains, vibrant colors",
        response_format="url",
        n=1,
        timeout=120,
    )
    print(response)
