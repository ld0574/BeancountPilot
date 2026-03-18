"""
Unit tests for AI prompt module
"""

import pytest

from src.ai.prompt import (
    DEFAULT_CLASSIFICATION_PROMPT,
    BATCH_CLASSIFICATION_PROMPT,
    build_classification_prompt,
    build_batch_classification_prompt,
    parse_classification_response,
    parse_batch_classification_response,
)


class TestBuildClassificationPrompt:
    """Test build_classification_prompt function"""

    def test_build_prompt_with_all_fields(self):
        """Test building prompt with all transaction fields"""
        transaction = {
            "peer": "Starbucks",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 35.50,
        }
        chart_of_accounts = "Assets:Bank\nExpenses:Food:Dining"
        historical_rules = "Starbucks -> Expenses:Food:Dining"

        prompt = build_classification_prompt(
            transaction, chart_of_accounts, historical_rules
        )

        assert "Starbucks" in prompt
        assert "Coffee" in prompt
        assert "Food" in prompt
        assert "35.5" in prompt
        assert chart_of_accounts in prompt
        assert historical_rules in prompt

    def test_build_prompt_with_missing_fields(self):
        """Test building prompt with missing transaction fields"""
        transaction = {
            "peer": "Unknown",
            "item": "",
            "category": "",
            "type": "",
            "time": "",
            "amount": "",
        }
        chart_of_accounts = "Assets:Bank"
        historical_rules = ""

        prompt = build_classification_prompt(
            transaction, chart_of_accounts, historical_rules
        )

        assert "Unknown" in prompt
        assert chart_of_accounts in prompt

    def test_build_prompt_with_custom_template(self):
        """Test building prompt with custom template"""
        transaction = {"peer": "Test", "item": "Item", "category": "Cat", "type": "Type", "time": "2024-01-01", "amount": 100}
        custom_template = "Custom: {peer} {item} {amount}"

        prompt = build_classification_prompt(
            transaction, "", "", template=custom_template
        )

        assert prompt == "Custom: Test Item 100"

    def test_default_template_contains_required_elements(self):
        """Test that default template contains required elements"""
        assert "{chart_of_accounts}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{historical_rules}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{peer}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{item}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{category}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{type}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{time}" in DEFAULT_CLASSIFICATION_PROMPT
        assert "{amount}" in DEFAULT_CLASSIFICATION_PROMPT


class TestBuildBatchClassificationPrompt:
    """Test build_batch_classification_prompt function"""

    def test_build_batch_prompt(self):
        """Test building batch classification prompt"""
        transactions = [
            {
                "peer": "Starbucks",
                "item": "Coffee",
                "category": "Food",
                "type": "支出",
                "time": "2024-01-01 10:00:00",
                "amount": 35.50,
            },
            {
                "peer": "Meituan",
                "item": "Dinner",
                "category": "Food",
                "type": "支出",
                "time": "2024-01-01 18:00:00",
                "amount": 120.00,
            },
        ]
        chart_of_accounts = "Assets:Bank\nExpenses:Food"
        historical_rules = "Starbucks -> Expenses:Food:Dining"

        prompt = build_batch_classification_prompt(
            transactions, chart_of_accounts, historical_rules
        )

        assert "Starbucks" in prompt
        assert "Meituan" in prompt
        assert "0. Payee: Starbucks" in prompt
        assert "1. Payee: Meituan" in prompt
        assert chart_of_accounts in prompt
        assert historical_rules in prompt

    def test_build_batch_prompt_with_custom_template(self):
        """Test building batch prompt with custom template"""
        transactions = [
            {"peer": "Test1", "item": "Item1", "category": "Cat1", "type": "Type1", "time": "2024-01-01", "amount": 100},
            {"peer": "Test2", "item": "Item2", "category": "Cat2", "type": "Type2", "time": "2024-01-02", "amount": 200},
        ]
        custom_template = "Batch: {transactions}"

        prompt = build_batch_classification_prompt(
            transactions, "", "", template=custom_template
        )

        assert "Batch:" in prompt
        assert "Test1" in prompt
        assert "Test2" in prompt


class TestParseClassificationResponse:
    """Test parse_classification_response function"""

    def test_parse_valid_json_response(self):
        """Test parsing valid JSON response"""
        response = '''{
  "account": "Expenses:Food:Dining",
  "confidence": 0.95,
  "reasoning": "This is a food expense"
}'''

        result = parse_classification_response(response)

        assert result["account"] == "Expenses:Food:Dining"
        assert result["confidence"] == 0.95
        assert result["reasoning"] == "This is a food expense"

    def test_parse_response_with_extra_text(self):
        """Test parsing response with extra text around JSON"""
        response = '''Here is the classification:
{
  "account": "Expenses:Transport:Taxi",
  "confidence": 0.88,
  "reasoning": "Transport expense"
}
End of response.'''

        result = parse_classification_response(response)

        assert result["account"] == "Expenses:Transport:Taxi"
        assert result["confidence"] == 0.88

    def test_parse_invalid_json_response(self):
        """Test parsing invalid JSON response"""
        response = "This is not a valid JSON"

        result = parse_classification_response(response)

        # Should return default values
        assert result["account"] == "Expenses:Other"
        assert result["confidence"] == 0.0
        assert "Error" in result["reasoning"]

    def test_parse_malformed_json_response(self):
        """Test parsing malformed JSON response"""
        response = '''{
  "account": "Expenses:Food:Dining",
  "confidence": 0.95,
  "reasoning": "Missing closing brace"
'''

        result = parse_classification_response(response)

        assert result["account"] == "Expenses:Other"
        assert result["confidence"] == 0.0


class TestParseBatchClassificationResponse:
    """Test parse_batch_classification_response function"""

    def test_parse_valid_batch_response(self):
        """Test parsing valid batch JSON response"""
        response = '''[
  {
    "index": 0,
    "account": "Expenses:Food:Dining",
    "confidence": 0.95,
    "reasoning": "Food expense"
  },
  {
    "index": 1,
    "account": "Expenses:Transport:Taxi",
    "confidence": 0.88,
    "reasoning": "Transport expense"
  }
]'''

        results = parse_batch_classification_response(response)

        assert len(results) == 2
        assert results[0]["account"] == "Expenses:Food:Dining"
        assert results[0]["index"] == 0
        assert results[1]["account"] == "Expenses:Transport:Taxi"
        assert results[1]["index"] == 1

    def test_parse_batch_response_with_extra_text(self):
        """Test parsing batch response with extra text"""
        response = '''Here are the classifications:
[
  {
    "index": 0,
    "account": "Expenses:Food:Dining",
    "confidence": 0.95,
    "reasoning": "Food expense"
  }
]
End of response.'''

        results = parse_batch_classification_response(response)

        assert len(results) == 1
        assert results[0]["account"] == "Expenses:Food:Dining"

    def test_parse_invalid_batch_response(self):
        """Test parsing invalid batch JSON response"""
        response = "This is not a valid JSON array"

        results = parse_batch_classification_response(response)

        # Should return empty list
        assert len(results) == 0

    def test_parse_malformed_batch_response(self):
        """Test parsing malformed batch JSON response"""
        response = '''[
  {
    "index": 0,
    "account": "Expenses:Food:Dining",
    "confidence": 0.95,
    "reasoning": "Missing closing bracket"
'''

        results = parse_batch_classification_response(response)

        assert len(results) == 0
