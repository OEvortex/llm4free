import json
import random
from typing import Any, Dict, Optional, Union, cast

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
from llm4free.browser_requests._http.compat import Session

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageData, ImageResponse


class Images(BaseImages):
    def __init__(self, client):
        self._client = client
        self.base_url = "https://api.together.xyz/v1"
        self.session = Session()

    def _setup_session_with_retries(self):
        """Setup session with retry strategy and timeout configurations"""
        pass

    def build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build headers with API authorization using consistent fingerprint"""
        api_key = self._client.api_key

        # Reuse or generate fingerprint once for the session
        if not hasattr(self._client, "_fingerprint") or self._client._fingerprint is None:
            self._client._fingerprint = self._generate_consistent_fingerprint()

        fp = self._client._fingerprint
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": fp["accept_language"],
            "User-Agent": fp["user_agent"],
            "Sec-CH-UA": fp["sec_ch_ua"],
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{fp["platform"]}"',
            "Origin": "https://api.together.xyz",
            "Referer": "https://api.together.xyz/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        }
        if extra:
            headers.update(extra)
        return headers

    def _generate_consistent_fingerprint(self) -> Dict[str, str]:
        """
        Generate a consistent browser fingerprint using the client's LitAgent.
        """
        from llm4free.litagent.constants import BROWSERS, FINGERPRINTS

        agent = self._client._agent
        user_agent = agent.browser("chrome")

        accept_language = random.choice(FINGERPRINTS["accept_language"])
        accept = random.choice(FINGERPRINTS["accept"])
        platform = random.choice(FINGERPRINTS["platforms"])

        # Generate sec-ch-ua for chrome
        version = random.randint(*BROWSERS["chrome"])
        sec_ch_ua_dict = cast(Dict[str, str], FINGERPRINTS["sec_ch_ua"])
        sec_ch_ua = sec_ch_ua_dict["chrome"].format(version, version)

        # Use the client's agent for consistent IP rotation
        ip = agent.rotate_ip()
        fingerprint = {
            "user_agent": user_agent,
            "accept_language": accept_language,
            "accept": accept,
            "sec_ch_ua": sec_ch_ua,
            "platform": platform,
            "x-forwarded-for": ip,
            "x-real-ip": ip,
            "x-client-ip": ip,
            "forwarded": f"for={ip};proto=https",
            "x-forwarded-proto": "https",
            "x-request-id": agent.random_id(8)
            if hasattr(agent, "random_id")
            else "".join(random.choices("0123456789abcdef", k=8)),
        }

        return fingerprint

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
        enhance: bool = True,
        steps: int = 20,
        **kwargs,
    ) -> ImageResponse:
        """
        Create images using Together.xyz image models
        """
        if not prompt:
            raise ValueError("Describe the image you want to create (use the 'prompt' property).")

        if not self._client.api_key:
            raise ValueError(
                "API key is required for TogetherImage. Please provide it in __init__."
            )

        # Validate model
        if model not in self._client.AVAILABLE_MODELS:
            raise ValueError(
                f"Model '{model}' not available. Choose from: {self._client.AVAILABLE_MODELS}"
            )

        # Parse size
        if "x" in size:
            width, height = map(int, size.split("x"))
        else:
            width = height = int(size)

        # Build request body
        body = {
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            # Clamp steps to 1-4 as required by Together.xyz API
            "steps": min(max(steps, 1), 4),
            "n": min(max(n, 1), 4),  # Clamp between 1-4
        }

        # Add optional parameters
        if seed is not None:
            body["seed"] = seed

        # Add any additional kwargs
        body.update(kwargs)

        try:
            resp = self.session.request(
                "POST",
                f"{self.base_url}/images/generations",
                json=body,
                headers=self.build_headers(),
                timeout=timeout,
            )

            data = resp.json()

            # Check for errors
            if "error" in data:
                error_msg = data["error"].get("message", str(data["error"]))
                raise RuntimeError(f"Together.xyz API error: {error_msg}")

            if not data.get("data") or len(data["data"]) == 0:
                raise RuntimeError("Failed to process image. No data found.")

            result = data["data"]
            result_data = []

            for i, item in enumerate(result):
                if response_format == "url":
                    if "url" in item:
                        result_data.append(ImageData(url=item["url"]))
                else:  # b64_json
                    if "b64_json" in item:
                        result_data.append(ImageData(b64_json=item["b64_json"]))

            if not result_data:
                raise RuntimeError("No valid image data found in response")

            return ImageResponse(data=result_data)

        except CurlError as e:
            print(f"[Together.xyz API error] {e}")
            raise RuntimeError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise RuntimeError("Invalid JSON response from Together.xyz API")
        except Exception as e:
            raise RuntimeError(f"An error occurred: {str(e)}")


class TogetherImage(TTICompatibleProvider):
    """
    Together.xyz Text-to-Image provider
    Updated: 2025-12-19 12:10:00 UTC
    Supports FLUX and other image generation models via Together.xyz API
    """

    # Provider status
    required_auth: bool = True  # Now requires user-provided API key
    working: bool = True  # Working as of 2025-12-19

    # Image models from Together.xyz API (filtered for image type only)
    AVAILABLE_MODELS = []

    @classmethod
    def get_models(cls, api_key: Optional[str] = None):
        """Fetch available image models from Together API."""
        if not api_key:
            # Return default models if no API key is provided
            return [
                "black-forest-labs/FLUX.1-canny",
                "black-forest-labs/FLUX.1-depth",
                "black-forest-labs/FLUX.1-dev",
                "black-forest-labs/FLUX.1-dev-lora",
                "black-forest-labs/FLUX.1-kontext-dev",
                "black-forest-labs/FLUX.1-kontext-max",
                "black-forest-labs/FLUX.1-kontext-pro",
                "black-forest-labs/FLUX.1-krea-dev",
                "black-forest-labs/FLUX.1-pro",
                "black-forest-labs/FLUX.1-redux",
                "black-forest-labs/FLUX.1-schnell",
                "black-forest-labs/FLUX.1-schnell-Free",
                "black-forest-labs/FLUX.1.1-pro",
            ]

        try:
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

            response = requests.get(
                "https://api.together.xyz/v1/models", headers=headers, timeout=30
            )

            if response.status_code != 200:
                return cls.get_models(None)

            models_data = response.json()

            # Filter image models
            image_models = []
            if isinstance(models_data, list):
                for model in models_data:
                    if isinstance(model, dict) and model.get("type", "").lower() == "image":
                        image_models.append(model["id"])

            if image_models:
                return sorted(image_models)
            else:
                return cls.get_models(None)

        except Exception:
            return cls.get_models(None)

    @classmethod
    def update_available_models(cls, api_key: Optional[str] = None):
        """Update the available models list from Together API"""
        try:
            models = cls.get_models(api_key)
            if models and len(models) > 0:
                cls.AVAILABLE_MODELS = models
        except Exception:
            cls.AVAILABLE_MODELS = cls.get_models(None)

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the TogetherImage client.

        Args:
            api_key (str, optional): Together.xyz API key.
        """
        self.api_key = api_key
        # Update available models if API key is provided
        if api_key:
            self.update_available_models(api_key)
        else:
            self.AVAILABLE_MODELS = self.get_models(None)

        self.images = Images(self)
        # Initialize LitAgent for consistent fingerprints across image generation requests
        self._agent = LitAgent()
        self._fingerprint = None

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)

    def convert_model_name(self, model: str) -> str:
        """Convert model alias to full model name"""
        if model in self.AVAILABLE_MODELS:
            return model

        # Default to first available model
        return self.AVAILABLE_MODELS[0]


if __name__ == "__main__":
    from rich import print

    client = TogetherImage(api_key="YOUR_API_KEY")

    # Test with a sample prompt - now requires model and prompt as keyword args
    response = client.images.create(
        model="black-forest-labs/FLUX.1-schnell-Free",  # Free FLUX model
        prompt="A majestic dragon flying over a mystical forest, fantasy art, highly detailed",
        size="1024x1024",
        n=1,
        steps=25,
        response_format="url",
        timeout=120,
    )
    print(response)
