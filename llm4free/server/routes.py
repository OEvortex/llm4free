"""
API routes for the LLM4Free server.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, cast

from fastapi import Body, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from litprinter import ic
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import (
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from llm4free.search.engines import ENGINES

from .config import AppConfig
from .exceptions import APIError
from .providers import (
    get_provider_instance,
    get_tti_provider_instance,
    get_tts_provider_instance,
    resolve_provider_and_model,
    resolve_tti_provider_and_model,
    resolve_tts_provider_and_model,
)
from .request_models import (
    AnthropicMessagesRequest,
    ChatCompletionRequest,
    ImageGenerationRequest,
    ModelListResponse,
    SpeechGenerationRequest,
)
from .request_processing import (
    convert_anthropic_to_openai,
    convert_openai_chunk_to_anthropic_events,
    convert_openai_to_anthropic_response,
    handle_non_streaming_response,
    handle_streaming_response,
    log_request,
    prepare_provider_params,
    process_messages,
)


class Api:
    """API route handler class."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def register_validation_exception_handler(self):
        """Register comprehensive exception handlers."""
        from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT, HTTP_500_INTERNAL_SERVER_ERROR

        from .exceptions import APIError

        github_footer = "If you believe this is a bug, please pull an issue at https://github.com/OEvortex/LLM4Free."

        @self.app.exception_handler(APIError)
        async def api_error_handler(request, exc: APIError):
            ic.configureOutput(prefix="ERROR| ")
            ic(f"API Error: {exc.message} (Status: {exc.status_code})")
            # Patch: add footer to error content before creating JSONResponse
            error_response = exc.to_response()
            # If the response is a JSONResponse, patch its content dict before returning
            if hasattr(error_response, "body") and hasattr(error_response, "media_type"):
                # Try to decode the body to dict and add footer if possible
                try:
                    import json

                    body_bytes = (
                        bytes(error_response.body) if hasattr(error_response, "body") else b""
                    )
                    content_dict = json.loads(body_bytes.decode())
                    if "error" in content_dict:
                        content_dict["error"]["footer"] = github_footer
                        return JSONResponse(
                            status_code=error_response.status_code, content=content_dict
                        )
                except Exception:
                    pass
            return error_response

        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request, exc: RequestValidationError):
            errors = exc.errors()
            error_messages = []
            body = await request.body()
            not body or body.strip() in (b"", b"null", b"{}")
            for error in errors:
                loc = error.get("loc", [])
                loc_str = " -> ".join(str(item) for item in loc)
                msg = error.get("msg", "Validation error")
                error_messages.append(
                    {
                        "loc": loc,
                        "message": f"{msg} at {loc_str}",
                        "type": error.get("type", "validation_error"),
                    }
                )
            content = {
                "error": {
                    "message": "Request validation error.",
                    "details": error_messages,
                    "type": "validation_error",
                    "footer": github_footer,
                }
            }
            return JSONResponse(status_code=HTTP_422_UNPROCESSABLE_CONTENT, content=content)

        @self.app.exception_handler(StarletteHTTPException)
        async def http_exception_handler(request, exc: StarletteHTTPException):
            content = {
                "error": {
                    "message": exc.detail or "HTTP error occurred.",
                    "type": "http_error",
                    "footer": github_footer,
                }
            }
            return JSONResponse(status_code=exc.status_code, content=content)

        @self.app.exception_handler(Exception)
        async def general_exception_handler(request, exc: Exception):
            ic.configureOutput(prefix="ERROR| ")
            ic(f"Unhandled server error: {exc}")
            content = {
                "error": {
                    "message": f"Internal server error: {str(exc)}",
                    "type": "server_error",
                    "footer": github_footer,
                }
            }
            return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content=content)

    def register_routes(self):
        """Register all API routes."""
        self._register_health_route()
        self._register_model_routes()
        self._register_chat_routes()
        self._register_anthropic_routes()
        self._register_image_routes()
        self._register_tts_routes()
        self._register_websearch_routes()

    def _register_health_route(self):
        """Register health check route."""

        @self.app.get("/monitor/health", include_in_schema=False)
        async def health_check():
            """Health check endpoint for monitoring."""
            return {"status": "healthy", "service": "llm4free-api", "version": "0.2.0"}

    def _register_model_routes(self):
        """Register model listing routes."""

        @self.app.get(
            "/v1/models",
            response_model=ModelListResponse,
            tags=["Chat Completions"],
            description="List all available chat completion models.",
        )
        async def list_models():
            models = []
            for model_name, provider_class in AppConfig.provider_map.items():
                if "/" not in model_name:
                    continue  # Skip provider names
                if any(m["id"] == model_name for m in models):
                    continue
                models.append(
                    {
                        "id": model_name,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "llm4free",  # Set owned_by to llm4free
                    }
                )
            # Sort models alphabetically by the part after the first '/'
            models = sorted(models, key=lambda m: str(m["id"]).split("/", 1)[1].lower())
            return {"object": "list", "data": models}

        @self.app.get(
            "/v1/models/{model}",
            response_model=dict,
            tags=["Chat Completions"],
            description="Retrieve model instance details.",
        )
        async def retrieve_model(model: str):
            """Retrieve model instance details."""
            try:
                # Check if model resolves to a valid provider/model pair
                resolve_provider_and_model(model)
                return {
                    "id": model,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "llm4free",
                }
            except APIError:
                raise
            except Exception:
                raise APIError(f"Model {model} not found", 404, "model_not_found", param="model")

        @self.app.get(
            "/v1/providers",
            tags=["Chat Completions"],
            description="Get details about available chat completion providers including supported models and parameters.",
        )
        async def list_providers():
            """Get information about all available chat completion providers."""
            providers = {}

            # Extract unique provider names (exclude model mappings)
            provider_names = set()
            for key, provider_class in AppConfig.provider_map.items():
                if "/" not in key:  # Provider name, not model mapping
                    provider_names.add(key)

            for provider_name in sorted(provider_names):
                provider_class = AppConfig.provider_map[provider_name]

                # Get available models for this provider
                models = []
                for key, cls in AppConfig.provider_map.items():
                    if key.startswith(f"{provider_name}/"):
                        model_name = key.split("/", 1)[1]
                        models.append(model_name)

                # Sort models
                models = sorted(models)

                # Get supported parameters (common OpenAI-compatible parameters)
                supported_params = [
                    "model",
                    "messages",
                    "max_tokens",
                    "temperature",
                    "top_p",
                    "presence_penalty",
                    "frequency_penalty",
                    "stop",
                    "stream",
                    "user",
                ]

                providers[provider_name] = {
                    "name": provider_name,
                    "class": provider_class.__name__,
                    "models": models,
                    "parameters": supported_params,
                    "model_count": len(models),
                }

            return {"providers": providers, "total_providers": len(providers)}

        @self.app.get(
            "/v1/TTI/models",
            response_model=ModelListResponse,
            tags=["Image Generation"],
            description="List all available text-to-image (TTI) models.",
        )
        async def list_tti_models():
            models = []
            for model_name, provider_class in AppConfig.tti_provider_map.items():
                if "/" not in model_name:
                    continue  # Skip provider names
                if any(m["id"] == model_name for m in models):
                    continue
                models.append(
                    {
                        "id": model_name,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "llm4free",  # Set owned_by to llm4free
                    }
                )
            # Sort models alphabetically by the part after the first '/'
            models = sorted(models, key=lambda m: str(m["id"]).split("/", 1)[1].lower())
            return {"object": "list", "data": models}

        @self.app.get(
            "/v1/TTI/providers",
            tags=["Image Generation"],
            description="Get details about available text-to-image (TTI) providers including supported models and parameters.",
        )
        async def list_tti_providers():
            """Get information about all available TTI providers."""
            providers = {}

            # Extract unique provider names (exclude model mappings)
            provider_names = set()
            for key, provider_class in AppConfig.tti_provider_map.items():
                if "/" not in key:  # Provider name, not model mapping
                    provider_names.add(key)

            for provider_name in sorted(provider_names):
                provider_class = AppConfig.tti_provider_map[provider_name]

                # Get available models for this provider
                models = []
                for key, cls in AppConfig.tti_provider_map.items():
                    if key.startswith(f"{provider_name}/"):
                        model_name = key.split("/", 1)[1]
                        models.append(model_name)

                # Sort models
                models = sorted(models)

                # Get supported parameters (common TTI parameters)
                supported_params = [
                    "prompt",
                    "model",
                    "n",
                    "size",
                    "response_format",
                    "user",
                    "style",
                    "aspect_ratio",
                    "timeout",
                    "image_format",
                    "seed",
                ]

                providers[provider_name] = {
                    "name": provider_name,
                    "class": provider_class.__name__,
                    "models": models,
                    "parameters": supported_params,
                    "model_count": len(models),
                }

            return {"providers": providers, "total_providers": len(providers)}

    def _register_chat_routes(self):
        """Register chat completion routes."""

        @self.app.post(
            "/v1/chat/completions",
            response_model_exclude_none=True,
            response_model_exclude_unset=True,
            tags=["Chat Completions"],
            description="Generate chat completions using the specified model.",
            openapi_extra={
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ChatCompletionRequest"},
                            "example": cast(Dict[str, Any], ChatCompletionRequest.model_config)[
                                "json_schema_extra"
                            ]["example"],
                        }
                    }
                }
            },
        )
        async def chat_completions(
            request: Request, chat_request: ChatCompletionRequest = Body(...)
        ):
            """Handle chat completion requests with comprehensive error handling."""
            start_time = time.time()
            request_id = f"chatcmpl-{uuid.uuid4()}"

            try:
                ic.configureOutput(prefix="INFO| ")
                ic(
                    f"Processing chat completion request {request_id} for model: {chat_request.model}"
                )

                # Resolve provider and model
                provider_class, model_name = resolve_provider_and_model(chat_request.model)

                # Initialize provider with caching and error handling
                try:
                    provider = get_provider_instance(provider_class)
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Using provider instance: {provider_class.__name__}")
                except Exception as e:
                    ic.configureOutput(prefix="ERROR| ")
                    ic(f"Failed to initialize provider {provider_class.__name__}: {e}")
                    raise APIError(
                        f"Failed to initialize provider {provider_class.__name__}: {e}",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "provider_error",
                    )

                # Process and validate messages
                processed_messages = process_messages(chat_request.messages)

                # Prepare parameters for provider
                params = prepare_provider_params(
                    chat_request,
                    model_name,
                    processed_messages,
                    provider_class.__name__,
                )

                # Extract client IP address
                client_ip = request.client.host if request.client else "unknown"
                if "x-forwarded-for" in request.headers:
                    client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
                elif "x-real-ip" in request.headers:
                    client_ip = request.headers["x-real-ip"]

                # Extract question from messages (last user message)
                question = ""
                for msg in reversed(processed_messages):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            question = content
                        elif isinstance(content, list) and content:
                            # Handle content with multiple parts (text, images, etc.)
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    question = part.get("text", "")
                                    break
                        break

                # Handle streaming vs non-streaming
                if chat_request.stream:
                    return await handle_streaming_response(
                        provider,
                        params,
                        request_id,
                        client_ip,
                        question,
                        model_name,
                        start_time,
                        provider_class.__name__,
                        request,
                    )
                else:
                    return await handle_non_streaming_response(
                        provider,
                        params,
                        request_id,
                        start_time,
                        client_ip,
                        question,
                        model_name,
                        provider_class.__name__,
                        request,
                    )

            except APIError:
                # Re-raise API errors as-is
                raise
            except Exception as e:
                ic.configureOutput(prefix="ERROR| ")
                ic(f"Unexpected error in chat completion {request_id}: {e}")
                raise APIError(
                    f"Internal server error: {str(e)}",
                    HTTP_500_INTERNAL_SERVER_ERROR,
                    "internal_error",
                )

    def _register_anthropic_routes(self):
        """Register Anthropic-compatible routes."""

        @self.app.post(
            "/v1/messages",
            tags=["Anthropic Messages"],
            description="Generate messages using the Anthropic-compatible API format.",
        )
        async def anthropic_messages(
            request: Request, anthropic_request: AnthropicMessagesRequest = Body(...)
        ):
            """Handle Anthropic Messages API requests."""
            start_time = time.time()
            request_id = f"msg_{uuid.uuid4().hex[:24]}"

            try:
                ic.configureOutput(prefix="INFO| ")
                ic(
                    f"Processing Anthropic messages request {request_id} for model: {anthropic_request.model}"
                )

                # Convert Anthropic request to OpenAI format
                openai_params = convert_anthropic_to_openai(anthropic_request)

                # Resolve provider and model
                provider_class, model_name = resolve_provider_and_model(openai_params["model"])

                # Initialize provider
                try:
                    provider = get_provider_instance(provider_class)
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Using provider instance: {provider_class.__name__}")
                except Exception as e:
                    ic.configureOutput(prefix="ERROR| ")
                    ic(f"Failed to initialize provider {provider_class.__name__}: {e}")
                    raise APIError(
                        f"Failed to initialize provider {provider_class.__name__}: {e}",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "provider_error",
                    )

                # Update model name in params
                openai_params["model"] = model_name

                # Extract client IP
                client_ip = request.client.host if request.client else "unknown"
                if "x-forwarded-for" in request.headers:
                    client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
                elif "x-real-ip" in request.headers:
                    client_ip = request.headers["x-real-ip"]

                # Extract question from messages
                question = ""
                for msg in reversed(openai_params.get("messages", [])):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            question = content
                        break

                # Handle streaming
                if anthropic_request.stream:
                    return await _handle_anthropic_streaming_response(
                        provider,
                        openai_params,
                        request_id,
                        client_ip,
                        question,
                        model_name,
                        start_time,
                        provider_class.__name__,
                        request,
                        anthropic_request.model,
                    )
                else:
                    return await _handle_anthropic_non_streaming_response(
                        provider,
                        openai_params,
                        request_id,
                        start_time,
                        client_ip,
                        question,
                        model_name,
                        provider_class.__name__,
                        request,
                        anthropic_request.model,
                    )

            except APIError:
                raise
            except Exception as e:
                ic.configureOutput(prefix="ERROR| ")
                ic(f"Unexpected error in Anthropic messages {request_id}: {e}")
                raise APIError(
                    f"Internal server error: {str(e)}",
                    HTTP_500_INTERNAL_SERVER_ERROR,
                    "internal_error",
                )

        @self.app.get(
            "/v1/messages",
            tags=["Anthropic Messages"],
            description="List available models (Anthropic-compatible endpoint).",
        )
        async def anthropic_list_models():
            """List available models in Anthropic-compatible format."""
            models = []
            for model_name, provider_class in AppConfig.provider_map.items():
                if "/" not in model_name:
                    continue
                if any(m["id"] == model_name for m in models):
                    continue
                models.append(
                    {
                        "id": model_name,
                        "type": "model",
                        "display_name": model_name.split("/", 1)[1],
                        "created_at": int(time.time()),
                    }
                )
            models = sorted(models, key=lambda m: str(m["id"]).split("/", 1)[1].lower())
            return {"data": models}

    def _register_image_routes(self):
        """Register image generation routes."""

        @self.app.post(
            "/v1/images/generations",
            tags=["Image Generation"],
            description="Generate images from text prompts using the specified TTI model.",
        )
        async def image_generations(image_request: ImageGenerationRequest = Body(...)):
            """Handle image generation requests."""
            start_time = time.time()
            request_id = f"img-{uuid.uuid4()}"

            try:
                ic.configureOutput(prefix="INFO| ")
                ic(
                    f"Processing image generation request {request_id} for model: {image_request.model}"
                )

                # Resolve TTI provider and model
                provider_class, model_name = resolve_tti_provider_and_model(image_request.model)

                # Initialize TTI provider
                try:
                    provider = get_tti_provider_instance(provider_class)
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Using TTI provider instance: {provider_class.__name__}")
                except APIError as e:
                    # Add helpful footer for provider errors
                    return JSONResponse(
                        status_code=e.status_code,
                        content={
                            "error": {
                                "message": e.message,
                                "type": e.error_type,
                                "footer": "If you believe this is a bug, please pull an issue at https://github.com/OEvortex/LLM4Free.",
                            }
                        },
                    )
                except Exception as e:
                    ic.configureOutput(prefix="ERROR| ")
                    ic(f"Failed to initialize TTI provider {provider_class.__name__}: {e}")
                    raise APIError(
                        f"Failed to initialize TTI provider {provider_class.__name__}: {e}",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "provider_error",
                    )

                # Prepare parameters for TTI provider
                params = {
                    "prompt": image_request.prompt,
                    "model": model_name,
                    "n": image_request.n,
                    "size": image_request.size,
                    "response_format": image_request.response_format,
                }

                # Add optional parameters
                optional_params = [
                    "user",
                    "style",
                    "aspect_ratio",
                    "timeout",
                    "image_format",
                    "seed",
                ]
                for param in optional_params:
                    value = getattr(image_request, param, None)
                    if value is not None:
                        params[param] = value

                # Generate images
                response = provider.images.create(**params)

                # Standardize response format
                if hasattr(response, "model_dump"):
                    response_data = response.model_dump(exclude_none=True)
                elif hasattr(response, "dict"):
                    response_data = response.dict(exclude_none=True)
                elif isinstance(response, dict):
                    response_data = response
                else:
                    raise APIError(
                        "Invalid response format from TTI provider",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "provider_error",
                    )

                elapsed = time.time() - start_time
                ic.configureOutput(prefix="INFO| ")
                ic(f"Completed image generation request {request_id} in {elapsed:.2f}s")

                return response_data
            except APIError:
                raise
            except Exception as e:
                ic.configureOutput(prefix="ERROR| ")
                ic(f"Unexpected error in image generation {request_id}: {e}")
                raise APIError(
                    f"Internal server error: {str(e)}",
                    HTTP_500_INTERNAL_SERVER_ERROR,
                    "internal_error",
                )

    def _register_tts_routes(self):
        """Register TTS (text-to-speech) endpoints."""

        @self.app.get(
            "/v1/TTS/models",
            response_model=ModelListResponse,
            tags=["Audio Generation"],
            description="List all available text-to-speech (TTS) models.",
        )
        async def list_tts_models():
            models = []
            for model_name, provider_class in AppConfig.tts_provider_map.items():
                if "/" not in model_name:
                    continue  # Skip provider names
                if any(m["id"] == model_name for m in models):
                    continue
                models.append(
                    {
                        "id": model_name,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "llm4free",  # Set owned_by to llm4free
                    }
                )
            # Sort models alphabetically by the part after the first '/'
            models = sorted(models, key=lambda m: str(m["id"]).split("/", 1)[1].lower())
            return {"object": "list", "data": models}

        @self.app.get(
            "/v1/TTS/providers",
            tags=["Audio Generation"],
            description="Get details about available text-to-speech (TTS) providers including supported models and parameters.",
        )
        async def list_tts_providers():
            """Get information about all available TTS providers."""
            providers = {}

            # Extract unique provider names (exclude model mappings)
            provider_names = set()
            for key, provider_class in AppConfig.tts_provider_map.items():
                if "/" not in key:  # Provider name, not model mapping
                    provider_names.add(key)

            for provider_name in sorted(provider_names):
                provider_class = AppConfig.tts_provider_map[provider_name]

                # Get available models for this provider
                models = []
                for key, cls in AppConfig.tts_provider_map.items():
                    if key.startswith(f"{provider_name}/"):
                        model_name = key.split("/", 1)[1]
                        models.append(model_name)

                # Sort models
                models = sorted(models)

                # Get supported parameters (common TTS parameters)
                supported_params = [
                    "input",
                    "model",
                    "voice",
                    "response_format",
                    "instructions",
                    "stream",
                ]

                providers[provider_name] = {
                    "name": provider_name,
                    "class": provider_class.__name__,
                    "models": models,
                    "parameters": supported_params,
                    "model_count": len(models),
                }

            return {"providers": providers, "total_providers": len(providers)}

        @self.app.post(
            "/v1/audio/speech",
            tags=["Audio Generation"],
            description="Generate audio from text using the specified TTS model.",
        )
        async def audio_speech(speech_request: SpeechGenerationRequest = Body(...)):
            """Handle speech generation requests."""
            start_time = time.time()
            request_id = f"tts-{uuid.uuid4()}"

            try:
                ic.configureOutput(prefix="INFO| ")
                ic(
                    f"Processing speech generation request {request_id} for model: {speech_request.model}"
                )

                # Resolve TTS provider and model
                provider_class, model_name = resolve_tts_provider_and_model(speech_request.model)

                # Initialize TTS provider
                try:
                    provider = get_tts_provider_instance(provider_class)
                    ic.configureOutput(prefix="DEBUG| ")
                    ic(f"Using TTS provider instance: {provider_class.__name__}")
                except APIError as e:
                    return JSONResponse(
                        status_code=e.status_code,
                        content={
                            "error": {
                                "message": e.message,
                                "type": e.error_type,
                                "footer": "If you believe this is a bug, please pull an issue at https://github.com/OEvortex/LLM4Free.",
                            }
                        },
                    )
                except Exception as e:
                    ic.configureOutput(prefix="ERROR| ")
                    ic(f"Failed to initialize TTS provider {provider_class.__name__}: {e}")
                    raise APIError(
                        f"Failed to initialize TTS provider {provider_class.__name__}: {e}",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "provider_error",
                    )

                # Prepare parameters for TTS provider
                params: Dict[str, Any] = {
                    "input_text": speech_request.input,
                    "model": model_name,
                    "voice": speech_request.voice,
                    "response_format": speech_request.response_format,
                    "verbose": False,
                }

                # Add optional parameters
                if speech_request.instructions is not None:
                    params["instructions"] = speech_request.instructions

                # Generate audio
                audio_file = provider.create_speech(**params)

                if not audio_file or not Path(audio_file).exists():
                    raise APIError(
                        "Failed to generate audio file",
                        HTTP_500_INTERNAL_SERVER_ERROR,
                        "generation_failed",
                    )

                elapsed = time.time() - start_time
                ic.configureOutput(prefix="INFO| ")
                ic(f"Completed speech generation request {request_id} in {elapsed:.2f}s")

                # Determine content type based on format
                content_type_map: Dict[str, str] = {
                    "mp3": "audio/mpeg",
                    "opus": "audio/opus",
                    "aac": "audio/aac",
                    "flac": "audio/flac",
                    "wav": "audio/wav",
                    "pcm": "audio/pcm",
                }
                content_type = content_type_map.get(
                    speech_request.response_format or "mp3", "audio/mpeg"
                )

                if speech_request.stream:
                    # Stream the audio file
                    def audio_stream():
                        with open(audio_file, "rb") as f:
                            while chunk := f.read(8192):
                                yield chunk

                    return StreamingResponse(
                        audio_stream(),
                        media_type=content_type,
                        headers={
                            "Content-Disposition": f'attachment; filename="speech.{speech_request.response_format}"'
                        },
                    )
                else:
                    return FileResponse(
                        audio_file,
                        media_type=content_type,
                        filename=f"speech.{speech_request.response_format}",
                    )

            except APIError:
                raise
            except Exception as e:
                ic.configureOutput(prefix="ERROR| ")
                ic(f"Unexpected error in speech generation {request_id}: {e}")
                raise APIError(
                    f"Internal server error: {str(e)}",
                    HTTP_500_INTERNAL_SERVER_ERROR,
                    "internal_error",
                )

    def _register_websearch_routes(self):
        """Register web search endpoint."""

        @self.app.get(
            "/search",
            tags=["Web search"],
            description="Unified web search endpoint supporting all available search engines with various search types including text, news, images, videos (Brave, DuckDuckGo, Yahoo), suggestions (Brave, Bing, DuckDuckGo, Yep, Yahoo), answers, maps, translate, and weather.",
        )
        async def websearch(
            q: str = Query(..., description="Search query"),
            engine: str = Query(
                "duckduckgo",
                description=f"Search engine: {', '.join(sorted(set(name for cat in ENGINES.values() for name in cat)))}",
            ),
            max_results: int = Query(10, description="Maximum number of results"),
            region: str = Query("all", description="Region code (optional)"),
            safesearch: str = Query("moderate", description="Safe search: on, moderate, off"),
            type: str = Query(
                "text",
                description="Search type: text, news, images, videos, suggestions, answers, maps, translate, weather",
            ),
            place: str = Query(None, description="Place for maps search"),
            street: str = Query(None, description="Street for maps search"),
            city: str = Query(None, description="City for maps search"),
            county: str = Query(None, description="County for maps search"),
            state: str = Query(None, description="State for maps search"),
            country: str = Query(None, description="Country for maps search"),
            postalcode: str = Query(None, description="Postal code for maps search"),
            latitude: str = Query(None, description="Latitude for maps search"),
            longitude: str = Query(None, description="Longitude for maps search"),
            radius: int = Query(0, description="Radius for maps search"),
            from_: str = Query(None, description="Source language for translate"),
            to: str = Query("en", description="Target language for translate"),
            language: str = Query("en", description="Language for weather"),
        ):
            """Unified web search endpoint."""
            github_footer = "If you believe this is a bug, please pull an issue at https://github.com/OEvortex/LLM4Free."
            try:
                # Dynamically support all engines in ENGINES
                found = False
                for category, engines in ENGINES.items():
                    if engine in engines:
                        found = True
                        engine_cls = engines[engine]
                        searcher = engine_cls()
                        # Try to call the appropriate method based on 'type'
                        if hasattr(searcher, "run"):
                            method = getattr(searcher, "run")
                            # Some engines may require different params
                            try:
                                if type in ("text", "images", "news", "videos"):
                                    results = method(
                                        keywords=q,
                                        region=region,
                                        safesearch=safesearch,
                                        max_results=max_results,
                                    )
                                elif type == "suggestions":
                                    # Suggestions method might have different signature
                                    try:
                                        results = method(q, region=region, max_results=max_results)
                                    except TypeError:
                                        results = method(q, max_results=max_results)
                                elif type == "answers":
                                    results = method(keywords=q)
                                elif type == "maps":
                                    results = method(
                                        keywords=q,
                                        place=place,
                                        street=street,
                                        city=city,
                                        county=county,
                                        state=state,
                                        country=country,
                                        postalcode=postalcode,
                                        latitude=latitude,
                                        longitude=longitude,
                                        radius=radius,
                                        max_results=max_results,
                                    )
                                elif type == "translate":
                                    results = method(keywords=q, from_=from_, to=to)
                                elif type == "weather":
                                    results = method(location=q, language=language)
                                else:
                                    return {
                                        "error": f"{engine} does not support type '{type}'.",
                                        "footer": github_footer,
                                    }
                                # Try to serialize results if needed
                                if (
                                    isinstance(results, list)
                                    and results
                                    and hasattr(results[0], "__dict__")
                                ):
                                    results = [r.__dict__ for r in results]
                                return {"engine": engine, "type": type, "results": results}
                            except Exception as ex:
                                return {
                                    "error": f"Error running {engine}.{type}: {ex}",
                                    "footer": github_footer,
                                }
                        else:
                            return {
                                "error": f"{engine} does not support type '{type}'.",
                                "footer": github_footer,
                            }
                if not found:
                    return {
                        "error": f"Unknown engine. Use one of: {', '.join(sorted(set(name for cat in ENGINES.values() for name in cat)))}.",
                        "footer": github_footer,
                    }
            except Exception as e:
                # Special handling for rate limit errors
                msg = str(e)
                if "429" in msg or "rate limit" in msg.lower():
                    return {
                        "error": "You have hit the search rate limit. Please try again later.",
                        "details": msg,
                        "code": 429,
                        "footer": github_footer,
                    }
                return {"error": f"Search request failed: {msg}", "footer": github_footer}

        @self.app.get(
            "/search/provider",
            tags=["Web search"],
            description="Get details about available search providers including supported categories and parameters.",
        )
        async def get_search_providers():
            """Get information about all available search providers."""
            providers = {}

            # Collect all unique engine names
            all_engines = set()
            for category_engines in ENGINES.values():
                all_engines.update(category_engines.keys())

            for engine_name in sorted(all_engines):
                # Find all categories this engine supports
                categories = []
                for category, engines in ENGINES.items():
                    if engine_name in engines:
                        categories.append(category)

                # Get supported parameters based on categories
                supported_params = ["q"]  # query is always supported

                if (
                    "text" in categories
                    or "images" in categories
                    or "news" in categories
                    or "videos" in categories
                ):
                    supported_params.extend(["max_results", "region", "safesearch"])

                if "suggestions" in categories:
                    supported_params.extend(["region"])

                if "maps" in categories:
                    supported_params.extend(
                        [
                            "place",
                            "street",
                            "city",
                            "county",
                            "state",
                            "country",
                            "postalcode",
                            "latitude",
                            "longitude",
                            "radius",
                            "max_results",
                        ]
                    )

                if "translate" in categories:
                    supported_params.extend(["from_", "to"])

                if "weather" in categories:
                    supported_params.extend(["language"])

                # Remove duplicates
                supported_params = list(set(supported_params))

                providers[engine_name] = {
                    "name": engine_name,
                    "categories": sorted(categories),
                    "supported_types": sorted(categories),  # types are the same as categories
                    "parameters": sorted(supported_params),
                }

            return {"providers": providers, "total_providers": len(providers)}


