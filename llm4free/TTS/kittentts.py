"""
KittenTTS Provider - Text-to-speech using KittenTTS Gradio API.

This provider uses the KittenTTS model hosted on HuggingFace Spaces.
It supports multiple model sizes and voice presets.

Features:
- 3 model sizes: Nano (15M), Micro (40M), Mini (80M)
- 8 voice presets: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
- Adjustable speech speed (0.5x to 2.0x)
- Gradio API integration with async event-based pattern
- OpenAI-compatible interface

Reference: https://kittenml-kittentts-demo.hf.space
"""

import json
import tempfile
from typing import Any, Optional, cast

from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider


class KittenTTS(BaseTTSProvider):
    """
    KittenTTS provider.

    Provides text-to-speech conversion using the KittenTTS model
    hosted on HuggingFace Spaces.

    Attributes:
        SUPPORTED_MODELS: Available TTS models
        SUPPORTED_VOICES: Available voice presets
        SUPPORTED_FORMATS: List of supported audio formats
    """

    required_auth = False

    # Supported models
    SUPPORTED_MODELS = [
        "nano",  # 15M - Fastest
        "micro",  # 40M - Balanced
        "mini",  # 80M - Best Quality
    ]

    # Model name mapping for Gradio API
    MODEL_NAMES = {
        "nano": "Nano (15M - Fastest)",
        "micro": "Micro (40M - Balanced)",
        "mini": "Mini (80M - Best Quality)",
    }

    # Supported voices
    SUPPORTED_VOICES = [
        "Bella",
        "Jasper",
        "Luna",
        "Bruno",
        "Rosie",
        "Hugo",
        "Kiki",
        "Leo",
    ]

    # Supported formats
    SUPPORTED_FORMATS = ["wav"]

    # Gradio API endpoint
    BASE_URL = "https://kittenml-kittentts-demo.hf.space"
    SYNTHESIZE_ENDPOINT = f"{BASE_URL}/gradio_api/call/synthesize"

    def __init__(
        self,
        timeout: int = 120,
        proxies: Optional[dict] = None,
    ):
        """
        Initialize the KittenTTS provider.

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
        self.default_model = "micro"
        self.default_voice = "Jasper"
        self.default_format = "wav"
        self.default_speed = 1.0

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using KittenTTS API.

        Args:
            text (str): The text to convert to speech
            voice (str, optional): Voice preset name. Defaults to "Jasper".
            verbose (bool, optional): Print debug information. Defaults to False.
            **kwargs: Additional parameters:
                - model (str): Model name ("nano", "micro", "mini")
                - response_format (str): Audio format (only "wav" supported)
                - speed (float): Speech speed 0.5-2.0 (default: 1.0)

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
        speed = kwargs.get("speed", self.default_speed)

        # Validate model
        self.validate_model(model)

        # Validate voice
        voice = voice or self.default_voice
        self.validate_voice(voice)

        # Validate format
        self.validate_format(response_format)

        # Validate speed
        if not 0.5 <= speed <= 2.0:
            raise ValueError(f"Speed must be between 0.5 and 2.0, got {speed}")

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(
                f"Generating TTS with KittenTTS: text_length={len(text)}, "
                f"model={model}, voice={voice}, speed={speed}"
            )

        try:
            # Get Gradio model name
            model_name = self.MODEL_NAMES[model]

            # Step 1: Submit TTS request to get event_id
            event_id = self._submit_synthesis(
                text=text,
                model_name=model_name,
                voice=voice,
                speed=speed,
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
                ic(f"KittenTTS generation failed: {e}")
            raise exceptions.FailedToGenerateResponseError(
                f"Failed to generate audio with KittenTTS: {e}"
            ) from e

    def _submit_synthesis(
        self,
        text: str,
        model_name: str,
        voice: str,
        speed: float,
        verbose: bool = False,
    ) -> str:
        """
        Submit TTS synthesis request and return event_id.

        Args:
            text (str): Text to synthesize
            model_name (str): Gradio model name
            voice (str): Voice preset name
            speed (float): Speech speed
            verbose (bool): Print debug info

        Returns:
            str: Event ID for polling results
        """
        payload = {"data": [text, model_name, voice, speed]}

        response = self.session.post(
            self.SYNTHESIZE_ENDPOINT,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

        result = response.json()
        event_id = result.get("event_id")

        if not event_id:
            raise exceptions.FailedToGenerateResponseError(
                f"No event_id returned from KittenTTS API: {result}"
            )

        return event_id

    def _get_result(self, event_id: str, verbose: bool = False) -> str:
        """
        Poll for synthesis result using SSE stream.

        Args:
            event_id (str): Event ID from submission
            verbose (bool): Print debug info

        Returns:
            str: URL of generated audio file
        """
        result_url = f"{self.BASE_URL}/gradio_api/call/synthesize/{event_id}"

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
                "No audio URL found in KittenTTS response"
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

    def get_available_models(self) -> dict[str, str]:
        """
        Get available models and their descriptions.

        Returns:
            dict: Mapping of model names to descriptions
        """
        return self.MODEL_NAMES.copy()

    def get_available_voices(self) -> list[str]:
        """
        Get available voice presets.

        Returns:
            list: List of available voice names
        """
        return self.SUPPORTED_VOICES.copy()

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        instructions: Optional[str] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Create speech from input text (OpenAI-compatible interface).

        KittenTTS supports preset voice names and custom speed,
        so we bypass base validation here to avoid rejecting
        provider-specific voices.
        """
        return self.tts(
            text=input_text,
            voice=voice or self.default_voice,
            model=model or self.default_model,
            response_format=response_format or self.default_format,
            speed=kwargs.get("speed", self.default_speed),
            verbose=verbose,
        )


if __name__ == "__main__":
    # Example usage
    provider = KittenTTS()
    audio_file = provider.tts(
        text="Hello, this is a test of the KittenTTS provider.",
        voice="Jasper",
        model="micro",
        speed=1.0,
        verbose=True,
    )
    print(f"Generated audio file: {audio_file}")
