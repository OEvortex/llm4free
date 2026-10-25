##################################################################################
##  Deepgram TTS Provider                                                      ##
##################################################################################
import pathlib
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional, Union, cast

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
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
    from llm4free.TTS import utils
    from llm4free.TTS.base import BaseTTSProvider


class DeepgramTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the Deepgram Aura-2 API.

    This provider follows the OpenAI TTS API structure with support for:
    - Aura-2 next-gen voices
    - Low-latency real-time performance
    - Multiple output formats
    - Concurrent generation for long texts
    """

    required_auth = False

    # Request headers
    headers: dict[str, str] = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://deepgram.com",
        "Referer": "https://deepgram.com/ai-voice-generator",
        "User-Agent": LitAgent().random(),
    }

    # Supported Aura-2 voices
    SUPPORTED_MODELS = ["aura-2"]

    SUPPORTED_VOICES = [
        "thalia",
        "odysseus",
        "harmonia",
        "theia",
        "electra",
        "arcas",
        "amalthea",
        "helena",
        "hyperion",
        "apollo",
        "luna",
        # Legacy Aura-1 voices (if still supported by the endpoint)
        "asteria",
        "luna",
        "stella",
        "athena",
        "hera",
        "zeus",
        "orpheus",
        "arcas",
        "perseus",
        "angus",
        "orion",
        "helios",
    ]

    # Voice mapping for Deepgram API compatibility
    voice_mapping = {
        # Aura-2 voices (correct language codes)
        "thalia": "aura-2-thalia-en",
        "odysseus": "aura-2-odysseus-en",
        "harmonia": "aura-2-harmonia-en",
        "theia": "aura-2-theia-au",
        "electra": "aura-2-electra-en",
        "arcas": "aura-2-arcas-en",
        "amalthea": "aura-2-amalthea-ph",
        "helena": "aura-2-helena-en",
        "hyperion": "aura-2-hyperion-au",
        "apollo": "aura-2-apollo-en",
        "luna": "aura-2-luna-en",
        # Aura-1 (Backward compatibility)
        "asteria": "aura-asteria-en",
        "stella": "aura-stella-en",
        "athena": "aura-athena-en",
        "hera": "aura-hera-en",
        "zeus": "aura-zeus-en",
        "orpheus": "aura-orpheus-en",
        "perseus": "aura-perseus-en",
        "angus": "aura-angus-en",
        "orion": "aura-orion-en",
        "helios": "aura-helios-en",
    }

    def __init__(self, timeout: int = 30, proxies: Optional[dict] = None):
        """
        Initialize the Deepgram TTS client.

        Args:
            timeout (int): Request timeout in seconds
            proxies (dict): Proxy configuration
        """
        super().__init__()
        self.api_url = "https://deepgram.com/api/tts"
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if proxies:
            self.session.proxies.update(cast(Any, proxies))
        self.timeout = timeout
        self.default_voice = "thalia"

    def tts(self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs) -> str:
        """
        Convert text to speech using Deepgram Aura-2 API.

        Args:
            text (str): The text to convert to speech
            voice (str): The voice to use (thalia, odysseus, etc.)
            verbose (bool): Whether to print debug information
            **kwargs: Additional parameters

        Returns:
            str: Path to the generated audio file
        """
        # Extract parameters from kwargs with defaults
        voice = voice or kwargs.get("voice", "thalia")
        response_format = kwargs.get("response_format", "mp3")
        verbose = verbose if verbose is not None else kwargs.get("verbose", True)

        if not text:
            raise ValueError("Input text must be a non-empty string")

        # Map voice to Deepgram API format
        voice_id = self.voice_mapping.get(voice.lower(), f"aura-2-{voice.lower()}-en")

        # Create temporary file
        file_extension = f".{response_format}"
        filename = pathlib.Path(
            tempfile.NamedTemporaryFile(suffix=file_extension, dir=self.temp_dir, delete=False).name
        )
        sentences = utils.split_sentences(text)
        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"DeepgramTTS: Processing {len(sentences)} chunks")
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"Voice: {voice} -> {voice_id}")

        def generate_audio_for_chunk(part_text: str, part_number: int):
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    payload = {
                        "text": part_text,
                        "model": voice_id,
                        "demoType": "voice-generator",
                    }
                    response = self.session.post(self.api_url, json=payload, timeout=self.timeout)
                    response.raise_for_status()

                    if response.content:
                        if verbose:
                            ic.configureOutput(prefix="DEBUG| ")
                            ic(f"Chunk {part_number} processed successfully")
                        return part_number, response.content

                except CurlError as e:
                    if verbose:
                        ic.configureOutput(prefix="WARNING| ")
                        ic(
                            f"Error processing chunk {part_number}: {e}. Retrying {attempt + 1}/{max_retries}"
                        )
                    time.sleep(1)
                except Exception as e:
                    if verbose:
                        ic.configureOutput(prefix="WARNING| ")
                        ic(
                            f"Error processing chunk {part_number}: {e}. Retrying {attempt + 1}/{max_retries}"
                        )
                    time.sleep(1)

            raise exceptions.FailedToGenerateResponseError(
                f"Failed to generate audio for chunk {part_number}"
            )

        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(generate_audio_for_chunk, sentence.strip(), i): i
                    for i, sentence in enumerate(sentences)
                }

                audio_chunks = {}
                for future in as_completed(futures):
                    part_num, data = future.result()
                    audio_chunks[part_num] = data

                with open(filename, "wb") as f:
                    for i in sorted(audio_chunks.keys()):
                        f.write(audio_chunks[i])

                if verbose:
                    ic.configureOutput(prefix="INFO| ")
                    ic(f"Audio saved to {filename}")

                return str(filename)

        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(f"Deepgram TTS failed: {e}")

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        instructions: Optional[str] = None,
        verbose: bool = False,
    ) -> str:
        return self.tts(
            text=input_text,
            model=model or "aura-2",
            voice=voice or "thalia",
            response_format=response_format or "mp3",
            instructions=instructions,
            verbose=verbose,
        )

    def with_streaming_response(self):
        return StreamingResponseContextManager(self)


class StreamingResponseContextManager:
    def __init__(self, tts_provider: DeepgramTTS):
        self.tts_provider = tts_provider

    def create(self, **kwargs):
        audio_file = self.tts_provider.create_speech(**kwargs)
        return StreamingResponse(audio_file)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class StreamingResponse:
    def __init__(self, audio_file: str):
        self.audio_file = audio_file

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def stream_to_file(self, file_path: str):
        import shutil

        shutil.copy2(self.audio_file, file_path)

    def iter_bytes(self, chunk_size: int = 1024):
        with open(self.audio_file, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk


if __name__ == "__main__":
    dg = DeepgramTTS()
    try:
        path = dg.tts(
            "Deepgram Aura-2 test successful. Generating high quality speech.",
            voice="thalia",
            verbose=True,
        )
        print(f"Saved to: {path}")
    except Exception as e:
        print(f"Error: {e}")