# ============================================================================
# Anthropic Response Handler Functions
# ============================================================================


async def _handle_anthropic_streaming_response(
    provider: Any,
    params: Dict[str, Any],
    request_id: str,
    ip_address: str,
    question: str,
    model_name: str,
    start_time: float,
    provider_name: Optional[str],
    request_obj: Any,
    anthropic_model: str,
) -> StreamingResponse:
    """Handle streaming response in Anthropic format."""
    collected_content = []

    async def streaming():
        nonlocal collected_content
        try:
            ic.configureOutput(prefix="DEBUG| ")
            ic(f"Starting Anthropic streaming response for request {request_id}")
            completion_stream = provider.chat.completions.create(**params)

            is_first_chunk = True

            if hasattr(completion_stream, "__iter__") and not isinstance(
                completion_stream, (str, bytes, dict)
            ):
                try:
                    for chunk in completion_stream:
                        model_dump = getattr(chunk, "model_dump", None)
                        model_dict = getattr(chunk, "dict", None)
                        if model_dump and callable(model_dump):
                            chunk_data = model_dump(exclude_none=True)
                        elif model_dict and callable(model_dict):
                            chunk_data = model_dict(exclude_none=True)
                        elif isinstance(chunk, dict):
                            chunk_data = chunk
                        else:
                            chunk_data = chunk

                        # Collect content for logging
                        if isinstance(chunk_data, dict) and "choices" in chunk_data:
                            for choice in chunk_data.get("choices", []):
                                if isinstance(choice, dict):
                                    delta = choice.get("delta", {})
                                    content = delta.get("content")
                                    if content:
                                        collected_content.append(content)

                        # Convert to Anthropic events
                        events = convert_openai_chunk_to_anthropic_events(
                            chunk_data, anthropic_model, is_first_chunk
                        )
                        is_first_chunk = False

                        for event in events:
                            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                except TypeError:
                    # Fall back to non-generator response
                    model_dump = getattr(completion_stream, "model_dump", None)
                    model_dict = getattr(completion_stream, "dict", None)
                    if model_dump and callable(model_dump):
                        response_data = model_dump(exclude_none=True)
                    elif model_dict and callable(model_dict):
                        response_data = model_dict(exclude_none=True)
                    else:
                        response_data = completion_stream

                    events = convert_openai_chunk_to_anthropic_events(
                        response_data, anthropic_model, True
                    )
                    for event in events:
                        yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            else:
                # Non-generator response
                model_dump = getattr(completion_stream, "model_dump", None)
                model_dict = getattr(completion_stream, "dict", None)
                if model_dump and callable(model_dump):
                    response_data = model_dump(exclude_none=True)
                elif model_dict and callable(model_dict):
                    response_data = model_dict(exclude_none=True)
                else:
                    response_data = completion_stream

                events = convert_openai_chunk_to_anthropic_events(
                    response_data, anthropic_model, True
                )
                for event in events:
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            ic.configureOutput(prefix="ERROR| ")
            ic(f"Error in Anthropic streaming response for request {request_id}: {e}")
            error_event = {"type": "error", "error": {"type": "api_error", "message": str(e)}}
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"

        finally:
            yield "event: message_stop\ndata: {}\n\n"

            # Log request
            if collected_content:
                answer = "".join(collected_content)
                response_time_ms = int((time.time() - start_time) * 1000)
                await log_request(
                    request_id=request_id,
                    ip_address=ip_address,
                    model_used=model_name,
                    question=question,
                    answer=answer,
                    response_time_ms=response_time_ms,
                    status_code=200,
                    provider=provider_name,
                    request_obj=request_obj,
                )

    return StreamingResponse(streaming(), media_type="text/event-stream")


