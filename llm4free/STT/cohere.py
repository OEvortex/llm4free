"""
Cohere STT provider with OpenAI-compatible interface.

This module provides an OpenAI Whisper API-compatible interface for Cohere's
multilingual speech-to-text transcription service hosted on Hugging Face Spaces.
"""

import json
import time
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

# Supported languages for Cohere Multilingual ASR
SUPPORTED_LANGUAGES = [
    "en",
    "fr",
    "de",
    "es",
    "pt",
    "it",
    "nl",
    "pl",
    "el",
    "ar",
    "ja",
    "ko",
    "zh",
    "vi",
]


class CohereTranscriptions(BaseSTTTranscriptions):
    """Cohere transcriptions interface."""

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
        """Create a transcription using Cohere API."""
        # Always use file as file-like object
        if isinstance(file, (str, Path)):
            audio_file: BinaryIO = open(str(file), "rb")
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
                result: TranscriptionResponse = self._create_non_stream(
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
        # This should never be reached, but satisfies type checker
        raise RuntimeError("Unexpected code path")

    def _upload_file(
        self,
        audio_file: BinaryIO,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> str:
        """Upload audio file to Gradio and return the file path."""
        headers = {
            "User-Agent": LitAgent().random(),
        }
        files = {
            "files": audio_file,
        }
        response = requests.post(
            f"{self._client.base_url}/gradio_api/upload",
            files=files,
            headers=headers,
            timeout=timeout or self._client.timeout,
            proxies=proxies or getattr(self._client, "proxies", None),
        )
        if response.status_code != 200:
            raise exceptions.FailedToGenerateResponseError(
                f"Cohere file upload failed: {response.status_code} - {response.text}"
            )
        result = response.json()
        # Gradio returns a list of file paths
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        elif isinstance(result, dict) and "path" in result:
            return result["path"]
        else:
            raise exceptions.FailedToGenerateResponseError(
                f"Unexpected upload response format: {result}"
            )

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
            # Step 1: Upload the audio file
            file_path = self._upload_file(audio_file, timeout, proxies)

            # Step 2: Submit transcription request
            headers = {
                "Content-Type": "application/json",
                "User-Agent": LitAgent().random(),
            }
            lang = language or self._client.default_language
            payload = {
                "data": [
                    {
                        "path": file_path,
                        "meta": {"_type": "gradio.FileData"},
                    },
                    lang,
                ]
            }
            response = requests.post(
                f"{self._client.base_url}/gradio_api/call/transcribe",
                headers=headers,
                json=payload,
                timeout=timeout or self._client.timeout,
                proxies=proxies or getattr(self._client, "proxies", None),
            )
            if response.status_code != 200:
                raise exceptions.FailedToGenerateResponseError(
                    f"Cohere API returned error: {response.status_code} - {response.text}"
                )
            result = response.json()
            event_id = result.get("event_id")
            if not event_id:
                raise exceptions.FailedToGenerateResponseError(f"No event_id in response: {result}")

            # Step 3: Get transcription result via SSE
            transcription_text = self._get_sse_result(event_id, timeout, proxies)

            simple_result = {"text": transcription_text}
            return TranscriptionResponse(simple_result, response_format)
        except exceptions.FailedToGenerateResponseError:
            raise
        except Exception as e:
            raise exceptions.FailedToGenerateResponseError(f"Cohere transcription failed: {str(e)}")

    def _get_sse_result(
        self,
        event_id: str,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> str:
        """Get transcription result from SSE endpoint."""
        headers = {
            "User-Agent": LitAgent().random(),
        }
        response = requests.get(
            f"{self._client.base_url}/gradio_api/call/transcribe/{event_id}",
            headers=headers,
            timeout=timeout or self._client.timeout,
            proxies=proxies or getattr(self._client, "proxies", None),
            stream=True,
        )
        if response.status_code != 200:
            raise exceptions.FailedToGenerateResponseError(
                f"Cohere SSE request failed: {response.status_code} - {response.text}"
            )

        # Parse SSE stream
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                    if isinstance(data, list) and len(data) > 0:
                        return data[0]
                    elif isinstance(data, str):
                        return data
                except json.JSONDecodeError:
                    continue

        raise exceptions.FailedToGenerateResponseError(
            "No transcription result received from SSE stream"
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
        """Create streaming transcription."""
        # Step 1: Upload the audio file
        file_path = self._upload_file(audio_file, timeout, proxies)

        # Step 2: Submit transcription request
        headers = {
            "Content-Type": "application/json",
            "User-Agent": LitAgent().random(),
        }
        lang = language or self._client.default_language
        payload = {
            "data": [
                {
                    "path": file_path,
                    "meta": {"_type": "gradio.FileData"},
                },
                lang,
            ]
        }
        response = requests.post(
            f"{self._client.base_url}/gradio_api/call/transcribe",
            headers=headers,
            json=payload,
            timeout=timeout or self._client.timeout,
            proxies=proxies or getattr(self._client, "proxies", None),
        )
        if response.status_code != 200:
            raise exceptions.FailedToGenerateResponseError(
                f"Cohere API returned error: {response.status_code} - {response.text}"
            )
        result = response.json()
        event_id = result.get("event_id")
        if not event_id:
            raise exceptions.FailedToGenerateResponseError(f"No event_id in response: {result}")

        # Step 3: Stream SSE results
        sse_headers = {
            "User-Agent": LitAgent().random(),
        }
        sse_response = requests.get(
            f"{self._client.base_url}/gradio_api/call/transcribe/{event_id}",
            headers=sse_headers,
            timeout=timeout or self._client.timeout,
            proxies=proxies or getattr(self._client, "proxies", None),
            stream=True,
        )
        if sse_response.status_code != 200:
            raise exceptions.FailedToGenerateResponseError(
                f"Cohere SSE request failed: {sse_response.status_code} - {sse_response.text}"
            )

        for line in sse_response.iter_lines(decode_unicode=True):
            if line:
                yield line


class CohereAudio(BaseSTTAudio):
    """Cohere audio interface."""

    def _create_transcriptions(self, client) -> CohereTranscriptions:
        return CohereTranscriptions(client)


class CohereSTT(STTCompatibleProvider):
    """
    OpenAI-compatible client for Cohere Multilingual ASR API.

    Usage:
        client = CohereSTT()
        audio_file = open("audio.wav", "rb")
        transcription = client.audio.transcriptions.create(
            model="cohere-multilingual-asr",
            file=audio_file,
            response_format="text"
        )
        print(transcription.text)
    """

    AVAILABLE_MODELS = [
        "cohere-multilingual-asr",
    ]

    def __init__(
        self,
        model_id: str = "cohere-multilingual-asr",
        default_language: str = "en",
        timeout: int = 120,
        proxies: Optional[dict] = None,
    ):
        """Initialize Cohere STT provider."""
        self.model_id = model_id
        self.default_language = default_language
        self.timeout = timeout
        self.proxies = proxies

        # API configuration - Hugging Face Space URL
        self.base_url = "https://coherelabs-cohere-transcribe-03-2026.hf.space"

        # Initialize interfaces
        self.audio = CohereAudio(self)
        self._models = STTModels(self.AVAILABLE_MODELS)

    @property
    def models(self):
        """Get models interface."""
        return self._models


if __name__ == "__main__":
    from rich import print

    client = CohereSTT()

    # Example audio file path - replace with your own
    audio_file_path = (
        r"C:\Users\koula\Desktop\CODEBASE\Projects\OEvortex\LLM4Free\tests\test_audio.wav"
    )

    print("=== Non-streaming example ===")
    with open(audio_file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="cohere-multilingual-asr", file=audio_file, stream=False
        )
        if hasattr(transcription, "text"):
            print(transcription.text)

    print("\n=== Streaming example ===")
    with open(audio_file_path, "rb") as audio_file:
        stream_gen = client.audio.transcriptions.create(
            model="cohere-multilingual-asr", file=audio_file, stream=True
        )
        for chunk in cast(Generator[str, None, None], stream_gen):
            print(chunk.strip())
