# Changelog

All notable changes to this project will be documented in this file.

## [2026.9.7] - 2026-09-07

### 🐛 Fixed
- **Toolbaz** — Synced `AVAILABLE_MODELS` with the live Pro app dropdown (`app.toolbaz.com/tools/ai-writing-assistant`). Replaced stale lowercase/guessed identifiers with the actual selectable model names: `Gemini 3.7 Flash`, `Gemini 3.5 Flash`, `Gemini-3-Flash`, `Gemini 3.1 Pro`, `Gemini-2.5-Pro`, `Gemini-2.5-Flash`, `Claude-Sonnet-4`, `GPT-5`, `GPT-4o (latest)`, `GPT-OSS-120B`, `GPT-4o`, `Grok-4-Fast`, `ToolBaz-v4.5-Fast`, `ToolBaz-v4`, `ToolBaz-v3.5-Pro`, `ToolBaz-v3`, `Deepseek-V3.1`, `DeepSeek-V3`, `Deepseek-R1-Distill`, and `Llama-3.3 (70B)`.
- **AI4Chat** — Removed 47 duplicate keys from the `MODELS` mapping that were silently overwriting earlier model name entries.
- **Cloudflare** — Added a `None` guard on `delta.content` in the streaming response path to satisfy type checking.
- **Surfsense** — Fixed `proxies` typing by casting to `Any` before updating the session proxies dict.
- **StableHorde** — Removed unused `LitAgent()` assignment that triggered an unused-variable lint error.

### 🚚 Moved
- **Test imports** — Sorted import blocks in `tests/test_tts_live.py` and `tests/search/test_serpbase.py` to satisfy linting.

## [2026.07.16] - 2026-07-16

