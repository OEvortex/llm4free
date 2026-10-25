##################################################################################
##  OpenAI.fm TTS Provider                                                     ##
##################################################################################
import pathlib
import tempfile
from typing import Any, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider


class OpenAIFMTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the OpenAI.fm API with OpenAI-compatible interface.

    This provider follows the OpenAI TTS API structure with support for:
    - Multiple TTS models (gpt-4o-mini-tts, tts-1, tts-1-hd)
    - 11 built-in voices optimized for English
    - Voice instructions for controlling speech aspects
    - Multiple output formats
    - Streaming support
    """

    required_auth = False

    # Request headers
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-fetch-dest": "audio",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "same-origin",
        "user-agent": LitAgent().random(),
        "referer": "https://www.openai.fm",
    }

    # Override supported models for OpenAI.fm
    SUPPORTED_MODELS = [
        "gpt-4o-mini-tts",  # Latest intelligent realtime model
        "tts-1",  # Lower latency model
        "tts-1-hd",  # Higher quality model
    ]

    # OpenAI.fm supported voices (11 built-in voices)
    SUPPORTED_VOICES = [
        "alloy",  # Neutral voice with balanced tone
        "ash",  # Calm and thoughtful male voice
        "ballad",  # Soft and melodic voice
        "coral",  # Warm and inviting female voice
        "echo",  # Clear and precise voice
        "fable",  # Authoritative and narrative voice
        "nova",  # Energetic and bright female voice
        "onyx",  # Deep and resonant male voice
        "sage",  # Measured and contemplative voice
        "shimmer",  # Bright and optimistic voice
    ]

    # Voice mapping for API compatibility
    voice_mapping = {
        "alloy": "alloy",
        "ash": "ash",
        "ballad": "ballad",
        "coral": "coral",
        "echo": "echo",
        "fable": "fable",
        "nova": "nova",
        "onyx": "onyx",
        "sage": "sage",
        "shimmer": "shimmer",
    }

    def __init__(self, timeout: int = 20, proxies: Optional[dict] = None):
        """
        Initialize the OpenAI.fm TTS client.

        Args:
            timeout (int): Request timeout in seconds
            proxies (dict): Proxy configuration
        """
        super().__init__()
        self.api_url = "https://www.openai.fm/api/generate"
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if proxies:
            self.session.proxies.update(cast(Any, proxies))
        self.timeout = timeout

    def tts(self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs) -> str:
        """
        Convert text to speech using OpenAI.fm API with OpenAI-compatible parameters.

        Args:
            text (str): The text to convert to speech (max 10,000 characters)
            model (str): The TTS model to use (gpt-4o-mini-tts, tts-1, tts-1-hd)
            voice (str): The voice to use for TTS (alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer)
            response_format (str): Audio format (mp3, opus, aac, flac, wav, pcm)
            instructions (str): Voice instructions for controlling speech aspects like accent, tone, speed
            verbose (bool): Whether to print debug information

        Returns:
            str: Path to the generated audio file

        Raises:
            ValueError: If input parameters are invalid
            exceptions.FailedToGenerateResponseError: If there is an error generating or saving the audio
        """
        # Extract optional parameters from kwargs
        model = kwargs.get("model", "gpt-4o-mini-tts")
        response_format = kwargs.get("response_format", "mp3")
        instructions = kwargs.get("instructions", None)

        # Validate input parameters
        if not text or not isinstance(text, str):
            raise ValueError("Input text must be a non-empty string")
        if len(text) > 10000:
            raise ValueError("Input text exceeds maximum allowed length of 10,000 characters")

        # Validate model, voice, and format using base class methods
        model = self.validate_model(model)
        voice = self.validate_voice(voice or "coral")
        response_format = self.validate_format(response_format)

        # Map voice to API format
        voice_id = self.voice_mapping.get(voice, voice)

        # Set default instructions if not provided
        if instructions is None:
            instructions = "Speak in a cheerful and positive tone."

        # Create temporary file with appropriate extension
        file_extension = f".{response_format}" if response_format != "pcm" else ".wav"
        with tempfile.NamedTemporaryFile(
            suffix=file_extension, dir=self.temp_dir, delete=False
        ) as temp_file:
            filename = pathlib.Path(temp_file.name)

        # Prepare parameters for the API request
        params = {
            "input": text,
            "prompt": instructions,
            "voice": voice_id,
            "model": model,
            "response_format": response_format,
        }

        try:
            # Make the API request
            response = self.session.get(self.api_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            # Validate response content
            if not response.content:
                raise exceptions.FailedToGenerateResponseError("Empty response from API")

            # Save the audio file
            with open(filename, "wb") as f:
                f.write(response.content)

            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic("Speech generated successfully")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Model: {model}")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Voice: {voice}")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Format: {response_format}")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Audio saved to {filename}")

            return filename.as_posix()

        except CurlError as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Failed to generate speech: {e}")
            raise exceptions.FailedToGenerateResponseError(f"Failed to generate speech: {e}")
        except Exception as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Unexpected error: {e}")
            raise exceptions.FailedToGenerateResponseError(
                f"Unexpected error during speech generation: {e}"
            )

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "gpt-4o-mini-tts",
        voice: Optional[str] = "alloy",
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        OpenAI-compatible speech creation interface.

        Args:
            input_text (str): The text to convert to speech
            model (str): The TTS model to use
            voice (str): The voice to use
            response_format (str): Audio format
            instructions (str): Voice instructions
            verbose (bool): Whether to print debug information

        Returns:
            str: Path to the generated audio file
        """
        return self.tts(
            text=input_text,
            voice=voice or "alloy",
            model=model or "gpt-4o-mini-tts",
            response_format=response_format or "mp3",
            verbose=verbose,
        )

    def with_streaming_response(self):
        """
        Return a streaming response context manager (OpenAI-compatible).

        Returns:
            StreamingResponseContextManager: Context manager for streaming responses
        """
        return StreamingResponseContextManager(self)


