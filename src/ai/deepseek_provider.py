"""
DeepSeek API Provider Implementation
"""

from typing import Dict, Any, List

from src.ai.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek API Provider (OpenAI-compatible)"""

    def __init__(self, config: Dict[str, Any]):
        # DeepSeek uses OpenAI-compatible API
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
        # DeepSeek has better Chinese support, can adjust prompts
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
        return await super().batch_classify(
            transactions, chart_of_accounts, historical_rules
        )
