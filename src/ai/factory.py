"""
AI Provider Factory
"""

from typing import Dict, Any

from src.ai.base import BaseLLMProvider
from src.ai.openai_provider import OpenAIProvider
from src.ai.deepseek_provider import DeepSeekProvider
from src.ai.ollama_provider import OllamaProvider


# Provider registry
PROVIDERS = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "ollama": OllamaProvider,
    "custom": OpenAIProvider,  # Custom provider uses OpenAI-compatible format
}


def create_provider(provider_name: str, config: Dict[str, Any]) -> BaseLLMProvider:
    """
    Create AI Provider instance

    Args:
        provider_name: Provider name (openai, deepseek, ollama, custom, etc.)
        config: Provider configuration

    Returns:
        Provider instance

    Raises:
        ValueError: If provider does not exist
    """
    provider_name = provider_name.lower()

    if provider_name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available providers: {list(PROVIDERS.keys())}"
        )

    provider_class = PROVIDERS[provider_name]
    return provider_class(config)


def register_provider(name: str, provider_class: type) -> None:
    """
    Register a new Provider

    Args:
        name: Provider name
        provider_class: Provider class (must inherit from BaseLLMProvider)
    """
    if not issubclass(provider_class, BaseLLMProvider):
        raise ValueError(
            f"Provider class must inherit from BaseLLMProvider: {provider_class}"
        )

    PROVIDERS[name.lower()] = provider_class


def get_available_providers() -> list[str]:
    """Get all available provider names"""
    return list(PROVIDERS.keys())
