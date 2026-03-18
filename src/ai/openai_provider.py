"""
OpenAI-compatible API Provider Implementation
"""

import asyncio
import random
from typing import Dict, Any, List, Optional, Callable, Awaitable
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

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
        self.max_retries = int(config.get("max_retries", 3))
        self.retry_min_delay = float(config.get("retry_min_delay", 1.0))
        self.retry_max_delay = float(config.get("retry_max_delay", 20.0))
        self.retry_backoff = float(config.get("retry_backoff", 2.0))
        self.max_concurrency = max(1, int(config.get("max_concurrency", 3)))

    def _get_retry_after(self, exc: Exception) -> Optional[float]:
        if isinstance(exc, APIStatusError) and getattr(exc, "response", None) is not None:
            retry_after = exc.response.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    return None
        return None

    def _should_retry(self, exc: Exception) -> bool:
        if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in {429, 500, 502, 503, 504}
        return False

    def _calc_delay(self, attempt: int, exc: Exception) -> float:
        retry_after = self._get_retry_after(exc)
        if retry_after is not None:
            return max(0.0, min(retry_after, self.retry_max_delay))
        base = self.retry_min_delay * (self.retry_backoff ** attempt)
        base = min(base, self.retry_max_delay)
        # add jitter to avoid thundering herd
        return base * (0.8 + random.random() * 0.4)

    async def _with_retry(self, func: Callable[[], Awaitable[Any]]) -> Any:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func()
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries or not self._should_retry(exc):
                    break
                await asyncio.sleep(self._calc_delay(attempt, exc))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unexpected retry state")

    async def classify(
        self,
        transaction: Dict[str, Any],
        chart_of_accounts: str,
        historical_rules: str,
        language: str = "en",
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
            transaction, chart_of_accounts, historical_rules, language=language
        )

        try:
            # Call API
            async def _call():
                return await self.client.chat.completions.create(
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
            response = await self._with_retry(_call)

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
        language: str = "en",
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
                transactions, chart_of_accounts, historical_rules, language=language
            )

            try:
                # Call API
                async def _call():
                    return await self.client.chat.completions.create(
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
                response = await self._with_retry(_call)

                # Parse response
                content = response.choices[0].message.content
                results = parse_batch_classification_response(content)

                # Ensure result count matches
                if len(results) != len(transactions):
                    # Mismatch, classify one by one
                    return await self._classify_one_by_one(
                        transactions, chart_of_accounts, historical_rules, language=language
                    )

                return results

            except Exception as e:
                # Error handling, classify one by one
                return await self._classify_one_by_one(
                    transactions, chart_of_accounts, historical_rules, language=language
                )
        else:
            # Large number of transactions, classify one by one
            return await self._classify_one_by_one(
                transactions, chart_of_accounts, historical_rules, language=language
            )

    async def _classify_one_by_one(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """Classify transactions one by one"""
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(tx: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.classify(
                    tx, chart_of_accounts, historical_rules, language=language
                )

        tasks = [asyncio.create_task(_run_one(tx)) for tx in transactions]
        return await asyncio.gather(*tasks)
