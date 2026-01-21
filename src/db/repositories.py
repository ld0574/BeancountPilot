"""
Data access layer (Repository pattern)
"""

import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.db.models import Transaction, Classification, Feedback, Rule, UserConfig


class TransactionRepository:
    """Transaction data access"""

    @staticmethod
    def create(
        db: Session,
        peer: str,
        item: str,
        category: str,
        transaction_type: str,
        time: str,
        amount: float,
        currency: str = "CNY",
        provider: str = "",
        raw_data: str = "",
    ) -> Transaction:
        """Create transaction record"""
        transaction = Transaction(
            id=str(uuid.uuid4()),
            peer=peer,
            item=item,
            category=category,
            type=transaction_type,
            time=time,
            amount=amount,
            currency=currency,
            provider=provider,
            raw_data=raw_data,
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def get_by_id(db: Session, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID"""
        return db.query(Transaction).filter(Transaction.id == transaction_id).first()

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[Transaction]:
        """Get all transactions (paginated)"""
        return db.query(Transaction).offset(skip).limit(limit).all()

    @staticmethod
    def list_by_provider(
        db: Session, provider: str, skip: int = 0, limit: int = 100
    ) -> List[Transaction]:
        """Get transactions by provider"""
        return (
            db.query(Transaction)
            .filter(Transaction.provider == provider)
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def search(
        db: Session,
        peer: Optional[str] = None,
        item: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[Transaction]:
        """Search transactions"""
        query = db.query(Transaction)

        filters = []
        if peer:
            filters.append(Transaction.peer.contains(peer))
        if item:
            filters.append(Transaction.item.contains(item))
        if start_time:
            filters.append(Transaction.time >= start_time)
        if end_time:
            filters.append(Transaction.time <= end_time)

        if filters:
            query = query.filter(and_(*filters))

        return query.all()

    @staticmethod
    def delete(db: Session, transaction_id: str) -> bool:
        """Delete transaction"""
        transaction = TransactionRepository.get_by_id(db, transaction_id)
        if transaction:
            db.delete(transaction)
            db.commit()
            return True
        return False


class ClassificationRepository:
    """Classification data access"""

    @staticmethod
    def create(
        db: Session,
        transaction_id: str,
        account: str,
        confidence: float,
        source: str = "ai",
        reasoning: str = "",
    ) -> Classification:
        """Create classification record"""
        classification = Classification(
            id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            account=account,
            confidence=confidence,
            source=source,
            reasoning=reasoning,
        )
        db.add(classification)
        db.commit()
        db.refresh(classification)
        return classification

    @staticmethod
    def get_by_transaction_id(
        db: Session, transaction_id: str
    ) -> List[Classification]:
        """Get all classification records for a transaction"""
        return (
            db.query(Classification)
            .filter(Classification.transaction_id == transaction_id)
            .all()
        )

    @staticmethod
    def get_latest_by_transaction_id(
        db: Session, transaction_id: str
    ) -> Optional[Classification]:
        """Get latest classification record for a transaction"""
        return (
            db.query(Classification)
            .filter(Classification.transaction_id == transaction_id)
            .order_by(Classification.created_at.desc())
            .first()
        )

    @staticmethod
    def update_account(db: Session, classification_id: str, account: str) -> bool:
        """Update classification account"""
        classification = (
            db.query(Classification)
            .filter(Classification.id == classification_id)
            .first()
        )
        if classification:
            classification.account = account
            classification.source = "user"
            db.commit()
            return True
        return False


class FeedbackRepository:
    """Feedback data access"""

    @staticmethod
    def create(
        db: Session,
        transaction_id: str,
        action: str,
        original_account: Optional[str] = None,
        corrected_account: Optional[str] = None,
    ) -> Feedback:
        """Create feedback record"""
        feedback = Feedback(
            id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            original_account=original_account,
            corrected_account=corrected_account,
            action=action,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback

    @staticmethod
    def get_by_transaction_id(
        db: Session, transaction_id: str
    ) -> List[Feedback]:
        """Get all feedback for a transaction"""
        return (
            db.query(Feedback).filter(Feedback.transaction_id == transaction_id).all()
        )

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[Feedback]:
        """Get all feedback (paginated)"""
        return db.query(Feedback).offset(skip).limit(limit).all()


class RuleRepository:
    """Rule data access"""

    @staticmethod
    def create(
        db: Session,
        name: str,
        conditions: Dict[str, Any],
        account: str,
        confidence: float = 1.0,
        source: str = "user",
    ) -> Rule:
        """Create rule"""
        rule = Rule(
            id=str(uuid.uuid4()),
            name=name,
            conditions=json.dumps(conditions, ensure_ascii=False),
            account=account,
            confidence=confidence,
            source=source,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def get_by_id(db: Session, rule_id: str) -> Optional[Rule]:
        """Get rule by ID"""
        return db.query(Rule).filter(Rule.id == rule_id).first()

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[Rule]:
        """Get all rules (paginated)"""
        return db.query(Rule).offset(skip).limit(limit).all()

    @staticmethod
    def update(
        db: Session,
        rule_id: str,
        name: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None,
        account: Optional[str] = None,
    ) -> Optional[Rule]:
        """Update rule"""
        rule = RuleRepository.get_by_id(db, rule_id)
        if rule:
            if name is not None:
                rule.name = name
            if conditions is not None:
                rule.conditions = json.dumps(conditions, ensure_ascii=False)
            if account is not None:
                rule.account = account
            rule.updated_at = datetime.utcnow().isoformat()
            db.commit()
            db.refresh(rule)
            return rule
        return None

    @staticmethod
    def delete(db: Session, rule_id: str) -> bool:
        """Delete rule"""
        rule = RuleRepository.get_by_id(db, rule_id)
        if rule:
            db.delete(rule)
            db.commit()
            return True
        return False

    @staticmethod
    def match_transaction(
        db: Session, peer: str, item: str, category: str
    ) -> List[Rule]:
        """Match all applicable rules for a transaction"""
        rules = RuleRepository.list_all(db)
        matched_rules = []

        for rule in rules:
            conditions = json.loads(rule.conditions)
            match = True

            # Check peer conditions
            if "peer" in conditions:
                peer_conditions = conditions["peer"]
                if isinstance(peer_conditions, str):
                    peer_conditions = [peer_conditions]
                if not any(p in peer for p in peer_conditions):
                    match = False

            # Check item conditions
            if match and "item" in conditions:
                item_conditions = conditions["item"]
                if isinstance(item_conditions, str):
                    item_conditions = [item_conditions]
                if not any(i in item for i in item_conditions):
                    match = False

            # Check category conditions
            if match and "category" in conditions:
                category_conditions = conditions["category"]
                if isinstance(category_conditions, str):
                    category_conditions = [category_conditions]
                if category not in category_conditions:
                    match = False

            if match:
                matched_rules.append(rule)

        return matched_rules


class UserConfigRepository:
    """User configuration data access"""

    @staticmethod
    def set(db: Session, key: str, value: str) -> UserConfig:
        """Set configuration item"""
        config = db.query(UserConfig).filter(UserConfig.key == key).first()
        if config:
            config.value = value
            config.updated_at = datetime.utcnow().isoformat()
        else:
            config = UserConfig(key=key, value=value)
            db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def get(db: Session, key: str) -> Optional[str]:
        """Get configuration item"""
        config = db.query(UserConfig).filter(UserConfig.key == key).first()
        return config.value if config else None

    @staticmethod
    def get_all(db: Session) -> Dict[str, str]:
        """Get all configurations"""
        configs = db.query(UserConfig).all()
        return {c.key: c.value for c in configs}

    @staticmethod
    def delete(db: Session, key: str) -> bool:
        """Delete configuration item"""
        config = db.query(UserConfig).filter(UserConfig.key == key).first()
        if config:
            db.delete(config)
            db.commit()
            return True
        return False
