from litprinter import ic
import importlib
import pkgutil
from typing import Any, Dict, List, Mapping, Optional, Union, cast

from llm4free.AIbase import Provider, TTSProvider


# Import TTI base class
BaseImages = None
try:
    from llm4free.TTI.base import BaseImages as BaseImagesClass

    BaseImages = BaseImagesClass
    TTI_AVAILABLE = True
except ImportError:
    TTI_AVAILABLE = False


class _LLMModels:
    """
    A class for managing LLM provider models in the llm4free package.
    """

    def list(self) -> Dict[str, List[str]]:
        """
        Gets all available models from each provider that has an AVAILABLE_MODELS attribute.

        Returns:
            Dictionary mapping provider names to their available models
        """
        return self._get_provider_models()

    def get(self, provider_name: str) -> List[str]:
        """
        Gets all available models for a specific provider.

        Args:
            provider_name: The name of the provider

        Returns:
            List of available models for the provider
        """
        all_models = self._get_provider_models()
        return all_models.get(provider_name, [])

    def summary(self) -> Dict[str, Any]:
        """
        Returns a summary of available providers and models.

        Returns:
            Dictionary with provider and model counts
        """
        provider_models = self._get_provider_models()
        total_providers = len(provider_models)
        total_models = sum(
            len(models) if isinstance(models, (list, tuple, set)) else 1
            for models in provider_models.values()
        )

        return {
            "providers": total_providers,
            "models": total_models,
            "provider_model_counts": {
                provider: len(models) if isinstance(models, (list, tuple, set)) else 1
                for provider, models in provider_models.items()
            },
        }

    def providers(self) -> Dict[str, Dict[str, Any]]:
        """
        Gets detailed information about all LLM providers including models, parameters, and metadata.

        Returns:
            Dictionary mapping provider names to detailed provider information
        """
        return self._get_provider_details()

    def provider(self, provider_name: str) -> Dict[str, Any]:
        """
        Gets detailed information about a specific LLM provider.

        Args:
            provider_name: The name of the provider

        Returns:
            Dictionary with detailed provider information
        """
        all_providers = self._get_provider_details()
        return all_providers.get(provider_name, {})

    def _get_provider_models(self) -> Dict[str, List[str]]:
        """
        Internal method to get all available models from each provider.

        Returns:
            Dictionary mapping provider names to their available models
        """
        provider_models = {}
        provider_packages = ["llm4free.llm", "llm4free.AISEARCH", "llm4free.STT"]

        for package_name in provider_packages:
            try:
                package = importlib.import_module(package_name)
                for _, module_name, _ in pkgutil.iter_modules(package.__path__):
                    try:
                        module = importlib.import_module(f"{package_name}.{module_name}")
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type):
                                get_models = getattr(attr, "get_models", None)
                                available_models = getattr(attr, "AVAILABLE_MODELS", None)
                                if callable(get_models):
                                    try:
                                        models = get_models()
                                        if isinstance(models, set):
                                            models = list(models)
                                        provider_models[attr_name] = cast(List[str], models)
                                    except Exception:
                                        provider_models[attr_name] = []
                                elif isinstance(available_models, (list, tuple, set)):
                                    provider_models[attr_name] = list(available_models)
                    except (ImportError, AttributeError):
                        pass
            except (ImportError, ValueError):
                pass

        return provider_models

    def _get_provider_details(self) -> Dict[str, Dict[str, Any]]:
        """
        Internal method to get detailed information about all LLM providers.

        Returns:
            Dictionary mapping provider names to detailed provider information
        """
        provider_details = {}
        provider_packages = ["llm4free.llm", "llm4free.AISEARCH", "llm4free.STT"]

        for package_name in provider_packages:
            try:
                package = importlib.import_module(package_name)
                for _, module_name, _ in pkgutil.iter_modules(package.__path__):
                    try:
                        module = importlib.import_module(f"{package_name}.{module_name}")
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type):
                                # Get available models
                                models = []
                                get_models = getattr(attr, "get_models", None)
                                available_models = getattr(attr, "AVAILABLE_MODELS", None)
                                if callable(get_models):
                                    try:
                                        fetched_models = get_models()
                                        if isinstance(fetched_models, set):
                                            models = list(fetched_models)
                                        elif isinstance(fetched_models, (list, tuple)):
                                            models = list(fetched_models)
                                        else:
                                            models = [str(fetched_models)] if fetched_models else []
                                    except Exception:
                                        models = []
                                elif isinstance(available_models, (list, tuple, set)):
                                    models = list(available_models)
                                else:
                                    continue

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

                                # Get additional metadata
                                metadata = {}
                                if hasattr(attr, "__doc__") and attr.__doc__:
                                    metadata["description"] = attr.__doc__.strip().split("\n")[0]

                                provider_details[attr_name] = {
                                    "name": attr_name,
                                    "class": attr.__name__,
                                    "module": module_name,
                                    "models": models,
                                    "parameters": supported_params,
                                    "model_count": len(models),
                                    "metadata": metadata,
                                }
                    except (ImportError, AttributeError):
                        pass
            except (ImportError, ValueError):
                pass

        return provider_details


