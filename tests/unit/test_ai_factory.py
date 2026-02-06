"""
Unit tests for AI provider factory
"""

import pytest

from src.ai.factory import (
    create_provider,
    register_provider,
    get_available_providers,
    PROVIDERS,
)
from src.ai.openai_provider import OpenAIProvider
from src.ai.deepseek_provider import DeepSeekProvider
from src.ai.ollama_provider import OllamaProvider
from src.ai.base import BaseLLMProvider


class TestCreateProvider:
    """Test create_provider function"""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        config = {
            "api_base": "https://api.openai.com/v1",
            "api_key": "test_key",
            "model": "gpt-4o-mini",
        }

        provider = create_provider("openai", config)

        assert isinstance(provider, OpenAIProvider)
        assert provider.api_base == "https://api.openai.com/v1"
        assert provider.api_key == "test_key"

    def test_create_deepseek_provider(self):
        """Test creating DeepSeek provider"""
        config = {
            "api_base": "https://api.deepseek.com/v1",
            "api_key": "test_key",
            "model": "deepseek-chat",
        }

        provider = create_provider("deepseek", config)

        assert isinstance(provider, DeepSeekProvider)
        assert provider.api_base == "https://api.deepseek.com/v1"

    def test_create_ollama_provider(self):
        """Test creating Ollama provider"""
        config = {
            "api_base": "http://localhost:11434/v1",
            "api_key": "ollama",
            "model": "llama3.2:3b",
        }

        provider = create_provider("ollama", config)

        assert isinstance(provider, OllamaProvider)
        assert provider.api_base == "http://localhost:11434/v1"

    def test_create_custom_provider(self):
        """Test creating custom provider (uses OpenAI format)"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "custom-model",
        }

        provider = create_provider("custom", config)

        assert isinstance(provider, OpenAIProvider)
        assert provider.api_base == "https://api.example.com/v1"

    def test_create_provider_case_insensitive(self):
        """Test that provider name is case insensitive"""
        config = {
            "api_base": "https://api.openai.com/v1",
            "api_key": "test_key",
            "model": "gpt-4o-mini",
        }

        provider = create_provider("OPENAI", config)

        assert isinstance(provider, OpenAIProvider)

    def test_create_unknown_provider_raises_error(self):
        """Test that creating unknown provider raises ValueError"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
        }

        with pytest.raises(ValueError) as exc_info:
            create_provider("unknown_provider", config)

        assert "Unknown provider: unknown_provider" in str(exc_info.value)
        assert "Available providers:" in str(exc_info.value)


class TestRegisterProvider:
    """Test register_provider function"""

    def test_register_new_provider(self):
        """Test registering a new provider"""
        class CustomProvider(BaseLLMProvider):
            async def classify(self, transaction, chart_of_accounts, historical_rules):
                return {"account": "Expenses:Misc", "confidence": 0.5, "reasoning": ""}

            async def batch_classify(self, transactions, chart_of_accounts, historical_rules):
                return []

        # Register provider
        register_provider("custom_test", CustomProvider)

        # Check if provider is available
        providers = get_available_providers()
        assert "custom_test" in providers

        # Clean up
        if "custom_test" in PROVIDERS:
            del PROVIDERS["custom_test"]

    def test_register_provider_not_subclass_raises_error(self):
        """Test that registering non-BaseLLMProvider raises ValueError"""
        class NotAProvider:
            pass

        with pytest.raises(ValueError) as exc_info:
            register_provider("invalid", NotAProvider)

        assert "must inherit from BaseLLMProvider" in str(exc_info.value)

    def test_register_provider_overwrites_existing(self):
        """Test that registering provider overwrites existing one"""
        class NewProvider(BaseLLMProvider):
            async def classify(self, transaction, chart_of_accounts, historical_rules):
                return {"account": "Expenses:Misc", "confidence": 0.5, "reasoning": ""}

            async def batch_classify(self, transactions, chart_of_accounts, historical_rules):
                return []

        # Save original
        original_provider = PROVIDERS.get("openai")

        # Register new provider
        register_provider("openai", NewProvider)

        # Check if provider was replaced
        assert PROVIDERS["openai"] == NewProvider

        # Restore original
        if original_provider:
            PROVIDERS["openai"] = original_provider


class TestGetAvailableProviders:
    """Test get_available_providers function"""

    def test_get_all_providers(self):
        """Test getting all available providers"""
        providers = get_available_providers()

        assert "openai" in providers
        assert "deepseek" in providers
        assert "ollama" in providers
        assert "custom" in providers

    def test_providers_is_list(self):
        """Test that get_available_providers returns a list"""
        providers = get_available_providers()

        assert isinstance(providers, list)

    def test_providers_count(self):
        """Test that default providers count is correct"""
        providers = get_available_providers()

        # Should have 4 default providers: openai, deepseek, ollama, custom
        assert len(providers) == 4
