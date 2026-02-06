"""
Unit tests for database models
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Transaction, Classification, Feedback, Rule, UserConfig


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestTransaction:
    """Test Transaction model"""

    def test_create_transaction(self, in_memory_db):
        """Test creating a transaction"""
        transaction = Transaction(
            id="test_tx_001",
            peer="Starbucks",
            item="Coffee",
            category="Food",
            type="支出",
            time="2024-01-01 10:00:00",
            amount=35.50,
            currency="CNY",
            provider="alipay",
            raw_data='{"raw": "data"}',
        )
        in_memory_db.add(transaction)
        in_memory_db.commit()
        in_memory_db.refresh(transaction)

        assert transaction.id == "test_tx_001"
        assert transaction.peer == "Starbucks"
        assert transaction.amount == 35.50
        assert transaction.currency == "CNY"

    def test_transaction_relationships(self, in_memory_db):
        """Test transaction relationships"""
        transaction = Transaction(
            id="test_tx_002",
            peer="Meituan",
            item="Dinner",
            category="Food",
            type="支出",
            time="2024-01-01 18:00:00",
            amount=120.00,
            currency="CNY",
            provider="alipay",
        )
        in_memory_db.add(transaction)
        in_memory_db.commit()

        # Add classification
        classification = Classification(
            id="test_cls_001",
            transaction_id=transaction.id,
            account="Expenses:Food:Dining",
            confidence=0.95,
            source="ai",
            reasoning="Food expense",
        )
        in_memory_db.add(classification)
        in_memory_db.commit()

        assert len(transaction.classifications) == 1
        assert transaction.classifications[0].account == "Expenses:Food:Dining"


class TestClassification:
    """Test Classification model"""

    def test_create_classification(self, in_memory_db):
        """Test creating a classification"""
        # Create transaction first
        transaction = Transaction(
            id="test_tx_003",
            peer="Amazon",
            item="Book",
            category="Education",
            type="支出",
            time="2024-01-01 12:00:00",
            amount=59.90,
            currency="CNY",
            provider="wechat",
        )
        in_memory_db.add(transaction)
        in_memory_db.commit()

        # Create classification
        classification = Classification(
            id="test_cls_002",
            transaction_id=transaction.id,
            account="Expenses:Education:Books",
            confidence=0.88,
            source="ai",
            reasoning="Educational material",
        )
        in_memory_db.add(classification)
        in_memory_db.commit()
        in_memory_db.refresh(classification)

        assert classification.account == "Expenses:Education:Books"
        assert classification.confidence == 0.88
        assert classification.source == "ai"

    def test_classification_transaction_relationship(self, in_memory_db):
        """Test classification to transaction relationship"""
        transaction = Transaction(
            id="test_tx_004",
            peer="Uber",
            item="Ride",
            category="Transport",
            type="支出",
            time="2024-01-01 15:00:00",
            amount=25.00,
            currency="CNY",
            provider="alipay",
        )
        in_memory_db.add(transaction)
        in_memory_db.commit()

        classification = Classification(
            id="test_cls_003",
            transaction_id=transaction.id,
            account="Expenses:Transport:Taxi",
            confidence=0.92,
            source="rule",
            reasoning="Transport expense",
        )
        in_memory_db.add(classification)
        in_memory_db.commit()

        assert classification.transaction.id == transaction.id
        assert classification.transaction.peer == "Uber"


class TestFeedback:
    """Test Feedback model"""

    def test_create_feedback(self, in_memory_db):
        """Test creating feedback"""
        transaction = Transaction(
            id="test_tx_005",
            peer="Walmart",
            item="Groceries",
            category="Food",
            type="支出",
            time="2024-01-01 09:00:00",
            amount=150.00,
            currency="CNY",
            provider="alipay",
        )
        in_memory_db.add(transaction)
        in_memory_db.commit()

        feedback = Feedback(
            id="test_fb_001",
            transaction_id=transaction.id,
            original_account="Expenses:Food:Dining",
            corrected_account="Expenses:Food:Groceries",
            action="modify",
        )
        in_memory_db.add(feedback)
        in_memory_db.commit()
        in_memory_db.refresh(feedback)

        assert feedback.action == "modify"
        assert feedback.original_account == "Expenses:Food:Dining"
        assert feedback.corrected_account == "Expenses:Food:Groceries"


class TestRule:
    """Test Rule model"""

    def test_create_rule(self, in_memory_db):
        """Test creating a rule"""
        import json

        rule = Rule(
            id="test_rule_001",
            name="Starbucks Coffee",
            conditions=json.dumps({"peer": ["Starbucks"], "category": ["Food"]}),
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )
        in_memory_db.add(rule)
        in_memory_db.commit()
        in_memory_db.refresh(rule)

        assert rule.name == "Starbucks Coffee"
        assert rule.account == "Expenses:Food:Dining"
        assert rule.confidence == 1.0
        assert rule.source == "user"

        conditions = json.loads(rule.conditions)
        assert conditions["peer"] == ["Starbucks"]


class TestUserConfig:
    """Test UserConfig model"""

    def test_create_user_config(self, in_memory_db):
        """Test creating user configuration"""
        config = UserConfig(
            key="chart_of_accounts",
            value="Assets:Bank\nExpenses:Food",
        )
        in_memory_db.add(config)
        in_memory_db.commit()
        in_memory_db.refresh(config)

        assert config.key == "chart_of_accounts"
        assert config.value == "Assets:Bank\nExpenses:Food"

    def test_update_user_config(self, in_memory_db):
        """Test updating user configuration"""
        config = UserConfig(
            key="ai_provider",
            value="deepseek",
        )
        in_memory_db.add(config)
        in_memory_db.commit()

        # Update
        config.value = "openai"
        in_memory_db.commit()
        in_memory_db.refresh(config)

        assert config.value == "openai"