class _TTSModels:
    """
    A class for managing TTS provider voices in the llm4free package.
    """

    def list(self) -> Dict[str, Union[List[str], Dict[str, str]]]:
        """
        Gets all available voices from each TTS provider that has an all_voices attribute.

        Returns:
            Dictionary mapping TTS provider names to their available voices
        """
        return self._get_tts_voices()

    def get(self, provider_name: str) -> Union[List[str], Dict[str, str]]:
        """
        Gets all available voices for a specific TTS provider.

        Args:
            provider_name: The name of the TTS provider

        Returns:
            List or Dictionary of available voices for the provider
        """
        all_voices = self._get_tts_voices()
        return all_voices.get(provider_name, [])

    def summary(self) -> Dict[str, Any]:
        """
        Returns a summary of available TTS providers and voices.

        Returns:
            Dictionary with provider and voice counts
        """
        provider_voices = self._get_tts_voices()
        total_providers = len(provider_voices)

        # Count voices, handling both list and dict formats
        total_voices = 0
        provider_voice_counts = {}

        for provider, voices in provider_voices.items():
            if isinstance(voices, dict):
                count = len(voices)
            elif isinstance(voices, (list, tuple, set)):
                count = len(voices)
            else:
                count = 1

            total_voices += count
            provider_voice_counts[provider] = count

        return {
            "providers": total_providers,
            "voices": total_voices,
            "provider_voice_counts": provider_voice_counts,
        }

    def _get_tts_voices(self) -> Dict[str, Union[List[str], Dict[str, str]]]:
        """
        Internal method to get all available voices from each TTS provider.

        Returns:
            Dictionary mapping TTS provider names to their available voices
        """
        provider_voices = {}

        try:
            # Import the TTS package specifically
            tts_package = importlib.import_module("llm4free.TTS")

            # Iterate through TTS modules
            for _, module_name, _ in pkgutil.iter_modules(tts_package.__path__):
                try:
                    module = importlib.import_module(f"llm4free.TTS.{module_name}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, TTSProvider)
                            and attr not in (TTSProvider,)
                            and not attr.__name__.startswith("Base")
                        ):
                            # TTS providers expose voices via 'all_voices' or 'SUPPORTED_VOICES'
                            voices = getattr(attr, "all_voices", None)
                            if voices is None:
                                voices = getattr(attr, "SUPPORTED_VOICES", None)
                            if isinstance(voices, (list, tuple, set, dict)):
                                provider_voices[attr_name] = list(voices) if isinstance(voices, set) else voices
                except (ImportError, AttributeError):
                    pass
        except (ImportError, ValueError):
            pass

        return provider_voices


