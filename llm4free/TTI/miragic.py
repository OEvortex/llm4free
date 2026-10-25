import json
import random
from typing import Any, Optional

from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageData, ImageResponse


class Images(BaseImages):
    """Handles image generation requests for the Miragic AI provider."""

    def __init__(self, client: "MiragicAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "flux",
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
        **kwargs,
    ) -> ImageResponse:
        """
        Creates images using the Miragic AI API.

        Args:
            model (str): The model to use. Options: "flux", "turbo", "gptimage". Defaults to "flux".
            prompt (str): The text description of the image to generate.
            n (int): Number of images to generate. Defaults to 1.
            size (str): Image dimensions in "WxH" format. Defaults to "1024x1024".
            response_format (str): Format of the response ("url" or "b64_json"). Defaults to "url".
            user (Optional[str]): Optional user identifier.
            style (str): Optional style parameter.
            aspect_ratio (str): Optional aspect ratio parameter.
            timeout (Optional[int]): Request timeout in seconds. Defaults to 60.
            image_format (str): Output image format ("png" or "jpeg"). Defaults to "png".
            seed (Optional[int]): Random seed for reproducibility.
            **kwargs: Additional parameters:
                - enhance_prompt (bool): Use AI to enhance the prompt.
                - safe_filter (bool): Enable strict NSFW filtering.
                - image_url (str): Source image URL for image-to-image models.

        Returns:
            ImageResponse: Object containing the generated image data.

        Raises:
            RuntimeError: If image generation or retrieval fails.
        """
        # Use default timeout if not provided
        effective_timeout = timeout if timeout is not None else 60

        width, height = 1024, 1024
        if size:
            try:
                parts = size.split("x")
                if len(parts) == 2:
                    width, height = int(parts[0]), int(parts[1])
            except ValueError:
                pass

        width = max(256, min(2048, width))
        height = max(256, min(2048, height))

        enhance = kwargs.get("enhance_prompt", False)
        safe = kwargs.get("safe_filter", False)
        image_url = kwargs.get("image_url")

        images_data = []

        for _ in range(n):
            current_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

            payload = {
                "data": [prompt, model, width, height, current_seed, image_url, enhance, safe]
            }

            try:
                post_url = f"{self._client.api_endpoint}/call/generate_image_via_api_secure"
                resp = self._client.session.post(post_url, json=payload, timeout=effective_timeout)
                resp.raise_for_status()

                event_id = resp.json().get("event_id")
                if not event_id:
                    raise RuntimeError(f"Failed to obtain event_id: {resp.text}")

                stream_url = (
                    f"{self._client.api_endpoint}/call/generate_image_via_api_secure/{event_id}"
                )
                image_url_result = None

                with self._client.session.get(
                    stream_url, stream=True, timeout=effective_timeout + 60
                ) as stream_resp:
                    stream_resp.raise_for_status()
                    for line in stream_resp.iter_lines():
                        if not line:
                            continue
                        line_text = line.decode("utf-8")

                        if line_text.startswith("data: "):
                            data_str = line_text[6:]
                            try:
                                data_json = json.loads(data_str)
                                if isinstance(data_json, list) and len(data_json) > 0:
                                    result_item = data_json[0]
                                    if isinstance(result_item, dict):
                                        image_url_result = result_item.get("url")
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                raise RuntimeError(f"Image generation failed: {e}")

            if image_url_result:
                images_data.append(ImageData(url=image_url_result))
            else:
                raise RuntimeError("Failed to retrieve image URL from the response stream.")

        return ImageResponse(data=images_data)


class MiragicAI(TTICompatibleProvider):
    """
    Miragic AI TTI Provider implementation.

    Reverse engineered from the Hugging Face Space:
    https://huggingface.co/spaces/Miragic-AI/Miragic-AI-Image-Generator
    """

    required_auth: bool = False
    working: bool = True
    AVAILABLE_MODELS = ["flux", "turbo", "gptimage"]

    def __init__(self, **kwargs: Any):
        """Initializes the MiragicAI provider with a persistent session."""
        self.api_endpoint = "https://miragic-ai-miragic-ai-image-generator.hf.space/gradio_api"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": LitAgent().random(),
                "Referer": "https://miragic-ai-miragic-ai-image-generator.hf.space/",
                "Origin": "https://miragic-ai-miragic-ai-image-generator.hf.space",
                "Content-Type": "application/json",
            }
        )
        self.images = Images(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    try:
        client = MiragicAI()
        print(f"Available Models: {client.models.list()}")

        print("Generating sample image...")
        response = client.images.create(
            prompt="A serene landscape with a lake and mountains, oil painting style",
            model="flux",
            size="1024x1024",
        )
        print(response)

    except Exception as error:
        print(f"Error during execution: {error}")
