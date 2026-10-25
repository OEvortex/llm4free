"""
MagicHour AI - Free TTI Provider for LLM4Free
https://magichour.ai/products/ai-image-generator

Uses the free API endpoint that doesn't require API key.
Note: Rate limited to ~10 requests per IP.
"""

import uuid
from typing import TYPE_CHECKING, Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

# Mapping from aspect ratio to MagicHour format
ASPECT_RATIO_MAP = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "16:9",
    "3:4": "9:16",
    "21:9": "16:9",
    "9:21": "9:16",
    "square": "1:1",
    "landscape": "16:9",
    "portrait": "9:16",
}


class Images(BaseImages):
    def __init__(self, client: "MagicHourAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "general",
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
        Generate images using MagicHour AI free API.

        Args:
            model: Tool/style to use (default: "general")
            prompt: The image generation prompt
            n: Number of images to generate (max 4)
            size: Image size (e.g., "1024x1024")
            response_format: "url" or "b64_json"
            user: Optional user identifier
            style: Style parameter (general, photorealistic, anime, etc.)
            aspect_ratio: Aspect ratio (1:1, 16:9, 9:16)
            timeout: Request timeout in seconds (default: 120)
            image_format: Output format "png" or "jpeg"
            seed: Optional random seed
            convert_format: If True, convert image to specified format

        Returns:
            ImageResponse with generated image data
        """
        import time as time_module

        effective_timeout = timeout if timeout is not None else 120

        # Map aspect ratio
        aspect = ASPECT_RATIO_MAP.get(aspect_ratio, "1:1")

        # Determine tool/style
        tool = style if style and style != "none" else "general"

        agent = LitAgent()
        images = []
        urls = []

        for i in range(n):
            # Generate unique task_id
            task_id = str(uuid.uuid4())

            # Prepare request payload
            payload = {
                "tool": tool,
                "image_count": 1,
                "prompt": prompt,
                "aspect_ratio": aspect,
                "task_id": task_id,
            }

            # Submit generation request
            try:
                resp = self._client.session.post(
                    "https://magichour.ai/api/free-tools/v5/ai-image-generator",
                    json=payload,
                    timeout=effective_timeout,
                )
                resp.raise_for_status()
            except CurlError as e:
                raise RuntimeError(f"Failed to submit request to MagicHour: {e}")
            except Exception as e:
                raise RuntimeError(f"API request failed: {e}")

            # Poll for results
            image_urls = self._poll_for_results(task_id, prompt, tool, aspect, effective_timeout)

            if not image_urls:
                raise RuntimeError("Failed to get image results from MagicHour")

            for url in image_urls:
                # Download the actual image
                try:
                    img_resp = self._client.session.get(url, timeout=effective_timeout)
                    img_resp.raise_for_status()
                    img_bytes = img_resp.content
                except CurlError as e:
                    raise RuntimeError(f"Failed to download generated image: {e}")

                images.append(img_bytes)

                if response_format == "url":
                    # Upload to hosting service
                    uploaded_url = upload_image_with_fallback(
                        img_bytes, image_format, agent, effective_timeout
                    )
                    if uploaded_url:
                        urls.append(uploaded_url)
                    else:
                        raise RuntimeError("Failed to upload image: all hosting services exhausted")

        # Build response
        result_data = []
        if response_format == "url":
            for url in urls:
                result_data.append(ImageData(url=url))
        elif response_format == "b64_json":
            import base64

            for img in images:
                b64 = base64.b64encode(img).decode("utf-8")
                result_data.append(ImageData(b64_json=b64))
        else:
            raise ValueError("response_format must be 'url' or 'b64_json'")

        return ImageResponse(created=int(time_module.time()), data=result_data)

    def _poll_for_results(
        self,
        task_id: str,
        prompt: str,
        tool: str,
        aspect_ratio: str,
        timeout: int,
    ) -> Optional[list]:
        """Poll for image generation results."""
        max_attempts = 30
        poll_interval = 3

        for attempt in range(max_attempts):
            try:
                # Re-submit with same task_id to check status
                payload = {
                    "tool": tool,
                    "image_count": 1,
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "task_id": task_id,
                }

                resp = self._client.session.post(
                    "https://magichour.ai/api/free-tools/v5/ai-image-generator",
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()

                data = resp.json()

                # Check rate limit response
                if not data.get("allow", True):
                    limit = data.get("limit", "unknown")
                    remaining = data.get("remaining", 0)
                    retry_after = data.get("retryAfter", "unknown")
                    raise RuntimeError(
                        f"Rate limit exceeded. Limit: {limit}, Remaining: {remaining}, "
                        f"Retry after: {retry_after} seconds"
                    )

                # Check for successful response
                if "urls" in data and data["urls"]:
                    return data["urls"]

                # Check for errors
                if data.get("detail"):
                    raise RuntimeError(f"MagicHour error: {data['detail']}")

            except CurlError as e:
                if attempt < max_attempts - 1:
                    import time

                    time.sleep(poll_interval)
                    continue
                raise RuntimeError(f"Polling error: {e}")

            # Wait before next poll
            if attempt < max_attempts - 1:
                import time

                time.sleep(poll_interval)

        return None


class MagicHourAI(TTICompatibleProvider):
    """
    MagicHour AI Free TTI Provider for LLM4Free.

    Uses the free endpoint that doesn't require API key.
    https://magichour.ai/products/ai-image-generator

    Rate Limit: ~10 free requests per IP
    """

    # Provider status
    required_auth: bool = False  # No auth required for free endpoint
    working: bool = True

    # Available models (tools/styles)
    AVAILABLE_MODELS = [
        "general",
        "photorealistic",
        "cinematic",
        "anime",
        "cartoon",
        "watercolor",
        "digital-art",
        "fantasy",
        "vector",
        "minimalist",
        "illustration",
        "3d-render",
        "oil-painting",
        "sketch",
        "retro",
        "surreal",
    ]

    def __init__(self, **kwargs: Any):
        """Initialize MagicHour AI provider (no API key needed)."""
        self.api_endpoint = "https://magichour.ai/api/free-tools/v5/ai-image-generator"
        self.session = requests.Session()

        # Set up headers
        user_agent = LitAgent().random()
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://magichour.ai",
            "referer": "https://magichour.ai/products/ai-image-generator",
            "user-agent": user_agent,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
        }
        self.session.headers.update(self.headers)
        self.images = Images(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    client = MagicHourAI()

    # List available models
    print("Available models:", client.models.list())

    # Generate an image
    response = client.images.create(
        model="general",
        prompt="A serene mountain landscape at golden hour",
        n=1,
        aspect_ratio="16:9",
        timeout=120,
    )
    print(response)
