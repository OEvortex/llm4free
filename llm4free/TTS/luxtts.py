"""
LuxTTS Voice Cloning Provider - Text-to-speech using LuxTTS Gradio API.

This provider uses the LuxTTS voice cloning model hosted on HuggingFace Spaces.
It supports voice cloning from a reference audio sample.

Features:
- Voice cloning from reference audio
- Adjustable speech parameters (speed, pitch, duration)
- Gradio API integration with async event-based pattern
- OpenAI-compatible interface

Reference: https://yatharths-luxtts.hf.space
"""

import io
import tempfile
import time
from typing import Any, Optional, cast

from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider


class LuxTTS(BaseTTSProvider):
    """
    LuxTTS voice cloning provider.

    Provides text-to-speech conversion with voice cloning capabilities
    using the LuxTTS model hosted on HuggingFace Spaces.

    Attributes:
        SUPPORTED_MODELS: Available TTS models
        SUPPORTED_VOICES: Available voice presets (reference audio URLs)
        SUPPORTED_FORMATS: List of supported audio formats
    """

    required_auth = False

    # Supported models
    SUPPORTED_MODELS = [
        "luxtts",
    ]

    # Preset reference audio URLs for common voices
    # Users can also provide their own reference audio URLs
    PRESET_VOICES = {
        "default": "https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav",
        "male_1": "https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav",
    }

    # Supported voices (preset names; urls are also accepted)
    SUPPORTED_VOICES = list(PRESET_VOICES.keys())

    # Supported formats
    SUPPORTED_FORMATS = ["wav", "mp3"]

    # Gradio API endpoint
    BASE_URL = "https://yatharths-luxtts.hf.space"
    INFER_ENDPOINT = f"{BASE_URL}/gradio_api/call/infer"

    def __init__(
        self,
        timeout: int = 120,
        proxies: Optional[dict] = None,
        reference_audio: Optional[str] = None,
    ):
        """
        Initialize the LuxTTS provider.

        Args:
            timeout (int): Request timeout in seconds. Defaults to 120 (generation can take ~20s).
            proxies (dict, optional): Proxy configuration for requests.
            reference_audio (str, optional): Default reference audio URL for voice cloning.
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
        self.default_model = "luxtts"
        self.default_voice = "default"
        self.default_format = "wav"
        self.reference_audio = reference_audio or self.PRESET_VOICES["default"]

        # TTS parameters
        self.default_rms = 0.01  # Loudness
        self.default_ref_duration = 5  # Reference duration in seconds
        self.default_t_shift = 0.9  # T-Shift parameter
        self.default_num_steps = 4  # Number of steps (1-10)
        self.default_speed = 0.8  # Speed (0.5-2.0)
        self.default_return_smooth = False  # Return smooth audio

    def validate_model(self, model: str) -> str:
        """
        Validate and return the model name.

        Args:
            model (str): Model name to validate

        Returns:
            str: Validated model name

        Raises:
            ValueError: If model is not supported
        """
        if self.SUPPORTED_MODELS is None:
            return model
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Model '{model}' not supported. Available models: {', '.join(self.SUPPORTED_MODELS)}"
            )
        return model

    def validate_voice(self, voice: str) -> str:
        """
        Validate and return the voice name.

        LuxTTS voices are either preset names or direct audio URLs.

        Args:
            voice (str): Voice name to validate

        Returns:
            str: Validated voice name

        Raises:
            ValueError: If voice is not supported
        """
        if voice in self.PRESET_VOICES:
            return voice
        if isinstance(voice, str) and voice.startswith(("http://", "https://")):
            return voice
        raise ValueError(
            f"Voice '{voice}' not supported. Available voices: {', '.join(self.SUPPORTED_VOICES)}"
        )

    def validate_format(self, response_format: str) -> str:
        """
        Validate and return the response format.

        Args:
            response_format (str): Format to validate

        Returns:
            str: Validated format

        Raises:
            ValueError: If format is not supported
        """
        if response_format not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Format '{response_format}' not supported. Available formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        return response_format

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using LuxTTS API.

        Args:
            text (str): The text to convert to speech
            voice (str, optional): Voice preset name or reference audio URL. Defaults to "default".
            verbose (bool, optional): Print debug information. Defaults to False.
            **kwargs: Additional parameters:
                - model (str): Model name (must be "luxtts")
                - response_format (str): Audio format ("wav" or "mp3")
                - reference_audio (str): Reference audio URL for voice cloning
                - rms (float): Loudness parameter (default: 0.01)
                - ref_duration (float): Reference duration in seconds (default: 5)
                - t_shift (float): T-Shift parameter (default: 0.9)
                - num_steps (int): Number of steps 1-10 (default: 4)
                - speed (float): Speed 0.5-2.0 (default: 0.8)
                - return_smooth (bool): Return smooth audio (default: False)

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
        reference_audio = kwargs.get("reference_audio", self.reference_audio)
        rms = kwargs.get("rms", self.default_rms)
        ref_duration = kwargs.get("ref_duration", self.default_ref_duration)
        t_shift = kwargs.get("t_shift", self.default_t_shift)
        num_steps = kwargs.get("num_steps", self.default_num_steps)
        speed = kwargs.get("speed", self.default_speed)
        return_smooth = kwargs.get("return_smooth", self.default_return_smooth)

        # Validate model
        self.validate_model(model)

        # Resolve voice to reference audio URL
        if voice:
            if voice in self.PRESET_VOICES:
                reference_audio = self.PRESET_VOICES[voice]
            elif voice.startswith(("http://", "https://")):
                reference_audio = voice
            else:
                raise ValueError(
                    f"Voice '{voice}' not recognized. Use a preset name or provide a URL."
                )

        # Validate format
        self.validate_format(response_format)

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"Generating TTS with LuxTTS: text_length={len(text)}, voice={voice or 'default'}")

        try:
            # Step 1: Submit TTS request to get event_id
            event_id = self._submit_inference(
                text=text,
                reference_audio=reference_audio,
                rms=rms,
                ref_duration=ref_duration,
                t_shift=t_shift,
                num_steps=num_steps,
                speed=speed,
                return_smooth=return_smooth,
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
            suffix = f".{response_format}" if response_format in ["mp3", "wav"] else ".wav"
            filename = tempfile.NamedTemporaryFile(
                suffix=suffix, dir=self.temp_dir, delete=False
            ).name

            with open(filename, "wb") as f:
                f.write(audio_data)

            if verbose:
                ic(f"Audio saved to {filename}")

            return filename

        except Exception as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"LuxTTS generation failed: {e}")
            raise exceptions.FailedToGenerateResponseError(
                f"Failed to generate audio with LuxTTS: {e}"
            ) from e

    def _submit_inference(
        self,
        text: str,
        reference_audio: str,
        rms: float,
        ref_duration: float,
        t_shift: float,
        num_steps: int,
        speed: float,
        return_smooth: bool,
        verbose: bool = False,
    ) -> str:
        """
        Submit TTS inference request and return event_id.

        Args:
            text (str): Text to synthesize
            reference_audio (str): URL of reference audio for voice cloning
            rms (float): Loudness parameter
            ref_duration (float): Reference duration in seconds
            t_shift (float): T-Shift parameter
            num_steps (int): Number of steps
            speed (float): Speed parameter
            return_smooth (bool): Return smooth audio flag
            verbose (bool): Print debug info

        Returns:
            str: Event ID for polling results
        """
        payload = {
            "data": [
                text,
                {
                    "path": reference_audio,
                    "meta": {"_type": "gradio.FileData"},
                    "orig_name": "reference.wav",
                    "url": reference_audio,
                },
                rms,
                ref_duration,
                t_shift,
                num_steps,
                speed,
                return_smooth,
            ]
        }

        response = self.session.post(
            self.INFER_ENDPOINT,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        event_id = result.get("event_id")

        if not event_id:
            raise exceptions.FailedToGenerateResponseError(
                f"No event_id returned from LuxTTS API: {result}"
            )

        return event_id

    def _get_result(self, event_id: str, verbose: bool = False) -> str:
        """
        Poll for inference result using SSE stream.

        Args:
            event_id (str): Event ID from submission
            verbose (bool): Print debug info

        Returns:
            str: URL of generated audio file
        """
        result_url = f"{self.BASE_URL}/gradio_api/call/infer/{event_id}"

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

            line_str = line.decode("utf-8")

            if line_str.startswith("data:"):
                data_str = line_str[5:].strip()
                if data_str and data_str != "[null]":
                    try:
                        import json

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
            raise exceptions.FailedToGenerateResponseError("No audio URL found in LuxTTS response")

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

    def get_available_voices(self) -> dict[str, str]:
        """
        Get available voice presets and their reference audio URLs.

        Returns:
            dict: Mapping of voice names to reference audio URLs
        """
        return self.PRESET_VOICES.copy()

    def set_reference_audio(self, url: str) -> None:
        """
        Set the default reference audio URL for voice cloning.

        Args:
            url (str): URL to a WAV file for voice cloning
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError("Reference audio must be a valid URL")
        self.reference_audio = url
