##################################################################################
##  ParlerTTS Provider                                                         ##
##################################################################################
import json
import pathlib
import random
import string
import tempfile
from typing import Any, Optional, Union, cast

from llm4free.browser_requests._http import compat as cf_requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent

try:
    from . import utils
    from .base import BaseTTSProvider
except ImportError:
    # Handle direct execution
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    from llm4free.TTS.base import BaseTTSProvider


class ParlerTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the Parler-TTS API (Hugging Face Spaces).

    Features:
    - High-fidelity speech generation
    - Controllable via simple text prompts (description)
    - Manual polling logic for robustness
    """

    required_auth = False

    BASE_URL = "https://parler-tts-parler-tts.hf.space"

    # Request headers
    headers: dict[str, str] = {
        "User-Agent": LitAgent().random(),
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/",
    }

    SUPPORTED_MODELS = ["parler-mini-v1", "parler-large-v1"]

    def __init__(self, timeout: int = 120, proxy: Optional[str] = None):
        """
        Initialize the ParlerTTS client.
        """
        super().__init__()
        self.timeout = timeout
        self.proxy = proxy
        self.default_model = "parler-mini-v1"

    def _generate_session_hash(self) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

    def tts(self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs) -> str:
        """
        Convert text to speech using Parler-TTS API.

        Args:
            text (str): The text to convert to speech
            voice (str): The voice to use
            verbose (bool): Whether to print debug information
            **kwargs: Additional parameters
        """
        # Extract parameters from kwargs with defaults
        description = kwargs.get(
            "description",
            "A female speaker delivers a slightly expressive and animated speech with a moderate speed. The recording features a low-pitch voice and very clear audio.",
        )
        use_large = kwargs.get("use_large", False)
        response_format = kwargs.get("response_format", "wav")
        verbose = verbose if verbose is not None else kwargs.get("verbose", True)

        if not text:
            raise ValueError("Input text must be a non-empty string")

        session_hash = self._generate_session_hash()
        filename = pathlib.Path(
            tempfile.NamedTemporaryFile(
                suffix=f".{response_format}", dir=self.temp_dir, delete=False
            ).name
        )

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"ParlerTTS: Generating speech for '{text[:20]}...'")

        client_kwargs: dict[str, Any] = {"headers": self.headers, "timeout": self.timeout}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        try:
            with cf_requests.Session(**client_kwargs) as client:
                # Step 1: Join the queue
                join_url = f"{self.BASE_URL}/queue/join?__theme=system"
                # fn_index 0 is for the main generation task
                payload = {
                    "data": [text, description, use_large],
                    "event_data": None,
                    "fn_index": 0,
                    "trigger_id": 8,
                    "session_hash": session_hash,
                }

                response = client.post(join_url, json=payload)
                response.raise_for_status()

                # Step 2: Poll for data
                data_url = f"{self.BASE_URL}/queue/data?session_hash={session_hash}"
                audio_url = None

                # Gradio Spaces can take time to wake up or process
                with client.stream("GET", data_url) as stream:
                    for line in stream.iter_lines():
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode("utf-8")
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue

                            msg = data.get("msg")
                            if msg == "process_completed":
                                if data.get("success"):
                                    output_data = data.get("output", {}).get("data", [])
                                    if output_data:
                                        audio_info = output_data[0]
                                        path = (
                                            audio_info["path"]
                                            if isinstance(audio_info, dict)
                                            else audio_info
                                        )
                                        audio_url = f"{self.BASE_URL}/file={path}"
                                    break
                                else:
                                    raise exceptions.FailedToGenerateResponseError(
                                        f"Generation failed: {data}"
                                    )
                            elif msg == "queue_full":
                                raise exceptions.FailedToGenerateResponseError("Queue is full")
                            elif msg == "send_hash":
                                # Normal handshake
                                pass

                if not audio_url:
                    raise exceptions.FailedToGenerateResponseError(
                        "Failed to get audio URL from stream"
                    )

                # Step 3: Download the audio file
                audio_response = client.get(audio_url)
                audio_response.raise_for_status()

                with open(filename, "wb") as f:
                    f.write(audio_response.content)

                if verbose:
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Speech generated successfully: {filename}")

                return filename.as_posix()

        except Exception as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Error in ParlerTTS: {e}")
            raise exceptions.FailedToGenerateResponseError(f"Failed to generate audio: {e}")

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "parler-mini-v1",
        voice: Optional[str] = None,
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
        verbose: bool = False,
    ) -> str:
        """
        OpenAI-compatible speech creation interface.

        Args:
            input_text (str): The text to convert to speech
            model (str): The TTS model to use
            voice (str): The voice to use (not used by ParlerAI directly)
            response_format (str): Audio format
            instructions (str): Voice instructions (used as description)
            verbose (bool): Whether to print debug information

        Returns:
            str: Path to the generated audio file
        """
        description = (
            instructions
            or "A female speaker delivers a slightly expressive and animated speech with a moderate speed. The recording features a low-pitch voice and very clear audio."
        )
        use_large = model == "parler-large-v1"

        return self.tts(
            text=input_text,
            description=description,
            use_large=use_large,
            response_format=response_format or "mp3",
            verbose=verbose,
        )


if __name__ == "__main__":
    tts = ParlerTTS()
    try:
        path = tts.tts("Testing Parler-TTS with manual polling.", verbose=True)
        ic.configureOutput(prefix="INFO| ")
        ic(f"Saved to {path}")
    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error: {e}")
