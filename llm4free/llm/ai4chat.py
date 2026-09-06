import time
import urllib.parse
import uuid
from typing import Any, Dict, Generator, List, Optional, Union, cast

from curl_cffi.requests import RequestsError

from llm4free.litagent import agent

# Import base classes and utility structures
from llm4free.llm.base import (
    BaseChat,
    BaseCompletions,
    OpenAICompatibleProvider,
    SimpleModelList,
)
from llm4free.llm.utils import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    Choice,
    ChoiceDelta,
    CompletionUsage,
    count_tokens,
)

# Available models for AI4Chat (text models only, synced from https://www.ai4chat.co/models)
MODELS = {
    # Popular Models
    "gpt-5.2": "GPT 5.2",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "gemini-3-flash": "Gemini 3 Flash",
    "grok-4.1-fast": "Grok 4.1 Fast",
    "kimi-k2.5": "Kimi K2.5",
    # OpenAI Models
    "gpt-3.5": "ChatGPT (GPT 3.5)",
    "gpt-4o": "GPT 4o",
    "gpt-4.5": "GPT-4.5",
    "gpt-4o-mini": "GPT 4o Mini",
    "gpt-4o-search-preview": "GPT-4o Search Preview",
    "gpt-4o-mini-search-preview": "GPT-4o mini Search Preview",
    "gpt-4.1": "GPT 4.1",
    "gpt-4.1-mini": "GPT 4.1 Mini",
    "gpt-4.1-nano": "GPT 4.1 Nano",
    "codex-mini": "Codex Mini",
    "o1": "o1",
    "o1-pro": "o1-pro",
    "o3-mini": "o3-mini",
    "o3-mini-high": "o3-mini-high",
    "o4-mini": "o4 Mini",
    "o4-mini-high": "o4 Mini High",
    "gpt-oss-20b": "GPT OSS 20B",
    "gpt-oss-120b": "GPT OSS 120B",
    "gpt-5-mini": "GPT-5 Mini",
    "gpt-5-nano": "GPT-5 Nano",
    "gpt-5": "GPT-5",
    "gpt-5.1": "GPT 5.1",
    "gpt-5.1-codex": "GPT 5.1 Codex",
    "gpt-5.1-codex-mini": "GPT 5.1 Codex-Mini",
    "gpt-5.2-codex": "GPT 5.2 Codex",
    "gpt-5.3-codex": "GPT 5.3 Codex",
    "gpt-5.3": "GPT 5.3",
    "gpt-5.4": "GPT 5.4",
    "gpt-5.4-pro": "GPT 5.4 Pro",
    "gpt-5.5": "GPT 5.5",
    # Anthropic Models
    "claude-3-haiku": "Claude 3 Haiku",
    "claude-3.5-haiku": "Claude 3.5 Haiku",
    "claude-3.7-sonnet": "Claude 3.7 Sonnet",
    "claude-sonnet-4": "Claude Sonnet 4",
    "claude-opus-4": "Claude Opus 4",
    "claude-opus-4.1": "Claude Opus 4.1",
    "claude-sonnet-4.5": "Claude Sonnet 4.5",
    "claude-opus-4.6": "Claude Opus 4.6",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-opus-4.7": "Claude Opus 4.7",
    "claude-v2.0": "Claude v2.0",
    "claude-v2.1": "Claude v2.1",
    "claude-instant-v1": "Claude Instant v1",
    "claude-3-opus": "Claude 3 Opus",
    "claude-3-sonnet": "Claude 3 Sonnet",
    "claude-3.5-sonnet": "Claude 3.5 Sonnet",
    # DeepSeek Models
    "deepseek-v3": "DeepSeek V3",
    "deepseek-v3.1": "DeepSeek v3.1",
    "deepseek-v3.2": "DeepSeek v3.2",
    "deepseek-v3-0324": "DeepSeek V3 0324",
    "deepseek-v4-flash": "DeepSeek v4 Flash",
    "deepseek-v4-pro": "DeepSeek v4 Pro",
    "deepseek-v2-chat": "DeepSeek-V2 Chat",
    "deepseek-coder": "Deepseek Coder",
    "r1-distill-qwen-1.5b": "R1 Distill Qwen 1.5B",
    "r1-distill-qwen-14b": "R1 Distill Qwen 14B",
    "r1-distill-qwen-32b": "R1 Distill Qwen 32B",
    "r1-distill-llama-70b": "R1 Distill Llama 70B",
    "r1": "R1",
    # Google Models
    "gemini-flash-2.0": "Gemini Flash 2.0",
    "gemini-flash-lite-2.0": "Gemini Flash Lite 2.0",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "gemini-2.5-flash-preview": "Gemini 2.5 Flash Preview",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemma-2-9b": "Gemma 2 9B",
    "gemma-2-27b": "Gemma 2 27B",
    "gemma-3-27b": "Gemma 3 27B",
    "gemma-4-31b": "Gemma 4 31B",
    "gemma-7b": "Gemma 7B",
    "gemini-3-pro": "Gemini 3 Pro",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    "gemini-3.1-pro": "Gemini 3.1 Pro",
    "gemini-1.0-pro": "Gemini 1.0 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
    "gemini-1.5-flash-8b": "Gemini 1.5 Flash 8B",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.0-flash-thinking-experimental": "Gemini 2.0 Flash Thinking Experimental",
    "gemini-pro-2.0-experimental": "Gemini Pro 2.0 Experimental",
    # Meta Models
    "llama-v3-8b": "Llama v3 8B",
    "llama-v3-70b": "Llama v3 70B",
    "llama-v3.1-8b": "Llama v3.1 8B",
    "llama-v3.1-70b": "Llama v3.1 70B",
    "llama-v3.1-405b": "Llama v3.1 405B",
    "llama-v3.2-1b": "Llama v3.2 1B",
    "llama-v3.2-3b": "Llama v3.2 3B",
    "llama-v3.2-11b": "Llama v3.2 11B",
    "llama-v3.2-90b": "Llama v3.2 90B",
    "llama-v3.3-70b": "Llama v3.3 70B",
    "llama-4-scout": "Llama 4 Scout",
    "llama-4-maverick": "Llama 4 Maverick",
    "llama-v2-13b": "Llama v2 13B",
    "llama-v2-70b": "Llama v2 70B",
    # Mistral Models
    "mistral-7b-instruct": "Mistral 7B Instruct",
    "mistral-7b-instruct-v0.1": "Mistral 7B Instruct v0.1",
    "mistral-7b-instruct-v0.2": "Mistral 7B Instruct v0.2",
    "mistral-7b-instruct-v0.3": "Mistral 7B Instruct v0.3",
    "mixtral-8x7b-instruct": "Mixtral 8x7B Instruct",
    "mixtral-8x22b-instruct": "Mixtral 8x22B Instruct",
    "mistral-nemo": "Mistral Nemo",
    "mistral-large-2": "Mistral Large 2",
    "mistral-large-3": "Mistral Large 3",
    "mistral-medium-3": "Mistral Medium 3",
    "mistral-small-3": "Mistral Small 3",
    "mistral-small-3.1-24b": "Mistral Small 3.1 24B",
    "mistral-small-3.2-24b": "Mistral Small 3.2 24B",
    "mistral-small-4": "Mistral Small 4",
    "ministral-3b": "Ministral 3B",
    "ministral-8b": "Ministral 8B",
    "ministral-3-3b": "Ministral 3 3B",
    "ministral-3-8b": "Ministral 3 8B",
    "ministral-3-14b": "Ministral 3 14B",
    "pixtral-12b": "Pixtral 12B",
    "codestral": "Codestral",
    "codestral-mamba": "Codestral Mamba",
    "saba": "Saba",
    "devstral-small-1.1": "Devstral Small 1.1",
    "devstral-medium": "Devstral Medium",
    "devstral-small": "Devstral Small",
    "devstral-2": "Devstral 2",
    # xAI Models
    "grok-2": "Grok 2",
    "grok-3-mini-beta": "Grok 3 Mini Beta",
    "grok-3-beta": "Grok 3 Beta",
    "grok-4": "Grok 4",
    "grok-4-fast": "Grok 4 Fast",
    "grok-4.2": "Grok 4.2",
    "grok-4.2-multi-agent": "Grok 4.2 Multi Agent",
    "grok-beta": "Grok Beta",
    "grok-code-fast-1": "Grok Code Fast 1",
    # Z.ai Models
    "glm-4-32b": "GLM 4 32B",
    "glm-4.5-air": "GLM 4.5 Air",
    "glm-4.5": "GLM 4.5",
    "glm-4.6": "GLM 4.6",
    "glm-4.7-flash": "GLM 4.7 Flash",
    "glm-5": "GLM 5",
    "glm-5-turbo": "GLM 5 Turbo",
    "glm-5.1": "GLM 5.1",
    # AI21 Models
    "jamba-mini-1.7": "Jamba Mini 1.7",
    "jamba-large-1.7": "Jamba Large 1.7",
    "jamba-1.5-large": "Jamba 1.5 Large",
    "jamba-1.5-mini": "Jamba 1.5 Mini",
    "jamba-instruct": "Jamba Instruct",
    "jamba-large-1.6": "Jamba Large 1.6",
    "jamba-mini-1.6": "Jamba Mini 1.6",
    # Amazon Models
    "nova-lite-1.0": "Nova Lite 1.0",
    "nova-micro-1.0": "Nova Micro 1.0",
    "nova-pro-1.0": "Nova Pro 1.0",
    "nova-premier-1.0": "Nova Premier 1.0",
    "nova-2-lite": "Nova 2 Lite",
    # Alibaba Cloud Models
    "qwen-2.5-7b": "Qwen 2.5 7B",
    "qwen-2.5-32b": "Qwen 2.5 32B",
    "qwen-2.5-72b": "Qwen 2.5 72B",
    "qwen-2.5-coder-32b": "Qwen 2.5 Coder 32B",
    "qwen-2-72b": "Qwen 2 72B",
    "qwen-2-7b": "Qwen 2 7B",
    "qwen-1.5-110b-chat": "Qwen 1.5 110B Chat",
    "qwen-1.5-4b-chat": "Qwen 1.5 4B Chat",
    "qwen-1.5-72b": "Qwen 1.5 72B",
    "qwen-1.5-7b-chat": "Qwen 1.5 7B Chat",
    "qwen-3-14b": "Qwen 3 14B",
    "qwen-3-32b": "Qwen 3 32B",
    "qwen-3-30b-a3b": "Qwen 3 30B A3B",
    "qwen-3-235b-a22b": "Qwen 3 235B A22B",
    "qwen-3-coder": "Qwen 3 Coder",
    "qwen3-coder-plus": "Qwen3 Coder Plus",
    "qwen3-max": "Qwen3 Max",
    "qwen-plus": "Qwen Plus",
    "qwen-max": "Qwen Max",
    "qwen-turbo": "Qwen Turbo",
    "qwq-32b": "QwQ 32B",
    "qwq-32b-preview": "QwQ 32B Preview",
    "qwen-3-max-thinking": "Qwen 3 Max Thinking",
    "qwen-3-coder-next": "Qwen 3 Coder Next",
    "qwen-3.5-397b-a17b": "Qwen 3.5 397B A17B",
    "qwen-3.5-plus": "Qwen 3.5 Plus",
    "qwen3.5-9b": "Qwen3.5-9B",
    # Cohere Models
    "command": "Command",
    "command-a": "Command A",
    "command-r": "Command R",
    "command-r7b": "Command R7B",
    "command-r-plus": "Command R+",
    # Dolphin Models
    "dolphin-2.9.2-mixtral-8x22b": "Dolphin 2.9.2 Mixtral 8x22B",
    "dolphin-2.6-mixtral-8x7b": "Dolphin 2.6 Mixtral 8x7B",
    "dolphin-llama-3-70b": "Dolphin Llama 3 70B",
    # Inception Models
    "inception-mercury": "Inception Mercury",
    "mercury-2": "Mercury 2",
    # Inflection AI Models
    "inflection-3-pi": "Inflection 3 Pi",
    "inflection-3-productivity": "Inflection 3 Productivity",
    # Liquid Models
    "lfm-3b": "LFM 3B",
    "lfm-7b": "LFM 7B",
    "lfm2-2.6b": "LFM2 2.6B",
    "lfm2-8b": "LFM2 8B",
    # Magnum Models
    "magnum-v4-72b": "Magnum v4 72B",
    "magnum-72b": "Magnum 72B",
    "magnum-v2-72b": "Magnum v2 72B",
    # Microsoft Models
    "phi-3-mini-instruct": "Phi-3 Mini Instruct",
    "phi-3.5-mini-128k-instruct": "Phi-3.5 Mini 128K Instruct",
    "phi-3-medium-instruct": "Phi-3 Medium Instruct",
    "phi-4": "Phi 4",
    "phi-4-reasoning-plus": "Phi 4 Reasoning Plus",
    "wizardlm-2-8x22b": "WizardLM-2 8x22B",
    "wizardlm-2-7b": "WizardLM-2 7B",
    # Midnight Rose Models
    "midnight-rose-70b": "Midnight Rose 70B",
    # MiniMax Models
    "minimax-01": "MiniMax-01",
    "minimax-m1": "MiniMax M1",
    "minimax-m2": "MiniMax M2",
    "minimax-m2.1": "MiniMax M2.1",
    "minimax-m2.5": "MiniMax M2.5",
    "minimax-m2.7": "MiniMax M2.7",
    "minimax-v01": "Minimax v01",
    # MoonshotAI Models
    "kimi-k2": "Kimi K2",
    "kimi-k2-thinking": "Kimi K2 Thinking",
    "kimi-k2.6": "Kimi K2.6",
    # MythoMax Models
    "mythomax-13b": "MythoMax 13B",
    "mythomist-7b": "MythoMist 7B",
    # Noromaid Models
    "noromaid-20b": "Noromaid 20B",
    "noromaid-mixtral-8x7b-instruct": "Noromaid Mixtral 8x7B Instruct",
    # NousResearch Models
    "hermes-2-pro-llama-3-8b": "Hermes 2 Pro - Llama-3 8B",
    "hermes-2-mixtral-8x7b-dpo": "Hermes 2 Mixtral 8x7B DPO",
    "hermes-2-mixtral-8x7b-sft": "Hermes 2 Mixtral 8x7B SFT",
    "hermes-2-theta-8b": "Hermes 2 Theta 8B",
    "hermes-13b": "Hermes 13B",
    "hermes-2-mistral-7b-dpo": "Hermes 2 - Mistral 7B DPO",
    "hermes-3-70b-instruct": "Hermes 3 70B Instruct",
    "hermes-3-405b-instruct": "Hermes 3 405B Instruct",
    "hermes-4-70b": "Hermes 4 70B",
    # NVIDIA Models
    "nvidia-llama-3.1-nemotron-70b": "NVIDIA Llama 3.1 Nemotron 70B",
    "nvidia-nemotron-4-340b-instruct": "NVIDIA Nemotron-4 340B Instruct",
    # Perplexity Models
    "sonar": "Sonar",
    "sonar-reasoning": "Sonar Reasoning",
    "sonar-pro": "Sonar Pro",
    "sonar-reasoning-pro": "Sonar Reasoning Pro",
    "sonar-deep-research": "Sonar Deep Research",
    # Rocinante Models
    "rocinante-12b": "Rocinante 12B",
    "unslopnemo-v4.1": "UnslopNemo v4.1",
    # Website new models
    "capybara-34b": "Capybara 34B",
    "capybara-7b": "Capybara 7B",
    "chronos-hermes-13b-v2": "Chronos Hermes 13B v2",
    "codellama-34b": "CodeLlama 34B",
    "codellama-70b-instruct": "CodeLlama 70B Instruct",
    "dbrx-132b-instruct": "DBRX 132B Instruct",
    "firellava-13b": "FireLLaVA 13B",
    "gpt-5.4-mini": "GPT 5.4 Mini",
    "gpt-5.4-nano": "GPT 5.4 Nano",
    "inferor-12b": "Inferor 12B",
    "llava-v1.6-34b": "LLaVA v1.6 34B",
    "llama-3-lumimaid-70b": "Llama 3 Lumimaid 70B",
    "llama-3-lumimaid-8b": "Llama 3 Lumimaid 8B",
    "llama-3-soliloquy-8b-v2": "Llama 3 Soliloquy 8B v2",
    "llama-3.1-sonar-405b-online": "Llama 3.1 Sonar 405B Online",
    "llama-3.1-sonar-70b-online": "Llama 3.1 Sonar 70B Online",
    "llama-3.1-sonar-8b-online": "Llama 3.1 Sonar 8B Online",
    "llama3-sonar-70b-online": "Llama3 Sonar 70B Online",
    "llama3-sonar-8b-online": "Llama3 Sonar 8B Online",
    "lumimaid-v0.2-70b": "Lumimaid v0.2 70B",
    "lzlv-70b": "Lzlv 70B",
    "mimo-v2-pro": "MiMo-V2-Pro",
    "nemotron-3-super": "Nemotron 3 Super",
    "olmo-7b-instruct": "OLMo 7B Instruct",
    "olmo-2-32b-instruct": "Olmo 2 32B Instruct",
    "openchat-3.5-8b": "OpenChat 3.5 8B",
    "openchat-3.6-8b": "OpenChat 3.6 8B",
    "openhermes-2.5-mistral-7b": "OpenHermes 2.5 Mistral 7B",
    "phind-codellama-34b-v2": "Phind CodeLlama 34B v2",
    "stripedhyena-nous-7b": "StripedHyena Nous 7B",
    "yi-1.5-34b": "Yi 1.5 34B",
    "yi-34b": "Yi 34B",
    "yi-6b": "Yi 6B",
    "yi-large": "Yi Large",
    "yi-large-turbo": "Yi Large Turbo",
    "o1-mini": "o1-mini",
    "o1-preview": "o1-preview",
}


