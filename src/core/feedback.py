"""
Feedback handling module - collects user feedback and optimizes classification
"""

from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from src.db.repositories import (
    FeedbackRepository,
    ClassificationRepository,
    RuleRepository,
)
from src.core.rule_engine import RuleEngine


class FeedbackHandler:
    """Feedback handler"""

    def __init__(self, db: Session):
        """
        Initialize feedback handler

        Args:
            db: Database session
        """
        self.db = db
        self.rule_engine = RuleEngine(db)

    def record_feedback(
        self,
        transaction_id: str,
        original_account: Optional[str],
        corrected_account: Optional[str],
        action: str,
    ) -> Dict[str, Any]:
        """
        Record user feedback

        Args:
            transaction_id: Transaction ID
            original_account: Original account
            corrected_account: Corrected account
            action: Action type (accept, reject, modify)

        Returns:
            Feedback record
        """
        feedback = FeedbackRepository.create(
            db=self.db,
            transaction_id=transaction_id,
            action=action,
            original_account=original_account,
            corrected_account=corrected_account,
        )

        # If it's a modify action, update classification record
        if action == "modify" and corrected_account:
            classifications = ClassificationRepository.get_by_transaction_id(
                self.db, transaction_id
            )
            if classifications:
                latest_classification = max(
                    classifications, key=lambda c: c.created_at
                )
                ClassificationRepository.update_account(
                    db=self.db,
                    classification_id=latest_classification.id,
                    account=corrected_account,
                )

        return {
            "id": feedback.id,
            "transaction_id": feedback.transaction_id,
            "original_account": feedback.original_account,
            "corrected_account": feedback.corrected_account,
            "action": feedback.action,
            "created_at": feedback.created_at,
        }

    def get_feedback_by_transaction(
        self, transaction_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all feedback for a transaction

        Args:
            transaction_id: Transaction ID

        Returns:
            List of feedback
        """
        feedbacks = FeedbackRepository.get_by_transaction_id(self.db, transaction_id)

        return [
            {
                "id": f.id,
                "transaction_id": f.transaction_id,
                "original_account": f.original_account,
                "corrected_account": f.corrected_account,
                "action": f.action,
                "created_at": f.created_at,
            }
            for f in feedbacks
        ]

    def list_all_feedback(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all feedback

        Args:
            skip: Number of records to skip
            limit: Number of records to limit

        Returns:
            List of feedback
        """
        feedbacks = FeedbackRepository.list_all(self.db, skip=skip, limit=limit)

        return [
            {
                "id": f.id,
                "transaction_id": f.transaction_id,
                "original_account": f.original_account,
                "corrected_account": f.corrected_account,
                "action": f.action,
                "created_at": f.created_at,
            }
            for f in feedbacks
        ]

    def analyze_feedback_and_generate_rules(self, min_confidence: int = 3) -> List[Dict[str, Any]]:
        """
        Analyze feedback and auto-generate rules

        Args:
            min_confidence: Minimum confidence (number of occurrences of same pattern)

        Returns:
            List of generated rules
        """
        # Get all modify feedback
        feedbacks = FeedbackRepository.list_all(self.db)
        modify_feedbacks = [f for f in feedbacks if f.action == "modify"]

        # Group by pattern
        from collections import defaultdict

        patterns = defaultdict(list)

        for feedback in modify_feedbacks:
            # Get transaction information
            from src.db.repositories import TransactionRepository

            transaction = TransactionRepository.get_by_id(
                self.db, feedback.transaction_id
            )

            if not transaction:
                continue

            # Create pattern key
            pattern_key = (
                f"{transaction.peer}|{transaction.item}|{transaction.category}"
            )

            patterns[pattern_key].append({
                "transaction_id": transaction.id,
                "peer": transaction.peer,
                "item": transaction.item,
                "category": transaction.category,
                "corrected_account": feedback.corrected_account,
            })

        # Generate rules for high-frequency patterns
        generated_rules = []

        for pattern_key, items in patterns.items():
            if len(items) >= min_confidence:
                # Check if all corrections are consistent
                accounts = {item["corrected_account"] for item in items}

                if len(accounts) == 1:
                    # Consistent correction, generate rule
                    peer = items[0]["peer"]
                    item = items[0]["item"]
                    category = items[0]["category"]
                    account = list(accounts)[0]

                    rule = self.rule_engine.auto_generate_rule_from_feedback(
                        peer=peer,
                        item=item,
                        category=category,
                        account=account,
                    )

                    generated_rules.append(rule)

        return generated_rules

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get feedback statistics

        Returns:
            Statistics information
        """
        feedbacks = FeedbackRepository.list_all(self.db)

        total = len(feedbacks)
        accept = sum(1 for f in feedbacks if f.action == "accept")
        reject = sum(1 for f in feedbacks if f.action == "reject")
        modify = sum(1 for f in feedbacks if f.action == "modify")

        return {
            "total": total,
            "accept": accept,
            "reject": reject,
            "modify": modify,
            "accept_rate": accept / total if total > 0 else 0,
            "modify_rate": modify / total if total > 0 else 0,
        }
