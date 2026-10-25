import base64
import random
import re
import time
from typing import Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.Extra.cookie_harvester import CookieHarvester
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

MODEL_STYLES: dict[str, tuple[str, str]] = {
    "painted-anime": ("", "bad quality, ugly, deformed"),
    "casual-photo": ("casual photo of", "bad quality, ugly, deformed"),
    "cinematic": ("cinematic shot of", "bad quality, ugly, deformed"),
    "digital-painting": ("digital painting of", "bad quality, ugly, deformed"),
    "concept-art": ("concept art of", "bad quality, ugly, deformed"),
    "no-style": ("", "bad quality, ugly, deformed"),
    "3d-disney-character": ("3D Disney character of", "bad quality, ugly, deformed"),
    "2d-disney-character": ("2D Disney character of", "bad quality, ugly, deformed"),
    "disney-sketch": ("Disney sketch of", "bad quality, ugly, deformed"),
    "concept-sketch": ("concept sketch of", "bad quality, ugly, deformed"),
    "painterly": ("painterly of", "bad quality, ugly, deformed"),
    "oil-painting": ("oil painting of", "bad quality, ugly, deformed"),
    "oil-painting-realism": ("oil painting of", "bad quality, ugly, deformed"),
    "oil-painting-old": ("vintage oil painting of", "bad quality, ugly, deformed"),
    "professional-photo": ("professional photo of", "bad quality, ugly, deformed"),
    "anime": ("anime style of", "bad quality, ugly, deformed"),
    "drawn-anime": ("drawn anime style of", "bad quality, ugly, deformed"),
    "anime-screencap": ("anime screencap of", "bad quality, ugly, deformed"),
    "cute-anime": ("cute anime style of", "bad quality, ugly, deformed"),
    "soft-anime": ("soft anime style of", "bad quality, ugly, deformed"),
    "fantasy-painting": ("fantasy painting of", "bad quality, ugly, deformed"),
    "fantasy-landscape": ("fantasy landscape of", "bad quality, ugly, deformed"),
    "fantasy-portrait": ("fantasy portrait of", "bad quality, ugly, deformed"),
    "studio-ghibli": ("Studio Ghibli style of", "bad quality, ugly, deformed"),
    "vintage-comic": ("vintage comic style of", "bad quality, ugly, deformed"),
    "medieval": ("medieval painting of", "bad quality, ugly, deformed"),
    "pixel-art": ("pixel art of", "bad quality, ugly, deformed"),
    "waifu": ("waifu of", "bad quality, ugly, deformed"),
    "manga": ("manga style of", "bad quality, ugly, deformed"),
    "watercolor": ("watercolor painting of", "bad quality, ugly, deformed"),
    "cartoon": ("cartoon style of", "bad quality, ugly, deformed"),
    "claymation": ("claymation of", "bad quality, ugly, deformed"),
    "illustration": ("illustration of", "bad quality, ugly, deformed"),
    "cute-illustration": ("cute illustration of", "bad quality, ugly, deformed"),
    "flat-illustration": ("flat illustration of", "bad quality, ugly, deformed"),
    "crayon-drawing": ("crayon drawing of", "bad quality, ugly, deformed"),
    "pencil": ("pencil sketch of", "bad quality, ugly, deformed"),
    "tattoo-design": ("tattoo design of", "bad quality, ugly, deformed"),
}

RESOLUTIONS: dict[str, str] = {
    "square": "512x512",
    "portrait": "512x768",
    "landscape": "768x512",
}


def _map_style(style: str) -> tuple[str, str]:
    key = style.lower().replace(" ", "-")
    if key in MODEL_STYLES:
        return MODEL_STYLES[key]
    for k, v in MODEL_STYLES.items():
        if k in key or key in k:
            return v
    return MODEL_STYLES["painted-anime"]


def _parse_size(size: str) -> str:
    if size in RESOLUTIONS:
        return RESOLUTIONS[size]
    if "x" in size:
        parts = size.split("x")
        return f"{parts[0]}x{parts[1]}"
    return RESOLUTIONS["square"]


