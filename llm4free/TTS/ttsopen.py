##################################################################################
##  TTSOpen.ai TTS Provider                                                      ##
##  Reverse-engineered from https://ttsopen.ai (OpenAI.fm alternative)            ##
##################################################################################
import hashlib
import hmac
import json
import pathlib
import tempfile
import time
from typing import Any, Generator, List, Optional, Union, cast

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent
from llm4free.TTS.base import BaseTTSProvider

# Static HMAC key (hex) used to sign every request. The browser hex-decodes this
# and computes HMAC-SHA256 over (x-ts + x-account + body).lowercase().
_SIGN_KEY_HEX = "b7c3e2d8f74b4698a4f7f9d8e6e5a2b4"


class TTSOpenTTS(BaseTTSProvider):
    """
    Text-to-speech provider for TTSOpen.ai with an OpenAI-compatible interface.

    TTSOpen is a free, login-free TTS service that proxies to ``api.ttsopen.ai``.
    Every request is authenticated with static ``x-*`` headers and an
    HMAC-SHA256 ``x-sign`` signature. The generation flow is:

    1. ``POST /user/loginAnonymously`` -> anonymous ``uuid`` (used as ``x-account``)
    2. ``POST /tts/submitTask`` -> ``taskSn`` for the queued job
    3. ``POST /tts/getByTaskSn`` -> poll until ``fileUrl`` (MP3) is ready
    4. Download the MP3 from ``cdn.ttsopen.ai``

    Supported voices mirror the OpenAI-style voice set (ids 1-13).

    Note:
        The anonymous free tier is rate-limited per IP: only one synthesis task
        may run concurrently, and there is a small daily quota (the API returns
        ``code 70002004`` while a task is in progress and ``code 70001006`` when
        the daily limit is reached). These are surfaced as
        ``FailedToGenerateResponseError``.
    """

    required_auth = False

    # TTSOpen does not expose a "model" selection; voice + speed drive synthesis.
    SUPPORTED_MODELS = None

    # Supported voices (OpenAI-style + TTSOpen high-fidelity additions)
    SUPPORTED_VOICES = [
        "alloy",  # natural, smooth (Young Male)
        "ash",  # enthusiastic, energetic (Young Male)
        "ballad",  # lyrical, emotive (Storytelling)
        "cedar",  # warm, high-fidelity
        "coral",  # cheerful, upbeat
        "echo",  # articulate, precise (Young Male)
        "fable",  # warm, engaging (Young Male)
        "marin",  # natural, high-fidelity
        "nova",  # bright, energetic (Young Female)
        "onyx",  # deep, authoritative (Old Male)
        "sage",  # calm, thoughtful
        "shimmer",  # soft, gentle (Young Female)
        "verse",  # poetic, rhythmic
    ]

    # Map voice name -> API voiceId
    voice_mapping = {
        "alloy": 1,
        "echo": 2,
        "fable": 3,
        "onyx": 4,
        "nova": 5,
        "shimmer": 6,
        "ash": 7,
        "ballad": 8,
        "coral": 9,
        "sage": 10,
        "verse": 11,
        "marin": 12,
        "cedar": 13,
    }

    def __init__(self, timeout: int = 30, proxies: Optional[dict] = None):
        """
        Initialize the TTSOpen.ai TTS client.

        Args:
            timeout (int): Request timeout in seconds
            proxies (dict): Proxy configuration
        """
        super().__init__()
        self.api_base = "https://api.ttsopen.ai"
        self.cdn_base = "https://cdn.ttsopen.ai"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json;charset=UTF-8",
                "origin": "https://ttsopen.ai",
                "referer": "https://ttsopen.ai/",
                "user-agent": LitAgent().random(),
            }
        )
        if proxies:
            self.session.proxies.update(cast(Any, proxies))
        self.timeout = timeout
        # Cached anonymous account credentials (uuid + token)
        self._account: str = ""
        self._token: str = ""

    # ------------------------------------------------------------------ signing
    @staticmethod
    def _sign(ts: int, account: str, body: dict) -> str:
        """Compute the HMAC-SHA256 ``x-sign`` value for a request.

        Args:
            ts (int): Millisecond timestamp used in ``x-ts``.
            account (str): Current ``x-account`` value (uuid or empty).
            body (dict): The JSON request body.

        Returns:
            str: Lowercase hex HMAC-SHA256 signature.
        """
        key = bytes.fromhex(_SIGN_KEY_HEX)
        msg = f"{ts}{account}{json.dumps(body, separators=(',', ':'))}".lower()
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()

    def _headers(self, body: dict) -> dict:
        """Build the static + signed ``x-*`` headers for a request."""
        ts = int(time.time() * 1000)
        return {
            "x-appid": "4",
            "x-code": "110",
            "x-os": "web",
            "x-ts": str(ts),
            "x-account": self._account,
            "x-token": self._token,
            "x-sign": self._sign(ts, self._account, body),
        }

    def _post(self, path: str, body: dict) -> dict:
        """Signed POST to the TTSOpen API; returns parsed JSON ``data``."""
        response = self.session.post(
            f"{self.api_base}{path}",
            headers=self._headers(body),
            data=json.dumps(body).encode("utf-8"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200 or "data" not in payload:
            raise exceptions.FailedToGenerateResponseError(
                f"TTSOpen API error: {payload}"
            )
        return payload["data"]

    # -------------------------------------------------------------------- login
    def _ensure_login(self) -> None:
        """Lazily perform anonymous login to obtain ``x-account``/``x-token``."""
        if self._account:
            return
        data = self._post("/user/loginAnonymously", {})
        self._account = data["user"]["base"]["uuid"]
        self._token = data["user"].get("token", "")

    # ---------------------------------------------------------------------- tts
    def tts(
        self,
        text: str,
        voice: Optional[str] = None,
        verbose: bool = False,
        **kwargs,
    ) -> str:
        """
        Convert text to speech using the TTSOpen.ai API.

        Args:
            text (str): The text to convert to speech.
            voice (str): Voice name (alloy, onyx, coral, ...). Defaults to "onyx".
            response_format (str): Output format (only ``mp3`` is supported).
            speed (float): Speech speed multiplier (e.g. 0.5-2.0). Defaults to 1.0.
            verbose (bool): Whether to print debug information.

        Returns:
            str: Path to the generated MP3 audio file.

        Raises:
            ValueError: If the input text is empty.
            exceptions.FailedToGenerateResponseError: On generation/download failure.
        """
        response_format = kwargs.get("response_format", "mp3")
        # TTSOpen only accepts integer speed values (e.g. 1, 1.5 rejected as float).
        speed = float(kwargs.get("speed", 1.0))
        speed = int(speed) if speed.is_integer() else speed

        if not text or not isinstance(text, str):
            raise ValueError("Input text must be a non-empty string")
        if response_format != "mp3":
            raise ValueError("TTSOpen only supports the 'mp3' response format")

        voice = voice or "onyx"
        if voice not in self.SUPPORTED_VOICES:
            raise ValueError(
                f"Voice '{voice}' not supported. Available: {', '.join(self.SUPPORTED_VOICES)}"
            )
        voice_id = self.voice_mapping[voice]

        # Create the output file (TTSOpen always returns MP3)
        with tempfile.NamedTemporaryFile(
            suffix=".mp3", dir=self.temp_dir, delete=False
        ) as temp_file:
            filename = pathlib.Path(temp_file.name)

        try:
            # 1) anonymous login (cached)
            self._ensure_login()

            # 2) submit synthesis task. The free anonymous account allows only one
            #    concurrent task; retry briefly while a previous one is still running
            #    (API code 70002004). Fail fast on the daily-quota error (70001006),
            #    since retrying cannot help.
            submit = None
            for _ in range(15):
                try:
                    submit = self._post(
                        "/tts/submitTask",
                        {"text": text, "voiceId": voice_id, "speed": speed},
                    )
                    break
                except exceptions.FailedToGenerateResponseError as e:
                    err = str(e)
                    if "70001006" in err or "come back tomorrow" in err:
                        raise
                    if "in progress" in err or "70002004" in err:
                        time.sleep(2.0)
                        continue
                    raise
            if submit is None:
                raise exceptions.FailedToGenerateResponseError(
                    "TTSOpen rejected the task (rate limited / in progress)"
                )
            task_sn = submit["taskSn"]

            # 3) poll for completion
            file_url = None
            for _ in range(30):
                result = self._post("/tts/getByTaskSn", {"taskSn": task_sn})
                file_url = result.get("fileUrl")
                if file_url:
                    break
                time.sleep(1.0)
            if not file_url:
                raise exceptions.FailedToGenerateResponseError(
                    "TTSOpen task did not complete in time"
                )

            # 4) download the MP3
            audio = self.session.get(file_url, timeout=self.timeout)
            audio.raise_for_status()
            if not audio.content:
                raise exceptions.FailedToGenerateResponseError("Empty audio response")
            with open(filename, "wb") as f:
                f.write(audio.content)

            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic("Speech generated successfully")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Voice: {voice} (id={voice_id})")
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Speed: {speed}")
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
        model: Optional[str] = None,
        voice: Optional[str] = "onyx",
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        OpenAI-compatible speech creation interface.

        Args:
            input_text (str): The text to convert to speech
            voice (str): The voice to use
            response_format (str): Audio format (only ``mp3``)
            verbose (bool): Whether to print debug information

        Returns:
            str: Path to the generated audio file
        """
        return self.tts(
            text=input_text,
            voice=voice or "onyx",
            response_format=response_format or "mp3",
            verbose=verbose,
            **kwargs,
        )


if __name__ == "__main__":
    tts_provider = TTSOpenTTS()

    try:
        ic.configureOutput(prefix="DEBUG| ")
        ic("Testing TTSOpen.ai speech generation...")
        audio_file = tts_provider.create_speech(
            input_text="Today is a wonderful day to build something people love!",
            voice="onyx",
            speed=1.0,
        )
        print(f"Audio file generated: {audio_file}")
    except exceptions.FailedToGenerateResponseError as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error: {e}")
    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Unexpected error: {e}")
