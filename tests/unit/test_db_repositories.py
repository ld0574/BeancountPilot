"""
Unit tests for database repositories
"""

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Transaction, Classification, Feedback, Rule, UserConfig
from src.db.repositories import (
    TransactionRepository,
    ClassificationRepository,
    FeedbackRepository,
    RuleRepository,
    UserConfigRepository,
)


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestTransactionRepository:
    """Test TransactionRepository"""

    def test_create_transaction(self, in_memory_db):
        """Test creating a transaction"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Coffee",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            currency="CNY",
            provider="alipay",
            raw_data='{"raw": "data"}',
        )

        assert transaction.id is not None
        assert transaction.peer == "Starbucks"
        assert transaction.amount == 35.50

    def test_get_by_id(self, in_memory_db):
        """Test getting transaction by ID"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Meituan",
            item="Dinner",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 18:00:00",
            amount=120.00,
            provider="alipay",
        )

        found = TransactionRepository.get_by_id(in_memory_db, transaction.id)
        assert found is not None
        assert found.peer == "Meituan"

    def test_list_all(self, in_memory_db):
        """Test listing all transactions"""
        TransactionRepository.create(
            db=in_memory_db,
            peer="Amazon",
            item="Book",
            category="Education",
            transaction_type="支出",
            time="2024-01-01 12:00:00",
            amount=59.90,
            provider="wechat",
        )
        TransactionRepository.create(
            db=in_memory_db,
            peer="Uber",
            item="Ride",
            category="Transport",
            transaction_type="支出",
            time="2024-01-01 15:00:00",
            amount=25.00,
            provider="alipay",
        )

        transactions = TransactionRepository.list_all(in_memory_db)
        assert len(transactions) == 2

    def test_list_by_provider(self, in_memory_db):
        """Test listing transactions by provider"""
        TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Coffee",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            provider="alipay",
        )
        TransactionRepository.create(
            db=in_memory_db,
            peer="Walmart",
            item="Groceries",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 09:00:00",
            amount=150.00,
            provider="wechat",
        )

        alipay_txs = TransactionRepository.list_by_provider(in_memory_db, "alipay")
        assert len(alipay_txs) == 1
        assert alipay_txs[0].provider == "alipay"

    def test_search(self, in_memory_db):
        """Test searching transactions"""
        TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Coffee",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            provider="alipay",
        )
        TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Tea",
            category="Food",
            transaction_type="支出",
            time="2024-01-02 10:00:00",
            amount=25.00,
            provider="alipay",
        )

        results = TransactionRepository.search(in_memory_db, peer="Starbucks")
        assert len(results) == 2


