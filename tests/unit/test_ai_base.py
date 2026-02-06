"""
Unit tests for AI base provider
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.ai.base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    """Mock implementation of BaseLLMProvider for testing"""

    async def classify(
        self,
        transaction,
        chart_of_accounts,
        historical_rules,
    ):
        """Mock classify method"""
        return {
            "account": "Expenses:Food:Dining",
            "confidence": 0.95,
            "reasoning": "Test classification",
        }

    async def batch_classify(
        self,
        transactions,
        chart_of_accounts,
        historical_rules,
    ):
        """Mock batch classify method"""
        return [
            {
                "account": "Expenses:Food:Dining",
                "confidence": 0.95,
                "reasoning": "Test classification",
            }
        ]


class TestBaseLLMProvider:
    """Test BaseLLMProvider abstract class"""

    def test_initialization(self):
        """Test provider initialization"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
            "temperature": 0.5,
            "timeout": 60,
        }

        provider = MockLLMProvider(config)

        assert provider.api_base == "https://api.example.com/v1"
        assert provider.api_key == "test_key"
        assert provider.model == "test-model"
        assert provider.temperature == 0.5
        assert provider.timeout == 60

    def test_default_values(self):
        """Test default configuration values"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
        }

        provider = MockLLMProvider(config)

        assert provider.temperature == 0.3  # Default value
        assert provider.timeout == 30  # Default value

    def test_validate_config_success(self):
        """Test configuration validation with valid config"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
        }

        provider = MockLLMProvider(config)
        assert provider.validate_config() is True

    def test_validate_config_missing_field(self):
        """Test configuration validation with missing field"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            # Missing "model"
        }

        provider = MockLLMProvider(config)
        assert provider.validate_config() is False

    @pytest.mark.asyncio
    async def test_classify_abstract_method(self):
        """Test that classify method can be called"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
        }

        provider = MockLLMProvider(config)

        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
        }

        result = await provider.classify(
            transaction=transaction,
            chart_of_accounts="Assets:Bank\nExpenses:Food",
            historical_rules="",
        )

        assert result["account"] == "Expenses:Food:Dining"
        assert result["confidence"] == 0.95
        assert result["reasoning"] == "Test classification"

    @pytest.mark.asyncio
    async def test_batch_classify_abstract_method(self):
        """Test that batch_classify method can be called"""
        config = {
            "api_base": "https://api.example.com/v1",
            "api_key": "test_key",
            "model": "test-model",
        }

        provider = MockLLMProvider(config)

        transactions = [
            {
                "peer": "Starbucks",
                "item": "Coffee",
                "category": "Food",
                "type": "支出",
                "time": "2024-01-01 10:00:00",
                "amount": 35.50,
            }
        ]

        results = await provider.batch_classify(
            transactions=transactions,
            chart_of_accounts="Assets:Bank\nExpenses:Food",
            historical_rules="",
        )

        assert len(results) == 1
        assert results[0]["account"] == "Expenses:Food:Dining"
