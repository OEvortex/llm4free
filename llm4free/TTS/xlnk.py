"""
XLNK TTS Provider - Text-to-speech using XLNK Gradio API.

This provider uses the XLNK TTS model hosted on HuggingFace Spaces.
It supports Kyutai voices and voice cloning.

Features:
- 8 Kyutai voice presets: alba, marius, javert, jean, fantine, cosette, eponine, azelma
- Voice cloning from uploaded audio
- Adjustable generation parameters: temperature, steps, noise, EOS threshold
- Gradio API integration with async event-based pattern
- OpenAI-compatible interface

Reference: https://xlnk-tts.hf.space
"""

import json
import tempfile
from typing import Any, Optional, cast

from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider


class XLNKTTS(BaseTTSProvider):
    """
    XLNK TTS provider.

    Provides text-to-speech conversion using the XLNK TTS model
    hosted on HuggingFace Spaces.

    Attributes:
        SUPPORTED_MODELS: Available TTS models
        SUPPORTED_VOICES: Available voice presets
        SUPPORTED_FORMATS: List of supported audio formats
    """

    required_auth = False

    # Supported models
    SUPPORTED_MODELS = [
        "xlnk-tts",
    ]

    # Supported voices (Kyutai voices)
    SUPPORTED_VOICES = [
        "alba",
        "marius",
        "javert",
        "jean",
        "fantine",
        "cosette",
        "eponine",
        "azelma",
    ]

    # Supported formats
    SUPPORTED_FORMATS = ["wav"]

    # Gradio API endpoint
    BASE_URL = "https://xlnk-tts.hf.space"
    GENERATE_ENDPOINT = f"{BASE_URL}/gradio_api/call/generate_speech"

    def __init__(
        self,
        timeout: int = 120,
        proxies: Optional[dict] = None,
    ):
        """
        Initialize the XLNK TTS provider.

        Args:
            timeout (int): Request timeout in seconds. Defaults to 120.
            proxies (dict, optional): Proxy configuration for requests.
        """
        super().__init__()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": LitAgent().random(),
            }
        )

        if proxies:
            self.session.proxies.update(cast(Any, proxies))

        # Set defaults
        self.default_model = "xlnk-tts"
        self.default_voice = "alba"
        self.default_format = "wav"

        # Default generation parameters
        self.default_temperature = 0.1
        self.default_lsd_decode_steps = 1
        self.default_noise_clamp = 0.0
        self.default_eos_threshold = -4.0
        self.default_frames_after_eos = 10
        self.default_enable_custom_frames = False

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using XLNK TTS API.

        Args:
            text (str): The text to convert to speech
            voice (str, optional): Voice preset name. Defaults to "alba".
            verbose (bool, optional): Print debug information. Defaults to False.
            **kwargs: Additional parameters:
                - model (str): Model name (must be "xlnk-tts")
                - response_format (str): Audio format (only "wav" supported)
                - temperature (float): Generation temperature 0.1-2.0 (default: 0.1)
                - lsd_decode_steps (int): LSD decode steps 1-20 (default: 1)
                - noise_clamp (float): Noise clamp 0.0-2.0 (default: 0.0)
                - eos_threshold (float): EOS threshold -10.0-0.0 (default: -4.0)
                - frames_after_eos (int): Frames after EOS 0-100 (default: 10)
                - enable_custom_frames (bool): Enable custom frames (default: False)

        Returns:
            str: Path to the generated audio file

        Raises:
            ValueError: If text is empty or parameters are invalid
            exceptions.FailedToGenerateResponseError: If generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Extract parameters from kwargs
        model = kwargs.get("model", self.default_model)
        response_format = kwargs.get("response_format", self.default_format)
        temperature = kwargs.get("temperature", self.default_temperature)
        lsd_decode_steps = kwargs.get("lsd_decode_steps", self.default_lsd_decode_steps)
        noise_clamp = kwargs.get("noise_clamp", self.default_noise_clamp)
        eos_threshold = kwargs.get("eos_threshold", self.default_eos_threshold)
        frames_after_eos = kwargs.get("frames_after_eos", self.default_frames_after_eos)
        enable_custom_frames = kwargs.get("enable_custom_frames", self.default_enable_custom_frames)

        # Validate model
        self.validate_model(model)

        # Validate voice
        voice = voice or self.default_voice
        self.validate_voice(voice)

        # Validate format
        self.validate_format(response_format)

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(
                f"Generating TTS with XLNK: text_length={len(text)}, "
                f"voice={voice}, temperature={temperature}"
            )

        try:
            # Step 1: Submit TTS request to get event_id
            event_id = self._submit_generation(
                text=text,
                voice=voice,
                temperature=temperature,
                lsd_decode_steps=lsd_decode_steps,
                noise_clamp=noise_clamp,
                eos_threshold=eos_threshold,
                frames_after_eos=frames_after_eos,
                enable_custom_frames=enable_custom_frames,
                verbose=verbose,
            )

            if verbose:
                ic(f"Received event_id: {event_id}")

            # Step 2: Poll for result using SSE
            audio_url = self._get_result(event_id, verbose=verbose)

            if verbose:
                ic(f"Audio URL received: {audio_url}")

            # Step 3: Download audio file
            audio_data = self._download_audio(audio_url, verbose=verbose)

            # Save to temp file
            filename = tempfile.NamedTemporaryFile(
                suffix=".wav", dir=self.temp_dir, delete=False
            ).name

            with open(filename, "wb") as f:
                f.write(audio_data)

            if verbose:
                ic(f"Audio saved to {filename}")

            return filename

        except Exception as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"XLNK TTS generation failed: {e}")
            raise exceptions.FailedToGenerateResponseError(
                f"Failed to generate audio with XLNK TTS: {e}"
            ) from e

    def _submit_generation(
        self,
        text: str,
        voice: str,
        temperature: float,
        lsd_decode_steps: int,
        noise_clamp: float,
        eos_threshold: float,
        frames_after_eos: int,
        enable_custom_frames: bool,
        verbose: bool = False,
    ) -> str:
        """
        Submit TTS generation request and return event_id.

        Args:
            text (str): Text to synthesize
            voice (str): Voice preset name
            temperature (float): Generation temperature
            lsd_decode_steps (int): LSD decode steps
            noise_clamp (float): Noise clamp
            eos_threshold (float): EOS threshold
            frames_after_eos (int): Frames after EOS
            enable_custom_frames (bool): Enable custom frames
            verbose (bool): Print debug info

        Returns:
            str: Event ID for polling results
        """
        payload = {
            "data": [
                text,
                "Kyutai Voices",  # voice_mode
                voice,  # voice_dropdown
                None,  # voice_upload (null for preset voices)
                temperature,
                lsd_decode_steps,
                noise_clamp,
                eos_threshold,
                frames_after_eos,
                enable_custom_frames,
            ]
        }

        response = self.session.post(
            self.GENERATE_ENDPOINT,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        event_id = result.get("event_id")

        if not event_id:
            raise exceptions.FailedToGenerateResponseError(
                f"No event_id returned from XLNK TTS API: {result}"
            )

        return event_id

    def _get_result(self, event_id: str, verbose: bool = False) -> str:
        """
        Poll for generation result using SSE stream.

        Args:
            event_id (str): Event ID from submission
            verbose (bool): Print debug info

        Returns:
            str: URL of generated audio file
        """
        result_url = f"{self.BASE_URL}/gradio_api/call/generate_speech/{event_id}"

        response = self.session.get(
            result_url,
            headers={"Accept": "text/event-stream"},
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()

        # Parse SSE events
        audio_url = None
        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode("utf-8") if isinstance(line, bytes) else line

            if line_str.startswith("data:"):
                data_str = line_str[5:].strip()
                if data_str and data_str != "[null]":
                    try:
                        data = json.loads(data_str)
                        if isinstance(data, list) and len(data) > 0:
                            file_data = data[0]
                            if isinstance(file_data, dict):
                                # Extract URL from file data
                                audio_url = file_data.get("url")
                                if not audio_url and "path" in file_data:
                                    audio_url = (
                                        f"{self.BASE_URL}/gradio_api/file={file_data['path']}"
                                    )
                                break
                    except json.JSONDecodeError:
                        continue

        if not audio_url:
            raise exceptions.FailedToGenerateResponseError(
                "No audio URL found in XLNK TTS response"
            )

        return audio_url

    def _download_audio(self, url: str, verbose: bool = False) -> bytes:
        """
        Download audio file from URL.

        Args:
            url (str): Audio file URL
            verbose (bool): Print debug info

        Returns:
            bytes: Audio file content
        """
        # Handle relative URLs
        if url.startswith("/"):
            url = f"{self.BASE_URL}{url}"

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        return response.content

    def get_available_voices(self) -> list[str]:
        """
        Get available voice presets.

        Returns:
            list: List of available voice names
        """
        return self.SUPPORTED_VOICES.copy()
