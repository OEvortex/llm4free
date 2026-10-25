"""
Centralized image hosting module for TTI providers.
Provides a fallback chain for uploading generated images.
"""

import os
import tempfile
import time
from typing import Optional

from llm4free.browser_requests._http.compat import post as requests_post
from llm4free.browser_requests._http.compat import put as requests_put


def upload_to_catbox(img_bytes: bytes, ext: str, agent, timeout: int) -> Optional[str]:
    """Upload image to catbox.moe."""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp.flush()
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                files = {"fileToUpload": (f"image.{ext}", f, f"image/{ext}")}
                data = {"reqtype": "fileupload", "json": "true"}
                upload_headers = {"User-Agent": agent.random()}
                upload_resp = requests_post(
                    "https://catbox.moe/user/api.php",
                    files=files,
                    data=data,
                    headers=upload_headers,
                    timeout=timeout,
                )
                if upload_resp.status_code == 200 and upload_resp.text.strip():
                    text = upload_resp.text.strip()
                    if text.startswith("http"):
                        return text
                    try:
                        result = upload_resp.json()
                        if "url" in result:
                            return result["url"]
                    except Exception:
                        if "http" in text:
                            return text
        finally:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception:
        pass
    return None


def upload_to_0x0st(img_bytes: bytes, ext: str, agent, timeout: int) -> Optional[str]:
    """Upload image to 0x0.st."""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp.flush()
            tmp_path = tmp.name

        try:
            if not os.path.isfile(tmp_path):
                return None
            with open(tmp_path, "rb") as img_file:
                files = {"file": img_file}
                alt_resp = requests_post("https://0x0.st", files=files, timeout=timeout)
                alt_resp.raise_for_status()
                image_url = alt_resp.text.strip()
                if not image_url.startswith("http"):
                    return None
                return image_url
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        pass
    return None


def upload_to_anonfiles(img_bytes: bytes, ext: str, agent, timeout: int) -> Optional[str]:
    """Upload image to anonfiles.com."""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp.flush()
            tmp_path = tmp.name

        try:
            if not os.path.isfile(tmp_path):
                return None
            with open(tmp_path, "rb") as img_file:
                files = {"file": img_file}
                resp = requests_post("https://anonfiles.com", files=files, timeout=timeout)
                if resp.status_code == 200:
                    result = resp.json()
                    if "file" in result and "url" in result["file"]:
                        return result["file"]["url"]["full"]
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        pass
    return None


def upload_to_transfersh(img_bytes: bytes, ext: str, agent, timeout: int) -> Optional[str]:
    """Upload image to transfer.sh."""
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp.flush()
            tmp_path = tmp.name

        try:
            if not os.path.isfile(tmp_path):
                return None
            with open(tmp_path, "rb") as img_file:
                data = img_file.read()
                resp = requests_put(
                    "https://transfer.sh/image",
                    data=data,
                    timeout=timeout,
                    headers={
                        "Content-Type": f"image/{ext}",
                        "User-Agent": agent.random(),
                    },
                )
                if resp.status_code == 200:
                    url = resp.text.strip()
                    if url.startswith("http"):
                        return url
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception:
        pass
    return None


def upload_image_with_fallback(
    img_bytes: bytes,
    image_format: str,
    agent,
    timeout: int = 30,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Upload image using a fallback chain of hosting services.

    Args:
        img_bytes: Raw image bytes
        image_format: Image format ("png", "jpg", or "jpeg")
        agent: LitAgent instance for user-agent rotation
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per service

    Returns:
        URL of the uploaded image, or None if all services fail.
    """
    ext = "jpg" if image_format.lower() in ("jpeg", "jpg") else "png"

    # Define the fallback chain
    upload_services = [
        ("catbox.moe", upload_to_catbox),
        ("0x0.st", upload_to_0x0st),
        ("anonfiles.com", upload_to_anonfiles),
        ("transfer.sh", upload_to_transfersh),
    ]

    for service_name, upload_func in upload_services:
        for attempt in range(max_retries):
            try:
                url = upload_func(img_bytes, ext, agent, timeout)
                if url:
                    return url
            except Exception:
                pass

            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))

    return None
