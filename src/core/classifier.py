"""
Classification coordinator - coordinates AI classification and rule engine
"""

import json
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from src.ai.base import BaseLLMProvider
from src.ai.factory import create_provider
from src.db.repositories import (
    TransactionRepository,
    ClassificationRepository,
    RuleRepository,
    UserConfigRepository,
)


class Classifier:
    """Classification coordinator"""

    def __init__(self, db: Session, provider_name: str = "deepseek"):
        """
        Initialize classifier

        Args:
            db: Database session
            provider_name: AI Provider name
        """
        self.db = db
        self.provider_name = provider_name
        self.provider: Optional[BaseLLMProvider] = None

    def _get_provider(self) -> BaseLLMProvider:
        """Get AI Provider instance"""
        if self.provider is None:
            # Get AI configuration from database
            ai_config = UserConfigRepository.get(self.db, "ai_config")
            if ai_config:
                config = json.loads(ai_config)
                provider_config = config.get("providers", {}).get(
                    self.provider_name, {}
                )
            else:
                # Default configuration
                provider_config = {
                    "api_base": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                    "temperature": 0.3,
                    "timeout": 30,
                }

            self.provider = create_provider(self.provider_name, provider_config)

        return self.provider

    def _get_chart_of_accounts(self) -> str:
        """Get chart of accounts"""
        config = UserConfigRepository.get(self.db, "chart_of_accounts")
        if config:
            return config

        # Default chart of accounts
        return """
Assets:Bank:Alipay
Assets:Bank:WeChat
Assets:Bank:Cash
Expenses:Food:Dining
Expenses:Food:Groceries
Expenses:Transport:Taxi
Expenses:Transport:Subway
Expenses:Shopping:Clothing
Expenses:Shopping:Electronics
Expenses:Entertainment:Movies
Expenses:Entertainment:Games
Expenses:Utilities:Phone
Expenses:Utilities:Internet
Expenses:Utilities:Electricity
Expenses:Health:Medicine
Expenses:Health:Insurance
Expenses:Education:Books
Expenses:Education:Courses
Expenses:Travel:Hotels
Expenses:Travel:Transport
Expenses:Misc
Income:Salary
Income:Investment
Income:Other
"""

    def _get_historical_rules(self) -> str:
        """Get historical rules"""
        rules = RuleRepository.list_all(self.db, limit=50)

        if not rules:
            return "No historical rules"

        rule_strings = []
        for rule in rules:
            conditions = json.loads(rule.conditions)
            rule_strings.append(
                f"- {rule.name}: {conditions} -> {rule.account}"
            )

        return "\n".join(rule_strings)

    async def classify_transaction(
        self, transaction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify a single transaction

        Args:
            transaction: Transaction data

        Returns:
            Classification result
        """
        # 1. Check for user override rules
        matched_rules = RuleRepository.match_transaction(
            self.db,
            peer=transaction.get("peer", ""),
            item=transaction.get("item", ""),
            category=transaction.get("category", ""),
        )

        # User rules take priority
        user_rules = [r for r in matched_rules if r.source == "user"]
        if user_rules:
            # Use highest priority user rule
            rule = max(user_rules, key=lambda r: r.confidence)
            return {
                "account": rule.account,
                "confidence": rule.confidence,
                "reasoning": f"Matched user rule: {rule.name}",
                "source": "rule",
            }

        # 2. Use AI classification
        provider = self._get_provider()
        chart_of_accounts = self._get_chart_of_accounts()
        historical_rules = self._get_historical_rules()

        result = await provider.classify(
            transaction, chart_of_accounts, historical_rules
        )
        result["source"] = "ai"

        return result

    async def classify_transactions(
        self, transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Batch classify transactions

        Args:
            transactions: List of transactions

        Returns:
            List of classification results
        """
        results = []

        # First check rule matching for all transactions
        for tx in transactions:
            # Check user rules
            matched_rules = RuleRepository.match_transaction(
                self.db,
                peer=tx.get("peer", ""),
                item=tx.get("item", ""),
                category=tx.get("category", ""),
            )

            user_rules = [r for r in matched_rules if r.source == "user"]
            if user_rules:
                rule = max(user_rules, key=lambda r: r.confidence)
                results.append({
                    "transaction": tx,
                    "account": rule.account,
                    "confidence": rule.confidence,
                    "reasoning": f"Matched user rule: {rule.name}",
                    "source": "rule",
                })
                continue

            # No matching rule, use AI
            results.append({"transaction": tx, "source": "ai"})

        # Batch classify transactions that need AI
        ai_transactions = [r["transaction"] for r in results if r["source"] == "ai"]

        if ai_transactions:
            provider = self._get_provider()
            chart_of_accounts = self._get_chart_of_accounts()
            historical_rules = self._get_historical_rules()

            ai_results = await provider.batch_classify(
                ai_transactions, chart_of_accounts, historical_rules
            )

            # Merge results
            ai_index = 0
            for i, result in enumerate(results):
                if result["source"] == "ai":
                    results[i].update({
                        "account": ai_results[ai_index]["account"],
                        "confidence": ai_results[ai_index]["confidence"],
                        "reasoning": ai_results[ai_index]["reasoning"],
                    })
                    ai_index += 1

        return results

    def save_classification(
        self, transaction_id: str, classification: Dict[str, Any]
    ) -> None:
        """
        Save classification result to database

        Args:
            transaction_id: Transaction ID
            classification: Classification result
        """
        ClassificationRepository.create(
            db=self.db,
            transaction_id=transaction_id,
            account=classification["account"],
            confidence=classification["confidence"],
            source=classification["source"],
            reasoning=classification.get("reasoning", ""),
        )
