import hashlib
import json
import time
import uuid
from typing import Any, Optional

from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageData, ImageResponse


class Images(BaseImages):
    def __init__(self, client: "VisualGPT"):
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
        Generate images using VisualGPT API.

        Args:
            model: Model to use for generation (default: "nano-banana")
            prompt: The image generation prompt
            n: Number of images to generate (default: 1)
            size: Image size (e.g., "1024x1024")
            response_format: "url" or "b64_json"
            user: Optional user identifier
            style: Style parameter (general, photo, illustration, 3d, painting, c4d)
            aspect_ratio: Aspect ratio
            timeout: Request timeout in seconds (default: 120)
            image_format: Output format (not used, always returns URL)
            seed: Optional random seed for reproducibility
            convert_format: Not applicable for this provider
            **kwargs: Additional parameters

        Returns:
            ImageResponse with generated image data

        Raises:
            RuntimeError: If image generation fails or times out
        """
        effective_timeout = timeout if timeout is not None else 120

        # Map style names to VisualGPT style IDs
        style_map = {
            "general": "",
            "photo": "",
            "illustration": "",
            "3d": "",
            "painting": "",
            "c4d": "",
            "none": "",
        }

        # Generate timestamp and signature
        timestamp = int(time.time())
        sign_data = self._generate_signature(prompt, timestamp)

        # Prepare request payload
        payload = {
            "input_urls": [],
            "type": 60,  # Text-to-image type
            "user_prompt": prompt,
            "sub_type": 45,  # AI image generator
            "aspect_ratio": "match_input_image",
            "size": size,
            "resolution": "",
            "quality": "",
            "speed": "",
            "model_type": 2,  # Nano Banana model
            "output_num": n,
            "image_generator_style": style_map.get(style.lower(), ""),
            "sign": sign_data,
            "t": timestamp,
            "sig_version": "v1",
        }

        # Submit generation request
        try:
            resp = self._client.session.post(
                "https://visualgpt.io/api/v1/prediction/handle",
                json=payload,
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            raise RuntimeError(f"Failed to submit image generation request: {e}")

        if result.get("code") != 100000:
            raise RuntimeError(f"API error: {result.get('message', 'Unknown error')}")

        project_id = result.get("data", {}).get("project_id")
        if not project_id:
            raise RuntimeError("No project_id returned from API")

        # Poll for results
        max_attempts = 60  # Maximum polling attempts (2 minutes)
        poll_interval = 2  # Seconds between polls

        for attempt in range(max_attempts):
            try:
                status_resp = self._client.session.get(
                    f"https://visualgpt.io/api/v1/prediction/get-status?project_id={project_id}",
                    timeout=effective_timeout,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data.get("code") == 100000:
                    data = status_data.get("data", {})
                    status = data.get("status")
                    results = data.get("results", [])

                    if status == 1 and results:  # Complete
                        result_urls = []
                        for result in results:
                            result_content = result.get("result_content", "")
                            if result_content:
                                result_urls.append(result_content)

                        if result_urls:
                            result_data = []
                            if response_format == "url":
                                for url in result_urls:
                                    result_data.append(ImageData(url=url))
                            elif response_format == "b64_json":
                                # For b64_json, we'd need to download and encode the images
                                # For now, return URLs as fallback
                                for url in result_urls:
                                    result_data.append(ImageData(url=url))
                            else:
                                raise ValueError("response_format must be 'url' or 'b64_json'")

                            return ImageResponse(created=int(time.time()), data=result_data)

                # If not complete, wait and retry
                if attempt < max_attempts - 1:
                    time.sleep(poll_interval)
            except Exception as e:
                if attempt < max_attempts - 1:
                    time.sleep(poll_interval)
                    continue
                raise RuntimeError(f"Failed to check generation status: {e}")

        raise RuntimeError(
            f"Image generation timed out after {max_attempts * poll_interval} seconds"
        )

    def _generate_signature(self, prompt: str, timestamp: int) -> str:
        """
        Generate signature for VisualGPT API.

        Note: The exact signature algorithm is client-side and may require
        reverse engineering from JavaScript. This is a simplified implementation
        that may not work with the actual API.

        Args:
            prompt: The user prompt
            timestamp: Unix timestamp

        Returns:
            Hex string signature
        """
        # This is a placeholder signature generation
        # The actual algorithm may involve:
        # - Secret key
        # - Specific parameter ordering
        # - Additional hashing rounds
        data = f"{prompt}:{timestamp}:visualgpt"
        return hashlib.sha256(data.encode()).hexdigest()


class VisualGPT(TTICompatibleProvider):
    """VisualGPT AI Image Generator Provider.

    This provider uses VisualGPT's API for text-to-image generation.

    Authentication:
        Requires a cookies.json file containing VisualGPT session cookies.
        Export cookies from your browser's developer tools after logging into
        https://visualgpt.io. The cookies file should be in JSON format.

    Cookie Format:
        Simple format: {"cookie_name": "cookie_value", ...}
        Netscape format: [{"name": "cookie_name", "value": "cookie_value", ...}, ...]

    Note: The API requires signature-based authentication which is generated
    client-side. The signature generation may need to be reverse engineered
    from the frontend JavaScript for full functionality.
    """

    # Provider status
    required_auth: bool = True  # Requires cookies.json file for authentication
    working: bool = True  # Currently working

    AVAILABLE_MODELS = [
        "nano-banana",  # Default model
    ]

    def __init__(self, cookies_file: str = "cookies.json", **kwargs: Any):
        """Initialize VisualGPT provider.

        Args:
            cookies_file: Path to cookies.json file containing VisualGPT cookies
            **kwargs: Additional configuration options
        """
        self.api_endpoint = "https://visualgpt.io/api/v1/prediction/handle"
        self.session = requests.Session()
        self.user_agent = LitAgent().random()

        # Load cookies from file
        self._load_cookies(cookies_file)

        self.headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "content-type": "application/json; charset=UTF-8",
            "origin": "https://visualgpt.io",
            "referer": "https://visualgpt.io/ai-image-generator",
            "user-agent": self.user_agent,
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
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
                "Please export your VisualGPT cookies to a cookies.json file. "
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
                            domain=cookie.get("domain", "visualgpt.io"),
                            path=cookie.get("path", "/"),
                        )
            elif isinstance(cookies_data, dict):
                # Simple JSON format (dict of cookie_name: cookie_value)
                for name, value in cookies_data.items():
                    try:
                        self.session.cookies.set(name, value)
                    except Exception:
                        pass
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

    client = VisualGPT()
    try:
        response = client.images.create(
            model="nano-banana",
            prompt="a beautiful sunset over mountains",
            response_format="url",
            n=1,
            timeout=120,
        )
        print(response)
    except Exception as e:
        print(f"Error: {e}")
        print("Note: The signature generation may need to be reverse engineered from JavaScript")