class TestClassificationRepository:
    """Test ClassificationRepository"""

    def test_create_classification(self, in_memory_db):
        """Test creating a classification"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Coffee",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            provider="alipay",
        )

        classification = ClassificationRepository.create(
            db=in_memory_db,
            transaction_id=transaction.id,
            account="Expenses:Food:Dining",
            confidence=0.95,
            source="ai",
            reasoning="Food expense",
        )

        assert classification.id is not None
        assert classification.account == "Expenses:Food:Dining"
        assert classification.confidence == 0.95

    def test_get_by_transaction_id(self, in_memory_db):
        """Test getting classifications by transaction ID"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Meituan",
            item="Dinner",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 18:00:00",
            amount=120.00,
            provider="alipay",
        )

        ClassificationRepository.create(
            db=in_memory_db,
            transaction_id=transaction.id,
            account="Expenses:Food:Dining",
            confidence=0.95,
            source="ai",
            reasoning="Food expense",
        )

        classifications = ClassificationRepository.get_by_transaction_id(in_memory_db, transaction.id)
        assert len(classifications) == 1
        assert classifications[0].account == "Expenses:Food:Dining"

    def test_update_account(self, in_memory_db):
        """Test updating classification account"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Walmart",
            item="Groceries",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 09:00:00",
            amount=150.00,
            provider="alipay",
        )

        classification = ClassificationRepository.create(
            db=in_memory_db,
            transaction_id=transaction.id,
            account="Expenses:Food:Dining",
            confidence=0.88,
            source="ai",
            reasoning="Food expense",
        )

        updated = ClassificationRepository.update_account(
            db=in_memory_db,
            classification_id=classification.id,
            account="Expenses:Food:Groceries",
        )

        assert updated.account == "Expenses:Food:Groceries"


class TestFeedbackRepository:
    """Test FeedbackRepository"""

    def test_create_feedback(self, in_memory_db):
        """Test creating feedback"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Starbucks",
            item="Coffee",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            provider="alipay",
        )

        feedback = FeedbackRepository.create(
            db=in_memory_db,
            transaction_id=transaction.id,
            action="accept",
            original_account="Expenses:Food:Dining",
            corrected_account="Expenses:Food:Dining",
        )

        assert feedback.id is not None
        assert feedback.action == "accept"

    def test_get_by_transaction_id(self, in_memory_db):
        """Test getting feedback by transaction ID"""
        transaction = TransactionRepository.create(
            db=in_memory_db,
            peer="Meituan",
            item="Dinner",
            category="Food",
            transaction_type="支出",
            time="2024-01-01 18:00:00",
            amount=120.00,
            provider="alipay",
        )

        FeedbackRepository.create(
            db=in_memory_db,
            transaction_id=transaction.id,
            action="modify",
            original_account="Expenses:Food:Dining",
            corrected_account="Expenses:Food:Groceries",
        )

        feedbacks = FeedbackRepository.get_by_transaction_id(in_memory_db, transaction.id)
        assert len(feedbacks) == 1
        assert feedbacks[0].action == "modify"


class TestRuleRepository:
    """Test RuleRepository"""

    def test_create_rule(self, in_memory_db):
        """Test creating a rule"""
        conditions = {"peer": ["Starbucks"], "category": ["Food"]}
        rule = RuleRepository.create(
            db=in_memory_db,
            name="Starbucks Coffee",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        assert rule.id is not None
        assert rule.name == "Starbucks Coffee"
        assert rule.account == "Expenses:Food:Dining"

    def test_get_by_id(self, in_memory_db):
        """Test getting rule by ID"""
        conditions = {"peer": ["Meituan"], "category": ["Food"]}
        rule = RuleRepository.create(
            db=in_memory_db,
            name="Meituan Dinner",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        found = RuleRepository.get_by_id(in_memory_db, rule.id)
        assert found is not None
        assert found.name == "Meituan Dinner"

    def test_list_all(self, in_memory_db):
        """Test listing all rules"""
        RuleRepository.create(
            db=in_memory_db,
            name="Starbucks Coffee",
            conditions={"peer": ["Starbucks"]},
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )
        RuleRepository.create(
            db=in_memory_db,
            name="Uber Ride",
            conditions={"peer": ["Uber"]},
            account="Expenses:Transport:Taxi",
            confidence=1.0,
            source="user",
        )

        rules = RuleRepository.list_all(in_memory_db)
        assert len(rules) == 2


class TestUserConfigRepository:
    """Test UserConfigRepository"""

    def test_set_and_get(self, in_memory_db):
        """Test setting and getting user configuration"""
        UserConfigRepository.set(in_memory_db, "chart_of_accounts", "Assets:Bank\nExpenses:Food")

        config = UserConfigRepository.get(in_memory_db, "chart_of_accounts")
        assert config == "Assets:Bank\nExpenses:Food"

    def test_update_config(self, in_memory_db):
        """Test updating configuration"""
        UserConfigRepository.set(in_memory_db, "ai_provider", "deepseek")

        UserConfigRepository.set(in_memory_db, "ai_provider", "openai")

        config = UserConfigRepository.get(in_memory_db, "ai_provider")
        assert config == "openai"

    def test_get_nonexistent_config(self, in_memory_db):
        """Test getting non-existent configuration"""
        config = UserConfigRepository.get(in_memory_db, "nonexistent_key")
        assert config is None
