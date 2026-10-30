"""
ElevenLabs STT provider with OpenAI-compatible interface.

This module provides an OpenAI Whisper API-compatible interface for ElevenLabs
speech-to-text transcription service.
"""

from pathlib import Path
from typing import Any, BinaryIO, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http import compat as requests

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.STT.base import (
    BaseSTTAudio,
    BaseSTTTranscriptions,
    STTCompatibleProvider,
    STTModels,
    TranscriptionResponse,
)


class ElevenLabsTranscriptions(BaseSTTTranscriptions):
    """ElevenLabs transcriptions interface."""

    def create(
        self,
        *,
        model: str,
        file: Union[BinaryIO, str, Path],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: Optional[float] = None,
        timestamp_granularities: Optional[List[str]] = None,
        stream: bool = False,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[TranscriptionResponse, Generator[str, None, None]]:
        """Create a transcription using ElevenLabs API."""
        # Always use file as file-like object
        if isinstance(file, (str, Path)):
            audio_file = open(str(file), "rb")
            close_file = True
        else:
            audio_file = file
            close_file = False
        try:
            if stream:
                return self._create_stream(
                    audio_file=audio_file,
                    model=model,
                    language=language,
                    prompt=prompt,
                    response_format=response_format,
                    temperature=temperature,
                    timestamp_granularities=timestamp_granularities,
                    timeout=timeout,
                    proxies=proxies,
                    **kwargs,
                )
            else:
                result = self._create_non_stream(
                    audio_file=audio_file,
                    model=model,
                    language=language,
                    prompt=prompt,
                    response_format=response_format,
                    temperature=temperature,
                    timestamp_granularities=timestamp_granularities,
                    timeout=timeout,
                    proxies=proxies,
                    **kwargs,
                )
                return result
        finally:
            if close_file:
                audio_file.close()

    def _create_non_stream(
        self,
        audio_file: BinaryIO,
        model: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: Optional[float] = None,
        timestamp_granularities: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> TranscriptionResponse:
        """Create non-streaming transcription."""
        try:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": LitAgent().random(),
            }
            api_url = self._client.api_url
            if getattr(self._client, "allow_unauthenticated", False):
                if "?" in api_url:
                    api_url += "&allow_unauthenticated=1"
                else:
                    api_url += "?allow_unauthenticated=1"
            files = {
                "file": audio_file,
                "model_id": (None, self._client.model_id),
                "tag_audio_events": (None, "true" if self._client.tag_audio_events else "false"),
                "diarize": (None, "true" if self._client.diarize else "false"),
            }
            if language:
                files["language"] = (None, language)
            response = requests.post(
                api_url,
                files=files,
                headers=headers,
                timeout=timeout or self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None)
            )
            if response.status_code != 200:
                raise exceptions.FailedToGenerateResponseError(
                    f"ElevenLabs API returned error: {response.status_code} - {response.text}"
                )
            result = response.json()
            simple_result = {"text": result.get("text", "")}
            return TranscriptionResponse(simple_result, response_format)
        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(
                f"ElevenLabs transcription failed: {str(e)}"
            )

    def _create_stream(
        self,
        audio_file: BinaryIO,
        model: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: str = "json",
        temperature: Optional[float] = None,
        timestamp_granularities: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Create streaming transcription using requests.post(..., stream=True)."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": LitAgent().random(),
        }
        api_url = self._client.api_url
        if getattr(self._client, "allow_unauthenticated", False):
            if "?" in api_url:
                api_url += "&allow_unauthenticated=1"
            else:
                api_url += "?allow_unauthenticated=1"
        files = {
            "file": audio_file,
            "model_id": (None, self._client.model_id),
            "tag_audio_events": (None, "true" if self._client.tag_audio_events else "false"),
            "diarize": (None, "true" if self._client.diarize else "false"),
        }
        if language:
            files["language"] = (None, language)
        response = requests.post(
            api_url,
            files=files,
            headers=headers,
            timeout=timeout or self._client.timeout,
            proxies=proxies or getattr(self._client, "proxies", None)
            stream=True,
        )
        if response.status_code != 200:
            raise exceptions.FailedToGenerateResponseError(
                f"ElevenLabs API returned error: {response.status_code} - {response.text}"
            )
        # Stream the response, decode utf-8
        for line in response.iter_lines(decode_unicode=True):
            if line:
                yield line


class ElevenLabsAudio(BaseSTTAudio):
    """ElevenLabs audio interface."""

    def _create_transcriptions(self, client) -> ElevenLabsTranscriptions:
        return ElevenLabsTranscriptions(client)


class ElevenLabsSTT(STTCompatibleProvider):
    """
    OpenAI-compatible client for ElevenLabs STT API.

    Usage:
        client = ElevenLabsSTT()
        audio_file = open("audio.mp3", "rb")
        transcription = client.audio.transcriptions.create(
            model="scribe_v1",
            file=audio_file,
            response_format="text"
        )
        print(transcription.text)
    """

    AVAILABLE_MODELS = [
        "scribe_v1",
    ]

    def __init__(
        self,
        model_id: str = "scribe_v1",
        allow_unauthenticated: bool = True,
        tag_audio_events: bool = True,
        diarize: bool = True,
        timeout: int = 60,
        proxies: Optional[dict] = None,
    ):
        """Initialize ElevenLabs STT provider."""
        self.model_id = model_id
        self.allow_unauthenticated = allow_unauthenticated
        self.tag_audio_events = tag_audio_events
        self.diarize = diarize
        self.timeout = timeout
        self.proxies = proxies

        # API configuration
        self.api_url = "https://api.elevenlabs.io/v1/speech-to-text"

        # Initialize interfaces
        self.audio = ElevenLabsAudio(self)
        self._models = STTModels(self.AVAILABLE_MODELS)

    @property
    def models(self):
        """Get models interface."""
        return self._models


if __name__ == "__main__":
    from rich import print

    client = ElevenLabsSTT()

    # Example audio file path - replace with your own
    audio_file_path = r"C:\Users\koula\Downloads\audio_2025-05-12_22-30-47.ogg"

    print("=== Non-streaming example ===")
    with open(audio_file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="scribe_v1", file=audio_file, stream=False
        )
        if hasattr(transcription, "text"):
            print(transcription.text)

    print("\n=== Streaming example ===")
    with open(audio_file_path, "rb") as audio_file:
        stream_gen = client.audio.transcriptions.create(
            model="scribe_v1", file=audio_file, stream=True
        )
        for chunk in cast(Generator[str, None, None], stream_gen):
            print(chunk.strip())