### ✨ Added
- **CDP browser client** — New `llm4free.requests.cdp` package providing `CDPSession` (async) and `SyncCDPSession` (sync) that wrap the [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI to drive Chrome for Cloudflare Turnstile solving and cookie/user-agent harvesting. Replaces the raw `websocket-client` CDP approach. Added `llm4free/browser_config.py` for browser/port configuration and a `get_args_from_cdp()` helper returning browser-derived request kwargs for `curl_cffi`.
- **Miklium** — New free chat provider (https://miklium.vercel.app) using `curl_cffi` with `impersonate="chrome"`. Added `llm4free/llm/miklium.py`, exported from `llm4free.llm`.
- **Surfsense** — New free streaming chat provider (https://api.surfsense.com) using `curl_cffi` SSE with `impersonate="safari15_3"`. Added `llm4free/llm/surfsense.py`, exported from `llm4free.llm`.
- **Tests** — Added `tests/providers/test_cdp.py` (mocked CDP/agent-browser wrapper) and `tests/providers/test_miklium_surfsense.py` (mocked `curl_cffi` request/response parsing).

### 🚚 Moved
- **DeepInfraFree, Perchance, Cloudflare** — Browser-backed providers ported from gpt4free PR #3483 (Turnstile-solving for DeepInfra/Perchance and the Cloudflare AI Playground) moved to `llm4free/llm/UNFINISHED/`. They are excluded from the active provider scan so the unified `Client` never auto-launches a browser. Cloudflare's Turnstile does not resolve in headless/sandboxed environments (confirmed against g4f's own upstream CDP client, which fails identically); they remain importable directly from `llm4free.llm.UNFINISHED` for environments where the challenge passes.

## [2026.07.13] - 2026-07-13

### ✨ Added
- **TTSOpenTTS** — New text-to-speech provider reverse-engineered from TTSOpen.ai (https://ttsopen.ai), a free OpenAI.fm alternative. Performs anonymous login, HMAC-SHA256-signed requests (`x-sign` over `x-ts + x-account + body`), task submission, polling, and MP3 download from `cdn.ttsopen.ai`. Supports 13 OpenAI-style voices (Alloy, Echo, Fable, Onyx, Nova, Shimmer, Ash, Ballad, Coral, Sage, Verse, Marin, Cedar) and speed control. Added `llm4free/TTS/ttsopen.py`, exported `TTSOpenTTS` from `llm4free/TTS/__init__.py`, and registered it in `tests/test_tts_live.py`.
- **Lexica** — New text-to-image (TTI) provider for lexica.art, scraping the Next.js RSC image-generation endpoint. Added `llm4free/TTI/lexica.py` and exported `Lexica` from `llm4free/TTI/__init__.py`.
- **`tests/test_tti_live.py`** — Live client test that runs every `llm4free.TTI` provider's `images.create()` against the real API and verifies the returned URL serves an image.

### 🐛 Fixed
- **Brave Videos** — Rewrote result parsing to match current Brave video snippet markup (`div.snippet[data-type="videos"]`, `a.thumbnail` links, `.duration`, `.site-name` source, badge-based views/dates).
- **Yahoo Images** — Updated XPath selectors and post-extraction to the current Yahoo image results markup (`data-origurl`, `tile-title`, `tile-domain`); replaced JSON-title parsing with direct metadata cleanup.
- **Yahoo News** — Updated XPath selectors and field extraction to current Yahoo news article markup.
- **Yahoo Videos** — Updated selectors/extraction for current Yahoo video results.
- **DuckDuckGo Weather** — Hardened formatting with safe `.get()` defaults, a date helper, and non-dict day skipping to avoid crashes on malformed/partial responses.

### 🗑️ Removed
- **`llm4free/Extra/cookie_harvester.py`** — Removed obsolete/unused code.
- **`.txt`** — Removed the large consolidated free-AI-sites list (out of scope).

## [2026.07.09] - 2026-07-09

### ✨ Added
- **SerpBase (Google)** — New search engine providing Google results via the SerpBase REST API. Requires `SERPBASE_API_KEY`; get a free key at https://serpbase.dev. Added `llm4free/search/engines/serpbase.py`, exported `SerpBase` from `llm4free/search/__init__.py`, and registered it in the engine `ENGINES` mapping.
- Added `required_auth: bool = False` to `BaseSearchEngine` (`llm4free/search/base.py`) and set `required_auth = True` on `SerpBase`, aligning search-engine auth metadata with the LLM provider pattern.
- Added search provider registry helpers in `llm4free/search/__init__.py`: `SEARCH_PROVIDERS`, `SEARCH_AUTH_REQUIRED`, and `_get_available_search_engines(api_key)`.
- Added `tests/search/test_serpbase.py` covering metadata, required-auth behavior, registry presence, keyed availability filtering, and error handling.
- Added `tests/test_tts_live.py` — live TTS provider test harness that exercises real endpoints and reports audio-generation status.

### 🚚 Moved
- **SerpBase integration** — Wired into `llm4free/cli.py` and `llm4free/search/engines/__init__.py` as a first-class text search option.

### 🐛 Fixed
- **LuxTTS** — `create_speech()` now works by adding `SUPPORTED_VOICES` and updating `validate_voice()` to accept preset names plus direct audio URLs. Previously the base class rejected LuxTTS's own `"default"` voice.
- **SherpaTTS** — Rewrote against the current `k2-fsa-text-to-speech.hf.space` config: updated supported models to the currently available voice-cloning entries, switched queue calls to `process` / `process_voice_clone`, and hardened SSE result parsing. `create_speech()` now succeeds.
- **TTS.ai** — Fixed endpoints to trailing-slash form, corrected `result_url` extraction from the API response, and updated `create_speech()` so it forwards `model` / `response_format` instead of silently dropping them.
- **KittenTTS** — Added a `create_speech()` override so provider-specific voices like `Jasper` are accepted without the base validator rejecting them.

### 🗑️ Removed
- **FasterQwen3TTS** — Deleted provider. The HuggingFace demo now returns 401 / “Sign in with Hugging Face to use this demo.”, so the endpoint is no longer usable without auth. Removed `llm4free/TTS/faster_qwen3.py`, exports from `llm4free/TTS/__init__.py`, README reference, changelog entries, and test references.

## [2026.07.03] - 2026-07-03

### ✨ Added
- **Supercode** — Added `llm4free/llm/supercode.py`, a new unified LLM gateway. Loads auth from `~/.better-auth/token.json` by default, with explicit `api_key` override. Supports streaming and non-streaming chat, provider-prefixed models (e.g. `concentrateai/deepseek-v4-flash`), and OpenAI-compatible responses. `__init__.py` updated to export `Supercode`.

## [2026.06.19] - 2026-06-19

### ✨ Added
- **FreeAIOnline** — New provider for free-ai-online.com. Reverse-engineered the WordPress AI Engine plugin REST API (`mwai-ui/v1/chats/submit`). Uses SSE streaming with `{"type":"live","data":"token"}` format. Supports conversation history and nonce-based session auth.

### 🚚 Moved
- **UncensoredChat** — Moved from `llm4free/llm/uncensoredchat.py` to `llm4free/llm/Auth/uncensoredchat.py` since it requires authentication (`required_auth = True`). Updated import in `__init__.py`.

### 🗑️ Removed
- **AI365VIP** — Deleted dead provider (`chat.ai365vip.com` behind Cloudflare Turnstile, all API endpoints return 403).
- **OaiBest** — Deleted dead provider (`free.oaibest.com` behind Cloudflare Turnstile, all API endpoints return 403).
- **PerchanceAI** — Deleted dead provider (`perchance.org/api/urv-ai-chat` returns 404, API no longer exists).

### 🐛 Fixed
- **FuckICoding** — Completely rewritten based on reverse engineering of link.fuckicoding.com. Fixed endpoint (`/api/v1/chat` → `/api/v1/gpt/message`), added required `guest-id` and `version: v2` headers, fixed SSE format (`{"c":"content","rc":"reasoning"}` not OpenAI format), corrected payload structure (`chatId`, `plugins`, `systemPrompt`, message `time`/`attachments`), and updated model list to match actual free models from `/api/v1/app/new-info`.
- **UncensoredChat** — Fixed import path in `__init__.py` after move to `Auth/` directory.

## [2026.06.18] - 2026-06-18

### ✨ Added
- **ArtingAI** — Added 3 new models discovered by reverse-engineering site JS: `gemini-3-pro-preview`, `deepseek-chat` (DeepSeek R1), `deepseek-reasoner` (DeepSeek V3). All 9 models verified working.
- **GptFree** — New OpenAI-compatible provider converted from gpt4free (`g4f/Provider/GptFree.py`). Uses Firebase anonymous auth + Cloud Functions streaming endpoint (`gptfree-2.cloudfunctions.net/agent_stream`). Supports message history, multimodal image inputs, and SSE streaming.
- `docs/Prompts/` — New prompt collection directory.

### 🐛 Fixed
- **Apriel** — Rewrote SSE parser for Gradio 5.x SSE v3 differential update protocol. Streaming tokens are now delivered as `["append", [msg_idx, "content"], "text"]` operations; previously only the initial full-message-list format was handled, causing empty responses.
- **FreeAssist** — Removed `decode_unicode=True` from `curl_cffi` `iter_lines()` (raises `NotImplementedError`); deduplicated streaming logic (`_create_non_stream` now consumes `_create_stream` generator); fixed `proxies` type mismatch with `cast(Any, proxies)`.
- **LLMChat** — Changed API endpoint from dead `https://coderelisher.com/ai/fetch` to `https://llmchat.in/inference/stream`; added dual response format parsing (OpenAI-compatible delta vs. `{"response":"..."}` for Deepseek R1); forwarded `temperature`/`top_p` to payload.
- **AI4Chat** — Updated model list from 178 to 277 entries based on `data-name` attributes scraped from `https://www.ai4chat.co/models`. All existing keys preserved, 99 new models appended.
- **Wikipedia** — Fixed default region `"en-us"`→`"us-en"` (was generating `us.wikipedia.org` which fails DNS); `limit=1`→`limit=max_results` (was returning only 1 result regardless of `max_results`).
- **search/`__init__.py`** — Updated docstring from "LLM4Free" to "LLM4Free".

### 🗑️ Removed
- **Elmo** — Deleted dead provider (file removed).
- **Ayle** — Deleted dead provider (file removed).
- **Jadve** — Deleted dead provider (file removed).
- **LLMChatCo** — Deleted dead provider (file removed).
- **Provider.md** — Deleted stale documentation file.
- **docs/compose/plans/2026-06-18-rename-llm4free-to-llm4free.md** — Deleted old plan document.
- **optimizers.py** — Deleted stale module.
- **conversation.py** — Deleted stale module.
- **AIauto.py** — Deleted stale module.
- **Dogpile** — Removed dead search engine (Next.js SPA, results rendered client-side via JS).
- **Yandex** — Removed dead search engine (SmartCaptcha blocks all automated requests).
- **Yep** — Removed dead search engine (`api.yep.com` returns HTTP 501 — server retired API).


## [2026.06.12] - 2026-06-12

### ✨ Added
- **New Providers**:
  - `ArtingAI` — port of arting.ai's public chat (`/api/aigc/comprehensive/chat/create-task`). No auth required; any UUID bearer is accepted. Supports `gpt-5`, `gpt-5.1`, `gpt-5.2`, `gpt-4o-mini`, `o4-mini`, `gemini-2.5-pro`.
  - `AskaiFree` — port of askai.free's chat (`/api/chat/stream`). No auth; per-IP free credits. Schema uses the `modelName` field with display names (`"ChatGPT 4o"`, `"Claude Sonnet 4"`, etc.).
  - `FreeAI` — port of free.ai's public OpenAI-compatible chat (`api.free.ai/v1/chat/`). No auth (any bearer accepted). Model `qwen7b`.
  - `OllamaSwarm` — port of gpt4free's OllamaSwarm: 200+ public Ollama instances, parallel probe, per-day disk cache, TTFT-failover. Both normal and OpenAI-compatible variants.
  - `OperaAria` — port of gpt4free's Opera Aria: anonymous 3-step OAuth, v1 (`aria-legacy`) and v2 (`aria`) endpoints, SSE streaming. Both normal and OpenAI-compatible variants.
- **Test Runner**: `tests/test_all_providers.py` — live provider test with `--only`, `--timeout`, `--prompt`, `--out`, `--include-auth` flags. No mocks; uses real HTTP against real endpoints.

### 🐛 Fixed
- **ExaAI** — dropped `decode_unicode=True` from `iter_lines()` to fix streaming parser.
- **HeckAI** — added `network`, `url`, `files` fields; dropped deprecated `imgUrls`/`superSmartMode`.
- **LLMChat** — moved endpoint to `https://coderelisher.com/ai/fetch?model=...`.
- **Apriel** — rewrote for Gradio 5 SSE v3 protocol.
- **CohereCommand** — rewrote for HuggingChat chat-ui v0.9.4.

### 🚚 Moved to UNFINISHED/
- Ayle, Elmo, Sonus, LLMChatCo, Meta — both normal and OpenAI-comp variants; their upstream endpoints are dead. Source preserved for future revival. Added `UNFINISHED/README.md` documenting why.

## [2026.04.07] - 2026-04-07

### 🔧 Changed
- **Typing Improvements**: Comprehensive type annotation fixes across the codebase:
  - Added `Dict[str, Any]` type annotations to payload dictionaries in OpenAI-compatible providers (TwoAI, Cerebras, DeepInfra, Groq, HuggingFace, NVIDIA, TogetherAI, SambaNova, Upstage)
  - Fixed yield type annotations in `llm4free/Provider/Auth/Upstage.py` for streaming responses
  - Added proper type casts for proxy updates in `llm4free/Extra/proxy_manager.py`
  - Fixed type narrowing for dict responses in `llm4free/Provider/Auth/Deepinfra.py`

### 🐛 Fixed
- **Test Conversions**: Converted mocked tests to real API tests:
  - `tests/providers/test_openai.py` - Real OpenAI API tests
  - `tests/providers/test_groq.py` - Real Groq API tests
  - `tests/providers/test_huggingface.py` - Real HuggingFace API tests
  - `tests/providers/test_gemini.py` - Real Gemini API tests
  - Deleted `tests/providers/test_all_mocked.py` - No longer needed
  - All real API tests use `pytest.mark.skipif` for environment variable checks
- **Type Checker**: Fixed `uvx ty check` errors:
  - Fixed unused `# type: ignore` comments in `llm4free/Bard.py`, `llm4free/Provider/Auth/cerebras.py`, `llm4free/Provider/Auth/Deepinfra.py`
  - Changed `# type: ignore` to `# ty:ignore` for proper ty syntax
  - Fixed payload type annotations to allow float values for `temperature` and `top_p` parameters
- **Provider Fixes**:
  - Fixed trio import comments to use `# ty:ignore[unresolved-import]` syntax
  - Fixed proxy type annotation issues with proper `cast()` usage
- **Test Infrastructure**: Fixed `tests/live_test.py` pytest collection error:
  - Renamed test functions to `run_*` to avoid pytest collecting them as tests
  - The file is a CLI tool, not a pytest test suite

### 🗑️ Removed
- **AvaSupernova Provider**: Removed non-functional provider (API returns 400 errors, service unavailable)
  - Deleted `llm4free/Provider/AvaSupernova.py`
  - Deleted `llm4free/Provider/Openai_comp/avasupernova.py`
  - Deleted `tests/providers/test_avasupernova.py`
  - Removed from `llm4free/Provider/__init__.py` exports
  - Removed from `llm4free/Provider/Openai_comp/__init__.py` exports

### 📦 Dependencies
- **pyproject.toml**: Added missing dependencies:
  - `typing_extensions>=4.0.0`
  - `httpx`
  - `tqdm`
  - `packaging`
  - `pytest-cov` (dev dependency with coverage configuration)

## [2026.04.03] - 2026-04-03

### 🔧 Changed
- **Release Workflow**: Updated `publish-to-pypi.yml` for daily stable releases:
  - Changed from beta (daily) + stable (Monday) to **daily stable releases**
  - Schedule now runs every day at 00:00 UTC instead of just Mondays for stable
  - Default release type changed from "beta" to "stable"
  - Version format is now date-based (YYYY.MM.DD) without beta suffix
  - Manual workflow dispatch now defaults to "stable" release type

### 🐛 Fixed
- **API Server**: Fixed provider initialization error in `llm4free/server/providers.py`:
  - Resolved `KeyError: 'llm4free.Provider.Openai_comp'` on server startup
  - Fixed module import order to ensure proper registration in `sys.modules`
  - Applied same fix to TTI and TTS provider maps
- **Provider discovery flow**: removed implicit server provider fallbacks
  - removed ChatGPT provider fallback from `initialize_provider_map()`
  - removed PollinationsAI fallback from `initialize_tti_provider_map()`
  - no fallback for missing TTS providers
  - added strict `required_auth=False` filter for TTI and TTS providers
- **API Server**: Added missing TTS model/provider GET routes in `llm4free/server/routes.py`:
  - Added `GET /v1/TTS/models` to list available TTS models
  - Added `GET /v1/TTS/providers` to list available TTS providers
  - Now mirrors TTI route pattern for consistency

## [2026.04.01] - 2026-04-01

### ✨ Added
- **OpenResearcher Provider**: Added new OpenResearcher provider for AI-powered research search:
  - `llm4free/Provider/AISEARCH/openresearcher.py` - AISearch-compatible interface for OpenResearcher
  - Multi-round iterative research (search → open page → find → answer)
  - Real-time streaming via Server-Sent Events
  - Configurable max research rounds (default: 50)
  - Built-in Serper API key (or custom key support)
  - HTML-formatted results with citations and thought process
  - Gradio API two-step flow (POST for event_id → GET SSE stream for result)
  - No authentication required (public Hugging Face Space)
  - Updated `llm4free/Provider/AISEARCH/__init__.py` to export OpenResearcher
  - Updated Provider.md documentation
  - Full test coverage in `tests/providers/test_openresearcher.py`

- **XLNK TTS Provider**: Added new XLNK TTS provider for text-to-speech synthesis:
  - `llm4free/Provider/TTS/xlnk.py` - OpenAI TTS API-compatible interface for XLNK TTS
  - 8 Kyutai voice presets: alba, marius, javert, jean, fantine, cosette, eponine, azelma
  - Voice cloning support via uploaded audio
  - Adjustable generation parameters: temperature, LSD decode steps, noise clamp, EOS threshold
  - Gradio API two-step flow (POST for event_id → GET SSE stream for result)
  - No authentication required (public Hugging Face Space)
  - Updated `llm4free/Provider/TTS/__init__.py` to export XLNKTTS
  - Updated Provider.md documentation
  - Full test coverage in `tests/providers/test_xlnk.py`

- **KittenTTS Provider**: Added new KittenTTS provider for text-to-speech synthesis:
  - `llm4free/Provider/TTS/kittentts.py` - OpenAI TTS API-compatible interface for KittenTTS
  - 3 model sizes: Nano (15M), Micro (40M), Mini (80M)
  - 8 voice presets: Bella, Jasper, Luna, Bruno, Rosie, Hugo, Kiki, Leo
  - Adjustable speech speed (0.5x to 2.0x)
  - Gradio API two-step flow (POST for event_id → GET SSE stream for result)
  - No authentication required (public Hugging Face Space)
  - Updated `llm4free/Provider/TTS/__init__.py` to export KittenTTS
  - Updated Provider.md documentation
  - Full test coverage in `tests/providers/test_kittentts.py`

- **LuxTTS Provider**: Added new LuxTTS voice cloning provider for text-to-speech synthesis:
  - `llm4free/Provider/TTS/luxtts.py` - OpenAI TTS API-compatible interface for LuxTTS voice cloning
  - Voice cloning from reference audio (preset voices or custom URLs)
  - Adjustable speech parameters: speed, loudness (RMS), reference duration, T-shift, steps
  - Gradio API two-step flow (POST for event_id → GET SSE stream for result)
  - No authentication required (public Hugging Face Space)
  - Updated `llm4free/Provider/TTS/__init__.py` to export LuxTTS
  - Updated Provider.md documentation
  - Full test coverage in `tests/providers/test_luxtts.py`

## [2026.03.31] - 2026-03-31

### ✨ Added
- **Server TTS endpoint**: Added OpenAI-compatible `/v1/audio/speech` endpoint to the FastAPI server:
  - `llm4free/server/request_models.py` - Added `SpeechGenerationRequest` model with OpenAI-compatible fields
  - `llm4free/server/providers.py` - Added TTS provider discovery, caching, and resolution functions
  - `llm4free/server/routes.py` - Added `_register_tts_routes()` with POST `/v1/audio/speech` endpoint
  - `llm4free/server/server.py` - Added TTS provider initialization on server startup
  - `llm4free/server/config.py` - Added `tts_provider_map` and `default_tts_provider` configuration
  - Supports multiple audio formats: mp3, opus, aac, flac, wav, pcm
  - Supports both file download and streaming responses
  - Automatic TTS provider discovery and model resolution
- **Client audio speech interface**: Added `client.audio.speech.create(...)` in `llm4free/client.py` for TTS-backed speech generation with provider discovery, caching, failover, and `last_provider` tracking.
- **Client docs refresh**: Rewrote `docs/client.md` into a shorter guide that still covers chat, image, and audio usage plus the updated helper methods.
- **Cohere STT Provider**: Added new Cohere Multilingual ASR provider for speech-to-text transcription:
  - `llm4free/Provider/STT/cohere.py` - OpenAI Whisper API-compatible interface for Cohere's multilingual ASR
  - Supports 14 languages: English, French, German, Spanish, Portuguese, Italian, Dutch, Polish, Greek, Arabic, Japanese, Korean, Chinese, Vietnamese
  - Implements Gradio API two-step flow (POST for event_id → GET SSE stream for result)
  - Supports both streaming and non-streaming transcription modes
  - Handles audio file uploads via multipart/form-data
  - No authentication required (public Hugging Face Space)
  - Updated `llm4free/Provider/STT/__init__.py` to export CohereSTT
  - Updated Provider.md documentation

### 🔧 Fixed
- **Client type checking**: Fixed `Attribute content may be missing` type errors in `llm4free/client.py`:
  - Added `TypeGuard` import and updated `_is_valid_chat_completion` to use proper type narrowing
  - Fixed `ChatCompletionChunk` cast issues for streaming responses
  - All type checks now pass with `uvx ty check`
- **ParlerTTS, QwenTTS, SherpaTTS**: Fixed `startswith` bytes vs string bug in SSE stream parsing:
  - Added `isinstance(line, bytes)` check before calling `startswith()`
  - Properly decode bytes to UTF-8 string before string operations
  - Fixed `FailedToGenerateResponseError: startswith first arg must be bytes or a tuple of bytes, not str`
  - All three providers now successfully generate audio files
- **FreeTTS**: Fixed audio download to follow HTTP redirects:
  - Added `allow_redirects=True` to the audio download request
  - The FreeTTS API returns redirect URLs for audio files that were not being followed
  - Provider now successfully downloads and saves audio files
- **PocketTTS**: Fixed test configuration to use valid voice name (`alba` instead of invalid voice)
- **TTS Provider Tests**: Added comprehensive test suite for all TTS providers:
  - `tests/providers/test_all_tts_providers.py` - Instantiation and attribute tests
  - `tests/providers/test_tts_audio_generation.py` - Actual audio generation tests
  - Results improved from 4/12 to 8/12 working providers (67%)

### 🗑️ Removed
- **SpeechMaTTS**: Removed non-functional provider (HTTP 403 errors, service no longer accessible)
  - Deleted `llm4free/Provider/TTS/speechma.py`
  - Removed from `llm4free/Provider/TTS/__init__.py` exports
  - Updated Provider.md documentation

## [2026.02.23] - 2026-02-23

### ✨ Added
- **Blackbox Provider**: Added new Blackbox AI provider in both standard and OpenAI-compatible formats:
  - `llm4free/Provider/blackbox.py` - Standard provider implementation with conversation support, streaming/non-streaming responses, and LitAgent fingerprinting
  - `llm4free/Provider/Openai_comp/blackbox.py` - OpenAI-compatible provider following the same pattern as Groq, Cerebras, and other OpenAI-compatible providers
  - Supports models: `moonshotai/kimi-k2.5`, `custom/blackbox-base-2`, `minimax-m2`
  - Uses Blackbox VSCode extension API endpoint with required headers (customerId, userId, version)
  - Both providers support streaming responses with proper SSE parsing

### 🔧 Improved
- **lmarena.py (UNFINISHED)**: Fixed all ruff linting errors and improved type safety:
  - Fixed 317+ ruff linting issues automatically (trailing whitespace, blank lines, f-string prefixes, etc.)
  - Fixed duplicate dictionary keys in `_ARENA_HOST_TO_ORIGIN`
  - Fixed bare `except` clause to `except Exception`
  - Added pyright type suppression comments for external library type stub issues
  - Added UNFINISHED directory to ty check exclusions in pyproject.toml
  - All ruff checks now pass successfully

## [2026.02.14] - 2026-02-14

### 🐛 Fixed
- **TypliAI Provider**: Fixed 403 errors by implementing CSRF token handling in the TypliAI provider. The provider now initializes the session properly to retrieve and use CSRF tokens, resolving authentication issues that were causing 403 errors.
- **OpenAI-Compatible TypliAI Provider**: Fixed 403 errors in the OpenAI-compatible TypliAI provider by implementing the same CSRF token handling logic as the main TypliAI provider. This ensures both providers can authenticate successfully and avoid 403 errors when making requests to the TypliAI service.
- **Toolbaz Provider**: Fixed 400 errors in the Toolbaz provider 
- **Server**: Fixed critical startup failure in `llm4free/server/server.py` when running with default settings (debug=False, workers=1) due to missing `else` clause in `run_api()` function's uvicorn configuration logic. The server now starts correctly in production mode.

### ✨ Added
- **TypliAI Reasoning Support**: Added support for reasoning models (e.g., `moonshotai/kimi-k2.5`) in both TypliAI providers:
  - Updated to use new `/api/chat2` endpoint
  - Added support for `reasoning-delta` and `text-delta` SSE event types
  - Exposed `reasoning_content` and `reasoning` fields in OpenAI-compatible response
  - Updated headers to match new API requirements (referer changed to `/ai-chat`)
- **Reasoning Fields in OpenAI Responses**: Added `reasoning_content` and `reasoning` fields to `ChoiceDelta` and `ChatCompletionMessage` classes in `llm4free/Provider/Openai_comp/utils.py` for OpenAI-compatible provider responses

### 🔧 Improved
- **OpenAI-Compatible TypliAI Provider**: Replaced `sanitize_stream` with manual SSE parsing for better control over streaming responses. Now parses both `reasoning-delta` and `text-delta` events directly without relying on the utility function.

## [2026.02.13] - 2026-02-13

### 🔧 Improved
- **curl_cffi Migration**: Complete migration from `requests` to `curl_cffi` library across all providers:
  - Updated all Provider files (`llm4free/Provider/`) to use `curl_cffi` for HTTP operations
  - Updated search engine files (`llm4free/search/`) to use curl_cffi
  - Updated core modules (`llm4free/scout/core/`) and Extra modules
  - Replaced `requests.Session()` with `curl_cffi.requests.Session()`
  - Updated exception handling from `requests.exceptions` to `curl_cffi.CurlError`
  - All ruff linting and ty type checks pass after migration
  - curl_cffi provides better browser impersonation, streaming support, and performance

### 🔧 Improved
- **Falcon provider**: `llm4free/Provider/Falcon.py` - Major refactor to align with QwenLM pattern:
  - Implemented cookie-from-file logic using `cookies_path` and `_load_cookies()`.
  - Updated to use `curl_cffi.Session` with chrome impersonation for better anti-detection.
  - Refactored `ask()` and `chat()` methods for consistent streaming and non-streaming behavior.
  - Added support for dynamic model selection and improved error handling.
  - Verified with `ruff` and `ty` for code quality and type safety.

## [2026.02.10] - 2026-02-10

### ✨ Added
- **K2Think Provider**: `llm4free/Provider/k2think.py` - New provider for K2 Think AI (https://www.k2think.ai/guest). Features no-auth guest access, streaming/non-streaming support using `sanitize_stream`, conversation history, optimizer support, and OpenAI-compatible API responses. Fully integrated with LLM4Free's provider discovery system.
- **K2Think OpenAI-Compatible Provider**: `llm4free/Provider/Openai_comp/k2think.py` - OpenAI-compatible implementation of K2Think provider following the same pattern as DeepInfra, Groq, and Sonus providers. Features direct JSON parsing without `sanitize_stream`, proper OpenAI-compatible streaming chunks, and full compatibility with OpenAI API interface.

### 🚮 Removed
 - **X0GPT provider**: Removed the X0GPT provider from the codebase.

### 🚮 Removed
- **ChatSandbox provider**: Completely removed `llm4free/Provider/ChatSandbox.py` and `llm4free/Provider/Openai_comp/chatsandbox.py`. The provider has been deprecated and removed from the codebase.

## [2026.02.01] - 2026-02-01

### 🚮 Removed
- **Algion provider**: Completely removed `llm4free/Provider/Algion.py` and `llm4free/Provider/Openai_comp/algion.py`. The provider has been deprecated and removed from the codebase.

## [2026.02.02] - 2026-02-02

### 🔧 Improved
 - **AkashGPT provider**: `llm4free/Provider/Openai_comp/akashgpt.py` & `llm4free\Provider\akashgpt.py`- Refactored to remove all `api_key` logic. The provider no longer requires or uses an API key for any operation. The constructor and all internal logic have been updated to reflect this, making AkashGPT fully no-auth and easier to use out of the box.

### 🔧 Improved
- **AkashGPT provider**: `llm4free/Provider/Openai_comp/akashgpt.py` & `llm4free\Provider\akashgpt.py`- Refactored to remove all `api_key` logic. The provider no longer requires or uses an API key for any operation. The constructor and all internal logic have been updated to reflect this, making AkashGPT fully no-auth and easier to use out of the box.
- Cleaned up docstrings and type hints for clarity and consistency.
- All ruff linting and ty type checks pass after the update.
  
## [2026.01.31] - 2026-01-31

### 🏷️ Renamed
- **OPENAI → Openai_comp**: Renamed `llm4free/Provider/OPENAI` directory to `llm4free/Provider/Openai_comp` for clarity and naming consistency.

### 🚮 Removed / Moved
- **BraveAI provider moved**: `llm4free/Provider/AISEARCH/brave_search.py` → `llm4free/Provider/UNFINISHED/brave_search.py`. The Brave Search AI Chat API currently returns 404 errors; further investigation needed.
- **BraveAI export removed**: `llm4free/Provider/AISEARCH/__init__.py` - BraveAI removed from active AISEARCH providers.
- **Legacy wrapper removed**: `lol.py` - Legacy compatibility wrapper removed; canonical implementation is now in `llm4free/Provider/AISEARCH/ayesoul_search.py`.

### ✨ Added
- **AyeSoul AI Search Provider**: `llm4free/Provider/AISEARCH/ayesoul_search.py` - New provider using AyeSoul's WebSocket endpoint. Supports streaming/non-streaming, image uploads, and LitAgent-based user-agent generation.
- **OpenAI-compatible Upstage Provider**: `llm4free/Provider/Openai_comp/upstage.py` - New OpenAI-compatible provider for Upstage AI with dynamic model fetching from `https://api.upstage.ai/v1/models` endpoint. Supports streaming and non-streaming modes with LitAgent browser fingerprinting.
- **Model Fetcher Infrastructure**: `llm4free/model_fetcher.py` - Non-blocking model fetching with caching:
  - Thread-safe `ModelFetcherCache` with file-based cache (`~/.llm4free/model_cache.json`)
  - TTL support (default 24h, configurable via `LLM4FREE_MODEL_CACHE_TTL`)
  - Disable cache with `LLM4FREE_NO_MODEL_CACHE`
  - `BackgroundModelFetcher` for async fetching (daemon threads)
  - Graceful timeout (default 10s) and error fallback
  - Thread-safe via `threading.Lock`
- **proxy_manager.py**: `llm4free/Extra/proxy_manager.py` - New ProxyManager utility for managing and rotating proxies with auto-fetching from public proxy lists. Supports HTTP/SOCKS proxies, health checks, and integration with LLM4Free providers.
### 🔧 Improved
- **AyeSoul stream handling**: `llm4free/Provider/AISEARCH/ayesoul_search.py` - Prefer `stream` key for response text; robust handling of dict/list payloads; serializes structured content to JSON as needed.
- **AyeSoul export**: `llm4free/Provider/AISEARCH/__init__.py` - Exported `AyeSoul` for unified import/discovery.
- **All AI providers**: Optimized model fetching to be non-blocking and parallel:
  - 14 OpenAI-compatible providers now use background model fetching:
    - `llm4free/Provider/Openai_comp/deepinfra.py`
    - `llm4free/Provider/Openai_comp/DeepAI.py`
    - `llm4free/Provider/Openai_comp/groq.py`
    - `llm4free/Provider/Openai_comp/openrouter.py`
    - `llm4free/Provider/Openai_comp/cerebras.py`
    - `llm4free/Provider/Openai_comp/textpollinations.py`
    - `llm4free/Provider/Openai_comp/TogetherAI.py`
    - `llm4free/Provider/Openai_comp/nvidia.py`
    - `llm4free/Provider/Openai_comp/huggingface.py`
    - `llm4free/Provider/Openai_comp/algion.py`
    - `llm4free/Provider/Openai_comp/upstage.py`
    - `llm4free/Provider/Openai_comp/typliai.py`
    - `llm4free/Provider/Openai_comp/easemate.py`
    - `llm4free/Provider/Openai_comp/freeassist.py`
  - 11 Standalone providers updated for direct background fetch:
    - `llm4free/Provider/Deepinfra.py`
    - `llm4free/Provider/HuggingFace.py`
    - `llm4free/Provider/TogetherAI.py`
    - `llm4free/Provider/TextPollinationsAI.py`
    - `llm4free/Provider/Sambanova.py`
    - `llm4free/Provider/OpenRouter.py`
    - `llm4free/Provider/Openai.py`
    - `llm4free/Provider/Nvidia.py`
    - `llm4free/Provider/Groq.py`
    - `llm4free/Provider/geminiapi.py`
    - `llm4free/Provider/cerebras.py`
    - `llm4free/Provider/Algion.py`
  - Added `_start_background_model_fetch()` to OpenAICompatibleProvider base class
  - Providers now initialize instantly with fallback models, fetching fresh models in background
  - Startup performance improved (2-5s faster)
  - Cache persists across restarts
  - All changes backward compatible

### 🔧 Fixed
- **Type checking compliance**: Fixed 33 type errors across provider implementations to pass strict type checking (`uvx ty check .`):
  - Added proper type guards for `Response` type access in `get_message()` methods across all providers
  - Implemented `cast(Dict[str, Any], response)` pattern after `isinstance(response, dict)` checks to satisfy type checker
  - Fixed dictionary subscript errors in 17 provider files:
    - llm4free/Provider/AISEARCH/ayesoul_search.py
    - llm4free/Provider/Cohere.py, ExaAI.py, Gemini.py, HeckAI.py
    - llm4free/Provider/IBM.py, Netwrck.py, Sambanova.py, TextPollinationsAI.py
    - llm4free/Provider/ai4chat.py, cleeai.py, julius.py, llama3mitril.py, meta.py
    - llm4free/Provider/Openai_comp/ibm.py, llmchat.py
  - Fixed null safety issues in streaming response handling (ibm.py, llmchat.py)
  - All providers now pass both `uvx ty check .` and `uv run ruff check .`

### 🚮 Removed
- **Deprecated providers**: Removed `oivscode.py` and `K2Think.py` from both `llm4free/Provider/` and `llm4free/Provider/Openai_comp/` to streamline the codebase.

### ✅ Quality & Testing
- Manual smoke tests on AyeSoul streaming and non-streaming flows
- Please add unit tests under `tests/providers/` to mock WebSocket responses for CI
- All ruff linting checks passed on modified files
- All type checking with `ty` passed
- Comprehensive test suite in `tests/providers/test_model_fetching.py` (898 lines):
  - Cache behavior (hit/miss/TTL/env var)
  - Background fetch non-blocking
  - Timeout/error handling
  - Concurrent provider init
  - Thread safety
  - Cache corruption recovery

---

## [2026.01.22] - 2026-01-22

### 🔧 Improved
- **provider**: llm4free/Provider/Deepinfra.py & llm4free/Provider/OPENAI/deepinfra.py - Enhanced model filtering:
  - Updated `get_models()` to only fetch and return model IDs that have complete metadata with both `context_length` and `max_tokens` fields
  - Ensures only production-ready, well-documented models are available in the model list
  - Both native and OpenAI-compatible providers now implement consistent filtering logic
  - Fallback to `AVAILABLE_MODELS` list when API fetch fails or no complete models are found

### 🐛 Fixed
- **fix**: llm4free/server/server.py - Fixed critical llm4free-server startup failure when running in production mode (debug=False, workers=1). The issue was a missing `else` clause in the `run_api()` function's uvicorn configuration logic, causing the server to never start when using default settings.

### ✅ Quality
- All ruff linting checks passed successfully on modified files
- All type checking with `ty` passed successfully

## [2026.01.19] - 2026-01-19

### 🔧 Improved
- **provider**: llm4free/Provider/Ayle.py - Reverse engineered ayle.chat to update available models and configs:
  - Added support for 11 verified working models including Gemini 2.5 Flash, Grok-based models, and Sonar.
  - Implemented a test suite to verify 31 discovered models, removing 20 non-functional ones.
  - Verified no authentication is required and streaming is fully supported.
  - Updated `AVAILABLE_MODELS` and `MODEL_CONFIGS` with the optimized list.

## [2026.01.17] - 2026-01-17

### 🔧 Improved
- **refactor**: llm4free/Provider/AISEARCH/iask_search.py - Streamlined IAsk AI search provider:
  - Removed Phoenix WebSocket complexity and unused `cache_find()` helper function
  - Simplified API flow to single GET request to `/q` endpoint with mode and detail_level parameters
  - Added `_extract_answer()` method to parse HTML response and extract answer from `div#id="text"`
  - Added `_iter_chunks()` method for improved chunked streaming (800-char chunks with word boundaries)
  - Removed unnecessary `aiohttp` WebSocket dependency, simplified async implementation
  - Updated endpoints: `api_endpoint` to `https://iask.ai`, new `query_endpoint` to `https://iask.ai/q`
  - **Integrated LitAgent** for realistic User-Agent header generation (replaced hardcoded static user agent)
  - Both streaming and non-streaming modes now use consistent `fetch_answer()` async flow
  - Performance: Reduced request overhead and latency by eliminating WebSocket handshake

### 🐛 Fixed

### � Fixed
- **fix**: llm4free/Provider/OPENAI/sonus.py - Fixed critical non-stream request error "stream mode is not enabled":
  - Root cause: SonusAI API returns a streaming response even for non-stream requests
  - Solution: Added `stream=True` parameter to the `session.post()` call in `_create_non_stream()` method
  - Impact: Non-streaming chat completions now work correctly with the OpenAI-compatible SonusAI provider

### 📝 Documentation
- **docs**: llm4free/client.py - Generated comprehensive PEP 257-compliant docstrings for all 32+ classes and methods:
  - Added detailed module-level docstrings for `load_openai_providers()`, `load_tti_providers()`, and `_get_models_safely()`
  - Documented `ClientCompletions` class with intelligent provider/model resolution algorithms
  - Documented `ClientChat` adapter interface for chat completions
  - Documented `ClientImages` class with automatic failover for image generation
  - Documented main `Client` class with comprehensive usage examples
  - All docstrings include parameter descriptions, return types, exception documentation, usage examples, and important behavioral notes
  - Improved IDE autocomplete and automated documentation generation support

### 🔧 Improved
- **refactor**: llm4free/Provider/akashgpt.py - Replaced `cloudscraper` with `curl_cffi` for better performance and TLS/SSL handling. Changed from `cloudscraper.create_scraper()` to `curl_cffi.requests.Session()` for HTTP requests.
- **refactor**: llm4free/Provider/OPENAI/akashgpt.py - Replaced `cloudscraper` with `curl_cffi` for improved HTTP request handling. Updated session initialization to use `curl_cffi.requests.Session()` with proper proxy support in the `__init__` method.

### ✅ Quality
- All ruff linting checks passed successfully on all modified files
- All type checking with `ty` passed successfully

## [2026.01.16] - 2026-01-16

### ✨ Added
- **feat**: llm4free/search/engines/brave/videos.py - New Brave video search engine that parses HTML to extract video results from YouTube and other platforms. Includes support for duration, view count, channel/uploader, published date, and pagination.
- **feat**: llm4free/search/engines/brave/news.py - New Brave news search engine that parses HTML to extract news articles with title, source, date, body, and thumbnail images. Includes pagination support.
- **feat**: llm4free/search/engines/brave/suggestions.py - New Brave search suggestions/autocomplete API that returns rich entity suggestions with metadata (name, description, category, image).
- **feat**: llm4free/search/engines/brave/images.py - New Brave image search engine using JavaScript-based crawling to extract image results with title, URL, dimensions, and source.

### 🔧 Improved
- **refactor**: llm4free/search/brave_main.py - Implemented images(), news(), videos(), and suggestions() methods in BraveSearch unified interface to support all new Brave search types.
- **refactor**: llm4free/search/engines/__init__.py - Updated ENGINES dictionary and __all__ exports to register BraveVideos, BraveNews, and BraveSuggestions in their respective categories.
- **refactor**: llm4free/cli.py - Added specialized print functions for improved CLI UI:
  - `_print_videos()` - Panel-based video results with duration, view count, channel, and date
  - `_print_news()` - Clean news article display with source, date, and body preview
  - `_print_suggestions()` - Table-based suggestions with entity type indicators
  - `_print_images()` - Image result display with resolution and source info
  - Updated video, news, suggestions, and images commands to use new specialized print functions
  - Added helper functions `_format_views()` and `_truncate()` for better formatting
- **refactor**: llm4free/server/routes.py - Updated web search endpoint documentation to mention Brave support for videos and suggestions. Improved suggestions parameter handling with better fallback logic.
- **refactor**: llm4free/search/brave_main.py - Implemented images() method for Brave image search (previously raised NotImplementedError).

### 📝 Documentation
- **docs**: Updated CLI help text to reflect Brave support for videos, news, images, and suggestions searches.

### ✨ Added
- **feat**: llm4free/Provider/AISEARCH/BraveAI.py - New BraveAI search provider supporting AI search and deep research (streaming and non-streaming modes). Updated `llm4free/Provider/AISEARCH/__init__.py` to export the provider and added documentation to `llm4free/Provider/AISEARCH/README.md`.

## [2026.01.06] - 2026-01-06

### 🚮 Removed
- **remove**: Completely removed `llm4free/Provider/AISEARCH/genspark_search.py` provider and all references to Genspark from the codebase
- **remove**: Updated `llm4free/Provider/AISEARCH/__init__.py` to remove Genspark import and export
- **remove**: Updated documentation in `llm4free/Provider/AISEARCH/README.md` and `Provider.md` to reflect removal of Genspark provider

### 🔧 Maintenance
- **refactor**: llm4free/Provider/AISEARCH/monica_search.py - Simplified streaming content extraction by switching to an inline lambda for `sanitize_stream`'s `content_extractor` that returns `chunk["text"]` when present. Removed the now-unused `_extract_monica_content` method. Note: this change intentionally stops persisting `session_id` from stream payloads; reintroduce session handling if session persistence is required.
- **fix**: llm4free/Provider/AISEARCH/webpilotai_search.py - Use `sanitize_stream`'s `content_extractor` for both streaming and non-streaming flows to parse JSON payloads and return the nested `content` (fallbacks to `text` and `data.delta.content` where present). This aligns behavior with `monica_search` and prevents empty or incomplete output when the service emits nested or delta-based content. Raw mode still returns unprocessed chunks.
- **fix**: llm4free/Provider/AISEARCH/PERPLEXED_search.py - Fixed critical streaming issues and standardized with other providers:
  - Replaced manual JSON parsing with `sanitize_stream` using `line_delimiter="[/PERPLEXED-SEPARATOR]"` parameter
  - Fixed streaming generator that was not yielding chunks due to incorrect delimiter handling
  - Updated both streaming and non-streaming modes to use consistent `sanitize_stream` configuration
  - Improved content extraction logic to properly handle answer fields from JSON responses
  - Fixed `if __name__ == "__main__"` block to properly consume and display streaming responses
  - Now follows same pattern as webpilotai, miromind, and monica providers for consistency

## [2026.01.01] - 2026-01-01

### 🚮 Removed
- **remove**: Completely removed `google-generativeai` package dependency from pyproject.toml - package was not actually used in the codebase (geminiapi.py uses curl_cffi directly), removing it fixes Python 3.14 compatibility issues with pydantic-core
- **remove**: Completely removed `openai` package dependency from pyproject.toml - project now uses `curl_cffi` exclusively for HTTP requests, reducing dependencies and improving consistency
- **remove**: Completely removed `orjson` dependency from codebase (including imports, `HAS_ORJSON` flag, and pyproject.toml entry) for better compatibility and simpler dependencies
- **remove**: Completely removed `llm4free/Provider/VercelAI.py` provider file and updated related imports and documentation
- **remove**: Removed `llm4free/Provider/VercelAI.py` provider file and updated related imports and documentation
- **remove**: Completely removed `nodriver` package dependency from pyproject.toml - nodriver was not actively used in the codebase, only listed as a dependency
- **remove**: Replaced aiofiles usage with Python's built-in asyncio.to_thread for async file operations in TTS streaming, removing aiofiles dependency from pyproject.toml
- **remove**: Replaced cloudscraper usage with curl_cffi Session in LLMChat and LLMChatCo providers, removing cloudscraper dependency from pyproject.toml

### 🔧 Improved
- **refactor**: Made `lxml` dependency optional in pyproject.toml
  - Moved `lxml` to optional `parser` dependency group in pyproject.toml
  - Updated `llm4free/search/base.py` to support lxml for HTML parsing
  - Updated `llm4free/search/engines/duckduckgo/base.py` to use lxml for HTML parsing
- **refactor**: Migrated from `requests` to `curl_cffi` for HTTP requests in multiple files to improve browser fingerprinting and anti-detection capabilities
- **refactor**: Migrated `llm4free/Provider/AISEARCH/iask_search.py` from `aiohttp` to `curl_cffi` for HTTP requests, while retaining `aiohttp` for WebSocket connections to improve browser fingerprinting and anti-detection capabilities

### 🐛 Fixed
- **fix**: Fixed ModuleNotFoundError for huggingface_hub in llm4free versions > 2025.12.19 by implementing lazy imports in gguf.py
  - Replaced unconditional `from huggingface_hub import HfApi` with lazy import pattern
  - Added `_ensure_huggingface_hub()` function that imports HfApi only when GGUF features are used
  - Updated all HfApi usage in ModelConverter class to use lazy imports
  - This fixes import issues for users who only need chat/LLM provider features without GGUF conversion
  - Provides clear error message when GGUF features are used without huggingface_hub installed

### ✨ Added
- **remove**: Removed HadadXYZ providers: `llm4free/Provider/HadadXYZ.py` and `llm4free/Provider/OPENAI/hadadxyz.py`. These implementations are deprecated and removed to streamline provider maintenance.

- **feat**: llm4free/Provider/QwenLM.py - Added new models to this provider

- **feat**: Added `gpt-5.2` model to Toolbaz providers in both `llm4free/Provider/toolbaz.py` and `llm4free/Provider/OPENAI/toolbaz.py`

- **refactor**: Migrated `llm4free/Provider/OPENAI/toolbaz.py` from `cloudscraper` to `curl_cffi` for consistent HTTP client implementation across providers

- **refactor**: Migrated `llm4free/Provider/OPENAI/sonus.py` from `requests` to `curl_cffi` for improved browser emulation and consistency; updated form data handling from multipart `files` to standard `data` parameter

- **feat**: Added new OpenRouter provider in both `llm4free/Provider/OpenRouter.py` and `llm4free/Provider/OPENAI/openrouter.py` with dynamic model fetching and LitAgent browser fingerprinting

## [2025.12.21] - 2025-12-21

### 🐛 Fixed
- **fix**: Conducted an extensive codebase cleanup using Ruff, resolving over 200 linting issues and potential bugs.
- **fix**: Standardized error handling by replacing bare `except:` blocks with `except Exception:` or specific exception types across multiple modules (Bing search, GGUF converter, SwiftCLI, and various AI providers).
- **fix**: Resolved numerous `F821 Undefined name` and `F405` errors:
    - Restored missing `get_item` method in `YTdownloader.py`.
    - Defined missing variables (`result`, `content`, `tool_calls`) in `TextPollinationsAI.py` response processing.
    - Fixed missing `ic` imports from `litprinter` in multiple TTS providers (`MurfAI`, `OpenAI.fm`, `Parler`, `Qwen`, `Sherpa`, `FreeTTS`).
    - Fixed missing `exceptions` import in `FreeTTS`.
    - Resolved undefined `CLI` reference in SwiftCLI `Context` using `TYPE_CHECKING` and explicit imports.
    - Added missing type hint imports (`Optional`, `Any`, `Union`, `Generator`, `Response`) across 30+ AI provider modules including Cohere, Gemini, Groq, HuggingFace, and more.
    - Fixed undefined `LitAgent` reference in `GitToolkit/utils.py` and missing `Union` in `YTdownloader.py`.
    - Resolved `Response` naming conflict in `Ayle.py` by aliasing `curl_cffi` response.
- **fix**: Corrected syntax errors and corrupted logic blocks in `YTdownloader.py` and `iask_search.py`.
- **fix**: Improved project adherence to PEP 8:
    - Moved module-level imports to the top of files in `server` and `aihumanizer`.
    - Replaced incorrect type comparisons (e.g., `== bool`) with idiomatic `is bool`.
    - Split multiple statements on single lines (E701, E702) across the entire project for better readability.
- **refactor**: Replaced star imports (`from ... import *`) with explicit imports in `GitToolkit` and `samurai` provider to eliminate name shadowing and improve static analysis.
- **refactor**: Added dynamic model fetching to both DeepInfra providers (`llm4free/Provider/Deepinfra.py`, `llm4free/Provider/OPENAI/deepinfra.py`) following Groq provider pattern. Implemented `get_models()` and `update_available_models()` class methods that fetch from `https://api.deepinfra.com/v1/models` API endpoint with fallback to default models on failure. Providers now automatically update their available models list during initialization.
### 🚮 Removed
- **removed**: `yep.py` - Removed the YEPCHAT provider and related files.

## [2025.12.20] - 2025-12-20

### 📝 Documentation Updates
- **docs**: litprinter.md - Completely rewrote documentation to be comprehensive and consistent with other LLM4Free docs. Added detailed sections for IceCream debugging, Rich Console, Panels & Layouts, Traceback Enhancement, Themes & Styling, Advanced Usage, Integration with LLM4Free, API Reference, Dependencies, and Supported Python Versions. Enhanced with professional formatting, extensive code examples, and parameter tables.

### ✨ Added

- **feat**: llm4free/Provider/Nvidia.py - New standalone Nvidia NIM provider with dynamic model fetching and advanced stream sanitization.
- **feat**: llm4free/Provider/OPENAI/nvidia.py - New OpenAI-compatible Nvidia NIM provider with manual stream parsing.
- **feat**: llm4free/Provider/HuggingFace.py - New standalone Hugging Face provider with dynamic model fetching and advanced stream sanitization.
- **feat**: llm4free/Provider/OPENAI/huggingface.py - New OpenAI-compatible Hugging Face provider using HF Router with manual stream parsing.
- **feat**: llm4free/Provider/ChatSandbox.py - Major update to ChatSandbox provider after reverse engineering. Expanded `AVAILABLE_MODELS` to include `deepseek-r1-full`, `gemini-thinking`, `llama`, and others.
- **feat**: llm4free/Provider/OPENAI/chatsandbox.py - Updated OpenAI-compatible ChatSandbox provider with new model list and improved response extraction for reasoning and content.
- **feat**: Enhanced SwiftCLI with advanced argument and option validation including min/max length, regex patterns, and choices
- **feat**: Added JSON and YAML output formatters (`json_output`, `yaml_output`) for structured data output
- **feat**: Implemented command aliases system with `app.alias()` method for creating command shortcuts
- **feat**: Added command chaining support with `app.enable_chaining()` for complex workflows
- **feat**: Implemented shell completion script generation for bash, zsh, and fish shells via `generate_completion_script()`
- **feat**: Added mutually exclusive options support to prevent conflicting option combinations
- **feat**: Enhanced argument decorator with validation and mutually exclusive support
- **feat**: Added comprehensive validation functions in `utils/parsing.py` including `validate_argument` and `check_mutually_exclusive`
- **feat**: Updated CLI core to handle command aliases and validation in argument parsing
- **feat**: Added example script demonstrating all new features in `examples/advanced_features.py`
- **feat**: Updated documentation with new features and usage examples
- **feat**: Enhanced error handling with detailed validation error messages
- **feat**: Improved type safety with better runtime validation
- **feat**: llm4free/Provider/TTI/together.py - Refactored TogetherImage provider to require a user-provided API key, removing the brittle auto-authentication logic. This aligns it with the TogetherAI chat providers.

### 🔧 Maintenance
- **chore**: Simplified optimizers module to include only the core coder optimizer, removing unused specialized optimizers to reduce complexity and maintenance overhead
- **chore**: Enhanced coder optimizer with improved system context and more detailed instructions for better code generation quality
- **feat**: llm4free/Provider/TTI/pollinations.py - Expanded supported models list to include `flux-pro`, `flux-realism`, `flux-anime`, and `any-dark`.
- **feat**: `llm4free/update_checker.py` - Major overhaul of the update system:
  - **Virtual Environment Awareness**: Intelligent detection of active `venv` and prioritized local package versioning.
  - **Pre-release Support**: Added capability to detect and recommend pre-release (beta/alpha) updates when running on a pre-release version.
  - **Development Version Detection**: Recognizes when the local version is ahead of PyPI (dev mode).
  - **Rich UI**: Integrated with `rich` for beautiful, high-fidelity update panels with vibrant colors and clear call-to-actions.
  - **Performance Optimization**: Implemented result caching (12 hours) and faster connection timeouts (3s) to ensure zero impact on script startup speed.
  - **Silent Mode**: Automatically disables check in non-TTY environments and respects `LLM4FREE_NO_UPDATE` environment variable.
- **refactor**: `llm4free/litagent/` - Major overhaul of the LitAgent module:
  - **Modernized Constants**: Updated browser and OS version ranges to reflect 2024/2025 standards (Chrome 131, Firefox 132, macOS 15.0, etc.).
  - **Enhanced Logic**: Improved user agent generation for diverse device types including Smart TVs, Gaming Consoles, and Wearables.
  - **Robust State Management**: Added internal pools for agents and IPs, with automatic background refresh capabilities.
  - **Thread Safety**: Implemented `RLock` support for multi-threaded environments.
  - **Fingerprinting**: Added support for `sec-ch-ua` headers and realistic browser fingerprints.
  - **Documentation**: Moved module documentation to `docs/litagent.md` and integrated it into the central hub.

### 🛠️ Improved
- **refactor**: llm4free/Provider/TTI/ - Cleaned up the TTI module by removing 8 non-functional or login-required providers (`AIArta`, `BingImageAI`, `GPT1Image`, `ImagenAI`, `InfipAI`, `MonoChatAI`, `PiclumenAI`, `PixelMuse`).
- **refactor**: llm4free/client.py - Updated unified client to support authenticated TTI providers in auto-failover mode when an API key is provided.
- **docs**: llm4free/Provider/TTI/README.md - Updated documentation to reflect the current set of 5 functional TTI providers.
- **refactor**: `llm4free/Provider/AISEARCH/` - Standardized `raw` parameter handling across all providers (Perplexity, Genspark, IAsk, Monica, PERPLEXED, webpilotai). Raw mode now returns/yields unprocessed strings/lines.
- **refactor**: `llm4free/Provider/AISEARCH/` - Replaced manual SSE parsing with `sanitize_stream` using `extract_regexes` for robust JSON payload extraction in Perplexity, Genspark, and webpilotai.
- **refactor**: `llm4free/Provider/AISEARCH/` - Standardized internal state tracking by renaming `last_SearchResponse` to `last_response` across all providers for better consistency.
- **fix**: `llm4free/Provider/AISEARCH/webpilotai_search.py` - Fixed critical issue where search results were empty due to incorrect content accumulation logic; now correctly handles delta-based streaming.
- **fix**: `llm4free/Provider/AISEARCH/iask_search.py` - Improved raw mode output to yield raw strings instead of dictionaries for better consistency with other providers.
- **refactor**: `llm4free/Provider/AISEARCH/` - Enhanced `sanitize_stream` configuration with explicit encoding, buffer handling, and custom `content_extractor` functions to maintain provider-specific metadata (sources, status updates) during streaming.

### 🛠️ Improved
- **docs**: docs/cli.md - Updated CLI documentation to reflect all available commands, options, and examples based on actual implementation in llm4free/cli.py.
- **docs**: README.md - Enhanced CLI section with comprehensive command examples and search provider information.
- **docs**: docs/openai-api-server.md - Updated documentation to reflect actual server implementation with Docker, configuration, and API endpoint details.
- **docs**: docs/client.md - Updated to emphasize client as Python-based API using models in OpenAI format, with relationship to server API clarified.

### ✨ Added
- **feat**: llm4free/Provider/TTS/sherpa.py - New SherpaTTS provider using Next-gen Kaldi (Sherpa-ONNX) HF Space API, supporting 50+ languages and multiple ONNX models.
- **feat**: llm4free/Provider/TTS/qwen.py - New Qwen3-TTS provider reverse engineered from Hugging Face Space demo, supporting 40+ high-quality voices and automatic language detection.
- **feat**: llm4free/Provider/TTS/deepgram.py - Updated to support Aura-2 next-gen voices and latest API endpoint.
- **feat**: llm4free/Provider/TTS/elevenlabs.py - Added support for ElevenLabs API keys.
- **feat**: llm4free/Provider/TTI/miragic.py - New MiragicAI TTI provider reverse engineered from Hugging Face Space, supporting 'flux', 'turbo', and 'gptimage' models with streaming support.
- **feat**: llm4free/server/routes.py - Added `/monitor/health` endpoint for Docker health checks, returning service status and version information.

### 🛠️ Improved
- **fix**: llm4free/Provider/TTS/freetts.py - Fixed 404 error by updating to the latest synthesis API and polling mechanism.
- **fix**: llm4free/Provider/TTS/parler.py - Switched to manual Gradio polling for improved reliability and timeout handling.
- **removed**: llm4free/Provider/TTS/gesserit.py - Removed dead TikTok TTS provider.
- **refactor**: llm4free/Provider/TTS/__init__.py - Added QwenTTS and SherpaTTS to the exported TTS providers.
- **refactor**: llm4free/Provider/OPENAI/__init__.py - Added LLMChat to the list of exported OpenAI-compatible providers.
- **refactor**: llm4free/Provider/OPENAI/e2b.py - Removed all unwanted `print` statements and ANSI escape codes to make the provider fully silent.
- **refactor**: llm4free/Provider/TTS/ - Updated all TTS providers to use `ic` from litprinter instead of `print` for debugging, following the pattern established in deepgram.py:
  - Updated `murfai.py`, `openai_fm.py`, `parler.py`, `qwen.py`, `sherpa.py`, `streamElements.py`, `base.py`, `freetts.py`, `speechma.py`
  - All debug statements now use `ic.configureOutput(prefix='DEBUG| '); ic(f"Debug message")` pattern
- **refactor**: Docker configuration files for better dynamic configuration support:
  - Updated `.dockerignore` to properly exclude documentation while keeping essential files
  - Enhanced `docker-compose.yml` with accurate environment variable documentation
  - Improved `docker-compose.no-auth.yml` to reflect actual server capabilities
  - Updated `Dockerfile` with proper health check endpoint and dynamic configuration defaults
  - Improved `docs/DOCKER.md` documentation with accurate environment variable information

### 🚮 Removed
- **removed**: `gradio_client` dependency from pyproject.toml as it's no longer needed.
- **removed**: `gemini-2.0-flash` from Ayle provider model lists (`llm4free/Provider/Ayle.py`, `llm4free/Provider/OPENAI/ayle.py`).
- **removed**: llm4free/Provider/AISEARCH/stellar_search.py - Removed dead Stellar AI search provider that was causing import errors and service unavailability.

### 🐛 Fixed
- **fix**: llm4free/Provider/meta.py - Fixed HTTP/2 stream closure errors (curl error 92) by implementing robust retry mechanism with exponential backoff using AIutel retry decorator
- **fix**: llm4free/Provider/meta.py - Added HTTP/1.1 fallback via requests library when HTTP/2 streams fail, ensuring compatibility with problematic networks
- **fix**: llm4free/Provider/meta.py - Improved cookie extraction with retry logic, fallback to browser cookies, and better error handling for region-blocked sites
- **fix**: llm4free/Provider/meta.py - Added `skip_init` parameter for offline testing and development without requiring live cookie fetching
- **fix**: llm4free/Provider/meta.py - Enhanced streaming error recovery to gracefully handle connection interruptions during response iteration
- **fix**: llm4free/Provider/meta.py - Improved main module error handling with helpful guidance for network issues and testing modes
- **test**: Added comprehensive unit tests in `tests/test_meta_http2.py` for HTTP/2 fallback functionality and retry mechanisms
- **fix**: llm4free/Provider/oivscode.py - Fixed type annotation bugs by updating optional parameters to use `Optional[str]` type hints, correcting method calls, and adding proper string handling in `get_message()` method
- **fix**: llm4free/Provider/oivscode.py - Removed unwanted print statements from `fetch_available_models()` method and updated its docstring to reflect that it no longer prints models
- **fix**: llm4free/sanitize.py - Fixed import organization issues using `ruff check --fix` to properly sort and format imports according to project standards
- **fix**: llm4free/scout - Fixed multiple critical bugs, removed direct BeautifulSoup references and updated BS4-compatible messaging across the scout component. (Applied ruff checks and whitespace fixes)
- **fix**: llm4free/scout/core/scout.py - Resolved `TypeError` in `extract_metadata` and standardized `find` return types.
- **fix**: llm4free/scout/core/crawler.py - Improved domain validation security, fixed overly aggressive URL normalization, and corrected parser selection logic.
- **fix**: llm4free/scout/element.py - Fixed class matching logic and self-closing tag rendering in `prettify`.
- **fix**: llm4free/scout/parsers/lxml_parser.py - Implemented XML namespace stripping for cleaner tag names.
- **fix**: llm4free/Provider/QwenLM.py - Fixed multiple critical bugs including syntax errors, indentation issues, and formatting problems. Applied ruff check fixes to resolve blank lines with whitespace, trailing whitespace, and proper docstring formatting.

## [2025.12.19] - 2025-12-19

### ✨ Added
  - **feat**: llm4free/client.py - Enhanced unified Client interface for AI providers:
  - `client.chat.completions.create()` - OpenAI-compatible chat completions
  - `client.images.generate()` / `client.images.create()` - Unified image generation
  - **Intelligent Model Resolution**:
    - `model="auto"`: Automatically selects a random free provider and its default model
    - `model="ProviderName/model_name"`: Directly target a specific provider and model (e.g., `"Toolbaz/grok-4.1-fast"`)
    - `model="model_name"`: Automatically finds which provider supports the requested model
  - **Simplified Auth Detection**: Providers are now identified as "free" or "auth-required" based solely on the `required_auth` attribute
  - **Auto-failover**: Improved failover logic that intelligently adjusts model names across different providers
  - **Failover on Empty Response**: Added logic to detect empty or invalid non-streaming responses and automatically trigger failover to alternative providers.
  - Dynamic discovery for all 39+ chat and 13+ image providers
  - Support for custom `exclude` and `exclude_images` lists
      - **Fuzzy Model Matching**: Automatically finds the closest matching model name across all providers (both chat and TTI) if an exact match is not found (e.g., `model="grok-4.1-fst"` matches `"grok-4.1-fast"` and `model="fluux"` matches `"flux"`). Uses `difflib` with a 0.6 confidence cutoff.
      - Added `last_provider` property to track successful provider/model pairs
    - Cleaned up internal implementation and removed redundant debug prints
  - **feat**: llm4free/Provider/OPENAI/typliai.py - New OpenAI-compatible TypliAI provider with streaming and non-streaming support for GPT-4.1, GPT-5, Gemini 2.5, Claude 4.5, and Grok 4 models.
  - **feat**: llm4free/Provider/OPENAI/easemate.py - New OpenAI-compatible Easemate provider.
  - **feat**: llm4free/Provider/OPENAI/freeassist.py - New OpenAI-compatible FreeAssist provider.
  
  ### 🔧 Improved
  - **refactor**: llm4free/client.py - Robust model discovery logic that safely handles class attributes, instance properties (including `@property`), and `.models.list()` methods during model resolution and fuzzy matching.
  - **refactor**: llm4free/Provider/Sambanova.py - Major refactor to align with TextPollinationsAI pattern:  - Implemented `sanitize_stream` for robust SSE parsing.
  - Added support for tools and tool calling via `tools` and `tool_choice`.
  - Added dynamic model fetching with `update_available_models`.
  - Integrated `LitAgent` for dynamic browser fingerprinting.

## [2025.12.18] - 2025-12-18

### 🚮 Removed
- **removed**: llm4free/Provider/Perplexitylabs.py - Removed PerplexityLabs provider file.
- **removed**: PerplexityLabs entry from Provider.md documentation and statistics.
- **removed**: References to PerplexityLabs from llm4free/Provider/__init__.py.
- **removed**: llm4free/Provider/TeachAnything.py - Removed TeachAnything provider file.
- **removed**: TeachAnything entry from Provider.md documentation and statistics.
- **removed**: References to TeachAnything from llm4free/Provider/__init__.py.
- **removed**: llm4free/Provider/GeminiProxy.py - Removed GeminiProxy provider file.
- **removed**: GeminiProxy entry from Provider.md documentation and statistics.
- **removed**: References to GeminiProxy from llm4free/Provider/__init__.py.

### 🛠️ Fixed
- **fix**: llm4free/Provider/OPENAI/ - Fixed "Accept-Encoding" issue in multiple providers (`K2Think`, `AkashGPT`, `LLMChatCo`, `Yep`, `Zenmux`, `DeepInfra`) that caused decompression errors and empty responses when using `requests` or `cloudscraper` libraries.
- **fix**: llm4free/Provider/turboseek.py - Updated provider to handle new HTML-based raw stream response format and improved HTML-to-Markdown conversion.


## [2025.12.17] - 2025-12-17

### ✨ Added

### 🚮 Removed
- **removed**: llm4free/Provider/Nemotron.py - Removed Nemotron provider as the file doesn't exist and was causing import errors
- **removed**: References to NEMOTRON from llm4free/Provider/__init__.py
- **removed**: Nemotron entry from Provider.md documentation

- **feat**: llm4free/Provider/OPENAI/gradient.py - New OpenAI-compatible Gradient Network provider for accessing distributed GPU clusters with models GPT OSS 120B and Qwen3 235B
- **feat**: llm4free/Provider/OPENAI/gradient.py - Supports both streaming and non-streaming modes with thinking/reasoning capability
- **feat**: llm4free/Provider/OPENAI/gradient.py - Auto-detection of cluster mode per model (nvidia for GPT OSS 120B, hybrid for Qwen3 235B)
- **feat**: llm4free/Provider/freeassist.py - New OpenAI-compatible FreeAssist provider using FreeAssist.ai API with access to multiple AI models including gemini 2.5 flash and flash lite and GPT-5-nano and GPT-5-mini
- **feat**: llm4free/Provider/OPENAI/sambanova.py - New OpenAI-compatible Sambanova provider supporting Llama 3.1/3.3, Qwen, and DeepSeek models with streaming capabilities
- **feat**: llm4free/Provider/OPENAI/meta.py - New OpenAI-compatible Meta AI provider with web authentication, optional Facebook login, and streaming support

### 🔧 Improved

- **refactor**: llm4free/Provider/Gradient.py - Major rewrite with correct headers matching actual API, proper SSE response parsing for content/reasoningContent
- **refactor**: llm4free/Provider/Gradient.py - Now uses sanitize_stream with custom _gradient_extractor following the pattern of other providers
- **refactor**: llm4free/Provider/Gradient.py - Added MODEL_CLUSTERS mapping for auto-detection of cluster mode (nvidia for GPT, hybrid for Qwen3)
- **refactor**: llm4free/Provider/Gradient.py - Updated model names to use spaces (GPT OSS 120B, Qwen3 235B) matching API format
- **feat**: llm4free/Provider/OPENAI/freeassist.py - Supports both streaming and non-streaming modes with proper SSE parsing
- **feat**: llm4free/Provider/OPENAI/zenmux.py - Implemented dynamic model list fetching from `https://zenmux.ai/api/v1/models` API endpoint, making it fully compatible with Groq provider pattern
- **refactor**: llm4free/Provider/TextPollinationsAI.py - Switched to requests library and implemented proper non-streaming support via `stream=False` to match API behavior
- **fix**: llm4free/Provider/OPENAI/textpollinations.py - Fixed duplicate code blocks and syntax errors, ensuring proper class structure and dynamic model fetching

### 🚮 Removed
- **removed**: llm4free/Provider/OPENAI/FreeGemini.py - Removed FreeGemini provider due to service deprecation
- **removed**: llm4free/Provider/OpenGPT.py - Removed OpenGPT provider from the project

### 🔧 Maintenance
- **refactor**: llm4free/Provider/OPENAI/DeepAI.py - Implemented dynamic model fetching using `get_models()` and `update_available_models()` class methods following Cerebras provider pattern
- **refactor**: llm4free/Provider/OPENAI/textpollinations.py - Implemented dynamic model fetching using `get_models()` and `update_available_models()` class methods following Cerebras provider pattern
- **refactor**: llm4free/Provider/TTI/together.py - Implemented dynamic model fetching using `get_models()` and `update_available_models()` class methods following Cerebras provider pattern
- **docs**: Updated provider documentation to reflect consistent dynamic model fetching implementation across providers

## [2025.12.16] - 2025-12-16

### ✨ Added

- **feat**: llm4free/Provider/OPENAI/zenmux.py - Added `get_models()` and `update_available_models()` class methods for automatic model discovery and updating AVAILABLE_MODELS on initialization

#### GGUF Converter v2.0 Major Update
- **feat**: llm4free/Extra/gguf.py - Upgraded to version 2.0.0 with latest llama.cpp features
- **feat**: Added new output types (`--outtype`): `f32`, `f16`, `bf16`, `q8_0`, `tq1_0`, `tq2_0`, `auto`
- **feat**: Added remote mode (`--remote`) for experimental tensor streaming without full model download
- **feat**: Added dry run mode (`--dry-run`) to preview split plans without writing files
- **feat**: Added vocab-only mode (`--vocab-only`) to extract just vocabulary without model weights
- **feat**: Added no-lazy mode (`--no-lazy`) to disable lazy evaluation for debugging
- **feat**: Added model name override (`--model-name`) for custom output naming
- **feat**: Added small first shard (`--small-first-shard`) for metadata-only first split file
- **feat**: Added new K-quant types: `q2_k_s`, `q4_k_l`, `q5_k_l`
- **feat**: Added ternary quantization: `tq1_0` (1-bit), `tq2_0` (2-bit) experimental
- **feat**: Added comprehensive IQ (importance-based) quantization methods:
  - 1-bit: `iq1_s`, `iq1_m`
  - 2-bit: `iq2_xxs`, `iq2_xs`, `iq2_s`, `iq2_m`
  - 3-bit: `iq3_xxs`, `iq3_xs`, `iq3_s`, `iq3_m`
  - 4-bit: `iq4_nl`, `iq4_xs`

#### GitToolkit Enhancements
- **feat**: llm4free/Extra/GitToolkit/gitapi/search.py - New `GitSearch` class with methods for GitHub Search API: `search_repositories()`, `search_users()`, `search_topics()`, `search_commits()`, `search_issues()`, `search_labels()`
- **feat**: llm4free/Extra/GitToolkit/gitapi/gist.py - New `Gist` class for public gist operations: `get()`, `list_public()`, `list_for_user()`, `get_commits()`, `get_forks()`, `get_revision()`, `get_comments()`
- **feat**: llm4free/Extra/GitToolkit/gitapi/organization.py - New `Organization` class for org data: `get_info()`, `get_repos()`, `get_public_members()`, `get_events()`
- **feat**: llm4free/Extra/GitToolkit/gitapi/trending.py - New `Trending` class for GitHub trending: `get_repositories()`, `get_developers()`
- **feat**: llm4free/Extra/GitToolkit/gitapi/repository.py - Added 9 new methods: `get_readme()`, `get_license()`, `get_topics()`, `get_forks()`, `get_stargazers()`, `get_watchers()`, `compare()`, `get_events()`
- **feat**: llm4free/Extra/GitToolkit/gitapi/user.py - Added 2 new methods: `get_social_accounts()`, `get_packages()`

#### YTToolkit Enhancements
- **feat**: llm4free/Extra/YTToolkit/ytapi/suggestions.py - New `Suggestions` class for YouTube autocomplete: `autocomplete()`, `trending_searches()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/shorts.py - New `Shorts` class for YouTube Shorts: `is_short()`, `get_trending()`, `search()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/hashtag.py - New `Hashtag` class for hashtag videos: `get_videos()`, `get_metadata()`, `extract_from_text()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/captions.py - New `Captions` class for video transcripts: `get_available_languages()`, `get_transcript()`, `get_timed_transcript()`, `search_transcript()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/video.py - Added new properties/methods: `is_live`, `is_short`, `hashtags`, `get_related_videos()`, `get_chapters()`, `stream_comments()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/query.py - Added new search methods: `shorts()`, `live_streams()`, `videos_by_duration()`, `videos_by_upload_date()`
- **feat**: llm4free/Extra/YTToolkit/ytapi/extras.py - Added new trending methods: `shorts_videos()`, `movies()`, `podcasts()`

### 🔧 Improved
- **refactor**: llm4free/Extra/YTToolkit/transcriber.py - Rewrote YTTranscriber to use YouTube's InnerTube API for more reliable transcript fetching, replacing brittle HTML parsing with direct API calls
  - Uses `/youtubei/v1/player` endpoint for stable data extraction
  - Added better error handling for IP blocks, bot detection, and age-restricted videos
  - Fixed caption name parsing for new YouTube format (runs vs simpleText)
  - Removed problematic `&fmt=srv3` from caption URLs
  - Added fallback XML parsing for edge cases

### 🔧 Maintenance
- **refactor**: llm4free/Extra/GitToolkit/gitapi/__init__.py - Updated exports to include new classes
- **refactor**: llm4free/Extra/YTToolkit/ytapi/__init__.py - Updated exports to include new classes
- **docs**: llm4free/Extra/GitToolkit/gitapi/README.md - Updated documentation with all new features and examples
- **docs**: llm4free/Extra/YTToolkit/README.md - Updated documentation with all new features and examples
- **refactor**: llm4free/Extra/gguf.py - Updated conversion logic to use dynamic outtype instead of hardcoded f16
- **refactor**: llm4free/Extra/gguf.py - Improved split size validation to support K, M, G units matching llama.cpp
- **refactor**: llm4free/Extra/gguf.py - Added outtype validation against VALID_OUTTYPES set
- **docs**: Moved llm4free/Extra/gguf.md → docs/gguf.md for better documentation organization
- **docs**: docs/gguf.md - Complete rewrite for v2.0 with all new features, examples, and troubleshooting

### 🚮 Removed
- **removed**: llm4free/Extra/autocoder/ - Completely removed AutoCoder package directory and all its files.
- **refactor**: llm4free/AIutel.py - Removed AutoCoder import.
- **refactor**: llm4free/Extra/__init__.py - Removed AutoCoder import.


## [2025.12.09] - 2025-12-09

### ✨ Added
- **feat**: pyproject.toml - Added `litprinter` dependency for improved logging functionality
- **feat**: llm4free/Provider/OPENAI/utils.py - Added dict-like access methods (`__getitem__`, `__setitem__`, `keys`, `values`, `items`) to `ChatCompletionMessage` class for better compatibility
- **feat**: llm4free/Provider/OPENAI/PI.py - Added missing `count_tokens` import for proper token counting functionality

### 🐛 Fixed
- **fix**: llm4free/server/providers.py - Added `required_auth = False` filtering to only initialize OpenAI-compatible providers that don't require authentication, improving server startup and reducing provider count to 28 no-auth providers

### 🔧 Maintenance
- **refactor**: Replaced Litlogger with litprinter across entire codebase for consistent logging:
  - **refactor**: llm4free/Extra/autocoder/autocoder.py - Updated logger initialization comment
  - **refactor**: llm4free/Extra/tempmail/async_utils.py - Replaced standard logging with litprinter
  - **refactor**: llm4free/Provider/OPENAI/K2Think.py - Replaced Litlogger imports with litprinter
  - **refactor**: llm4free/Provider/OPENAI/base.py - Replaced Litlogger with litprinter for error logging
  - **refactor**: llm4free/Provider/TTS/speechma.py - Replaced Litlogger with litprinter
  - **refactor**: llm4free/Provider/meta.py - Removed unused logging import
  - **refactor**: llm4free/__init__.py - Removed Litlogger import
  - **refactor**: llm4free/conversation.py - Replaced logging with litprinter
  - **refactor**: llm4free/search/base.py - Replaced logging with litprinter
  - **refactor**: llm4free/search/engines/wikipedia.py - Replaced logging with litprinter
  - **refactor**: llm4free/search/http_client.py - Replaced logging with litprinter
  - **refactor**: llm4free/server/config.py - Replaced Litlogger with litprinter
  - **refactor**: llm4free/server/providers.py - Replaced Litlogger with litprinter
  - **refactor**: llm4free/server/request_processing.py - Replaced Litlogger with litprinter and added inline utility functions
  - **refactor**: llm4free/server/routes.py - Replaced Litlogger with litprinter
  - **refactor**: llm4free/server/server.py - Replaced Litlogger with litprinter
- **refactor**: llm4free/search/engines/__init__.py - Changed from auto-discovery to static imports for better performance and reliability
- **refactor**: llm4free/Provider/AISEARCH/__init__.py - Cleaned up import comments
- **refactor**: llm4free/server/request_processing.py - Added inline implementations of `get_client_ip()`, `generate_request_id()`, and `log_api_request()` functions to replace dependency on simple_logger.py
- **refactor**: README.md - Removed reference to deprecated LitLogger
- **refactor**: lol.py - Updated example to use ChatGPT provider and added cprint import

### 🚮 Removed
- **removed**: AGENTS.md - Deleted unused documentation file
- **removed**: llm4free/Litlogger/ - Completely removed Litlogger package directory and all its files (README.md, __init__.py, formats.py, handlers.py, levels.py, logger.py)
- **removed**: llm4free/litprinter/__init__.py - Removed redundant wrapper file
- **removed**: llm4free/server/simple_logger.py - Deleted file as functionality moved inline to request_processing.py

## [2025.12.03] - 2025-12-03

### ✨ Added
- **feat**: llm4free/search/engines/__init__.py - Updated auto-discovery logic to register all search engine classes with `name` and `category` attributes, not just BaseSearchEngine subclasses
- **feat**: llm4free/server/routes.py - Added new `/search/provider` endpoint that returns details about each search provider including name, supported categories, and parameters
- **feat**: llm4free/models.py - Enhanced LLM models class with `providers()` and `provider()` methods that return detailed provider information including models, parameters, and metadata
- **feat**: llm4free/models.py - Added TTI (Text-to-Image) models support with `_TTIModels` class including detailed provider information methods
- **feat**: added all engines to cli.py
- **feat**: cli.py - Added CLI commands for Bing search (text, images, news, suggestions)
- **feat**: cli.py - Added CLI commands for Yahoo search (text, images, videos, news, answers, maps, translate, suggestions, weather)
- **feat**: Algion.py - Implemented dynamic model loading from API without hardcoded defaults, ensuring AVAILABLE_MODELS is only populated if API fetch succeeds
- **feat**: Cerebras.py - Modified AVAILABLE_MODELS to use dynamic loading without defaults, requiring API key for model fetching
- **feat**: OPENAI/algion.py - Added OpenAI-compatible Algion provider with dynamic model loading
- **feat**: OPENAI/cerebras.py - Added OpenAI-compatible Cerebras provider with dynamic model loading
- **feat**: OPENAI/elmo.py - Added OpenAI-compatible Elmo provider
- **feat**: conversation.py - Added logging import for debug messages in file operations
- **feat**: conversation.py - Added __trim_chat_history private method for history length management

### 🐛 Fixed
- **fix**: llm4free/server/routes.py - Fixed search engine method checking bug where it was looking for `hasattr(searcher, type)` instead of `hasattr(searcher, "run")`, preventing DuckDuckGo and other engines from working
- **fix**: llm4free/server/routes.py - Fixed FastAPI UI documentation issue where search engines were listed multiple times by using `set()` to get unique engine names
- **fix**: llm4free/search/engines/brave.py - Added `run` method to Brave search engine class for compatibility with search endpoint
- **fix**: llm4free/search/engines/mojeek.py - Added `run` method to Mojeek search engine class for compatibility with search endpoint
- **fix**: llm4free/search/engines/yandex.py - Added `run` method to Yandex search engine class for compatibility with search endpoint
- **fix**: llm4free/search/engines/wikipedia.py - Added `run` method to Wikipedia search engine class for compatibility with search endpoint
- **fix**: llm4free/models.py - Fixed `_LLMModels.summary()` method which was missing its return statement, causing it to return `None` instead of the expected dictionary with provider and model counts

### 🔧 Maintenance
- **refactor**: Added dynamic model fetching to OPENAI and GEMINIAPI providers similar to Algion provider, with get_models() classmethod that fetches available models from API
- **refactor**: Updated models.py to prioritize get_models() method over AVAILABLE_MODELS for dynamic model loading in provider discovery
- **refactor**: Added `name` and `category` attributes to all DuckDuckGo search engine classes (text, images, videos, news, suggestions, answers, maps, translate, weather)
- **refactor**: Added `name` and `category` attributes to Bing search engine classes (text, images, news, suggestions)
- **refactor**: Added `name` and `category` attributes to Yep search engine classes (text, images, suggestions)
- **refactor**: Updated llm4free/search/engines/bing/__init__.py to import and expose Bing search engine classes
- **refactor**: Updated `/search` endpoint description to reflect support for all available search engines and search types
- **refactor**: prompt_manager.py - Removed unused imports, redundant code, and cleaned up class for clarity and minimalism
- **chore**: prompt_manager.py - Minor optimizations and code style improvements
- **refactor**: cli.py - Cleaned up incomplete command stubs and fixed inconsistencies in option decorators
- **removed**: cli.py - Removed unused imports and broken command implementations
- **cleanup**: Removed unused `schemas.py` file from server.
- **refactor**: Removed all imports and references to `HealthCheckResponse` and `ErrorResponse` from `routes.py` and `__init__.py`.
- **refactor**: Cleaned up unused imports (secrets, etc.) in `routes.py`.
- **refactor**: Updated `__init__.py` to only export actively used symbols and remove legacy schema references.
- **refactor**: Ensured all server modules only contain necessary code and imports, improving maintainability and clarity.
- **refactor**: conversation.py - Simplified Conversation class to use string-based chat history instead of message objects, removing tool handling, metadata, timestamps, and complex validation
- **refactor**: conversation.py - Updated history format to use "User : %(user)s\nLLM :%(llm)s" pattern for consistency
- **refactor**: conversation.py - Removed all tool-related methods (handle_tool_response, _parse_function_call, execute_function, get_tools_description, update_chat_history_with_tool)
- **refactor**: conversation.py - Streamlined file loading and history management to use simple string concatenation
- **refactor**: yep.py - Removed tool parameter and tool handling logic from YEPCHAT provider
- **refactor**: yep.py - Simplified ask method to directly update chat history without tool processing
- **refactor**: TeachAnything.py - No changes needed as it didn't use tool functionality

### 🚮 Removed
- **removed**: conversation.py - Removed Fn class, Message dataclass, FunctionCall, ToolDefinition, FunctionCallData TypedDicts
- **removed**: conversation.py - Removed add_message, validate_message, _append_to_file, _compress_history methods
- **removed**: conversation.py - Removed tool_history_format and related attributes
- **removed**: yep.py - Removed tool-related imports and examples from docstrings
- **removed**: AsyncProvider - Completely removed AsyncProvider class and all imports from provider files (Cohere.py, Groq.py, Koboldai.py, julius.py, HeckAI.py, ChatHub.py)
- **removed**: AsyncGROQ - Removed AsyncGROQ class from Groq.py that inherited from AsyncProvider
- **removed**: llm4free/server/routes.py - Removed monitoring endpoints (`/monitor/requests`, `/monitor/stats`, `/monitor/health`) and related code from server
- **removed**: llm4free/server/simple_logger.py - Removed unused monitoring methods (`get_recent_requests`, `get_stats`) from SimpleRequestLogger class


## [2025.12.01] - 2025-12-01
### ✨ Added
 - **feat**: sanitize.py - Added `output_formatter` parameter to `sanitize_stream()` for custom output transformation
 - **feat**: sanitize.py - Users can now define custom formatter functions to transform each output item into any desired structure before yielding

### 🚮 Removed
 - **removed**: sanitize.py - Removed built-in response formatters (`ResponseFormatter`, `OutputFormat`, `create_openai_response`, `create_openai_stream_chunk`, `create_anthropic_response`, `create_anthropic_stream_chunk`, `format_output`) in favor of user-defined `output_formatter` functions
 - **removed**: sanitize.py - Removed `output_format` and `format_options` parameters from `sanitize_stream()` - use `output_formatter` instead

### 📝 Documentation
 - **docs**: sanitize.md - Updated documentation with `output_formatter` parameter and usage examples
 - **docs**: sanitize.md - Removed references to removed built-in formatters

## [2025.11.30] - 2025-11-30

### 🔧 Maintenance
 - **refactor**: Added missing `# type: ignore` to imports for optional dependencies (trio, numpy, tiktoken, pandas) in multiple modules for better compatibility and linting
 - **refactor**: Improved type hints and error handling in `scout/core/crawler.py` and `scout/core/scout.py`
 - **refactor**: Updated `oivscode.py` to generate and use a unique ClientId (UUID) in headers
 - **refactor**: Updated CLI group import in `swiftcli/core/cli.py` to avoid circular dependency
 - **refactor**: Minor docstring and comment cleanups in AISEARCH providers
 - **chore**: Removed unfinished providers: `Aitopia.py`, `VercelAIGateway.py`, `puterjs.py`, `scira_search.py`, `hika_search.py` from Provider/UNFINISHED and Provider/AISEARCH

### 🐛 Fixed
 - **fix**: Fixed error handling in `sanitize.py` async stream processing (removed logger usage in extractor error branch)
 - **fix**: Fixed import and type hint issues in `duckduckgo/base.py`, `search/http_client.py`, `Provider/cerebras.py`, and others
 - **fix**: Fixed streaming output and test code in `genspark_search.py`, `PERPLEXED_search.py`, and `iask_search.py` for more robust CLI testing
 - **fix**: Fixed YahooSearch import for Dict type in `search/yahoo_main.py`

### 🚮 Removed
 - **removed**: Deleted unfinished provider files: `Aitopia.py`, `VercelAIGateway.py`, `puterjs.py`, `scira_search.py`, `hika_search.py` for codebase cleanup

### 🐛 Fixed
 - **fix**: TogetherAI.py - Updated API endpoint from `https://chat.together.ai/api/chat-completion` to `https://api.together.xyz/v1/chat/completions` for compatibility with the public Together API
 - **fix**: TogetherAI.py - Fixed payload parameters to use OpenAI-compatible format (`model`, `max_tokens`, `top_p` instead of `modelId`, `maxTokens`, `topP`)
 - **fix**: OPENAI/TogetherAI.py - Removed self-activation endpoint logic that auto-fetched API keys from external service

### ✨ Added
 - **feat**: TogetherAI.py - Implemented dynamic model loading from `https://api.together.xyz/v1/models` API, similar to Groq provider
 - **feat**: TogetherAI.py - Added `get_models()` and `update_available_models()` class methods for automatic model discovery
 - **feat**: OPENAI/TogetherAI.py - Added dynamic model loading support with automatic model list updates on initialization
 - **feat**: OPENAI/TogetherAI.py - Now requires user-provided API key via `api_key` parameter, following Groq provider pattern

### 🔧 Maintenance
 - **refactor**: TogetherAI.py - Changed `AVAILABLE_MODELS` from hardcoded dictionary to dynamically populated list
 - **refactor**: TogetherAI.py - Updated model validation to handle empty model lists gracefully when API fetch fails
 - **refactor**: OPENAI/TogetherAI.py - Removed `activation_endpoint` and `get_activation_key()` method for better security practices
 - **refactor**: OPENAI/TogetherAI.py - Updated `__init__` to accept `api_key` parameter and conditionally update models if key is provided

## [2025.11.21] - 2025-11-21

### 🐛 Fixed
 - **fix**: IBM.py - Fixed typo in `refresh_identity` method where `s-elf.headers` was incorrectly used instead of `self.headers`
 - **fix**: AIauto.py - Fixed critical bug where `chat` method could return a generator when `stream=False`, causing `AssertionError` in providers like AI4Chat
 - **fix**: AIauto.py - Added proper handling for providers that return generators even in non-streaming mode by consuming the generator to extract the return value

### ✨ Added
 - **feat**: AIauto.py - Enhanced provider failover mechanism to "peek" at the first chunk of streaming responses, allowing automatic failover to next provider if current one fails immediately
 - **feat**: AIauto.py - Split `chat` method into `_chat_stream` and `_chat_non_stream` helper methods for clearer separation of streaming vs non-streaming logic
 - **feat**: OPENAI/ibm.py - Added OpenAI-compatible IBM Granite provider in `llm4free/Provider/OPENAI/` with support for `granite-chat` and `granite-search` models
 - **feat**: OPENAI/ibm.py - Implemented using `format_prompt()` and `count_tokens()` utilities from utils.py for proper message formatting and accurate token counting
 - **feat**: OPENAI/ibm.py - Manual SSE (Server-Sent Events) stream parsing without sanitize_stream dependency, consistent with other OPENAI providers

### 🔧 Maintenance
 - **refactor**: AIauto.py - Improved robustness of AUTO provider to work seamlessly with all providers in llm4free.Provider package
 - **refactor**: AIauto.py - Added generator type checking and handling to prevent type mismatches between streaming and non-streaming responses

## [2025.11.20] - 2025-11-20

### 🐛 Fixed
 - **fix**: sanitize.py - Fixed critical async stream processing logic error where variable `idx` was used outside its conditional scope, causing potential `UnboundLocalError`
 - **fix**: sanitize.py - Fixed Python 3.9+ compatibility issue by replacing `Pattern` from typing with `re.Pattern` for proper isinstance() checks

### 🔧 Maintenance
 - **refactor**: sanitize.py - Reorganized imports for better structure (moved chain, functools, asyncio to top level)
 - **chore**: sanitize.py - Added `__all__` export list for explicit public API definition
 - **docs**: sanitize.py - Added comprehensive module docstring
 - **refactor**: sanitize.py - Updated all type hints to use modern syntax with `re.Pattern[str]`
 - **refactor**: Apriel.py - Simplified raw mode streaming logic for better performance

## [2025.11.19] - 2025-11-19

### 🔧 Maintenance
 - **chore**: Bard - added `gemini-3-pro` model with appropriate headers to `BardModel` enum
 - **GEMINI** - added `gemini-3-pro` model support in `GEMINI` class
 - **feat**: Updated search engines to use dataclass objects from results.py for better type safety and consistency
 - **refactor**: Updated all Providers to use `raw` flag of sanatize_stream for easy debugging
 - **removed**: Removed Cloudflare Provider

### 🐛 Fixed
 - **fix**: ChatGPT provider - Fixed OpenAI compatibility issues in `llm4free/Provider/OPENAI/chatgpt.py` by updating streaming and non-streaming implementations to properly handle Server-Sent Events format and match OpenAI's response structure exactly
 - **fix**: ChatGPT provider - Enhanced error handling and parameter validation to follow OpenAI conventions
 - **fix**: AkashGPT provider - Fixed authentication issue in `llm4free/Provider/akashgpt.py` by updating API key handling to use cookies for authentication

### ✨ Added
 - **feat**: ChatGPT provider - Added new models to AVAILABLE_MODELS including `gpt-5-1`, `gpt-5-1-instant`, `gpt-5-1-thinking`, `gpt-5`, `gpt-5-instant`, `gpt-5-thinking`
 - **feat**: New Provider: Algion with `gpt-5.1`and other models 

## [2025.11.17] - 2025-11-17

### 🔧 Maintenance
 - **fix**: swiftcli - improved argument parsing: support `--key=value` and `-k=value` syntax; handle repeated flags/options (collected into lists)
 - **fix**: swiftcli - `convert_type` now handles boolean inputs and list-typed values robustly
 - **feat**: swiftcli - added support for option attributes: `count`, `multiple`, and `is_flag`; option callbacks supported; `choices` validation extended to multiple options
 - **fix**: swiftcli - option decorator uses a sentinel for unspecified defaults to avoid overriding function defaults with `None`
 - **feat**: swiftcli - CLI and `Group` now support the `@pass_context` decorator to inject `Context` and can run `async` coroutine commands
 - **fix**: swiftcli - help output deduplicates commands and displays aliases clearly; group help deduplicated and improved formatting
 - **test**: swiftcli - added comprehensive unit tests covering parsing, option handling (count/multiple/choices), `pass_context`, async behavior, group commands, and plugin manager lifecycle
 - **chore**: swiftcli - updated README with changelog, improved examples, and removed temporary debug/test helper files
 - **testing**: All swiftcli tests added in this change pass locally (14 tests total)

## [2025.11.16] - 2025-11-16
- **feat**: added `moonshotai/Kimi-K2-Thinking` and `MiniMaxAI/MiniMax-M2` models to DeepInfra provider AVAILABLE_MODELS in both `llm4free/Provider/Deepinfra.py` and `llm4free/Provider/OPENAI/deepinfra.py`
- **feat**: 

###  Maintenance
- **feat**: fixed formating issue in HeckAI replaced `strip_chars=" \n\r\t",`  with `strip_chars=""`
- **chore**: updated CHANGELOG.md to changelog.md in MANIFEST.in for consistency
- **chore**: updated release-with-changelog.yml to handle multiple version formats in changelog parsing
- **feat**: Updated changelog parsing to recognize multiple version formats (e.g., "vX.Y.Z", "X.Y.Z") for improved release automation.
- **feat**: updated `sanitize_stream` to support both `extract_regexes` and `content_extractor` at same time
- **chore**: updated `release-with-changelog.yml` to normalize version strings by stripping leading 'v' or 'V'
- **chore**: updated `sanitize_stream` docstring to clarify usage of `extract_regexes` and `content_extractor`
- **chore**: updated models list in textpollionations provider
- **chore**: replaced `anthropic:claude-3-5-haiku-20241022` with `anthropic:claude-haiku-4-5-20251001` in typefully provider 

### Added
- **feat**: added `anthropic:claude-haiku-4-5-20251001` to typefully provider AVAILABLE_MODELS
- **feat**: New IBM provider with `granite-search` and `granite-chat` models 

## [2025.11.06] - 2025-11-06

### 🔧 Maintenance
- **chore**: Remove GMI provider (a8928a0) — Cleaned up provider roster by removing GMI to simplify maintenance and reduce duplicate or deprecated provider support.

## [2025.10.22] - 2025-10-22

### ✨ Added
- **feat**: Add `claude-haiku-4.5` model to Flowith provider (3a80249) — Flowith now supports additional Claude variants for creative text generation.
- **feat**: Add `openai/gpt-oss-20b` and `openai/gpt-oss-120b` models to GMI provider (3a80249) — Added support for larger OSS GPT models via GMI.

### 🔧 Maintenance
- **refactor**: Change `DeepAI` `required_auth` to `True` (3a80249) — Ensure DeepAI provider requires authentication for API access.
- **chore**: Add import error handling for `OLLAMA` provider (3a80249) — Graceful degradation when optional dependencies are missing.
- **chore**: Remove deprecated `FalconH1` and `deepseek_assistant` providers (3a80249) — Reduced clutter and removed unsupported providers.
- **chore**: Update `OPENAI`, `flowith`, and `gmi` providers with new model lists and aliases (3a80249) — Keep model availability up-to-date and consistent.

## [2025.10.18] - 2025-10-18

### 🚀 Major Enhancements
- **🤖 AI Provider Expansion**: Integrated SciRA-AI and SciRA-Chat providers, adding robust model mapping and aliasing to unify behavior across providers.

### 📦 Package Structure
- **🛠️ Model Mapping System**: Introduced `MODEL_MAPPING` and `SCI_RA_TO_MODEL` dictionaries and updated `AVAILABLE_MODELS` lists to keep model names consistent and avoid duplication.

### ⚡ Improvements
- **🔄 Enhanced Model Resolution**: Improved `convert_model_name` and `_resolve_model` logic to better handle aliases, fallbacks, and unsupported names with clearer error messages.
- **🧪 Test and Example Updates**: Updated provider `__main__` blocks to list available models and print streaming behavior for easier local testing.
- **📝 Documentation**: Improved docstrings and comments clarifying model resolution and provider behavior.

### 🔧 Refactoring
- **⚙️ Provider Interface Standardization**: Refactored provider base classes and initialization logic to standardize how models are selected and aliases are resolved.

## [2025.10.17] - 2025-10-17

### ✨ Added
- **feat**: Add `sciRA-Coding` and `sciRA-Vision` providers (7e8f2a1)
- **feat**: Add `sciRA-Reasoning` and `sciRA-Analyze` providers (7e8f2a1)

### 🔧 Maintenance
- **chore**: Update provider initialization logic to more robustly support new sciRA families (7e8f2a1)
- **chore**: Add comprehensive model listings for newly added providers (7e8f2a1)

## [2025.10.16] - 2025-10-16

### ✨ Added
- **feat**: Add `sciRA-General` and `sciRA-Assistant` providers (9c4d1b3)
- **feat**: Add `sciRA-Research` and `sciRA-Learn` providers (9c4d1b3)

### 🔧 Maintenance
- **chore**: Refactor provider base classes for improved extensibility (9c4d1b3)
- **chore**: Add model validation logic to avoid exposing unsupported names (9c4d1b3)

## [2025.10.15] - 2025-10-15

### ✨ Added
- **feat**: Introduce SciRA provider framework and initial model mappings (5a2f8c7)

### 🔧 Maintenance
- **chore**: Set up SciRA provider infrastructure and basic authentication handling (5a2f8c7)

## [2025.10.10] - 2025-10-10

### ✨ Added
- **feat**: Add Flowith provider with multiple model support (b3d8a21)
- **feat**: Add GMI provider with advanced model options (b3d8a21)

### 🔧 Maintenance
- **chore**: Update provider documentation and add installation instructions for new providers (b3d8a21)

## [2025.10.05] - 2025-10-05

### ✨ Added
- **feat**: Initial release with core LLM4Free functionality (1a2b3c4) — Added web scraping, AI provider integration, and base CLI tooling.

### 🔧 Maintenance
- **chore**: Set up project structure, initial docs, and example workflows (1a2b3c4)

---

For more details, see the [documentation](docs/) or [GitHub repository](https://github.com/pyscout/LLM4Free).
---

For more details, see the [documentation](docs/) or [GitHub repository](https://github.com/pyscout/LLM4Free).
