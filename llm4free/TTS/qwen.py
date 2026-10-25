##################################################################################
##  Qwen3-TTS Provider                                                         ##
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


class QwenTTS(BaseTTSProvider):
    """
    Text-to-speech provider using the Qwen3-TTS API (Hugging Face Spaces).

    This provider follows the OpenAI TTS API structure with support for:
    - Multiple TTS models (mapped to Gradio fn_index)
    - 40+ high-quality voices across multiple languages
    - Automatic language detection or manual selection
    - Multiple output formats
    - Streaming response simulation
    """

    required_auth = False

    BASE_URL = "https://qwen-qwen3-tts-demo.hf.space"

    # Request headers
    headers: dict[str, str] = {
        "User-Agent": LitAgent().random(),
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/",
    }

    # Override supported models
    SUPPORTED_MODELS = ["qwen3-tts"]

    # Supported voices
    SUPPORTED_VOICES = [
        "cherry",
        "serena",
        "ethan",
        "chelsie",
        "momo",
        "vivian",
        "moon",
        "maia",
        "kai",
        "nofish",
        "bella",
        "jennifer",
        "ryan",
        "katerina",
        "aiden",
        "bodega",
        "alek",
        "dolce",
        "sohee",
        "ono_anna",
        "lenn",
        "sonrisa",
        "emilien",
        "andre",
        "radio_gol",
        "eldric_sage",
        "mia",
        "mochi",
        "bellona",
        "vincent",
        "bunny",
        "neil",
        "elias",
        "arthur",
        "nini",
        "ebona",
        "seren",
        "pip",
        "stella",
        "li",
        "marcus",
        "roy",
        "peter",
        "eric",
        "rocky",
        "kiki",
        "sunny",
        "jada",
        "dylan",
    ]

    # Voice mapping for API compatibility
    voice_mapping = {
        "cherry": "Cherry / 芊悦",
        "serena": "Serena / 苏瑶",
        "ethan": "Ethan / 晨煦",
        "chelsie": "Chelsie / 千雪",
        "momo": "Momo / 茉兔",
        "vivian": "Vivian / 十三",
        "moon": "Moon / 月白",
        "maia": "Maia / 四月",
        "kai": "Kai / 凯",
        "nofish": "Nofish / 不吃鱼",
        "bella": "Bella / 萌宝",
        "jennifer": "Jennifer / 詹妮弗",
        "ryan": "Ryan / 甜茶",
        "katerina": "Katerina / 卡捷琳娜",
        "aiden": "Aiden / 艾登",
        "bodega": "Bodega / 西班牙语-博德加",
        "alek": "Alek / 俄语-阿列克",
        "dolce": "Dolce / 意大利语-多尔切",
        "sohee": "Sohee / 韩语-素熙",
        "ono_anna": "Ono Anna / 日语-小野杏",
        "lenn": "Lenn / 德语-莱恩",
        "sonrisa": "Sonrisa / 西班牙语拉美-索尼莎",
        "emilien": "Emilien / 法语-埃米尔安",
        "andre": "Andre / 葡萄牙语欧-安德雷",
        "radio_gol": "Radio Gol / 葡萄牙语巴-拉迪奥·戈尔",
        "eldric_sage": "Eldric Sage / 精品百人-沧明子",
        "mia": "Mia / 精品百人-乖小妹",
        "mochi": "Mochi / 精品百人-沙小弥",
        "bellona": "Bellona / 精品百人-燕铮莺",
        "vincent": "Vincent / 精品百人-田叔",
        "bunny": "Bunny / 精品百人-萌小姬",
        "neil": "Neil / 精品百人-阿闻",
        "elias": "Elias / 墨讲师",
        "arthur": "Arthur / 精品百人-徐大爷",
        "nini": "Nini / 精品百人-邻家妹妹",
        "ebona": "Ebona / 精品百人-诡婆婆",
        "seren": "Seren / 精品百人-小婉",
        "pip": "Pip / 精品百人-调皮小新",
        "stella": "Stella / 精品百人-美少女阿月",
        "li": "Li / 南京-老李",
        "marcus": "Marcus / 陕西-秦川",
        "roy": "Roy / 闽南-阿杰",
        "peter": "Peter / 天津-李彼得",
        "eric": "Eric / 四川-程川",
        "rocky": "Rocky / 粤语-阿强",
        "kiki": "Kiki / 粤语-阿清",
        "sunny": "Sunny / 四川-晴儿",
        "jada": "Jada / 上海-阿珍",
        "dylan": "Dylan / 北京-晓东",
    }

    def __init__(self, timeout: int = 60, proxy: Optional[str] = None):
        """
        Initialize the QwenTTS client.

        Args:
            timeout (int): Request timeout in seconds
            proxy (str): Proxy configuration string
        """
        super().__init__()
        self.timeout = timeout
        self.proxy = proxy
        self.default_voice = "cherry"
        self.default_model = "qwen3-tts"

    def _generate_session_hash(self) -> str:
        """Generates a random session hash for Gradio."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

    def tts(self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs) -> str:
        """
        Convert text to speech using Qwen3-TTS API with OpenAI-compatible parameters.

        Args:
            text (str): The text to convert to speech (max 10,000 characters)
            **kwargs: Additional parameters (model, voice, response_format, language, verbose)
        """
        # Extract parameters from kwargs with defaults
        voice = kwargs.get("voice", "cherry")
        response_format = kwargs.get("response_format", "wav")
        language = kwargs.get("language", "Auto / 自动")
        verbose = kwargs.get("verbose", True)
        if not text or not isinstance(text, str):
            raise ValueError("Input text must be a non-empty string")

        voice = self.validate_voice(voice)
        qwen_voice = self.voice_mapping.get(voice, self.voice_mapping["cherry"])

        # Create temporary file
        file_extension = f".{response_format}"
        filename = pathlib.Path(
            tempfile.NamedTemporaryFile(suffix=file_extension, dir=self.temp_dir, delete=False).name
        )

        session_hash = self._generate_session_hash()

        if verbose:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"Joining queue for voice: {voice} ({qwen_voice})")

        client_kwargs: dict[str, Any] = {"headers": self.headers, "timeout": self.timeout}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        try:
            with cf_requests.Session(**client_kwargs) as client:
                # Step 1: Join the queue
                join_url = f"{self.BASE_URL}/gradio_api/queue/join?"
                payload = {
                    "data": [text, qwen_voice, language],
                    "event_data": None,
                    "fn_index": 1,
                    "trigger_id": 7,
                    "session_hash": session_hash,
                }

                response = client.post(join_url, json=payload)
                response.raise_for_status()

                # Step 2: Poll for data (SSE)
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
                                if data.get("success"):
                                    output_data = data.get("output", {}).get("data", [])
                                    if output_data:
                                        audio_info = output_data[0]
                                        path = (
                                            audio_info["path"]
                                            if isinstance(audio_info, dict)
                                            else audio_info
                                        )
                                        audio_url = f"{self.BASE_URL}/gradio_api/file={path}"
                                    break
                                else:
                                    raise exceptions.FailedToGenerateResponseError(
                                        f"Generation failed: {data}"
                                    )
                            elif msg == "queue_full":
                                raise exceptions.FailedToGenerateResponseError("Queue is full")

                if not audio_url:
                    raise exceptions.FailedToGenerateResponseError(
                        "Failed to get audio URL from stream"
                    )

                # Step 3: Download the audio file
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
                ic(f"Error in QwenTTS: {e}")
            raise exceptions.FailedToGenerateResponseError(f"Failed to generate audio: {e}")

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "gpt-4o-mini-tts",
        voice: Optional[str] = "alloy",
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
        verbose: bool = False,
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
            **kwargs: Additional parameters

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


# ... (keep other classes as is)

if __name__ == "__main__":
    qwen = QwenTTS()
    try:
        ic.configureOutput(prefix="DEBUG| ")
        ic("Testing Qwen3-TTS...")
        path = qwen.create_speech(
            input_text="Hello, this is a test.", voice="jennifer", verbose=True
        )
        ic.configureOutput(prefix="INFO| ")
        ic(f"Saved to {path}")
    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error: {e}")
