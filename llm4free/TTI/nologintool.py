import base64
import random
import time
from typing import Any, Optional

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests

from llm4free.AIbase import SimpleModelList
from llm4free.litagent import LitAgent
from llm4free.TTI.base import BaseImages, TTICompatibleProvider
from llm4free.TTI.image_hosting import upload_image_with_fallback
from llm4free.TTI.utils import ImageData, ImageResponse

WORKER_PRIMARY = "https://nologintoo.abdelatifana0.workers.dev"
WORKER_BACKUP = "https://broad-tree-0b90.sari63252.workers.dev"
HORDE_BASE = "https://stablehorde.net/api/v2"
HORDE_KEY = "9EQ6zZwIMjTRLUffoEPKqA"

MODEL_MAP: dict[str, dict[str, str]] = {
    "pollinations": {
        "flux": "Flux (Best for Text)",
    },
    "cloudflare": {
        "@cf/black-forest-labs/flux-1-schnell": "Flux 1 Schnell",
        "@cf/bytedance/stable-diffusion-xl-lightning": "SDXL Lightning",
        "@cf/stabilityai/stable-diffusion-xl-base-1.0": "Stable Diffusion XL",
    },
    "cloudflare2": {
        "@cf/black-forest-labs/flux-1-schnell": "Flux 1 Schnell",
        "@cf/bytedance/stable-diffusion-xl-lightning": "SDXL Lightning",
        "@cf/stabilityai/stable-diffusion-xl-base-1.0": "Stable Diffusion XL",
    },
    "horde": {
        "stable_diffusion": "Standard",
        "Albedobase XL (SDXL)": "Realistic",
        "Anything Diffusion": "Anime",
    },
}

ALL_MODELS = list(dict.fromkeys(m for server_models in MODEL_MAP.values() for m in server_models))


def _resolve_server(model: str) -> str:
    for server, models in MODEL_MAP.items():
        if model in models:
            return server
    return "cloudflare"


class Images(BaseImages):
    def __init__(self, client: "NoLoginTool"):
        self._client = client

    def create(
        self,
        *,
        model: str = "@cf/black-forest-labs/flux-1-schnell",
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

        if "x" in size:
            parts = size.split("x")
            width, height = int(parts[0]), int(parts[1])
        else:
            width = height = 1024

        server = kwargs.get("server") or _resolve_server(model)
        actual_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        for _ in range(n):
            if server == "horde":
                img_bytes = self._generate_horde(
                    prompt, model, width, height, effective_timeout, session
                )
            else:
                img_bytes = self._generate_worker(
                    server, prompt, model, width, height, actual_seed, effective_timeout, session
                )

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

    def _generate_worker(
        self,
        server: str,
        prompt: str,
        model: str,
        width: int,
        height: int,
        seed: int,
        timeout: int,
        session: requests.Session,
    ) -> bytes:
        target = "cloudflare" if server in ("cloudflare", "cloudflare2") else server
        worker = WORKER_BACKUP if server == "cloudflare2" else WORKER_PRIMARY

        params = {
            "target": target,
            "prompt": prompt,
            "model": model,
            "width": width,
            "height": height,
            "seed": seed,
        }

        try:
            resp = session.get(
                worker,
                params=params,
                timeout=timeout,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except CurlError as e:
            raise RuntimeError(f"Worker request failed: {e}")

        content_type = resp.headers.get("content-type", "")
        if "image/" in content_type:
            return resp.content

        if resp.content[:4] == b"\x89PNG" or resp.content[:3] == b"\xff\xd8\xff":
            return resp.content

        raise RuntimeError(f"Unexpected response: {resp.text[:200]}")

    def _generate_horde(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int,
        timeout: int,
        session: requests.Session,
    ) -> bytes:
        payload = {
            "prompt": prompt,
            "params": {
                "sampler_name": "k_euler_a",
                "width": width,
                "height": height,
                "steps": 30,
                "n": 1,
            },
            "models": [model],
        }

        try:
            resp = session.post(
                f"{HORDE_BASE}/generate/async",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "apikey": HORDE_KEY,
                    "Client-Agent": "NoLoginTool:v1.0:unknown",
                },
                timeout=30,
                impersonate="chrome",
            )
            resp.raise_for_status()
        except CurlError as e:
            raise RuntimeError(f"Horde submit failed: {e}")

        data = resp.json()
        task_id = data.get("id")
        if not task_id:
            raise RuntimeError(f"No task_id: {data}")

        return self._poll_horde(task_id, timeout, session)

    def _poll_horde(self, task_id: str, timeout: int, session: requests.Session) -> bytes:
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = session.get(
                    f"{HORDE_BASE}/generate/check/{task_id}",
                    timeout=15,
                    impersonate="chrome",
                )
                resp.raise_for_status()
                status = resp.json()
            except CurlError:
                time.sleep(2)
                continue

            if status.get("done"):
                break
            time.sleep(2)
        else:
            raise RuntimeError("Horde generation timed out")

        try:
            resp = session.get(
                f"{HORDE_BASE}/generate/status/{task_id}",
                timeout=30,
                impersonate="chrome",
            )
            resp.raise_for_status()
            result = resp.json()
        except CurlError as e:
            raise RuntimeError(f"Horde status failed: {e}")

        generations = result.get("generations", [])
        if not generations:
            raise RuntimeError("Horde returned no image")

        img_url = generations[0].get("img", "")
        if not img_url:
            raise RuntimeError("No image URL in Horde response")

        try:
            img_resp = session.get(img_url, timeout=30, impersonate="chrome")
            img_resp.raise_for_status()
            return img_resp.content
        except CurlError as e:
            raise RuntimeError(f"Failed to download Horde image: {e}")


class NoLoginTool(TTICompatibleProvider):
    required_auth: bool = False
    working: bool = True

    AVAILABLE_MODELS = ALL_MODELS[:]

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

    client = NoLoginTool()
    response = client.images.create(
        model="@cf/black-forest-labs/flux-1-schnell",
        prompt="a beautiful sunset over mountains, vibrant colors",
        response_format="url",
        n=1,
        timeout=120,
    )
    print(response)
