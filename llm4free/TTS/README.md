# 🎙️ LLM4Free Text-to-Speech (TTS)

LLM4Free bundles 14 text-to-speech providers behind a shared, OpenAI-style base class. Each provider exposes:

- `tts(text, voice=None, verbose=False, **kwargs)` — generate speech and return the path to a temporary audio file
- `create_speech(input_text, model=None, voice=None, response_format=None, instructions=None, verbose=False)` — validate the parameters and delegate to `tts()`
- `save_audio(audio_file, destination=None, verbose=False)` — copy an audio file (default: current directory with a timestamp)
- `stream_audio(text, model=None, voice=None, response_format=None, instructions=None, chunk_size=1024, verbose=False)` — yield a generated file in byte chunks
- `validate_model()`, `validate_voice()`, `validate_format()` — raise `ValueError` on unsupported values

## 📦 Providers

Everything below is importable from `llm4free.TTS`.

| Provider | Auth | Models | Example voices | Formats |
|---|---|---|---|---|
| `DeepgramTTS` | No | `aura-2` | `thalia`, `odysseus`, `athena`, `orion`, ... | mp3, opus, aac, flac, wav, pcm |
| `ElevenlabsTTS` | Yes – `ELEVENLABS_API_KEY` or `api_key=` | `eleven_multilingual_v2`, `eleven_flash_v2_5`, `eleven_flash_v2`, `eleven_turbo_v2_5`, `eleven_turbo_v2`, `eleven_monolingual_v1` | `brian`, `alice`, `bill`, `charlotte`, `george`, ... | mp3, opus, aac, flac, wav, pcm |
| `KittenTTS` | No | `nano`, `micro`, `mini` | `Bella`, `Jasper`, `Luna`, `Bruno`, ... | wav |
| `LuxTTS` | No | `luxtts` | `default`, `male_1` | wav, mp3 |
| `MurfAITTS` | No | not validated (`SUPPORTED_MODELS = None`) | `Hazel`, `Marcus`, `Samantha`, `Natalie`, ... | mp3, wav |
| `OpenAIFMTTS` | No | `gpt-4o-mini-tts`, `tts-1`, `tts-1-hd` | `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `nova`, `onyx`, `sage`, `shimmer` | mp3, opus, aac, flac, wav, pcm |
| `ParlerTTS` | No | `parler-mini-v1`, `parler-large-v1` | driven by a text `description` | mp3, opus, aac, flac, wav, pcm |
| `PocketTTS` | No | `pocket-tts`, `tts-1.6b` | `alba`, `fantine`, `Unmute - Gertrude`, ... | wav, mp3, aac, opus |
| `QwenTTS` | No | `qwen3-tts` | `cherry`, `serena`, `ethan`, `vivian`, ... | mp3, opus, aac, flac, wav, pcm |
| `SherpaTTS` | No | two voice-cloning models (see `SUPPORTED_MODELS`) | driven by `model_choice` + optional reference audio | mp3, opus, aac, flac, wav, pcm |
| `StreamElements` | No | not validated | 100+ international voices (`Emma`, `Brian`, `Joanna`, `Takumi`, ...) | mp3, opus, aac, flac, wav, pcm |
| `TTSAI` | No | `piper`, `vits`, `melotts`, `kitten-tts`, `kokoro`, `outetts`, `pocket-tts`, `ming-omni-tts` | model-dependent | wav, mp3 |
| `TTSOpenTTS` | No | not validated | `alloy`, `coral`, `cedar`, `marin`, `verse`, ... | mp3, opus, aac, flac, wav, pcm |
| `XLNKTTS` | No | `xlnk-tts` | `alba`, `marius`, `javert`, `jean`, ... | wav |

`required_auth` is `False` for every provider except `ElevenlabsTTS`. `SUPPORTED_VOICES` and `SUPPORTED_FORMATS` are class attributes; `StreamElements.all_voices` is an alias of its `SUPPORTED_VOICES`. `TTSAI.models` is the only `models` property (`SimpleModelList`).

## 🚀 Installation

```bash
pip install -U llm4free
```

## 💻 Quick start

```python
from llm4free.TTS import StreamElements

tts = StreamElements()
audio_file = tts.tts("Hello, this is a test of text-to-speech conversion.", voice="Emma")

saved_path = tts.save_audio(audio_file, destination="my_speech.mp3")
print(sorted(set(StreamElements.SUPPORTED_VOICES))[:10])
```

### ElevenLabs

```python
import os
from llm4free.TTS import ElevenlabsTTS

tts = ElevenlabsTTS(api_key=os.getenv("ELEVENLABS_API_KEY"))
audio_file = tts.tts(
    "Hello from ElevenLabs.",
    voice="brian",
    model="eleven_multilingual_v2",
)
```

ElevenLabs also accepts a plain voice ID (anything not in `SUPPORTED_VOICES` is passed through).

### Listing voices and models

```python
from llm4free.TTS import DeepgramTTS, TTSAI

