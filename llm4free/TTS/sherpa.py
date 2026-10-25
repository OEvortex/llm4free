##################################################################################
##  SherpaTTS Provider                                                         ##
##################################################################################
import json
import pathlib
import random
import string
import tempfile
from typing import Any, Generator, Optional, Union, cast

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


class SherpaTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the Next-gen Kaldi (Sherpa-ONNX) API.

    This provider follows the OpenAI TTS API structure with support for:
    - Voice cloning via Pocket TTS and ZipVoice models
    - Reference audio from URL or uploaded file
    - Multiple output formats
    """

    required_auth = False

    BASE_URL = "https://k2-fsa-text-to-speech.hf.space"

    # Request headers
    headers: dict[str, str] = {
        "User-Agent": LitAgent().random(),
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/",
    }

    # Current supported models (as of latest space revision)
    SUPPORTED_MODELS = [
        "csukuangfj2/sherpa-onnx-pocket-tts-int8-2026-01-26|voice cloning",
        "sherpa-onnx-zipvoice-distill-int8-zh-en-emilia|Chinese+English voice cloning",
    ]

    LANGUAGES = [
        "Voice Cloning (声音克隆)",
        "English",
        "Chinese (Mandarin, 普通话)",
        "Chinese+English",
        "Persian+English",
        "Cantonese (粤语)",
        "Min-nan (闽南话)",
        "Arabic",
        "Afrikaans",
        "Bengali",
        "Bulgarian",
        "Catalan",
        "Croatian",
        "Czech",
        "Danish",
        "Dutch",
        "Estonian",
        "Finnish",
        "French",
        "Georgian",
        "German",
        "Greek",
        "Gujarati",
        "Hindi",
        "Hungarian",
        "Icelandic",
        "Indonesian",
        "Irish",
        "Italian",
        "Japanese",
        "Kazakh",
        "Korean",
        "Kurdish",
        "Latvian",
        "Lithuanian",
        "Luxembourgish",
        "Maltese",
        "Nepali",
        "Norwegian",
        "Persian",
        "Polish",
        "Portuguese",
        "Romanian",
        "Russian",
        "Serbian",
        "Slovak",
        "Slovenian",
        "Spanish",
        "Swahili",
        "Swedish",
        "Thai",
        "Tswana",
        "Turkish",
        "Ukrainian",
        "Vietnamese",
        "Welsh",
    ]

    # API function indices from current space config
    PROCESS_FN_INDEX = 10
    PROCESS_VOICE_CLONE_FN_INDEX = 11

    def __init__(self, timeout: int = 60, proxy: Optional[str] = None):
        """
        Initialize the SherpaTTS client.
        """
        super().__init__()
        self.timeout = timeout
        self.proxy = proxy
        self.default_language = "Voice Cloning (声音克隆)"
        self.default_model_choice = "csukuangfj2/sherpa-onnx-pocket-tts-int8-2026-01-26|voice cloning"

    def _generate_session_hash(self) -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=11))

    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using Sherpa-ONNX API.

        Args:
            text: Input text
            voice: Ignored here; SherpaTTS is driven by model choice and optional reference audio.
            verbose: Whether to print debug information.
            **kwargs: Additional parameters:
                - model_choice (str): Current supported voice cloning model.
                - language (str): Language selection. Defaults to Voice Cloning.
                - speaker_id (str): Speaker id. Defaults to "0".
                - speed (float): Speed factor. Defaults to 1.0.
                - response_format (str): Audio format. Defaults to "wav".
                - reference_audio_url (str): Optional reference audio url for voice cloning.
                - reference_text (str): Transcript of reference audio.
        """
        language = kwargs.get("language", "Voice Cloning (声音克隆)")
        model_choice = kwargs.get("model_choice", self.default_model_choice)
        speaker_id = kwargs.get("speaker_id", "0")
        speed = kwargs.get("speed", 1.0)
        response_format = kwargs.get("response_format", "wav")
        reference_audio_url = kwargs.get("reference_audio_url")
        reference_text = kwargs.get("reference_text", text)

        if not text:
            raise ValueError("Input text must be a non-empty string")

        model_choice = self.validate_model(model_choice)

        session_hash = self._generate_session_hash()
        filename = pathlib.Path(
            tempfile.NamedTemporaryFile(
                suffix=f".{response_format}", dir=self.temp_dir, delete=False
            ).name
        )

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"SherpaTTS: Generating speech for '{text[:20]}...' using {language}/{model_choice}")

        client_kwargs: dict[str, Any] = {"headers": self.headers, "timeout": self.timeout}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        try:
            with cf_requests.Session(**client_kwargs) as client:
                # Voice cloning models require reference audio.
                if reference_audio_url:
                    fn_index = self.PROCESS_VOICE_CLONE_FN_INDEX
                    data = [
                        language,
                        model_choice,
                        text,
                        speaker_id,
                        speed,
                        None,
                        None,
                        reference_audio_url,
                        reference_text,
                    ]
                else:
                    fn_index = self.PROCESS_FN_INDEX
                    data = [language, model_choice, text, speaker_id, speed]

                payload = {
                    "data": data,
                    "event_data": None,
                    "fn_index": fn_index,
                    "trigger_id": 9,
                    "session_hash": session_hash,
                }

                join_url = f"{self.BASE_URL}/gradio_api/queue/join?"
                response = client.post(join_url, json=payload)
                response.raise_for_status()

                data_url = f"{self.BASE_URL}/gradio_api/queue/data?session_hash={session_hash}"
                audio_url = None

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
                                output = data.get("output") or {}
                                if data.get("success"):
                                    output_data = output.get("data") or []
                                    if output_data:
                                        audio_info = output_data[0]
                                        if isinstance(audio_info, dict):
                                            audio_url = audio_info.get("url") or audio_info.get("path")
                                    break
                                else:
                                    raise exceptions.FailedToGenerateResponseError(
                                        f"Generation failed: {output}"
                                    )
                            elif msg == "queue_full":
                                raise exceptions.FailedToGenerateResponseError("Queue is full")

                if not audio_url:
                    raise exceptions.FailedToGenerateResponseError(
                        "Failed to get audio URL from stream"
                    )

                if audio_url.startswith("/"):
                    audio_url = f"{self.BASE_URL}{audio_url}"

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
                ic(f"Error in SherpaTTS: {e}")
            raise exceptions.FailedToGenerateResponseError(f"Failed to generate audio: {e}")

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "csukuangfj2/sherpa-onnx-pocket-tts-int8-2026-01-26|voice cloning",
        voice: Optional[str] = None,
        response_format: Optional[str] = "wav",
        instructions: Optional[str] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        OpenAI-compatible speech creation interface.

        Args:
            input_text (str): The text to convert to speech
            model (str): The TTS model to use
            voice (str): Ignored for SherpaTTS
            response_format (str): Audio format
            instructions (str): Voice instructions
            verbose (bool): Whether to print debug information
            **kwargs: Additional parameters:
                - language (str): Language selection.
                - speaker_id (str): Speaker id.
                - speed (float): Speed factor.
                - reference_audio_url (str): Optional reference audio url for voice cloning.
                - reference_text (str): Transcript of reference audio.

        Returns:
            str: Path to the generated audio file
        """
        merge = {}
        if instructions:
            merge["reference_text"] = instructions
        merge.update(kwargs)
        return self.tts(
            text=input_text,
            model_choice=model or self.default_model_choice,
            response_format=response_format or "wav",
            verbose=verbose,
            **merge,
        )

    def with_streaming_response(self):
        return StreamingResponseContextManager(self)


class StreamingResponseContextManager:
    def __init__(self, tts_provider: SherpaTTS):
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
    tts = SherpaTTS()
    try:
        path = tts.tts(
            "This is a Sherpa-ONNX test.",
            verbose=True,
            language="Voice Cloning (声音克隆)",
            model_choice="csukuangfj2/sherpa-onnx-pocket-tts-int8-2026-01-26|voice cloning",
            reference_audio_url="https://github.com/gradio-app/gradio/raw/main/test/test_files/audio_sample.wav",
            reference_text="This is reference audio text.",
        )
        ic.configureOutput(prefix="INFO| ")
        ic(f"Result: {path}")
    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error: {e}")
