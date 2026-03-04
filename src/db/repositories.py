"""
Data access layer (Repository pattern)
"""

import json
import re
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.db.models import (
    Transaction,
    Classification,
    Feedback,
    Rule,
    UserConfig,
    User,
    Knowledge,
)


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
        confidence: Optional[float] = None,
        source: Optional[str] = None,
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
            if confidence is not None:
                rule.confidence = confidence
            if source is not None:
                rule.source = source
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
        db: Session,
        peer: str,
        item: str,
        category: str,
        provider: str = "",
        raw_data: str = "",
        tx_type: str = "",
        tx_time: str = "",
        tx_fields: Optional[Dict[str, Any]] = None,
    ) -> List[Rule]:
        """Match all applicable rules for a transaction"""
        rules = RuleRepository.list_all(db)
        matched_rules = []
        provider = (provider or "").strip().lower()
        tx_fields = tx_fields or {}
        tx_fields_normalized = {str(k): str(v or "") for k, v in tx_fields.items()}
        tx_time = str(tx_time or tx_fields_normalized.get("time", "")).strip()
        haystack = " ".join(
            [
                str(peer or ""),
                str(item or ""),
                str(category or ""),
                str(tx_type or ""),
                str(tx_time or ""),
                str(raw_data or ""),
                " ".join(tx_fields_normalized.values()),
            ]
        )

        def _to_minutes(value: str) -> Optional[int]:
            """Parse first HH:MM from text."""
            text = str(value or "")
            match = re.search(r"(\d{1,2}):(\d{2})", text)
            if not match:
                return None
            hour = int(match.group(1))
            minute = int(match.group(2))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            return hour * 60 + minute

        def _time_matches(rule_time: str, tx_minutes: Optional[int]) -> bool:
            """Match a DEG-style time token like 06:00-10:00."""
            token = str(rule_time or "").strip()
            if not token or token == "/":
                return True
            if tx_minutes is None:
                return False

            for sep in ("-", "~", "～", "—", "－", "至", "to"):
                if sep in token:
                    start_text, end_text = token.split(sep, 1)
                    start = _to_minutes(start_text)
                    end = _to_minutes(end_text)
                    if start is None or end is None:
                        return False
                    if start <= end:
                        return start <= tx_minutes <= end
                    # Overnight window, e.g. 22:00-02:00
                    return tx_minutes >= start or tx_minutes <= end

            exact = _to_minutes(token)
            return exact is not None and tx_minutes == exact

        tx_minutes = _to_minutes(tx_time)

        for rule in rules:
            conditions = json.loads(rule.conditions)
            if conditions.get("skip") is True or conditions.get("_deg_only") is True:
                continue
            match = True

            # Optional provider condition (string or list).
            if "provider" in conditions:
                expected = conditions["provider"]
                if isinstance(expected, str):
                    expected = [expected]
                normalized = {str(x).strip().lower() for x in expected if str(x).strip()}
                if normalized and provider not in normalized:
                    match = False

            # DEG-style regex condition.
            if match and "regexp" in conditions:
                regex_text = str(conditions.get("regexp", "")).strip()
                if regex_text:
                    try:
                        if re.search(regex_text, haystack, flags=re.IGNORECASE) is None:
                            match = False
                    except re.error:
                        match = False

            # Check peer conditions
            if match and "peer" in conditions:
                peer_conditions = conditions["peer"]
                if isinstance(peer_conditions, str):
                    peer_conditions = [peer_conditions]
                tokens = [str(p).strip() for p in peer_conditions if str(p).strip()]
                if "/" not in tokens and not any(token in str(peer or "") for token in tokens):
                    match = False

            # Check item conditions
            if match and "item" in conditions:
                item_conditions = conditions["item"]
                if isinstance(item_conditions, str):
                    item_conditions = [item_conditions]
                tokens = [str(i).strip() for i in item_conditions if str(i).strip()]
                if "/" not in tokens and not any(token in str(item or "") for token in tokens):
                    match = False

            # Check category conditions
            if match and "category" in conditions:
                category_conditions = conditions["category"]
                if isinstance(category_conditions, str):
                    category_conditions = [category_conditions]
                tokens = [str(c).strip() for c in category_conditions if str(c).strip()]
                if "/" not in tokens and not any(token in str(category or "") for token in tokens):
                    match = False

            # DEG time condition such as "06:00-10:00".
            if match and "time" in conditions:
                time_conditions = conditions["time"]
                if isinstance(time_conditions, str):
                    time_conditions = [time_conditions]
                tokens = [str(v).strip() for v in time_conditions if str(v).strip()]
                if "/" not in tokens and not any(_time_matches(token, tx_minutes) for token in tokens):
                    match = False

            # Check transaction type conditions against normalized tx_type.
            if match and "type" in conditions:
                type_conditions = conditions["type"]
                if isinstance(type_conditions, str):
                    type_conditions = [type_conditions]
                tokens = [str(v).strip() for v in type_conditions if str(v).strip()]
                if "/" not in tokens and not any(token in str(tx_type or "") for token in tokens):
                    match = False

            # DEG transactionType / txType (provider specific transaction subtype).
            tx_type_detail = str(tx_fields_normalized.get("txType", "")).strip()
            if match and "transactionType" in conditions:
                tx_type_conditions = conditions["transactionType"]
                if isinstance(tx_type_conditions, str):
                    tx_type_conditions = [tx_type_conditions]
                tokens = [str(v).strip() for v in tx_type_conditions if str(v).strip()]
                if "/" not in tokens and not any(token in tx_type_detail for token in tokens):
                    match = False
            if match and "txType" in conditions:
                tx_type_conditions = conditions["txType"]
                if isinstance(tx_type_conditions, str):
                    tx_type_conditions = [tx_type_conditions]
                tokens = [str(v).strip() for v in tx_type_conditions if str(v).strip()]
                if "/" not in tokens and not any(token in tx_type_detail for token in tokens):
                    match = False

            # Provider-specific custom fields (e.g., method/status/txType).
            if match:
                reserved = {
                    "provider",
                    "regexp",
                    "peer",
                    "item",
                    "category",
                    "skip",
                    "_deg_only",
                    "_deg_has_target",
                    "transactionType",
                    "tx_type",
                    "type",
                    "txType",
                    "time",
                    "sep",
                    "fullMatch",
                    "methodAccount",
                    "commissionAccount",
                    "pnlAccount",
                    "targetAccount",
                    "description",
                    "source",
                    "confidence",
                }
                for key, expected in conditions.items():
                    if key in reserved:
                        continue
                    actual = tx_fields_normalized.get(str(key), "")
                    if isinstance(expected, str):
                        expected = [expected]
                    expected_tokens = [str(x).strip() for x in expected if str(x).strip()]
                    if (
                        expected_tokens
                        and "/" not in expected_tokens
                        and not any(token in actual for token in expected_tokens)
                    ):
                        match = False
                        break

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


