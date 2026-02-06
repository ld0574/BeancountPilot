"""
Unit tests for rule engine
"""

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Transaction, Rule
from src.db.repositories import RuleRepository
from src.core.rule_engine import RuleEngine


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class TestRuleEngine:
    """Test RuleEngine class"""

    def test_initialization(self, in_memory_db):
        """Test rule engine initialization"""
        engine = RuleEngine(in_memory_db)
        assert engine.db == in_memory_db

    def test_create_rule(self, in_memory_db):
        """Test creating a rule"""
        engine = RuleEngine(in_memory_db)

        conditions = {"peer": ["Starbucks"], "category": ["Food"]}
        rule = engine.create_rule(
            name="Starbucks Coffee",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        assert rule["id"] is not None
        assert rule["name"] == "Starbucks Coffee"
        assert rule["account"] == "Expenses:Food:Dining"
        assert rule["confidence"] == 1.0
        assert rule["source"] == "user"

    def test_get_rule(self, in_memory_db):
        """Test getting a rule by ID"""
        engine = RuleEngine(in_memory_db)

        conditions = {"peer": ["Meituan"], "category": ["Food"]}
        created = engine.create_rule(
            name="Meituan Dinner",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        retrieved = engine.get_rule(created["id"])

        assert retrieved is not None
        assert retrieved["name"] == "Meituan Dinner"
        assert retrieved["account"] == "Expenses:Food:Dining"

    def test_get_nonexistent_rule(self, in_memory_db):
        """Test getting a non-existent rule"""
        engine = RuleEngine(in_memory_db)

        retrieved = engine.get_rule("nonexistent_id")

        assert retrieved is None

    def test_list_rules(self, in_memory_db):
        """Test listing all rules"""
        engine = RuleEngine(in_memory_db)

        engine.create_rule(
            name="Starbucks Coffee",
            conditions={"peer": ["Starbucks"]},
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )
        engine.create_rule(
            name="Uber Ride",
            conditions={"peer": ["Uber"]},
            account="Expenses:Transport:Taxi",
            confidence=1.0,
            source="user",
        )

        rules = engine.list_rules()

        assert len(rules) == 2

    def test_list_rules_with_pagination(self, in_memory_db):
        """Test listing rules with pagination"""
        engine = RuleEngine(in_memory_db)

        for i in range(5):
            engine.create_rule(
                name=f"Rule {i}",
                conditions={"peer": [f"Peer{i}"]},
                account="Expenses:Misc",
                confidence=1.0,
                source="user",
            )

        rules = engine.list_rules(skip=2, limit=2)

        assert len(rules) == 2

    def test_update_rule(self, in_memory_db):
        """Test updating a rule"""
        engine = RuleEngine(in_memory_db)

        conditions = {"peer": ["Starbucks"], "category": ["Food"]}
        created = engine.create_rule(
            name="Starbucks Coffee",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        updated = engine.update_rule(
            rule_id=created["id"],
            name="Starbucks Coffee (Updated)",
            conditions={"peer": ["Starbucks"], "category": ["Food", "Beverage"]},
            account="Expenses:Food:Dining",
            confidence=0.95,
        )

        assert updated["name"] == "Starbucks Coffee (Updated)"
        assert updated["confidence"] == 0.95

    def test_delete_rule(self, in_memory_db):
        """Test deleting a rule"""
        engine = RuleEngine(in_memory_db)

        conditions = {"peer": ["Starbucks"], "category": ["Food"]}
        created = engine.create_rule(
            name="Starbucks Coffee",
            conditions=conditions,
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        result = engine.delete_rule(created["id"])

        assert result is True

        # Verify rule is deleted
        retrieved = engine.get_rule(created["id"])
        assert retrieved is None

    def test_delete_nonexistent_rule(self, in_memory_db):
        """Test deleting a non-existent rule"""
        engine = RuleEngine(in_memory_db)

        result = engine.delete_rule("nonexistent_id")

        assert result is False

    def test_match_transaction(self, in_memory_db):
        """Test matching transaction against rules"""
        engine = RuleEngine(in_memory_db)

        # Create rule for Starbucks
        engine.create_rule(
            name="Starbucks Coffee",
            conditions={"peer": ["Starbucks"], "category": ["Food"]},
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        # Create transaction
        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
        }

        # Match transaction
        matched = engine.match_transaction(transaction)

        assert matched is not None
        assert matched["account"] == "Expenses:Food:Dining"
        assert matched["confidence"] == 1.0

    def test_match_transaction_no_match(self, in_memory_db):
        """Test matching transaction with no matching rules"""
        engine = RuleEngine(in_memory_db)

        # Create rule for Starbucks
        engine.create_rule(
            name="Starbucks Coffee",
            conditions={"peer": ["Starbucks"]},
            account="Expenses:Food:Dining",
            confidence=1.0,
            source="user",
        )

        # Create transaction for different peer
        transaction = {
            "peer": "Meituan",
            "item": "Dinner",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 18:00:00",
            "amount": 120.00,
        }

        # Match transaction
        matched = engine.match_transaction(transaction)

        assert matched is None

    def test_match_transaction_multiple_conditions(self, in_memory_db):
        """Test matching transaction with multiple conditions"""
        engine = RuleEngine(in_memory_db)

        # Create rule with multiple conditions
        engine.create_rule(
            name="Starbucks Coffee (Evening)",
            conditions={
                "peer": ["Starbucks"],
                "category": ["Food"],
                "time_range": ["18:00", "22:00"],
            },
            account="Expenses:Food:Dinner",
            confidence=1.0,
            source="user",
        )

        # Create transaction matching all conditions
        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 19:00:00",
            "amount": 35.50,
        }

        # Match transaction
        matched = engine.match_transaction(transaction)

        assert matched is not None
        assert matched["account"] == "Expenses:Food:Dinner"

    def test_match_transaction_partial_conditions(self, in_memory_db):
        """Test matching transaction with partial conditions"""
        engine = RuleEngine(in_memory_db)

        # Create rule with multiple conditions
        engine.create_rule(
            name="Starbucks Coffee (Evening)",
            conditions={
                "peer": ["Starbucks"],
                "category": ["Food"],
                "time_range": ["18:00", "22:00"],
            },
            account="Expenses:Food:Dinner",
            confidence=1.0,
            source="user",
        )

        # Create transaction not matching all conditions
        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",  # Not in time range
            "amount": 35.50,
        }

        # Match transaction
        matched = engine.match_transaction(transaction)

        assert matched is None

    def test_get_matching_rules(self, in_memory_db):
        """Test getting all matching rules for a transaction"""
        engine = RuleEngine(in_memory_db)

        # Create multiple rules
        engine.create_rule(
            name="Starbucks Rule",
            conditions={"peer": ["Starbucks"]},
            account="Expenses:Food:Dining",
            confidence=0.9,
            source="user",
        )
        engine.create_rule(
            name="Food Rule",
            conditions={"category": ["Food"]},
            account="Expenses:Food:Groceries",
            confidence=0.7,
            source="auto",
        )

        # Create transaction
        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
        }

        # Get matching rules
        matched_rules = engine.get_matching_rules(transaction)

        # Should match both rules
        assert len(matched_rules) == 2

        # Should be sorted by confidence (descending)
        assert matched_rules[0]["confidence"] >= matched_rules[1]["confidence"]
