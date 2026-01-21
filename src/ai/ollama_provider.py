"""
Ollama Local LLM Provider Implementation
"""

from typing import Dict, Any, List

from src.ai.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Ollama Local LLM Provider (OpenAI-compatible)"""

    def __init__(self, config: Dict[str, Any]):
        # Ollama uses OpenAI-compatible API
        # Local deployment, can set longer timeout
        config["timeout"] = config.get("timeout", 60)
        super().__init__(config)

    async def classify(
        self,
        transaction: Dict[str, Any],
        chart_of_accounts: str,
        historical_rules: str,
    ) -> Dict[str, Any]:
        """
        Classify a transaction

        Args:
            transaction: Transaction data
            chart_of_accounts: Chart of accounts
            historical_rules: Historical rules

        Returns:
            Classification result
        """
        # Local model may need more detailed prompts
        return await super().classify(transaction, chart_of_accounts, historical_rules)

    async def batch_classify(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
    ) -> List[Dict[str, Any]]:
        """
        Batch classify transactions

        Args:
            transactions: List of transactions
            chart_of_accounts: Chart of accounts
            historical_rules: Historical rules

        Returns:
            List of classification results
        """
        # Local model batch processing may be slow, use one-by-one classification
        return await self._classify_one_by_one(
            transactions, chart_of_accounts, historical_rules
        )
