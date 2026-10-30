##################################################################################
##  ElevenLabs TTS Provider                                                      ##
##################################################################################
import os
import pathlib
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional, Union, cast

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


class ElevenlabsTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the ElevenLabs API.

    This provider supports both authenticated (with API key) and
    unauthenticated (limited) usage if available.
    """

    required_auth = True

    # Supported models
    SUPPORTED_MODELS = [
        "eleven_multilingual_v2",
        "eleven_flash_v2_5",
        "eleven_flash_v2",
        "eleven_turbo_v2_5",
        "eleven_turbo_v2",
        "eleven_monolingual_v1",
    ]

    # Request headers
    headers: dict[str, str] = {
        "User-Agent": LitAgent().random(),
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    # ElevenLabs voices
    SUPPORTED_VOICES = [
        "brian",
        "alice",
        "bill",
        "callum",
        "charlie",
        "charlotte",
        "chris",
        "daniel",
        "eric",
        "george",
        "jessica",
        "laura",
        "liam",
        "lily",
        "matilda",
        "sarah",
        "will",
    ]

    # Voice mapping
    voice_mapping = {
        "brian": "nPczCjzI2devNBz1zQrb",
        "alice": "Xb7hH8MSUJpSbSDYk0k2",
        "bill": "pqHfZKP75CvOlQylNhV4",
        "callum": "N2lVS1w4EtoT3dr4eOWO",
        "charlie": "IKne3meq5aSn9XLyUdCD",
        "charlotte": "XB0fDUnXU5powFXDhCwa",
        "chris": "iP95p4xoKVk53GoZ742B",
        "daniel": "onwK4e9ZLuTAKqWW03F9",
        "eric": "cjVigY5qzO86Huf0OWal",
        "george": "JBFqnCBsd6RMkjVDRZzb",
        "jessica": "cgSgspJ2msm6clMCkdW9",
        "laura": "FGY2WhTYpPnrIDTdsKH5",
        "liam": "TX3LPaxmHKxFdv7VOQHJ",
        "lily": "pFZP5JQG7iQjIQuC4Bku",
        "matilda": "XrExE9yKIg1WjnnlVkGX",
        "sarah": "EXAVITQu4vr4xnSDxMaL",
        "will": "bIHbv24MWmeRgasZH58o",
    }

    def __init__(
        self, api_key: Optional[str] = None, timeout: int = 30, proxies: Optional[dict] = None
    ):
        """
        Initialize the ElevenLabs TTS client.

        Args:
            api_key (str): ElevenLabs API key. If None, tries to use unauthenticated endpoint.
            timeout (int): Request timeout in seconds.
            proxies (dict): Proxy configuration.
        """
        super().__init__()
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.api_url = "https://api.elevenlabs.io/v1/text-to-speech"
        self.session = requests.Session()
        try:
            self.session.headers.update(self.headers)
        except Exception:
            self.session.headers = dict(self.session.headers or {})
            self.session.headers.update(self.headers)
        if self.api_key:
            try:
                self.session.headers.update({"xi-api-key": self.api_key})
            except Exception:
                self.session.headers["xi-api-key"] = self.api_key
        if proxies:
            try:
                self.session.proxies.update(cast(Any, proxies))
            except Exception:
                self.session.proxies = {**(self.session.proxies or {}), **dict(proxies)}
        self.timeout = timeout
        self.default_voice = "brian"

    def tts(self, text: str, voice: str | None = None, verbose: bool = False, **kwargs) -> str:
        """
        Convert text to speech using ElevenLabs API.
        """
        model = kwargs.get("model", "eleven_multilingual_v2")
        response_format = kwargs.get("response_format", "mp3")
        if voice is None:
            voice = "brian"
        if verbose is False:
            verbose = kwargs.get("verbose", True)
        if not text:
            raise ValueError("Input text must be a non-empty string")

        voice_id = self.voice_mapping.get(voice.lower(), voice)

        file_extension = f".{response_format}"
        temp_file = tempfile.NamedTemporaryFile(
            suffix=file_extension, dir=self.temp_dir, delete=False
        )
        temp_file.close()
        filename = pathlib.Path(temp_file.name)

        sentences = utils.split_sentences(text)
        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"ElevenlabsTTS: Processing {len(sentences)} chunks")

        def generate_chunk(part_text: str, part_num: int):
            payload = {
                "text": part_text,
                "model_id": model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
            }
            url = f"{self.api_url}/{voice_id}"
            params = {}
            if not self.api_key:
                # Some public endpoints might still work without key but they are very restricted
                params["allow_unauthenticated"] = "1"

            response = self.session.post(url, json=payload, params=params, timeout=self.timeout)
            if response.status_code == 401 and not self.api_key:
                raise exceptions.FailedToGenerateResponseError(
                    "ElevenLabs requires an API key for this request."
                )
            response.raise_for_status()
            return part_num, response.content

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(generate_chunk, s.strip(), i): i
                    for i, s in enumerate(sentences)
                }
                audio_chunks = {}
                for future in as_completed(futures):
                    idx, data = future.result()
                    audio_chunks[idx] = data

                with open(filename, "wb") as f:
                    for i in sorted(audio_chunks.keys()):
                        f.write(audio_chunks[i])

                if verbose:
                    ic.configureOutput(prefix="INFO| ")
                    ic(f"Audio saved to {filename}")
                return str(filename)
        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(f"ElevenLabs TTS failed: {e}")

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
        return self.tts(
            text=input_text,
            model=model or "eleven_multilingual_v2",
            voice=voice or "brian",
            response_format=response_format or "mp3",
            verbose=verbose,
        )
