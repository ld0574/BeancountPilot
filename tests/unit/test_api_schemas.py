"""
Unit tests for API schemas
"""

import pytest
from pydantic import ValidationError

from src.api.schemas.transaction import (
    TransactionCreate,
    TransactionResponse,
    ClassificationRequest,
    ClassificationResult,
    ClassificationResponse,
    FeedbackRequest,
    FeedbackResponse,
    GenerateRequest,
    GenerateResponse,
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    UserCreate,
    UserResponse,
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeResponse,
)


class TestTransactionSchemas:
    """Test transaction-related schemas"""

    def test_transaction_create_valid(self):
        """Test valid TransactionCreate schema"""
        data = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
            "currency": "CNY",
            "provider": "alipay",
            "raw_data": '{"raw": "data"}',
        }

        transaction = TransactionCreate(**data)

        assert transaction.peer == "Starbucks"
        assert transaction.amount == 35.50
        assert transaction.currency == "CNY"

    def test_transaction_create_defaults(self):
        """Test TransactionCreate with default values"""
        data = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
        }

        transaction = TransactionCreate(**data)

        assert transaction.currency == "CNY"  # Default
        assert transaction.provider == ""  # Default

    def test_transaction_create_invalid_amount(self):
        """Test TransactionCreate with invalid amount"""
        data = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": "not_a_number",
        }

        with pytest.raises(ValidationError):
            TransactionCreate(**data)

    def test_transaction_response_valid(self):
        """Test valid TransactionResponse schema"""
        data = {
            "id": "test_tx_001",
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
            "currency": "CNY",
            "provider": "alipay",
            "raw_data": '{"raw": "data"}',
            "created_at": "2024-01-01T10:00:00Z",
        }

        transaction = TransactionResponse(**data)

        assert transaction.id == "test_tx_001"
        assert transaction.peer == "Starbucks"


class TestClassificationSchemas:
    """Test classification-related schemas"""

    def test_classification_request_valid(self):
        """Test valid ClassificationRequest schema"""
        data = {
            "transactions": [
                {
                    "peer": "Starbucks",
                    "item": "Coffee",
                    "category": "Food",
                    "type": "支出",
                    "time": "2024-01-01 10:00:00",
                    "amount": 35.50,
                }
            ],
            "chart_of_accounts": "Assets:Bank\nExpenses:Food",
            "provider": "deepseek",
        }

        request = ClassificationRequest(**data)

        assert len(request.transactions) == 1
        assert request.chart_of_accounts == "Assets:Bank\nExpenses:Food"
        assert request.provider == "deepseek"

    def test_classification_request_defaults(self):
        """Test ClassificationRequest with default provider"""
        data = {
            "transactions": [],
            "chart_of_accounts": "Assets:Bank",
        }

        request = ClassificationRequest(**data)

        assert request.provider == "deepseek"  # Default

    def test_classification_result_valid(self):
        """Test valid ClassificationResult schema"""
        data = {
            "transaction_id": "test_tx_001",
            "account": "Expenses:Food:Dining",
            "confidence": 0.95,
            "reasoning": "Food expense",
            "source": "ai",
        }

        result = ClassificationResult(**data)

        assert result.account == "Expenses:Food:Dining"
        assert result.confidence == 0.95
        assert result.source == "ai"

    def test_classification_response_valid(self):
        """Test valid ClassificationResponse schema"""
        data = {
            "results": [
                {
                    "transaction_id": "test_tx_001",
                    "account": "Expenses:Food:Dining",
                    "confidence": 0.95,
                    "reasoning": "Food expense",
                    "source": "ai",
                }
            ]
        }

        response = ClassificationResponse(**data)

        assert len(response.results) == 1
        assert response.results[0].account == "Expenses:Food:Dining"

    def test_classification_result_invalid_confidence(self):
        """Test ClassificationResult with invalid confidence"""
        data = {
            "transaction_id": "test_tx_001",
            "account": "Expenses:Food:Dining",
            "confidence": 1.5,  # Invalid: should be 0-1
            "reasoning": "Food expense",
            "source": "ai",
        }

        with pytest.raises(ValidationError):
            ClassificationResult(**data)


class TestFeedbackSchemas:
    """Test feedback-related schemas"""

    def test_feedback_request_valid(self):
        """Test valid FeedbackRequest schema"""
        data = {
            "transaction_id": "test_tx_001",
            "original_account": "Expenses:Food:Dining",
            "corrected_account": "Expenses:Food:Groceries",
            "action": "modify",
        }

        request = FeedbackRequest(**data)

        assert request.transaction_id == "test_tx_001"
        assert request.action == "modify"

    def test_feedback_request_valid_actions(self):
        """Test FeedbackRequest with valid actions"""
        valid_actions = ["accept", "reject", "modify"]

        for action in valid_actions:
            data = {
                "transaction_id": "test_tx_001",
                "action": action,
            }
            request = FeedbackRequest(**data)
            assert request.action == action

    def test_feedback_request_invalid_action(self):
        """Test FeedbackRequest with invalid action"""
        data = {
            "transaction_id": "test_tx_001",
            "action": "invalid_action",
        }

        with pytest.raises(ValidationError):
            FeedbackRequest(**data)

    def test_feedback_response_valid(self):
        """Test valid FeedbackResponse schema"""
        data = {
            "id": "test_fb_001",
            "transaction_id": "test_tx_001",
            "original_account": "Expenses:Food:Dining",
            "corrected_account": "Expenses:Food:Groceries",
            "action": "modify",
            "created_at": "2024-01-01T10:00:00Z",
        }

        response = FeedbackResponse(**data)

        assert response.id == "test_fb_001"
        assert response.action == "modify"