# --- AI4Chat Client ---


class Completions(BaseCompletions):
    def __init__(self, client: "AI4Chat"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
        **kwargs: Any,
    ) -> Union[ChatCompletion, Generator[ChatCompletionChunk, None, None]]:
        """
        Creates a model response for the given chat conversation.
        Mimics openai.chat.completions.create
        """
        # Use the format_prompt utility to format the conversation
        from llm4free.llm.utils import format_prompt

        # Format the messages into a single string
        conversation_prompt = format_prompt(messages, add_special_tokens=True, include_system=True)

        # Set up request parameters
        country_param = kwargs.get("country", self._client.country)
        user_id_param = kwargs.get("user_id", self._client.user_id)

        # Generate request ID and timestamp
        request_id = f"chatcmpl-{uuid.uuid4()}"
        created_time = int(time.time())

        # AI4Chat doesn't support streaming, so we'll simulate it if requested
        if stream:
            return self._create_stream(
                request_id,
                created_time,
                model,
                conversation_prompt,
                country_param,
                user_id_param,
                timeout=timeout,
                proxies=proxies,
            )
        else:
            return self._create_non_stream(
                request_id,
                created_time,
                model,
                conversation_prompt,
                country_param,
                user_id_param,
                timeout=timeout,
                proxies=proxies,
            )

    def _create_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        conversation_prompt: str,
        country: str,
        user_id: str,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> Generator[ChatCompletionChunk, None, None]:
        """Simulate streaming by breaking up the full response into fixed-size character chunks."""
        try:
            # Get the full response first
            full_response = self._get_ai4chat_response(
                conversation_prompt, country, user_id, model=model, timeout=timeout, proxies=proxies
            )

            # Track token usage
            count_tokens(conversation_prompt)
            completion_tokens = 0

            # Stream fixed-size character chunks (e.g., 48 chars)
            buffer = full_response
            chunk_size = 48
            while buffer:
                chunk_text = buffer[:chunk_size]
                buffer = buffer[chunk_size:]
                completion_tokens += count_tokens(chunk_text)

                if chunk_text.strip():
                    # Create the delta object
                    delta = ChoiceDelta(content=chunk_text, role="assistant", tool_calls=None)

                    # Create the choice object
                    choice = Choice(index=0, delta=delta, finish_reason=None, logprobs=None)

                    # Create the chunk object
                    chunk = ChatCompletionChunk(
                        id=request_id,
                        choices=[choice],
                        created=created_time,
                        model=model,
                        system_fingerprint=None,
                    )

                    yield chunk

            # Final chunk with finish_reason="stop"
            delta = ChoiceDelta(content=None, role=None, tool_calls=None)

            choice = Choice(index=0, delta=delta, finish_reason="stop", logprobs=None)

            chunk = ChatCompletionChunk(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                system_fingerprint=None,
            )

            yield chunk

        except RequestsError as e:
            print(f"Error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except Exception as e:
            print(f"Unexpected error during AI4Chat stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    def _create_non_stream(
        self,
        request_id: str,
        created_time: int,
        model: str,
        conversation_prompt: str,
        country: str,
        user_id: str,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> ChatCompletion:
        """Get a complete response from AI4Chat."""
        try:
            # Get the full response
            full_response = self._get_ai4chat_response(
                conversation_prompt, country, user_id, model=model, timeout=timeout, proxies=proxies
            )

            # Estimate token counts
            prompt_tokens = count_tokens(conversation_prompt)
            completion_tokens = count_tokens(full_response)
            total_tokens = prompt_tokens + completion_tokens

            # Create the message object
            message = ChatCompletionMessage(role="assistant", content=full_response)

            # Create the choice object
            choice = Choice(index=0, message=message, finish_reason="stop")

            # Create the usage object
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            # Create the completion object
            completion = ChatCompletion(
                id=request_id,
                choices=[choice],
                created=created_time,
                model=model,
                usage=usage,
            )

            return completion

        except RequestsError as e:
            print(f"Error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e
        except Exception as e:
            print(f"Unexpected error during AI4Chat non-stream request: {e}")
            raise IOError(f"AI4Chat request failed: {e}") from e

    def _get_ai4chat_response(
        self,
        prompt: str,
        country: str,
        user_id: str,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        proxies: Optional[dict] = None,
    ) -> str:
        """Make the actual API request to AI4Chat."""
        timeout_val = timeout if timeout is not None else self._client.timeout
        original_proxies = dict(self._client.session.proxies)
        if proxies is not None:
            self._client.session.proxies.update(cast(Any, proxies))

        # Get model name
        model_key = model or self._client.model
        if model_key not in MODELS:
            raise ValueError(
                f"Invalid model '{model_key}'. Available models: {list(MODELS.keys())[:10]}... (and {len(MODELS) - 10} more)"
            )
        model_name = MODELS[model_key]

        try:
            # URL encode parameters
            encoded_text = urllib.parse.quote(prompt)
            encoded_country = urllib.parse.quote(country)
            encoded_user_id = urllib.parse.quote(user_id)
            encoded_model = urllib.parse.quote(model_name)

            # Construct the API URL with model parameter
            url = f"{self._client.api_endpoint}?text={encoded_text}&country={encoded_country}&user_id={encoded_user_id}&model={encoded_model}"

            # Make the request
            response = self._client.session.get(
                url, headers=self._client.headers, timeout=timeout_val
            )
            response.raise_for_status()
        except RequestsError as e:
            raise IOError(f"Failed to generate response: {e}")
        finally:
            if proxies is not None:
                cast(Dict, self._client.session.proxies).clear()
                self._client.session.proxies.update(cast(Any, original_proxies))

        # Process the response text
        response_text = response.text

        # Remove surrounding quotes if present
        if response_text.startswith('"'):
            response_text = response_text[1:]
        if response_text.endswith('"'):
            response_text = response_text[:-1]

        # Replace escaped newlines
        response_text = response_text.replace("\\n", "\n").replace("\\n\\n", "\n\n")

        return response_text


class Chat(BaseChat):
    def __init__(self, client: "AI4Chat"):
        self.completions = Completions(client)


class AI4Chat(OpenAICompatibleProvider):
    """
    OpenAI-compatible client for AI4Chat API with support for multiple AI models.

    Usage:
        client = AI4Chat()
        response = client.chat.completions.create(
            model="gpt-5.2",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)

        # List available models
        print(client.models.list())
    """

    required_auth = False
    AVAILABLE_MODELS = list(MODELS.keys())
    default_model = "gpt-5.2"

    def __init__(
        self,
        system_prompt: str = "You are a helpful and informative AI assistant.",
        country: str = "Asia",
        user_id: str = "usersmjb2oaz7y",
        proxies: Optional[Dict[str, str]] = None,
        model: str = default_model,
    ):
        """
        Initialize the AI4Chat client.

        Args:
            system_prompt: System prompt to guide the AI's behavior
            country: Country parameter for API
            user_id: User ID for API
            proxies: Proxy configuration
            model: Default model to use (default: "gpt-5.2")
        """
        super().__init__(proxies=proxies)
        self.timeout = 30
        self.system_prompt = system_prompt
        self.country = country
        self.user_id = user_id

        # Validate and set default model
        if model not in MODELS:
            raise ValueError(
                f"Invalid model '{model}'. Available models: {list(MODELS.keys())[:10]}... (and {len(MODELS) - 10} more)"
            )
        self.model = model
        self.model_name = MODELS[model]

        # API endpoint
        self.api_endpoint = (
            "https://yw85opafq6.execute-api.us-east-1.amazonaws.com/default/boss_mode_15aug"
        )

        # Set headers
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "id-ID,id;q=0.9",
            "Origin": "https://www.ai4chat.co",
            "Priority": "u=1, i",
            "Referer": "https://www.ai4chat.co/",
            "Sec-CH-UA": '"Chromium";v="131", "Not_A Brand";v="24", "Microsoft Edge Simulate";v="131", "Lemur";v="131"',
            "Sec-CH-UA-Mobile": "?1",
            "Sec-CH-UA-Platform": '"Android"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": agent.random(),
        }

        # Update session headers
        self.session.headers.update(self.headers)

        # Initialize chat interface
        self.chat = Chat(self)

    @property
    def models(self) -> SimpleModelList:
        return SimpleModelList(type(self).AVAILABLE_MODELS)


if __name__ == "__main__":
    from rich import print

    # List available models
    print("[bold cyan]Available Models:[/bold cyan]")
    for model_key, model_name in list(MODELS.items())[:10]:
        print(f"  - {model_key}: {model_name}")
    print(f"  ... and {len(MODELS) - 10} more models\n")

    client = AI4Chat(model="gpt-5.2")

    print("[bold green]NON-STREAMING RESPONSE (GPT 5.2):[/bold green]")
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "user", "content": "how many r in strawberryr?"},
        ],
    )
    print(response)

    print("\n[bold green]STREAMING RESPONSE (Claude Haiku 4.5):[/bold green]")
    stream_response = client.chat.completions.create(
        model="claude-haiku-4.5",
        messages=[
            {"role": "user", "content": "Tell me a short joke."},
        ],
        stream=True,
    )
    for chunk in stream_response:
        if isinstance(chunk, ChatCompletionChunk):
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta is not None and delta.content is not None:
                    print(delta.content, end="", flush=True)
    print("\n")
