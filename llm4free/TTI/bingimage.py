"""
Bing Image Creator TTI Provider.
Uses Microsoft/Bing authentication via cookies.json.
Reverse engineered from https://www.bing.com/images/create/ai-image-generator
"""

import json
import re
import time
import uuid
from typing import Any, Optional

from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse


class Images(BaseImages):
    """Handles image generation requests for the Bing Image Creator provider."""

    def __init__(self, client: "BingImageAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "dalle3",
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
        Creates images using Bing Image Creator.

        Args:
            model (str): Model to use. Options: "dalle3", "mai-image-1", "gpt4o". Defaults to "dalle3".
            prompt (str): The text description of the image to generate.
            n (int): Number of images to generate. Defaults to 1.
            size (str): Image dimensions in "WxH" format. Defaults to "1024x1024".
            response_format (str): Format of the response ("url" or "b64_json"). Defaults to "url".
            user (Optional[str]): Optional user identifier.
            style (str): Optional style parameter.
            aspect_ratio (str): Optional aspect ratio parameter.
            timeout (Optional[int]): Request timeout in seconds. Defaults to 120.
            image_format (str): Output image format ("png" or "jpeg"). Defaults to "png".
            seed (Optional[int]): Random seed for reproducibility.

        Returns:
            ImageResponse: Object containing the generated image data.

        Raises:
            RuntimeError: If image generation or retrieval fails.
        """
        effective_timeout = timeout if timeout is not None else 120

        # Parse aspect ratio
        aspect_map = {
            "1:1": "1:1",
            "16:9": "16:9",
            "9:16": "9:16",
            "square": "1:1",
            "landscape": "16:9",
            "portrait": "9:16",
        }
        ar = aspect_map.get(aspect_ratio, "1:1")

        images_data = []

        for _ in range(n):
            # Step 1: Upload prompt to get request ID
            request_id = self._upload_prompt(prompt, model, ar, effective_timeout)
            if not request_id:
                raise RuntimeError("Failed to upload prompt to Bing")

            # Step 2: Poll for completion
            image_urls = self._poll_for_results(request_id, effective_timeout)
            if not image_urls:
                raise RuntimeError("Failed to get image results from Bing")

            for url in image_urls:
                images_data.append(ImageData(url=url))

        return ImageResponse(data=images_data)

    def _upload_prompt(
        self, prompt: str, model: str, aspect_ratio: str, timeout: int
    ) -> Optional[str]:
        """Upload prompt and get request ID."""
        try:
            # First, get the IG value from the page
            session = self._client.session
            ig_value = self._get_ig_value()
            if not ig_value:
                return None

            # Map model names to API values
            model_map = {
                "dalle3": "DALL-E 3",
                "mai-image-1": "MAI-Image-1",
                "gpt4o": "GPT-4o",
            }
            api_model = model_map.get(model.lower(), model)

            # Upload prompt API
            url = "https://www.bing.com/images/create/api/uploadprompt"
            data = {
                "prompt": prompt,
                "model": api_model,
                "aspectRatio": aspect_ratio,
                "IG": ig_value,
            }

            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.bing.com",
                "Referer": "https://www.bing.com/images/create/ai-image-generator",
                "x-ms-client-request-id": str(uuid.uuid4()),
            }

            # Use curl_cffi session for the request
            resp = session.post(url, json=data, headers=headers, timeout=timeout)

            if resp.status_code == 200:
                try:
                    result = resp.json()
                    return result.get("requestId")
                except json.JSONDecodeError:
                    # Response might be plain text with requestId
                    text = resp.text
                    match = re.search(r'"requestId"\s*:\s*"([^"]+)"', text)
                    if match:
                        return match.group(1)
                    # Try to extract from URL pattern
                    if resp.headers.get("location"):
                        match = re.search(r"requestId=([^&]+)", resp.headers["location"])
                        if match:
                            return match.group(1)
            return None
        except Exception as e:
            print(f"Upload prompt error: {e}")
            return None

    def _poll_for_results(self, request_id: str, timeout: int) -> Optional[list]:
        """Poll for image generation results."""
        max_attempts = 60
        poll_interval = 2

        for attempt in range(max_attempts):
            try:
                url = f"https://www.bing.com/images/create/api/status?requestId={request_id}"
                headers = {
                    "Accept": "application/json",
                    "Referer": "https://www.bing.com/images/create/ai-image-generator",
                }

                resp = self._client.session.get(url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    try:
                        result = resp.json()
                    except json.JSONDecodeError:
                        result = {}

                    status = result.get("status", "").lower()

                    if status == "complete" or status == "succeeded":
                        images = result.get("images", [])
                        if images:
                            urls = []
                            for img in images:
                                if "url" in img:
                                    urls.append(img["url"])
                                elif "thumbnailUrl" in img:
                                    # Get the full size image from thumbnail
                                    thumb = img["thumbnailUrl"]
                                    # Replace thumbnail suffix with full image
                                    full_url = thumb.replace("th?id=", "og?id=")
                                    urls.append(full_url)
                            return urls
                    elif status == "failed" or status == "error":
                        error_msg = result.get("message", "Generation failed")
                        raise RuntimeError(f"Bing generation failed: {error_msg}")

                    # Still processing, wait and retry
                    if attempt < max_attempts - 1:
                        time.sleep(poll_interval)
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(poll_interval)
                    continue
                raise RuntimeError(f"Polling error: {e}")

        return None

    def _get_ig_value(self) -> Optional[str]:
        """Get the IG value from Bing page."""
        try:
            # Fetch the main page to get IG value
            session = self._client.session
            resp = session.get(
                "https://www.bing.com/images/create/ai-image-generator",
                timeout=30,
            )

            if resp.status_code == 200:
                text = resp.text

                # Try to extract IG from page
                # Pattern: "IG":"value"
                match = re.search(r'"IG"\s*:\s*"([^"]+)"', text)
                if match:
                    return match.group(1)

                # Alternative patterns
                patterns = [
                    r'IG\s*=\s*"([^"]+)"',
                    r'ig="([^"]+)"',
                    r'data-ig="([^"]+)"',
                ]
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return match.group(1)

            return None
        except Exception as e:
            print(f"IG value error: {e}")
            return None


class BingImageAI(TTICompatibleProvider):
    """
    Bing Image Creator TTI Provider.

    Reverse engineered from https://www.bing.com/images/create/ai-image-generator

    Authentication:
        Requires a cookies.json file containing Bing session cookies.
        Export cookies from your browser's developer tools after signing into
        https://www.bing.com and navigating to the image creator.
        The cookies file should be in JSON format.

    Cookie Format:
        Simple format: {"cookie_name": "cookie_value", ...}
        Netscape format: [{"name": "cookie_name", "value": "cookie_value", ...}, ...]

    Required Cookies:
        - SRCHD, SRCHUID, SRCHUSR (Bing search cookies)
        - _C_ETH, _C_Auth (authentication cookies)
        - _SS, MUID (session cookies)

    Note: You need Microsoft Rewards to generate images (free tier ~15/day).
    """

    required_auth: bool = True
    working: bool = True
    AVAILABLE_MODELS = [
        "dalle3",
        "mai-image-1",
        "gpt4o",
    ]

    def __init__(self, cookies_file: str = "cookies.json", **kwargs: Any):
        """Initialize Bing Image Creator provider.

        Args:
            cookies_file: Path to cookies.json file containing Bing cookies
            **kwargs: Additional configuration options
        """
        self.api_endpoint = "https://www.bing.com/images/create/ai-image-generator"
        self.session = requests.Session()
        self.user_agent = LitAgent().random()

        # Load cookies from file
        self._load_cookies(cookies_file)

        self.headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.bing.com",
            "referer": "https://www.bing.com/",
            "user-agent": self.user_agent,
        }
        self.session.headers.update(self.headers)

        self.images = Images(self)

    def _load_cookies(self, cookies_file: str) -> None:
        """Load cookies from a JSON file.

        Args:
            cookies_file: Path to cookies.json file

        Raises:
            FileNotFoundError: If cookies file doesn't exist
            json.JSONDecodeError: If cookies file is invalid JSON
        """
        import os

        if not os.path.exists(cookies_file):
            raise FileNotFoundError(
                f"Cookies file not found: {cookies_file}. "
                "Please export your Bing cookies to a cookies.json file. "
                "You can export cookies from your browser's developer tools."
            )

        try:
            with open(cookies_file, "r", encoding="utf-8") as f:
                cookies_data = json.load(f)

            # Support both Netscape format and simple JSON format
            if isinstance(cookies_data, list):
                # Netscape cookie format (list of cookie objects)
                for cookie in cookies_data:
                    if cookie.get("name") and cookie.get("value"):
                        self.session.cookies.set(
                            cookie["name"],
                            cookie["value"],
                            domain=cookie.get("domain", ".bing.com"),
                            path=cookie.get("path", "/"),
                        )
            elif isinstance(cookies_data, dict):
                # Simple JSON format (dict of cookie_name: cookie_value)
                for name, value in cookies_data.items():
                    self.session.cookies.set(name, value, domain=".bing.com")
            else:
                raise ValueError(
                    "Invalid cookies format. Expected a list (Netscape format) "
                    "or dict (simple format)."
                )
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in cookies file: {cookies_file}", e.doc, e.pos
            )

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    try:
        client = BingImageAI()
        print(f"Available Models: {client.models.list()}")

        print("Generating sample image...")
        response = client.images.create(
            prompt="A serene landscape with mountains at sunset",
            model="dalle3",
            size="1024x1024",
        )
        print(response)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(
            "\nTo use Bing Image Creator:\n"
            "1. Sign in to https://www.bing.com\n"
            "2. Go to https://www.bing.com/images/create/ai-image-generator\n"
            "3. Export cookies from browser DevTools (Application > Cookies)\n"
            "4. Save as cookies.json\n"
        )
    except Exception as error:
        print(f"Error during execution: {error}")
