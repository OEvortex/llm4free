import base64
import json
import random
import time
from io import BytesIO
from typing import TYPE_CHECKING, Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

# Optional Pillow import for image format conversion
Image: Any = None
PILLOW_AVAILABLE = False
try:
    from PIL import Image  # type: ignore

    PILLOW_AVAILABLE = True
except ImportError:
    pass

if TYPE_CHECKING:
    from PIL import Image as PILImage  # type: ignore


def _convert_image_format(img_bytes: bytes, target_format: str) -> bytes:
    """
    Convert image bytes to the specified format using Pillow.

    Args:
        img_bytes: Raw image bytes
        target_format: Target format ('png' or 'jpeg')

    Returns:
        Converted image bytes

    Raises:
        ImportError: If Pillow is not installed
    """
    if not PILLOW_AVAILABLE or Image is None:
        raise ImportError(
            "Pillow (PIL) is required for image format conversion. "
            "Install it with: pip install pillow"
        )

    with BytesIO(img_bytes) as input_io:
        with Image.open(input_io) as im:
            out_io = BytesIO()
            if target_format.lower() == "jpeg":
                im = im.convert("RGB")
                im.save(out_io, format="JPEG")
            else:
                im.save(out_io, format="PNG")
            return out_io.getvalue()


def _detect_image_format(img_bytes: bytes) -> Optional[str]:
    """
    Detect image format from magic bytes.

    Args:
        img_bytes: Raw image bytes

    Returns:
        Format string ('png', 'jpeg', 'gif', 'webp') or None if unknown
    """
    if len(img_bytes) < 12:
        return None

    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    # JPEG: FF D8 FF
    if img_bytes[:3] == b"\xff\xd8\xff":
        return "jpeg"

    # GIF: GIF87a or GIF89a
    if img_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    # WebP: RIFF....WEBP
    if img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
        return "webp"

    return None


class Images(BaseImages):
    def __init__(self, client: "PollinationsAI"):
        self._client = client

    def create(
        self,
        *,
        model: str,
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
        """
        Generate images using Pollinations API.

        Args:
            model: Model to use for generation
            prompt: The image generation prompt
            n: Number of images to generate
            size: Image size (e.g., "1024x1024")
            response_format: "url" or "b64_json"
            user: Optional user identifier
            style: Style parameter
            aspect_ratio: Aspect ratio
            timeout: Request timeout in seconds (default: 60)
            image_format: Output format "png" or "jpeg" (used for upload filename)
            seed: Optional random seed for reproducibility
            convert_format: If True, convert image to specified format (requires Pillow)

        Returns:
            ImageResponse with generated image data
        """
        # Use default timeout if not provided
        effective_timeout = timeout if timeout is not None else 60

        agent = LitAgent()
        images = []
        urls = []

        for i in range(n):
            # Prepare parameters for Pollinations API
            params: dict[str, Any] = {
                "model": model,
                "width": int(size.split("x")[0]) if "x" in size else 1024,
                "height": int(size.split("x")[1]) if "x" in size else 1024,
                "seed": seed if seed is not None else random.randint(0, 2**32 - 1),
                "nologo": kwargs.get("nologo", True),
            }

            # Optional boolean parameters
            if "enhance" in kwargs:
                params["enhance"] = kwargs["enhance"]
            if "safe" in kwargs:
                params["safe"] = kwargs["safe"]
            if "private" in kwargs:
                params["private"] = kwargs["private"]
            if "transparent" in kwargs:
                params["transparent"] = kwargs["transparent"]

            # Build the API URL
            base_url = f"https://image.pollinations.ai/prompt/{prompt}"
            # Compose query string
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{base_url}?{query}"
            try:
                resp = self._client.session.get(
                    url,
                    timeout=effective_timeout,
                )
                resp.raise_for_status()
                img_bytes = resp.content
            except CurlError as e:
                raise RuntimeError(f"Failed to fetch image from Pollinations API: {e}")

            # Convert image format if requested
            if convert_format:
                img_bytes = _convert_image_format(img_bytes, image_format)
                actual_format = image_format
            else:
                # Detect actual image format from bytes
                actual_format = _detect_image_format(img_bytes) or image_format

            images.append(img_bytes)

            if response_format == "url":
                uploaded_url = upload_image_with_fallback(
                    img_bytes, actual_format, agent, effective_timeout
                )
                if uploaded_url:
                    urls.append(uploaded_url)
                else:
                    raise RuntimeError("Failed to upload image: all hosting services exhausted")

        result_data = []
        if response_format == "url":
            for url in urls:
                result_data.append(ImageData(url=url))
        elif response_format == "b64_json":
            for img in images:
                b64 = base64.b64encode(img).decode("utf-8")
                result_data.append(ImageData(b64_json=b64))
        else:
            raise ValueError("response_format must be 'url' or 'b64_json'")

        return ImageResponse(created=int(time.time()), data=result_data)


class PollinationsAI(TTICompatibleProvider):
    """PollinationsAI TTI Provider - Allows setting a custom seed for reproducible results."""

    # Provider status
    required_auth: bool = False  # No authentication required
    working: bool = True  # Currently working

    AVAILABLE_MODELS = [
        "flux",
        "flux-pro",
        "flux-realism",
        "flux-anime",
        "flux-3d",
        "any-dark",
        "turbo",
        "gptimage",
        "gptimage-large",
        "kontext",
        "nanobanana",
        "nanobanana-pro",
        "seedream",
        "seedream-pro",
        "qwen-image",
        "grok-imagine",
    ]

    def __init__(self):
        self.api_endpoint = "https://image.pollinations.ai/prompt"
        self.session = requests.Session()
        self.user_agent = LitAgent().random()
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://image.pollinations.ai",
            "referer": "https://image.pollinations.ai/",
            "user-agent": self.user_agent,
        }
        self.session.headers.update(self.headers)
        self.images = Images(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = PollinationsAI()
    response = client.images.create(
        model="flux",
        prompt="a japanese waifu in short kimono clothes",
        response_format="url",
        n=4,
        timeout=30,
        seed=None,  # You can set a specific seed for reproducibility
        convert_format=False,  # Set to True to convert format (requires Pillow)
    )
    print(response)