class StreamingResponseContextManager:
    """
    Context manager for streaming TTS responses (OpenAI-compatible).
    """

    def __init__(self, tts_provider: OpenAIFMTTS):
        self.tts_provider = tts_provider
        self.audio_file = None

    def create(
        self,
        input_text: str,
        model: Optional[str] = "gpt-4o-mini-tts",
        voice: Optional[str] = "coral",
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
    ):
        """
        Create speech with streaming capability.

        Args:
            input_text (str): The text to convert to speech
            model (str): The TTS model to use
            voice (str): The voice to use
            response_format (str): Audio format
            instructions (str): Voice instructions

        Returns:
            StreamingResponse: Streaming response object
        """
        self.audio_file = self.tts_provider.create_speech(
            input_text=input_text,
            model=model,
            voice=voice,
            response_format=response_format,
            instructions=instructions,
        )
        return StreamingResponse(self.audio_file)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class StreamingResponse:
    """
    Streaming response object for TTS audio (OpenAI-compatible).
    """

    def __init__(self, audio_file: str):
        self.audio_file = audio_file

    def __enter__(self):
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager."""
        pass

    def stream_to_file(self, file_path: str, chunk_size: int = 1024):
        """
        Stream audio content to a file.

        Args:
            file_path (str): Destination file path
            chunk_size (int): Size of chunks to read/write
        """
        import shutil

        shutil.copy2(self.audio_file, file_path)

    def iter_bytes(self, chunk_size: int = 1024):
        """
        Iterate over audio bytes in chunks.

        Args:
            chunk_size (int): Size of chunks to yield

        Yields:
            bytes: Audio data chunks
        """
        with open(self.audio_file, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk


if __name__ == "__main__":
    # Example usage demonstrating OpenAI-compatible interface
    tts_provider = OpenAIFMTTS()

    try:
        # Basic usage
        ic.configureOutput(prefix="DEBUG| ")
        ic("Testing basic speech generation...")
        audio_file = tts_provider.create_speech(
            input_text="Today is a wonderful day to build something people love!",
            model="gpt-4o-mini-tts",
            voice="coral",
            instructions="Speak in a cheerful and positive tone.",
        )
        print(f"Audio file generated: {audio_file}")

        # Streaming usage
        ic.configureOutput(prefix="DEBUG| ")
        ic("Testing streaming response...")
        with tts_provider.with_streaming_response().create(
            input_text="This is a streaming test.", voice="alloy", response_format="wav"
        ) as response:
            response.stream_to_file("streaming_test.wav")
            ic.configureOutput(prefix="INFO| ")
            ic("Streaming audio saved to streaming_test.wav")

    except exceptions.FailedToGenerateResponseError as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error: {e}")
    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Unexpected error: {e}")