class Images(BaseImages):
    def __init__(self, client: "PerchanceAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "painted-anime",
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

        prompt_style = _map_style(model or style)
        resolution = _parse_size(size or aspect_ratio or "square")

        for _ in range(n):
            create_url = "https://image-generation.perchance.org/api/generate"
            params = {
                "prompt": f"'{prompt}, {prompt_style[0]}",
                "negativePrompt": "'bad quality, ugly, deformed",
                "userKey": self._client.user_key,
                "__cache_bust": str(random.random()),
                "seed": str(seed) if seed is not None else "-1",
                "resolution": resolution,
                "guidanceScale": "7",
                "channel": "ai-text-to-image-generator",
                "subChannel": "public",
                "requestId": str(random.random()),
            }

            try:
                resp = session.get(
                    create_url,
                    params=params,
                    timeout=effective_timeout,
                    impersonate="chrome",
                )
                resp.raise_for_status()
                data = resp.json()
                image_id = data.get("imageId")
                if not image_id:
                    raise RuntimeError(f"No imageId in response: {data}")
            except CurlError as e:
                raise RuntimeError(f"Failed to generate image: {e}")

            try:
                download_url = "https://image-generation.perchance.org/api/downloadTemporaryImage"
                dl_resp = session.get(
                    download_url,
                    params={"imageId": image_id},
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


class PerchanceAI(TTICompatibleProvider):
    required_auth: bool = False
    working: bool = True

    AVAILABLE_MODELS = sorted(MODEL_STYLES.keys())

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        user_key: str = "",
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
        self.user_key = user_key
        self.images = Images(self)

    @classmethod
    def from_browser(
        cls,
        url: str = "https://perchance.org/ai-text-to-image-generator",
        headed: bool = False,
        harvest_timeout: int = 120,
    ) -> "PerchanceAI":

        ch = CookieHarvester(headed=headed, timeout=harvest_timeout)
        ch.harvest(url, wait=8.0, domain_filter=["perchance.org"])
        session = ch.to_requests_session()

        user_key = cls._extract_user_key(session) or ""
        return cls(session=session, user_key=user_key)

    @staticmethod
    def _extract_user_key(session: requests.Session) -> Optional[str]:
        """Try to get a valid userKey by checking with the API."""

        test_key = "0" * 64
        check_url = "https://image-generation.perchance.org/api/checkVerificationStatus"
        try:
            resp = session.get(
                check_url,
                params={"userKey": test_key, "__cacheBust": str(random.random())},
                impersonate="chrome",
                timeout=30,
            )
            text = resp.text
            match = re.search(r"[a-f0-9]{64}", text)
            if match:
                return match.group(0)
        except Exception:
            pass
        return None

    def extract_user_key_from_page(self, headed: bool = True) -> str:
        """Open the page, click generate, and extract userKey from network traffic.

        Requires headed=True so Cloudflare challenges can be solved.
        Returns the extracted 64-char hex key.
        """
        import subprocess

        binary = "agent-browser"
        try:
            subprocess.run([binary, "close", "--all"], capture_output=True, timeout=10)
        except Exception:
            pass

        open_args = ["open", "https://perchance.org/ai-text-to-image-generator"]
        if headed:
            open_args.insert(0, "--headed")
        subprocess.run([binary] + open_args, capture_output=True, timeout=60)

        time.sleep(8)

        try:
            r = subprocess.run(
                [binary, "find", "text", "generate", "click"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            r = subprocess.run(
                [binary, "eval", "document.querySelector('button')?.click()"],
                capture_output=True,
                text=True,
                timeout=30,
            )

        time.sleep(10)

        r = subprocess.run(
            [binary, "state", "save", "/dev/stdout"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        try:
            subprocess.run([binary, "close", "--all"], capture_output=True, timeout=10)
        except Exception:
            pass

        urls = r.stdout + r.stderr
        match = re.search(r"userKey=([a-f0-9]{64})", urls)
        if match:
            key = match.group(1)
            self.user_key = key
            return key

        raise RuntimeError(
            "Could not extract userKey. "
            "Try running with headed=True and solve the Cloudflare challenge."
        )

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    provider = PerchanceAI.from_browser(headed=True)
    response = provider.images.create(
        model="painted-anime",
        prompt="a beautiful mountain landscape at sunset",
        size="portrait",
        response_format="url",
        n=1,
        timeout=120,
    )
    print(response)
