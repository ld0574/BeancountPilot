"""
OpenAI-compatible API Provider Implementation
"""

import asyncio
import random
import time
from typing import Dict, Any, List, Optional, Callable, Awaitable
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from src.ai.base import BaseLLMProvider
from src.ai.prompt import (
    build_classification_prompt,
    build_batch_classification_prompt,
    parse_classification_response,
    parse_batch_classification_response,
)
from src.utils.logger import get_logger


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible API Provider"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = get_logger(__name__)
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
        self.batch_size = max(1, int(config.get("batch_size", 20)))

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
            start = time.monotonic()
            try:
                result = await func()
                elapsed = time.monotonic() - start
                if attempt > 0:
                    self.logger.info(
                        "llm.retry.success attempt=%s elapsed_s=%.2f",
                        attempt,
                        elapsed,
                    )
                return result
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries or not self._should_retry(exc):
                    break
                delay = self._calc_delay(attempt, exc)
                self.logger.warning(
                    "llm.retry attempt=%s error=%s delay_s=%.2f",
                    attempt + 1,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
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
            start = time.monotonic()
            response = await self._with_retry(_call)
            self.logger.info(
                "llm.classify.done model=%s elapsed_s=%.2f",
                self.model,
                time.monotonic() - start,
            )

            # Parse response
            content = response.choices[0].message.content
            result = parse_classification_response(content)

            return result

        except Exception as e:
            # Error handling
            self.logger.exception("llm.classify.failed error=%s", str(e))
            return {
                "account": "Expenses:Other",
                "confidence": 0.0,
                "reasoning": f"API call failed: {str(e)}",
            }

    async def batch_classify(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
        language: str = "en",
        progress_callback: Optional[Callable[[int], None]] = None,
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
        async def _batch_call(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            prompt = build_batch_classification_prompt(
                batch, chart_of_accounts, historical_rules, language=language
            )
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
            start = time.monotonic()
            response = await self._with_retry(_call)
            self.logger.info(
                "llm.batch.done model=%s batch=%s elapsed_s=%.2f",
                self.model,
                len(batch),
                time.monotonic() - start,
            )
            content = response.choices[0].message.content
            results = parse_batch_classification_response(content)
            if len(results) != len(batch):
                self.logger.warning(
                    "llm.batch.mismatch expected=%s got=%s",
                    len(batch),
                    len(results),
                )
                return await self._classify_one_by_one(
                    batch,
                    chart_of_accounts,
                    historical_rules,
                    language=language,
                    progress_callback=None,
                )
            return results

        if self.batch_size <= 1:
            return await self._classify_one_by_one(
                transactions,
                chart_of_accounts,
                historical_rules,
                language=language,
                progress_callback=progress_callback,
            )

        batches: List[List[Dict[str, Any]]] = [
            transactions[start : start + self.batch_size]
            for start in range(0, len(transactions), self.batch_size)
        ]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _run_batch(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            async with semaphore:
                try:
                    batch_results = await _batch_call(batch)
                except Exception:
                    batch_results = await self._classify_one_by_one(
                        batch,
                        chart_of_accounts,
                        historical_rules,
                        language=language,
                        progress_callback=None,
                    )
                if progress_callback:
                    progress_callback(len(batch_results))
                return batch_results

        task_list = [asyncio.create_task(_run_batch(batch)) for batch in batches]
        batch_results_list = await asyncio.gather(*task_list)

        aggregated: List[Dict[str, Any]] = []
        for batch_results in batch_results_list:
            aggregated.extend(batch_results)
        return aggregated

    async def _classify_one_by_one(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: str,
        historical_rules: str,
        language: str = "en",
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Classify transactions one by one"""
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(tx: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                result = await self.classify(
                    tx, chart_of_accounts, historical_rules, language=language
                )
                if progress_callback:
                    progress_callback(1)
                return result

        tasks = [asyncio.create_task(_run_one(tx)) for tx in transactions]
        return await asyncio.gather(*tasks)
