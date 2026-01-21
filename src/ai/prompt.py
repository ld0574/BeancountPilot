"""
Prompt Template Management
"""

from typing import Dict, Any, List


# Default classification prompt template
DEFAULT_CLASSIFICATION_PROMPT = """You are a professional financial accounting assistant, responsible for classifying transactions into Beancount accounts.

User chart of accounts:
{chart_of_accounts}

Historical classification rules:
{historical_rules}

Transaction to classify:
- Payee: {peer}
- Item: {item}
- Category: {category}
- Transaction type: {type}
- Time: {time}
- Amount: {amount}

Please analyze the above transaction, select the most appropriate account from the chart of accounts, and provide a confidence score (0-1).

Output format (JSON):
{{
  "account": "Expenses:Food:Dining",
  "confidence": 0.95,
  "reasoning": "Explain the classification reason"
}}

Return only JSON, do not include any other content."""


# Batch classification prompt template
BATCH_CLASSIFICATION_PROMPT = """You are a professional financial accounting assistant, responsible for classifying multiple transactions into Beancount accounts.

User chart of accounts:
{chart_of_accounts}

Historical classification rules:
{historical_rules}

List of transactions to classify:
{transactions}

Please analyze the above transactions, for each transaction select the most appropriate account from the chart of accounts, and provide a confidence score (0-1).

Output format (JSON array):
[
  {{
    "index": 0,
    "account": "Expenses:Food:Dining",
    "confidence": 0.95,
    "reasoning": "Explain the classification reason"
  }},
  ...
]

Return only JSON array, do not include any other content."""


def build_classification_prompt(
    transaction: Dict[str, Any],
    chart_of_accounts: str,
    historical_rules: str,
    template: str = None,
) -> str:
    """
    Build classification prompt

    Args:
        transaction: Transaction data
        chart_of_accounts: Chart of accounts
        historical_rules: Historical rules
        template: Custom template (optional)

    Returns:
        Formatted prompt
    """
    if template is None:
        template = DEFAULT_CLASSIFICATION_PROMPT

    return template.format(
        chart_of_accounts=chart_of_accounts,
        historical_rules=historical_rules,
        peer=transaction.get("peer", ""),
        item=transaction.get("item", ""),
        category=transaction.get("category", ""),
        type=transaction.get("type", ""),
        time=transaction.get("time", ""),
        amount=transaction.get("amount", ""),
    )


def build_batch_classification_prompt(
    transactions: List[Dict[str, Any]],
    chart_of_accounts: str,
    historical_rules: str,
    template: str = None,
) -> str:
    """
    Build batch classification prompt

    Args:
        transactions: List of transactions
        chart_of_accounts: Chart of accounts
        historical_rules: Historical rules
        template: Custom template (optional)

    Returns:
        Formatted prompt
    """
    if template is None:
        template = BATCH_CLASSIFICATION_PROMPT

    # Format transaction list
    tx_list = []
    for i, tx in enumerate(transactions):
        tx_list.append(
            f"{i}. Payee: {tx.get('peer', '')}, "
            f"Item: {tx.get('item', '')}, "
            f"Category: {tx.get('category', '')}, "
            f"Transaction type: {tx.get('type', '')}, "
            f"Time: {tx.get('time', '')}, "
            f"Amount: {tx.get('amount', '')}"
        )

    transactions_str = "\n".join(tx_list)

    return template.format(
        chart_of_accounts=chart_of_accounts,
        historical_rules=historical_rules,
        transactions=transactions_str,
    )


def parse_classification_response(response: str) -> Dict[str, Any]:
    """
    Parse classification response

    Args:
        response: Response from LLM

    Returns:
        Parsed classification result
    """
    import json
    import re

    # Try to extract JSON part
    json_match = re.search(r'\{[^{}]*"account"[^{}]*\}', response, re.DOTALL)
    if json_match:
        response = json_match.group()

    try:
        result = json.loads(response)
        # Ensure required fields exist
        if "account" not in result:
            result["account"] = "Expenses:Misc"
        if "confidence" not in result:
            result["confidence"] = 0.5
        if "reasoning" not in result:
            result["reasoning"] = ""
        return result
    except json.JSONDecodeError:
        # Parse failed, return default values
        return {
            "account": "Expenses:Misc",
            "confidence": 0.0,
            "reasoning": f"Parse failed: {response[:100]}",
        }


def parse_batch_classification_response(response: str) -> List[Dict[str, Any]]:
    """
    Parse batch classification response

    Args:
        response: Response from LLM

    Returns:
        List of parsed classification results
    """
    import json
    import re

    # Try to extract JSON array part
    json_match = re.search(r'\[[^\]]*\]', response, re.DOTALL)
    if json_match:
        response = json_match.group()

    try:
        results = json.loads(response)
        # Ensure each result has required fields
        for result in results:
            if "account" not in result:
                result["account"] = "Expenses:Misc"
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "reasoning" not in result:
                result["reasoning"] = ""
        return results
    except json.JSONDecodeError:
        # Parse failed, return empty list
        return []