class TestGenerateSchemas:
    """Test generation-related schemas"""

    def test_generate_request_valid(self):
        """Test valid GenerateRequest schema"""
        data = {
            "transactions": [
                {
                    "peer": "Starbucks",
                    "item": "Coffee",
                    "category": "Food",
                    "type": "支出",
                    "time": "2024-01-01 10:00:00",
                    "amount": 35.50,
                }
            ],
            "provider": "alipay",
        }

        request = GenerateRequest(**data)

        assert len(request.transactions) == 1
        assert request.provider == "alipay"

    def test_generate_response_valid(self):
        """Test valid GenerateResponse schema"""
        data = {
            "success": True,
            "beancount_file": "2024-01-01 * \"Starbucks\" \"Coffee\"\n  Expenses:Food:Dining  35.50 CNY\n  Assets:Bank:Alipay",
            "message": "Generation successful",
        }

        response = GenerateResponse(**data)

        assert response.success is True
        assert "Expenses:Food:Dining" in response.beancount_file

    def test_generate_response_failure(self):
        """Test GenerateResponse for failure case"""
        data = {
            "success": False,
            "beancount_file": "",
            "message": "Generation failed",
        }

        response = GenerateResponse(**data)

        assert response.success is False
        assert response.message == "Generation failed"


class TestRuleSchemas:
    """Test rule-related schemas"""

    def test_rule_create_valid(self):
        """Test valid RuleCreate schema"""
        data = {
            "name": "Coffee rule",
            "conditions": {"peer": ["Starbucks"]},
            "account": "Expenses:Food:Dining",
            "confidence": 0.9,
            "source": "user",
        }

        rule = RuleCreate(**data)

        assert rule.name == "Coffee rule"
        assert rule.confidence == 0.9
        assert rule.source == "user"

    def test_rule_create_invalid_confidence(self):
        """Test RuleCreate with invalid confidence"""
        data = {
            "name": "Bad rule",
            "conditions": {"peer": ["Starbucks"]},
            "account": "Expenses:Food:Dining",
            "confidence": 1.5,
        }

        with pytest.raises(ValidationError):
            RuleCreate(**data)

    def test_rule_update_valid(self):
        """Test valid RuleUpdate schema"""
        data = {
            "name": "Updated rule",
            "account": "Expenses:Food:Groceries",
        }

        rule = RuleUpdate(**data)

        assert rule.name == "Updated rule"
        assert rule.account == "Expenses:Food:Groceries"

    def test_rule_response_valid(self):
        """Test valid RuleResponse schema"""
        data = {
            "id": "rule_001",
            "name": "Coffee rule",
            "conditions": {"peer": ["Starbucks"]},
            "account": "Expenses:Food:Dining",
            "confidence": 1.0,
            "source": "user",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
        }

        rule = RuleResponse(**data)

        assert rule.id == "rule_001"
        assert rule.account == "Expenses:Food:Dining"


class TestUserSchemas:
    """Test user-related schemas"""

    def test_user_create_valid(self):
        """Test valid UserCreate schema"""
        user = UserCreate(username="tester")
        assert user.username == "tester"

    def test_user_response_valid(self):
        """Test valid UserResponse schema"""
        data = {
            "id": "user_001",
            "username": "tester",
            "created_at": "2024-01-01T00:00:00Z",
        }
        user = UserResponse(**data)
        assert user.id == "user_001"
        assert user.username == "tester"


class TestKnowledgeSchemas:
    """Test knowledge-related schemas"""

    def test_knowledge_create_valid(self):
        """Test valid KnowledgeCreate schema"""
        record = KnowledgeCreate(key="peer:Starbucks", value="Expenses:Food:Dining")
        assert record.key == "peer:Starbucks"

    def test_knowledge_update_valid(self):
        """Test valid KnowledgeUpdate schema"""
        record = KnowledgeUpdate(value="Expenses:Food:Groceries")
        assert record.value == "Expenses:Food:Groceries"

    def test_knowledge_response_valid(self):
        """Test valid KnowledgeResponse schema"""
        data = {
            "id": "kn_001",
            "key": "peer:Starbucks",
            "value": "Expenses:Food:Dining",
            "source": "feedback",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
        }
        record = KnowledgeResponse(**data)
        assert record.id == "kn_001"
        assert record.key == "peer:Starbucks"