class _TTIModels:
    """
    A class for managing TTI (Text-to-Image) provider models in the llm4free package.
    """

    def list(self) -> Dict[str, List[str]]:
        """
        Gets all available models from each TTI provider that has an AVAILABLE_MODELS attribute.

        Returns:
            Dictionary mapping TTI provider names to their available models
        """
        return self._get_tti_models()

    def get(self, provider_name: str) -> List[str]:
        """
        Gets all available models for a specific TTI provider.

        Args:
            provider_name: The name of the TTI provider

        Returns:
            List of available models for the provider
        """
        all_models = self._get_tti_models()
        return all_models.get(provider_name, [])

    def providers(self) -> Dict[str, Dict[str, Any]]:
        """
        Gets detailed information about all TTI providers including models, parameters, and metadata.

        Returns:
            Dictionary mapping provider names to detailed provider information
        """
        return self._get_tti_provider_details()

    def provider(self, provider_name: str) -> Dict[str, Any]:
        """
        Gets detailed information about a specific TTI provider.

        Args:
            provider_name: The name of the TTI provider

        Returns:
            Dictionary with detailed provider information
        """
        all_providers = self._get_tti_provider_details()
        return all_providers.get(provider_name, {})

    def summary(self) -> Dict[str, Any]:
        """
        Returns a summary of available TTI providers and models.

        Returns:
            Dictionary with provider and model counts
        """
        provider_models = self._get_tti_models()
        total_providers = len(provider_models)
        total_models = sum(
            len(models) if isinstance(models, (list, tuple, set)) else 1
            for models in provider_models.values()
        )

        return {
            "providers": total_providers,
            "models": total_models,
            "provider_model_counts": {
                provider: len(models) if isinstance(models, (list, tuple, set)) else 1
                for provider, models in provider_models.items()
            },
        }

    def _get_tti_models(self) -> Dict[str, List[str]]:
        """
        Internal method to get all available models from each TTI provider.

        Returns:
            Dictionary mapping TTI provider names to their available models
        """
        if not TTI_AVAILABLE:
            return {}

        provider_models = {}
        tti_package = importlib.import_module("llm4free.TTI")

        for _, module_name, _ in pkgutil.iter_modules(tti_package.__path__):
            try:
                module = importlib.import_module(f"llm4free.TTI.{module_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and attr.__name__ != "TTICompatibleProvider"
                        and not attr.__name__.startswith("Base")
                    ):
                        models = getattr(attr, "AVAILABLE_MODELS", None)
                        if isinstance(models, (list, tuple, set)):
                            provider_models[attr_name] = list(models)
            except (ImportError, AttributeError):
                pass

        return provider_models

    def _get_tti_provider_details(self) -> Dict[str, Dict[str, Any]]:
        """
        Internal method to get detailed information about all TTI providers.

        Returns:
            Dictionary mapping provider names to detailed provider information
        """
        if not TTI_AVAILABLE:
            return {}

        provider_details = {}
        tti_package = importlib.import_module("llm4free.TTI")

        for _, module_name, _ in pkgutil.iter_modules(tti_package.__path__):
            try:
                module = importlib.import_module(f"llm4free.TTI.{module_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and attr.__name__ != "TTICompatibleProvider"
                        and not attr.__name__.startswith("Base")
                    ):
                        # Get available models
                        models = []
                        get_models = getattr(attr, "get_models", None)
                        available_models = getattr(attr, "AVAILABLE_MODELS", None)
                        if callable(get_models):
                            try:
                                fetched_models = get_models()
                                if isinstance(fetched_models, set):
                                    models = list(fetched_models)
                                elif isinstance(fetched_models, (list, tuple)):
                                    models = list(fetched_models)
                                else:
                                    models = [str(fetched_models)] if fetched_models else []
                            except Exception:
                                models = []
                        elif isinstance(available_models, (list, tuple, set)):
                            models = list(available_models)
                        else:
                            continue

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

                        # Get additional metadata
                        metadata = {}
                        if hasattr(attr, "__doc__") and attr.__doc__:
                            metadata["description"] = attr.__doc__.strip().split("\n")[0]

                        provider_details[attr_name] = {
                            "name": attr_name,
                            "class": attr.__name__,
                            "module": module_name,
                            "models": models,
                            "parameters": supported_params,
                            "model_count": len(models),
                            "metadata": metadata,
                        }
            except (ImportError, AttributeError):
                pass

        return provider_details


# Create singleton instances
llm = _LLMModels()
tts = _TTSModels()
tti = _TTIModels()


# Container class for all model types
class Models:
    def __init__(self) -> None:
        self.llm: _LLMModels = llm
        self.tts: _TTSModels = tts
        self.tti: _TTIModels = tti


# Create a singleton instance
model = Models()
