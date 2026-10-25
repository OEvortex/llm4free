import pathlib
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Optional, Union, cast

from llm4free.browser_requests._http.exceptions import CurlError
from llm4free.browser_requests._http import compat as requests
from litprinter import ic

from llm4free import exceptions
from llm4free.litagent import LitAgent

from . import utils
from .base import BaseTTSProvider


class StreamElements(BaseTTSProvider):
    """

    Text-to-speech provider using the StreamElements API.

    """

    required_auth = False

    # Supported voices

    SUPPORTED_VOICES = [
        "Filiz",
        "Astrid",
        "Tatyana",
        "Maxim",
        "Carmen",
        "Ines",
        "Cristiano",
        "Vitoria",
        "Ricardo",
        "Maja",
        "Jan",
        "Jacek",
        "Ewa",
        "Ruben",
        "Lotte",
        "Liv",
        "Seoyeon",
        "Takumi",
        "Mizuki",
        "Giorgio",
        "Carla",
        "Bianca",
        "Karl",
        "Dora",
        "Mathieu",
        "Celine",
        "Chantal",
        "Penelope",
        "Miguel",
        "Mia",
        "Enrique",
        "Conchita",
        "Geraint",
        "Salli",
        "Matthew",
        "Kimberly",
        "Kendra",
        "Justin",
        "Joey",
        "Joanna",
        "Ivy",
        "Raveena",
        "Aditi",
        "Emma",
        "Brian",
        "Amy",
        "Russell",
        "Nicole",
        "Vicki",
        "Marlene",
        "Hans",
        "Naja",
        "Mads",
        "Gwyneth",
        "Zhiyu",
        "es-ES-Standard-A",
        "it-IT-Standard-A",
        "it-IT-Wavenet-A",
        "ja-JP-Standard-A",
        "ja-JP-Wavenet-A",
        "ko-KR-Standard-A",
        "ko-KR-Wavenet-A",
        "pt-BR-Standard-A",
        "tr-TR-Standard-A",
        "sv-SE-Standard-A",
        "nl-NL-Standard-A",
        "nl-NL-Wavenet-A",
        "en-US-Wavenet-A",
        "en-US-Wavenet-B",
        "en-US-Wavenet-C",
        "en-US-Wavenet-D",
        "en-US-Wavenet-E",
        "en-US-Wavenet-F",
        "en-GB-Standard-A",
        "en-GB-Standard-B",
        "en-GB-Standard-C",
        "en-GB-Standard-D",
        "en-GB-Wavenet-A",
        "en-GB-Wavenet-B",
        "en-GB-Wavenet-C",
        "en-GB-Wavenet-D",
        "en-US-Standard-B",
        "en-US-Standard-C",
        "en-US-Standard-D",
        "en-US-Standard-E",
        "de-DE-Standard-A",
        "de-DE-Standard-B",
        "de-DE-Wavenet-A",
        "de-DE-Wavenet-B",
        "de-DE-Wavenet-C",
        "de-DE-Wavenet-D",
        "en-AU-Standard-A",
        "en-AU-Standard-B",
        "en-AU-Wavenet-A",
        "en-AU-Wavenet-B",
        "en-AU-Wavenet-C",
        "en-AU-Wavenet-D",
        "en-AU-Standard-C",
        "en-AU-Standard-D",
        "fr-CA-Standard-A",
        "fr-CA-Standard-B",
        "fr-CA-Standard-C",
        "fr-CA-Standard-D",
        "fr-FR-Standard-C",
        "fr-FR-Standard-D",
        "fr-FR-Wavenet-A",
        "fr-FR-Wavenet-B",
        "fr-FR-Wavenet-C",
        "fr-FR-Wavenet-D",
        "da-DK-Wavenet-A",
        "pl-PL-Wavenet-A",
        "pl-PL-Wavenet-B",
        "pl-PL-Wavenet-C",
        "pl-PL-Wavenet-D",
        "pt-PT-Wavenet-A",
        "pt-PT-Wavenet-B",
        "pt-PT-Wavenet-C",
        "pt-PT-Wavenet-D",
        "ru-RU-Wavenet-A",
        "ru-RU-Wavenet-B",
        "ru-RU-Wavenet-C",
        "ru-RU-Wavenet-D",
        "sk-SK-Wavenet-A",
        "tr-TR-Wavenet-A",
        "tr-TR-Wavenet-B",
        "tr-TR-Wavenet-C",
        "tr-TR-Wavenet-D",
        "tr-TR-Wavenet-E",
        "uk-UA-Wavenet-A",
        "ar-XA-Wavenet-A",
        "ar-XA-Wavenet-B",
        "ar-XA-Wavenet-C",
        "cs-CZ-Wavenet-A",
        "nl-NL-Wavenet-B",
        "nl-NL-Wavenet-C",
        "nl-NL-Wavenet-D",
        "nl-NL-Wavenet-E",
        "en-IN-Wavenet-A",
        "en-IN-Wavenet-B",
        "en-IN-Wavenet-C",
        "fil-PH-Wavenet-A",
        "fi-FI-Wavenet-A",
        "el-GR-Wavenet-A",
        "hi-IN-Wavenet-A",
        "hi-IN-Wavenet-B",
        "hi-IN-Wavenet-C",
        "hu-HU-Wavenet-A",
        "id-ID-Wavenet-A",
        "id-ID-Wavenet-B",
        "id-ID-Wavenet-C",
        "it-IT-Wavenet-B",
        "it-IT-Wavenet-C",
        "it-IT-Wavenet-D",
        "ja-JP-Wavenet-B",
        "ja-JP-Wavenet-C",
        "ja-JP-Wavenet-D",
        "cmn-CN-Wavenet-A",
        "cmn-CN-Wavenet-B",
        "cmn-CN-Wavenet-C",
        "cmn-CN-Wavenet-D",
        "nb-no-Wavenet-E",
        "nb-no-Wavenet-A",
        "nb-no-Wavenet-B",
        "nb-no-Wavenet-C",
        "nb-no-Wavenet-D",
        "vi-VN-Wavenet-A",
        "vi-VN-Wavenet-B",
        "vi-VN-Wavenet-C",
        "vi-VN-Wavenet-D",
        "sr-rs-Standard-A",
        "lv-lv-Standard-A",
        "is-is-Standard-A",
        "bg-bg-Standard-A",
        "af-ZA-Standard-A",
        "Tracy",
        "Danny",
        "Huihui",
        "Yaoyao",
        "Kangkang",
        "HanHan",
        "Zhiwei",
        "Asaf",
        "An",
        "Stefanos",
        "Filip",
        "Ivan",
        "Heidi",
        "Herena",
        "Kalpana",
        "Hemant",
        "Matej",
        "Andika",
        "Rizwan",
        "Lado",
        "Valluvar",
        "Linda",
        "Heather",
        "Sean",
        "Michael",
        "Karsten",
        "Guillaume",
        "Pattara",
        "Jakub",
        "Szabolcs",
        "Hoda",
        "Naayf",
    ]

    all_voices = SUPPORTED_VOICES

    # Request headers

    headers: dict[str, str] = {"User-Agent": LitAgent().random()}

    def __init__(self, timeout: int = 20, proxies: Optional[dict] = None):
        """Initializes the StreamElements TTS client."""
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        if proxies:
            self.session.proxies.update(cast(Any, proxies))
        self.timeout = timeout

    def tts(self, text: str, voice: Optional[str] = None, verbose: bool = False, **kwargs) -> str:
        """
        Converts text to speech using the StreamElements API and saves it to a file.

        Args:
            text (str): The text to convert to speech
            voice (str): The voice to use for TTS
            verbose (bool): Whether to print progress messages
            **kwargs: Additional parameters

        Returns:
            str: Path to the generated audio file
        """
        voice = voice or kwargs.get("voice", "Emma")
        verbose = verbose if verbose is not None else kwargs.get("verbose", True)
        if voice not in self.all_voices:
            # Try case-insensitive match
            found_voice = None
            for v in self.all_voices:
                if v.lower() == voice.lower():
                    found_voice = v
                    break
            if found_voice:
                voice = found_voice
            else:
                raise ValueError(f"Voice '{voice}' not one of [{', '.join(self.all_voices)}]")

        filename = pathlib.Path(
            tempfile.NamedTemporaryFile(suffix=".mp3", dir=self.temp_dir, delete=False).name
        )

        # Split text into sentences
        sentences = utils.split_sentences(text)

        # Function to request audio for each chunk
        def generate_audio_for_chunk(part_text: str, part_number: int):
            while True:
                try:
                    # URL encode the text and voice
                    encoded_text = urllib.parse.quote(part_text)
                    encoded_voice = urllib.parse.quote(voice)

                    url = f"https://streamelements.com/tts/{encoded_voice}/{encoded_text}"

                    response = self.session.get(url, headers=self.headers, timeout=self.timeout)
                    response.raise_for_status()

                    # Check if the request was successful
                    if response.ok and response.status_code == 200:
                        if verbose:
                            ic.configureOutput(prefix="DEBUG| ")
                            ic(f"Chunk {part_number} processed successfully")
                        return part_number, response.content
                    else:
                        if verbose:
                            ic.configureOutput(prefix="DEBUG| ")
                            ic(f"No data received for chunk {part_number}. Retrying...")
                except CurlError as e:
                    if verbose:
                        ic.configureOutput(prefix="DEBUG| ")
                        ic(f"Error for chunk {part_number}: {e}. Retrying...")
                    time.sleep(1)

        try:
            # Using ThreadPoolExecutor to handle requests concurrently
            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(
                        generate_audio_for_chunk, sentence.strip(), chunk_num
                    ): chunk_num
                    for chunk_num, sentence in enumerate(sentences, start=1)
                }

                # Dictionary to store results with order preserved
                audio_chunks = {}

                for future in as_completed(futures):
                    chunk_num = futures[future]
                    try:
                        part_number, audio_data = future.result()
                        audio_chunks[part_number] = (
                            audio_data  # Store the audio data in correct sequence
                        )
                    except Exception as e:
                        if verbose:
                            ic.configureOutput(prefix="DEBUG| ")
                            ic(f"Failed to generate audio for chunk {chunk_num}: {e}")

            # Combine audio chunks in the correct sequence
            combined_audio = BytesIO()
            for part_number in sorted(audio_chunks.keys()):
                combined_audio.write(audio_chunks[part_number])
                if verbose:
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Added chunk {part_number} to the combined file.")

            # Save the combined audio data to a single file
            with open(filename, "wb") as f:
                f.write(combined_audio.getvalue())
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Final Audio Saved as {filename}")
            return filename.as_posix()

        except CurlError as e:
            if verbose:
                ic.configureOutput(prefix="DEBUG| ")
                ic(f"Failed to perform the operation: {e}")
            raise exceptions.FailedToGenerateResponseError(f"Failed to perform the operation: {e}")

    def create_speech(
        self,
        input_text: str,
        model: Optional[str] = "gpt-4o-mini-tts",
        voice: Optional[str] = "Emma",
        response_format: Optional[str] = "mp3",
        instructions: Optional[str] = None,
        verbose: bool = False,
    ) -> str:
        """
        OpenAI-compatible speech creation interface.
        """
        return self.tts(
            text=input_text,
            model=model,
            voice=voice or "Emma",
            response_format=response_format or "mp3",
            instructions=instructions,
            verbose=verbose,
        )


# Example usage
if __name__ == "__main__":
    streamelements = StreamElements()
    text = "This is a test of the StreamElements text-to-speech API. It supports multiple sentences and advanced logging."

    ic.configureOutput(prefix="DEBUG| ")
    ic("Generating audio...")
    audio_file = streamelements.tts(text, voice="Mathieu")
    ic.configureOutput(prefix="INFO| ")
    ic(f"Audio saved to: {audio_file}")