async def _handle_anthropic_non_streaming_response(
    provider: Any,
    params: Dict[str, Any],
    request_id: str,
    start_time: float,
    ip_address: str,
    question: str,
    model_name: str,
    provider_name: Optional[str],
    request_obj: Any,
    anthropic_model: str,
) -> Dict[str, Any]:
    """Handle non-streaming response in Anthropic format."""
    try:
        ic.configureOutput(prefix="DEBUG| ")
        ic(f"Starting Anthropic non-streaming response for request {request_id}")

        # Ensure stream is False for non-streaming
        params["stream"] = False
        completion = provider.chat.completions.create(**params)

        if completion is None:
            return {
                "id": f"msg_{request_id}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "No response generated."}],
                "model": anthropic_model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

        # Convert to Anthropic format
        if hasattr(completion, "model_dump"):
            response_data = completion.model_dump(exclude_none=True)
        elif hasattr(completion, "dict"):
            response_data = completion.dict(exclude_none=True)
        elif isinstance(completion, dict):
            response_data = completion
        else:
            raise APIError(
                "Invalid response format from provider",
                HTTP_500_INTERNAL_SERVER_ERROR,
                "provider_error",
            )

        anthropic_response = convert_openai_to_anthropic_response(response_data, anthropic_model)

        elapsed = time.time() - start_time
        response_time_ms = int(elapsed * 1000)
        ic.configureOutput(prefix="INFO| ")
        ic(f"Completed Anthropic non-streaming request {request_id} in {elapsed:.2f}s")

        # Log request
        answer = ""
        for block in anthropic_response.get("content", []):
            if block.get("type") == "text":
                answer += block.get("text", "")

        await log_request(
            request_id=request_id,
            ip_address=ip_address,
            model_used=model_name,
            question=question,
            answer=answer,
            response_time_ms=response_time_ms,
            status_code=200,
            provider=provider_name,
            request_obj=request_obj,
        )

        return anthropic_response

    except Exception as e:
        ic.configureOutput(prefix="ERROR| ")
        ic(f"Error in Anthropic non-streaming response for request {request_id}: {e}")
        error_message = str(e)

        await log_request(
            request_id=request_id,
            ip_address=ip_address,
            model_used=model_name,
            question=question,
            answer="",
            response_time_ms=int((time.time() - start_time) * 1000),
            status_code=500,
            error_message=error_message,
            provider=provider_name,
            request_obj=request_obj,
        )

        raise APIError(
            f"Provider error: {error_message}", HTTP_500_INTERNAL_SERVER_ERROR, "provider_error"
        )