class UserRepository:
    """User data access"""

    @staticmethod
    def create(db: Session, username: str) -> User:
        """Create user"""
        user = User(
            id=str(uuid.uuid4()),
            username=username,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_by_id(db: Session, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        """Get user by username"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        """List users"""
        return db.query(User).offset(skip).limit(limit).all()

    @staticmethod
    def delete(db: Session, user_id: str) -> bool:
        """Delete user"""
        user = UserRepository.get_by_id(db, user_id)
        if user:
            db.delete(user)
            db.commit()
            return True
        return False


class KnowledgeRepository:
    """Knowledge base data access"""

    @staticmethod
    def create(db: Session, key: str, value: str, source: str = "feedback") -> Knowledge:
        """Create knowledge record"""
        record = Knowledge(
            id=str(uuid.uuid4()),
            key=key,
            value=value,
            source=source,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_by_id(db: Session, knowledge_id: str) -> Optional[Knowledge]:
        """Get knowledge by ID"""
        return db.query(Knowledge).filter(Knowledge.id == knowledge_id).first()

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[Knowledge]:
        """List knowledge records"""
        return db.query(Knowledge).offset(skip).limit(limit).all()

    @staticmethod
    def search_by_key(db: Session, key: str) -> List[Knowledge]:
        """Search knowledge by key"""
        return db.query(Knowledge).filter(Knowledge.key.contains(key)).all()

    @staticmethod
    def update_value(db: Session, knowledge_id: str, value: str) -> Optional[Knowledge]:
        """Update knowledge value"""
        record = KnowledgeRepository.get_by_id(db, knowledge_id)
        if record:
            record.value = value
            record.updated_at = datetime.utcnow().isoformat()
            db.commit()
            db.refresh(record)
        return record

    @staticmethod
    def delete(db: Session, knowledge_id: str) -> bool:
        """Delete knowledge record"""
        record = KnowledgeRepository.get_by_id(db, knowledge_id)
        if record:
            db.delete(record)
            db.commit()
            return True
        return False
