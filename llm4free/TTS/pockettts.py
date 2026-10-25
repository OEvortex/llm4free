"""
Kyutai TTS Provider - Text-to-speech using Kyutai's official APIs.

This provider supports both Kyutai TTS models:
1. Pocket TTS: A lightweight model (100M parameters) optimized for CPU inference
2. TTS 1.6B: A streaming model with extensive voice library and low latency

Features:
- Pocket TTS: 6 preset voices with fast, lightweight inference
- TTS 1.6B: 50+ voices including expresso, VCTK, CML TTS, and voice donations
- Direct REST API calls to official Kyutai endpoints
- Production-ready error handling
- OpenAI-compatible interface
"""

import io
import tempfile
from typing import Any, Optional, cast

from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider


class KyutaiTTS(BaseTTSProvider):
    """
    Kyutai TTS provider supporting both Pocket TTS and TTS 1.6B models.

    Provides text-to-speech conversion with support for multiple voices
    from the official Kyutai TTS services.

    Attributes:
        SUPPORTED_MODELS: Available TTS models
        POCKET_TTS_VOICES: Available voices for Pocket TTS
        TTS_1_6B_VOICES: Available voices for TTS 1.6B
        SUPPORTED_FORMATS: List of supported audio formats
    """

    required_auth = False

    # Supported models
    SUPPORTED_MODELS = [
        "pocket-tts",
        "tts-1.6b",
    ]

    # Pocket TTS voices
    POCKET_TTS_VOICES = [
        "alba",
        "javert",
        "azelma",
        "eponine",
        "fantine",
        "jean",
    ]

    # TTS 1.6B preset voices
    TTS_1_6B_PRESET_VOICES = [
        "Show host (US, m)",
        "Angry (US, f)",
        "Angry (US, m)",
        "Calming (US, f)",
        "Calming (US, m)",
        "Confused (US, f)",
        "Confused (US, m)",
        "Default (US, f)",
        "Desire (US, f)",
        "Desire (US, m)",
        "Fearful (US, f)",
        "Jazz radio (US, m)",
        "Narration (US, f)",
        "Sad (IE, m)",
        "Sad (US, f)",
        "Sarcastic (US, f)",
        "Sarcastic (US, m)",
        "Whisper (US, f)",
    ]

    # Voice donation voices
    TTS_1_6B_VOICE_DONATIONS = [
        "Voice donation - dwp (AU, m)",
    ]

    # CML TTS voices (French speakers)
    TTS_1_6B_CML_VOICES = [
        "CML 12977 (FR, f)",
        "CML 1406 (FR, m)",
        "CML 2154 (FR, f)",
        "CML 4724 (FR, m)",
    ]

    # VCTK voices (UK speakers)
    TTS_1_6B_VCTK_VOICES = [
        "VCTK 226 (UK, m)",
        "VCTK 228 (UK, f)",
        "VCTK 231 (UK, f)",
        "VCTK 255 (UK, m)",
        "VCTK 277 (UK, f)",
        "VCTK 292 (UK, m)",
    ]

    # Unmute voices
    TTS_1_6B_UNMUTE_VOICES = [
        "Unmute - Charles de Gaulle",
        "Unmute - Dev",
        "Unmute - Développeuse",
        "Unmute - Fabieng",
        "Unmute - Gertrude",
        "Unmute - Quiz show",
        "Unmute - Watercooler",
    ]

    # EARS dataset voices
    TTS_1_6B_EARS_VOICES = [
        "EARS dataset - Speaker 003",
        "EARS dataset - Speaker 013",
        "EARS dataset - Speaker 022",
        "EARS dataset - Speaker 031",
        "EARS dataset - Speaker 040",
        "EARS dataset - Speaker 051",
        "EARS dataset - Speaker 060",
        "EARS dataset - Speaker 070",
        "EARS dataset - Speaker 080",
        "EARS dataset - Speaker 091",
        "EARS dataset - Speaker 105",
    ]

    # Combine all TTS 1.6B voices
    TTS_1_6B_ALL_VOICES = (
        TTS_1_6B_PRESET_VOICES
        + TTS_1_6B_VOICE_DONATIONS
        + TTS_1_6B_CML_VOICES
        + TTS_1_6B_VCTK_VOICES
        + TTS_1_6B_UNMUTE_VOICES
        + TTS_1_6B_EARS_VOICES
    )

    # All available voices across both models
    SUPPORTED_VOICES = list(set(POCKET_TTS_VOICES + TTS_1_6B_ALL_VOICES))

    # Supported formats
    SUPPORTED_FORMATS = ["wav", "mp3", "aac", "opus"]

    # API endpoints
    POCKET_TTS_ENDPOINT = (
        "https://kyutaipockettts6ylex2y4-kyutai-pocket-tts.functions.fnc.fr-par.scw.cloud/tts"
    )
    TTS_1_6B_ENDPOINT = (
        "https://kyutaitts1_6b6ylex2y4-kyutai-tts-1-6b.functions.fnc.fr-par.scw.cloud/tts"
    )

    def __init__(
        self,
        timeout: int = 30,
        proxies: Optional[dict] = None,
    ):
        """
        Initialize the Kyutai TTS provider.

        Args:
            timeout (int): Request timeout in seconds. Defaults to 30.
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
        self.default_model = "pocket-tts"
        self.default_voice = "alba"
        self.default_format = "wav"

    def get_pocket_tts_voices(self) -> list[str]:
        """
        Get available voices for Pocket TTS model.

        Returns:
            List of available voice names for Pocket TTS
        """
        return self.POCKET_TTS_VOICES.copy()

    def get_tts_1_6b_voices(self) -> list[str]:
        """
        Get all available voices for TTS 1.6B model.

        Returns:
            List of all available voice names for TTS 1.6B
        """
        return self.TTS_1_6B_ALL_VOICES.copy()

    def _get_voices_for_model(self, model: str) -> list[str]:
        """Get available voices for a specific model."""
        if model == "pocket-tts":
            return self.POCKET_TTS_VOICES.copy()
        elif model == "tts-1.6b":
            return self.TTS_1_6B_ALL_VOICES.copy()
        else:
            raise ValueError(f"Unknown model: {model}")

    def _normalize_tts_1_6b_voice(self, voice: str) -> str:
        """
        Normalize TTS 1.6B voice name (preserves exact format).

        Args:
            voice (str): The voice name to normalize

        Returns:
            str: The normalized voice name (unchanged for TTS 1.6B)
        """
        return voice

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using Kyutai TTS API.

        Args:
            text (str): The text to convert to speech
            voice (str, optional): Voice to use. Defaults to model's default voice.
            verbose (bool, optional): Print debug information. Defaults to False.
            **kwargs: Additional parameters (model, response_format, etc.)

        Returns:
            str: Path to the generated audio file

        Raises:
            ValueError: If text is empty, model is invalid, or voice is invalid
            exceptions.FailedToGenerateResponseError: If generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Use defaults
        model = kwargs.get("model", self.default_model)
        response_format = kwargs.get("response_format", self.default_format)

        # Validate model
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Model '{model}' not supported. Available models: "
                f"{', '.join(self.SUPPORTED_MODELS)}"
            )

        # Set default voice for model if not provided
        if voice is None:
            voice = "alba" if model == "pocket-tts" else "Show host (US, m)"

        # Validate voice for the specific model
        available_voices = self._get_voices_for_model(model)
        if voice not in available_voices:
            raise ValueError(
                f"Voice '{voice}' not available for model '{model}'. "
                f"Available voices: {', '.join(available_voices[:5])}... "
                f"(showing first 5 of {len(available_voices)})"
            )

        try:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Kyutai TTS: Generating speech (model={model}, voice={voice})")

            if model == "pocket-tts":
                audio_data = self._generate_pocket_tts(text, voice)
            else:  # tts-1.6b
                audio_data = self._generate_tts_1_6b(text, voice)

            # Save audio to temp file
            temp_file = tempfile.NamedTemporaryFile(
                suffix=f".{response_format}",
                dir=self.temp_dir,
                delete=False,
            )
            temp_file.close()

            with open(temp_file.name, "wb") as f:
                f.write(audio_data)

            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Kyutai TTS: Audio saved to {temp_file.name}")

            return temp_file.name

        except exceptions.FailedToGenerateResponseError:
            raise
        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(f"Kyutai TTS generation failed: {e}")

    def _generate_pocket_tts(self, text: str, voice: str) -> bytes:
        """Generate audio using Pocket TTS API."""
        data = {
            "text": text,
            "voice_url": voice.lower(),
        }

        response = self.session.post(
            self.POCKET_TTS_ENDPOINT,
            data=data,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.content

    def _generate_tts_1_6b(self, text: str, voice: str) -> bytes:
        """Generate audio using TTS 1.6B API."""
        data = {
            "text": text,
            "voice": voice,
        }

        response = self.session.post(
            self.TTS_1_6B_ENDPOINT,
            data=data,
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()

        # Collect all chunks from streaming response
        audio_data = io.BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                audio_data.write(chunk)

        return audio_data.getvalue()

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "pocket-tts",
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        instructions: Optional[str] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Create speech from input text (OpenAI-compatible interface).

        Args:
            input_text (str): The text to convert to speech
            model (str, optional): Model to use (pocket-tts or tts-1.6b)
            voice (str, optional): Voice to use
            response_format (str, optional): Audio format
            instructions (str, optional): Voice instructions (ignored)
            verbose (bool, optional): Print debug information
            **kwargs: Additional arguments passed to tts()

        Returns:
            str: Path to the generated audio file
        """
        return self.tts(
            text=input_text,
            model=model,
            voice=voice,
            response_format=response_format or "wav",
            verbose=verbose,
            **kwargs,
        )

    def close(self) -> None:
        """Close the session."""
        if self.session:
            self.session.close()

    def __enter__(self) -> "KyutaiTTS":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Backward compatibility alias
class PocketTTS(KyutaiTTS):
    """
    Backward compatibility alias for KyutaiTTS.
    Use KyutaiTTS instead for new code.
    """

    def __init__(self, *args, **kwargs):
        """Initialize PocketTTS (alias for KyutaiTTS)."""
        super().__init__(*args, **kwargs)
        self.default_model = "pocket-tts"


if __name__ == "__main__":
    import os

    tts = PocketTTS()
    try:
        audio_file = tts.create_speech(
            input_text="Pocket TTS makes text to speech simple and fast.",
            voice="fantine",
            response_format="wav",
            verbose=True,
        )

    except Exception as e:
        print(f"Error: {e}")
