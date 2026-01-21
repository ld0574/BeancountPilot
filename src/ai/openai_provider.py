"""
OpenAI-compatible API Provider Implementation
"""

import asyncio
from typing import Dict, Any, List
from openai import AsyncOpenAI

from src.ai.base import BaseLLMProvider
from src.ai.prompt import (
    build_classification_prompt,
    build_batch_classification_prompt,
    parse_classification_response,
    parse_batch_classification_response,
)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible API Provider"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base,
            timeout=self.timeout,
        )

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
        # Build prompt
        prompt = build_classification_prompt(
            transaction, chart_of_accounts, historical_rules
        )

        try:
            # Call API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional financial accounting assistant, responsible for classifying transactions into Beancount accounts.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=200,
            )

            # Parse response
            content = response.choices[0].message.content
            result = parse_classification_response(content)

            return result

        except Exception as e:
            # Error handling
            return {
                "account": "Expenses:Misc",
                "confidence": 0.0,
                "reasoning": f"API call failed: {str(e)}",
            }

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
        # If transaction count is small, use batch prompt
        if len(transactions) <= 10:
            # Build batch prompt
            prompt = build_batch_classification_prompt(
                transactions, chart_of_accounts, historical_rules
            )

            try:
                # Call API
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional financial accounting assistant, responsible for classifying transactions into Beancount accounts.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=1000,
                )

                # Parse response
                content = response.choices[0].message.content
                results = parse_batch_classification_response(content)

                # Ensure result count matches
                if len(results) != len(transactions):
                    # Mismatch, classify one by one
                    return await self._classify_one_by_one(
                        transactions, chart_of_accounts, historical_rules
                    )

                return results

            except Exception as e:
                # Error handling, classify one by one
                return await self._classify_one_by_one(
                    transactions, chart_of_accounts, historical_rules
                )
        else:
            # Large number of transactions, classify one by one
            return await self._classify_one_by_one(
                transactions, chart_of_accounts, historical_rules
            )

    async def _classify_one_by_one(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
    ) -> List[Dict[str, Any]]:
        """Classify transactions one by one"""
        tasks = [
            self.classify(tx, chart_of_accounts, historical_rules) for tx in transactions
        ]
        return await asyncio.gather(*tasks)
