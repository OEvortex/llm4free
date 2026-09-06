"""Stable Horde text-to-image provider.

Stable Horde (AI Horde) is a crowdsourced distributed cluster for AI image
generation. Anonymously accessible with optional API key.
"""

import base64
import random
import time
from typing import Any, Dict, List, Optional, Union

from curl_cffi import CurlError, requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.utils import ImageData, ImageResponse

BASE_URL = "https://stablehorde.net/api/v2"
ANON_KEY = "0000000000"

DEFAULT_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
}


def _build_client_agent() -> str:
    # Format: client_name:version:contact_details
    return "llm4free:1.0:unknown"


class Images(BaseImages):
    def __init__(self, client: "StableHordeAI"):
        self._client = client

    def create(
        self,
        *,
        model: str = "auto",
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
        steps: int = 30,
        cfg_scale: float = 7.0,
        sampler_name: str = "k_euler_a",
        karras: bool = True,
        trusted_workers: bool = False,
        nsfw: bool = False,
        censor_nsfw: bool = False,
        negative_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ImageResponse:
        """Generate images using Stable Horde.

        Args:
            model: Model name from available models, or "auto".
            prompt: Positive prompt for image generation.
            n: Number of images to generate (1-10).
            size: Image size in "widthxheight" format.
            response_format: "url" or "b64_json".
            timeout: Overall timeout in seconds (default: 300).
            seed: Optional random seed.
            steps: Number of sampling steps.
            cfg_scale: Classifier-free guidance scale.
            sampler_name: Sampler algorithm.
            karras: Whether to use Karras noise schedule.
            trusted_workers: Only use trusted workers.
            nsfw: Allow NSFW generation.
            censor_nsfw: Censor NSFW content.
            negative_prompt: Negative prompt (appended with "###").
        """
        effective_timeout = timeout if timeout is not None else 300
        session = self._client.session

        if "x" in size:
            width, height = map(int, size.split("x"))
        else:
            width = height = int(size)

        width = max(64, width - (width % 64))
        height = max(64, height - (height % 64))

        resolved_model = model
        if model == "auto":
            available = self._client.models.list()
            resolved_model = random.choice(available) if available else "Deliberate"
        else:
            available = self._client.models.list()
            if resolved_model not in available:
                matches = [m for m in available if resolved_model.lower() in m.lower()]
                resolved_model = matches[0] if matches else (available[0] if available else "Deliberate")

        effective_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}###{negative_prompt}"

        params: Dict[str, Any] = {
            "steps": min(max(steps, 1), 150),
            "cfg_scale": cfg_scale,
            "width": width,
            "height": height,
            "seed": str(effective_seed),
            "sampler_name": sampler_name,
            "karras": karras,
            "n": min(max(n, 1), 10),
        }

        if kwargs.get("denoising_strength") is not None:
            params["denoising_strength"] = kwargs["denoising_strength"]
        if kwargs.get("hires_fix"):
            params["hires_fix"] = True
        if kwargs.get("hires_fix_denoising_strength") is not None:
            params["hires_fix_denoising_strength"] = kwargs["hires_fix_denoising_strength"]
        if kwargs.get("tiling"):
            params["tiling"] = True
        if kwargs.get("clip_skip") is not None:
            params["clip_skip"] = kwargs["clip_skip"]
        if kwargs.get("facefixer_strength") is not None:
            params["facefixer_strength"] = kwargs["facefixer_strength"]

        payload: Dict[str, Any] = {
            "prompt": full_prompt,
            "params": params,
            "models": [resolved_model],
            "nsfw": nsfw,
            "censor_nsfw": censor_nsfw,
            "trusted_workers": trusted_workers,
            "r2": True,
            "replacement_filter": kwargs.get("replacement_filter", enhance),
        }

        if user:
            payload["proxyid"] = user

        headers = self._build_headers()

        try:
            resp = session.post(
                f"{BASE_URL}/generate/async",
                json=payload,
                headers=headers,
                timeout=30,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except CurlError as e:
            raise RuntimeError(f"Stable Horde request failed: {e}")

        data = resp.json()
        task_id = data.get("id")
        if not task_id:
            raise RuntimeError(f"No task_id returned: {data}")

        return self._poll_and_download(task_id, effective_timeout, n, session)

    def _build_headers(self) -> Dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers["apikey"] = self._client.api_key
        headers["Client-Agent"] = self._client.client_agent
        return headers

    def _poll_and_download(
        self,
        task_id: str,
        timeout: int,
        expected_n: int,
        session: requests.Session,
    ) -> ImageResponse:
        start = time.time()
        poll_headers = {
            "apikey": self._client.api_key,
            "Client-Agent": self._client.client_agent,
            "accept": "application/json",
        }

        while time.time() - start < timeout:
            try:
                resp = session.get(
                    f"{BASE_URL}/generate/check/{task_id}",
                    headers=poll_headers,
                    timeout=20,
                    impersonate="chrome",
                )
                resp.raise_for_status()
                status = resp.json()
            except CurlError:
                time.sleep(2)
                continue

            if status.get("done"):
                break
            if status.get("faulted"):
                raise RuntimeError(f"Stable Horde generation faulted: {status}")
            time.sleep(2)
        else:
            raise RuntimeError("Stable Horde generation timed out")

        try:
            resp = session.get(
                f"{BASE_URL}/generate/status/{task_id}",
                headers=poll_headers,
                timeout=30,
                impersonate="chrome",
            )
            resp.raise_for_status()
            result = resp.json()
        except CurlError as e:
            raise RuntimeError(f"Stable Horde status failed: {e}")

        generations = result.get("generations", [])
        if not generations:
            raise RuntimeError("Stable Horde returned no generations")

        images: List[bytes] = []
        urls: List[str] = []

        for gen in generations:
            img = gen.get("img", "")
            if not img:
                continue

            try:
                img_resp = session.get(img, timeout=30, impersonate="chrome")
                img_resp.raise_for_status()
                img_bytes = img_resp.content
            except CurlError as e:
                raise RuntimeError(f"Failed to download Stable Horde image: {e}")

            images.append(img_bytes)
            urls.append(img)

        if not images:
            raise RuntimeError("No images could be downloaded from Stable Horde")

        result_data: List[ImageData] = []
        for img_url in urls:
            result_data.append(ImageData(url=img_url))

        return ImageResponse(created=int(time.time()), data=result_data)


class StableHordeAI(TTICompatibleProvider):
    """Stable Horde (AI Horde) text-to-image provider.

    Generates images via the distributed AI Horde cluster. Works without
    authentication, but an API key improves queue priority.
    """

    required_auth: bool = False
    working: bool = True

    def __init__(self, api_key: Optional[str] = None, **kwargs: Any):
        self.api_key = api_key or ANON_KEY
        self.client_agent = _build_client_agent()
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update(DEFAULT_HEADERS)
        self._models: List[str] = []
        self.images = Images(self)

    @property
    def models(self) -> SimpleModelList:
        if not self._models:
            self._fetch_models()
        return SimpleModelList(self._models)

    def _fetch_models(self) -> None:
        try:
            resp = self.session.get(
                f"{BASE_URL}/status/models",
                timeout=30,
                impersonate="chrome",
            )
            resp.raise_for_status()
            models_data = resp.json()
            image_models = [m["name"] for m in models_data if m.get("type") == "image"]
            if image_models:
                self._models = sorted(image_models)
            else:
                self._models = ["Deliberate"]
        except Exception:
            self._models = ["Deliberate"]


if __name__ == "__main__":
    from rich import print

    client = StableHordeAI()
    response = client.images.create(
        model="auto",
        prompt="a japanese waifu in short kimono clothes",
        response_format="url",
        n=1,
        size="1024x1024",
        timeout=180,
        steps=30,
    )
    print(response)
