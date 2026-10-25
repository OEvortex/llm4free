import base64
import time
import uuid
from io import BytesIO
from typing import TYPE_CHECKING, Any, Optional

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


def _convert_image_format(img_bytes: bytes, image_format: str) -> bytes:
    """
    Convert image bytes to the specified format using Pillow.

    Args:
        img_bytes: Raw image bytes
        image_format: Target format ("png", "jpg", or "jpeg")

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
            if image_format.lower() in ("jpeg", "jpg"):
                im = im.convert("RGB")
                im.save(out_io, format="JPEG")
            else:
                im.save(out_io, format="PNG")
            return out_io.getvalue()


class Images(BaseImages):
    def __init__(self, client: "MagicStudioAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "magicstudio",
        prompt: str,
        n: int = 1,
        size: str = "1024x1024",
        response_format: str = "url",
        user: Optional[str] = None,
        style: str = "none",
        aspect_ratio: str = "1:1",
        timeout: Optional[int] = None,
        image_format: str = "jpg",
        seed: Optional[int] = None,
        convert_format: bool = False,
        **kwargs,
    ) -> ImageResponse:
        """
        Generate images using MagicStudio's AI art generator.

        Args:
            model: Model to use (default: "magicstudio")
            prompt: The image generation prompt (required)
            n: Number of images to generate
            size: Image size (not used by this provider)
            response_format: "url" or "b64_json"
            user: Optional user identifier
            style: Optional style parameter
            aspect_ratio: Optional aspect ratio
            timeout: Request timeout in seconds (default: 60)
            image_format: Output format "png" or "jpg" (used for upload and conversion)
            seed: Optional random seed for reproducibility
            convert_format: If True, convert image to specified format (requires Pillow)
            **kwargs: Additional parameters

        Returns:
            ImageResponse with generated image data

        Raises:
            ValueError: If prompt is not provided or response_format is invalid
            ImportError: If convert_format is True but Pillow is not installed
        """
        if not prompt:
            raise ValueError("Prompt is required!")

        # Use default timeout if not provided
        effective_timeout = timeout if timeout is not None else 60

        agent = LitAgent()
        images = []
        urls = []
        api_url = "https://ai-api.magicstudio.com/api/ai-art-generator"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": agent.random(),
            "Origin": "https://magicstudio.com",
            "Referer": "https://magicstudio.com/ai-art-generator/",
            "DNT": "1",
            "Sec-GPC": "1",
        }
        session = requests.Session()
        session.headers.update(headers)
        for _ in range(n):
            form_data = {
                "prompt": prompt,
                "output_format": "bytes",
                "user_profile_id": "null",
                "anonymous_user_id": str(uuid.uuid4()),
                "request_timestamp": str(time.time()),
                "user_is_subscribed": "false",
                "client_id": str(uuid.uuid4().hex),
            }
            resp = session.post(
                api_url,
                data=form_data,
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            img_bytes = resp.content

            # Convert image format if requested (requires Pillow)
            if convert_format:
                img_bytes = _convert_image_format(img_bytes, image_format)

            images.append(img_bytes)
            if response_format == "url":
                uploaded_url = upload_image_with_fallback(
                    img_bytes, image_format, agent, effective_timeout
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


class MagicStudioAI(TTICompatibleProvider):
    """MagicStudio AI TTI Provider - Generates images through MagicStudio's public endpoint."""

    # Provider status
    required_auth: bool = False  # No authentication required
    working: bool = True  # Currently working

    AVAILABLE_MODELS = ["magicstudio"]

    def __init__(self):
        self.api_endpoint = "https://ai-api.magicstudio.com/api/ai-art-generator"
        self.session = requests.Session()
        self.user_agent = LitAgent().random()
        self.headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://magicstudio.com",
            "referer": "https://magicstudio.com/ai-art-generator/",
            "user-agent": self.user_agent,
        }
        self.session.headers.update(self.headers)
        self.images = Images(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = MagicStudioAI()
    response = client.images.create(
        model="magicstudio",
        prompt="A cool cyberpunk city at night",
        response_format="url",
        n=2,
        timeout=30,
    )
    print(response)
