"""
AI Provider Abstract Base Class
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM Provider"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Provider

        Args:
            config: Configuration dict containing api_base, api_key, model, etc.
        """
        self.config = config
        self.api_base = config.get("api_base", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.3)
        self.timeout = config.get("timeout", 30)

    @abstractmethod
    async def classify(
        self,
        transaction: Dict[str, Any],
        chart_of_accounts: str,
        historical_rules: str,
    ) -> Dict[str, Any]:
        """
        Classify a transaction

        Args:
            transaction: Transaction data containing peer, item, category, type, time, etc.
            chart_of_accounts: Chart of accounts
            historical_rules: Historical rules

        Returns:
            Classification result containing account, confidence, reasoning
        """
        pass

    @abstractmethod
    async def batch_classify(
        self,
        transactions: list[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
    ) -> list[Dict[str, Any]]:
        """
        Batch classify transactions

        Args:
            transactions: List of transactions
            chart_of_accounts: Chart of accounts
            historical_rules: Historical rules

        Returns:
            List of classification results
        """
        pass

    def validate_config(self) -> bool:
        """Validate if configuration is complete"""
        required_fields = ["api_base", "api_key", "model"]
        return all(field in self.config for field in required_fields)