deepgram = DeepgramTTS()
print(deepgram.SUPPORTED_VOICES)
print(deepgram.SUPPORTED_FORMATS)

ttsai = TTSAI()
print(ttsai.models.list())
```

## 🎛️ OpenAI-style interface

```python
from llm4free.TTS import OpenAIFMTTS

tts = OpenAIFMTTS()

audio_file = tts.create_speech(
    "A short sentence.",
    model="gpt-4o-mini-tts",
    voice="coral",
    response_format="mp3",
)
tts.save_audio(audio_file, destination="output.mp3")

for chunk in tts.stream_audio("Streamed audio.", voice="nova", chunk_size=2048):
    # send chunk to a socket / file / player
    ...
```

> **Defaults caveat.** `create_speech()` / `stream_audio()` fall back to the provider's `default_model`, `default_voice`, and `default_format`. A few providers ship a default that their own validator rejects (`ElevenlabsTTS`, `MurfAITTS`, `StreamElements`, `SherpaTTS`). For those, pass `model=` and/or `voice=` explicitly, or call `tts()` directly, which applies its own fallback.

`save_audio()` accepts either a file path or a directory. It creates missing parent directories and raises `FileNotFoundError` if the source file does not exist.

## 🔧 Provider notes

### ElevenlabsTTS

- Requires `api_key=` or the `ELEVENLABS_API_KEY` environment variable. Without a key no `xi-api-key` header is sent and the API rejects the request.
- `tts()` uses `eleven_multilingual_v2` and voice `brian` by default.

### DeepgramTTS

- Uses the Aura-2 endpoint; voice names are lowercased and mapped to `aura-2-<voice>-en` when not found in `voice_mapping`.

### MurfAITTS

- Voices map to MurfAI IDs (`Hazel` → `en-UK-hazel`, etc.).
- `tts()` defaults to `Hazel`; text longer than 10,000 characters raises `ValueError`.
- Only `mp3` and `wav` are accepted.

### ParlerTTS

- No voice list; pass `description="..."` (and optionally `use_large=True`) to steer the speaker.

### QwenTTS / SherpaTTS

- Gradio-backed. Construct with `proxy="http://..."` (singular `proxy`, not `proxies`).
- `SherpaTTS` ignores `voice`; select `model_choice=` and optionally `reference_audio_url=` / `reference_text=` for voice cloning.

### LuxTTS

- Accepts `reference_audio=<path>` in the constructor for voice cloning.

### PocketTTS

- Local-model-style wrapper around the Kyutai pocket TTS endpoint; `PocketTTS()` is an alias of `KyutaiTTS` with `default_model="pocket-tts"`.

### TTSAI

- Exposes `models.list()` and validates `model` against `SUPPORTED_MODELS`.

### StreamElements

- The largest free voice catalog; `all_voices` aliases `SUPPORTED_VOICES`.
- `tts()` falls back to `Emma` when no voice is supplied.

## 🌐 Proxy support

Most constructors accept `proxies={"http": ..., "https": ...}`:

```python
from llm4free.TTS import OpenAIFMTTS

tts = OpenAIFMTTS(proxies={"https": "http://proxy.example.com:8080"})
```

`ParlerTTS`, `QwenTTS`, and `SherpaTTS` take a single `proxy` string instead. `PocketTTS` accepts `proxies=` and forwards other arguments through `*args, **kwargs`.

## 🛡️ Error handling

```python
from llm4free import exceptions
from llm4free.TTS import ElevenlabsTTS

tts = ElevenlabsTTS()
try:
    tts.tts("Hello", voice="brian")
except exceptions.FailedToGenerateResponseError as exc:
    print(f"TTS generation failed: {exc}")
```

Unsupported models, voices, or formats raise `ValueError` from the `validate_*` helpers. Network and API failures surface as `llm4free.exceptions` types (for example `FailedToGenerateResponseError`).

## ⏱️ Async support

`llm4free.TTS` exports `AsyncBaseTTSProvider`, an abstract async counterpart with `create_speech`, `save_audio`, `stream_audio`, and `tts` coroutines. **There are no concrete async providers in the package yet**; subclass `AsyncBaseTTSProvider` and implement `async def tts(...)` if you need one.

```python
from llm4free.TTS import AsyncBaseTTSProvider

class MyAsyncTTS(AsyncBaseTTSProvider):
    default_model = "gpt-4o-mini-tts"
    default_voice = "coral"
    default_format = "mp3"
    SUPPORTED_MODELS = ["gpt-4o-mini-tts"]
    SUPPORTED_VOICES = ["coral"]
    SUPPORTED_FORMATS = ["mp3"]

    async def tts(self, text, **kwargs):
        raise NotImplementedError
```

## 📄 License

Part of the LLM4Free project — Apache-2.0.
