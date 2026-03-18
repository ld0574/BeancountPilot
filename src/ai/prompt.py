"""
Prompt Template Management
"""

from typing import Dict, Any, List


def _reasoning_language_instruction(language: str = "en") -> str:
    """Build prompt instruction for reasoning language."""
    lang = str(language or "en").strip().lower()
    if lang.startswith("zh"):
        return "Write `reasoning` in Simplified Chinese."
    return "Write `reasoning` in English."


OUTPUT_CONSTRAINTS = """Output rules (must follow):
- Return ONLY valid JSON. Do NOT include markdown fences, XML tags, or extra text.
- Do NOT include thinking, analysis, or explanations outside the JSON fields.
- Do NOT wrap JSON in quotes.
"""

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
Rules:
- You must choose targetAccount and methodAccount exactly from "User chart of accounts". Do not invent accounts.
- targetAccount = category account (expense/income/etc).
- methodAccount = payment/funding account (typically Assets:* or Liabilities:*).
- Never output empty methodAccount.
- {reasoning_language_instruction}
- Keep reasoning concise (one short sentence).
- {output_constraints}

Output format (JSON):
{{
  "targetAccount": "Expenses:Food:Dining",
  "methodAccount": "Assets:Bank:Alipay",
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
Rules:
- You must choose targetAccount and methodAccount exactly from "User chart of accounts". Do not invent accounts.
- targetAccount = category account (expense/income/etc).
- methodAccount = payment/funding account (typically Assets:* or Liabilities:*).
- Never output empty methodAccount.
- {reasoning_language_instruction}
- Keep reasoning concise (one short sentence).
- {output_constraints}

Output format (JSON array):
[
  {{
    "index": 0,
    "targetAccount": "Expenses:Food:Dining",
    "methodAccount": "Assets:Bank:Alipay",
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
    language: str = "en",
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
        reasoning_language_instruction=_reasoning_language_instruction(language),
        output_constraints=OUTPUT_CONSTRAINTS.strip(),
    )


def build_batch_classification_prompt(
    transactions: List[Dict[str, Any]],
    chart_of_accounts: str,
    historical_rules: str,
    template: str = None,
    language: str = "en",
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
        reasoning_language_instruction=_reasoning_language_instruction(language),
        output_constraints=OUTPUT_CONSTRAINTS.strip(),
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
    json_match = re.search(r"\{[\s\S]*\}", response, re.DOTALL)
    if json_match:
        response = json_match.group()

    try:
        result = json.loads(response)
        target = str(result.get("targetAccount", "")).strip()
        account = str(result.get("account", "")).strip()
        if not target and account:
            target = account
        if not target:
            target = "Expenses:Other"
        result["targetAccount"] = target
        result["account"] = target

        method = str(result.get("methodAccount", "")).strip()
        result["methodAccount"] = method

        if "confidence" not in result:
            result["confidence"] = 0.5
        if "reasoning" not in result:
            result["reasoning"] = ""
        return result
    except json.JSONDecodeError:
        # Parse failed, return default values
        return {
            "account": "Expenses:Other",
            "targetAccount": "Expenses:Other",
            "methodAccount": "",
            "confidence": 0.0,
            "reasoning": f"Error: parse failed: {response[:100]}",
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

    def _normalize(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            target = str(result.get("targetAccount", "")).strip()
            account = str(result.get("account", "")).strip()
            if not target and account:
                target = account
            if not target:
                target = "Expenses:Other"
            result["targetAccount"] = target
            result["account"] = target
            result["methodAccount"] = str(result.get("methodAccount", "")).strip()
            if "confidence" not in result:
                result["confidence"] = 0.5
            if "reasoning" not in result:
                result["reasoning"] = ""
            normalized.append(result)
        return normalized

    def _try_load(text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    candidates: List[str] = []

    # Extract fenced JSON blocks first.
    for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", response, re.IGNORECASE):
        candidates.append(match.group(1))

    # Add raw response.
    candidates.append(response)

    for text in list(candidates):
        # Try JSON array part.
        json_match = re.search(r"\[[\s\S]*\]", text, re.DOTALL)
        if json_match:
            candidates.append(json_match.group())
        # Try JSON object part.
        obj_match = re.search(r"\{[\s\S]*\}", text, re.DOTALL)
        if obj_match:
            candidates.append(obj_match.group())

    # Attempt to parse candidates.
    for text in candidates:
        data = _try_load(text)
        if isinstance(data, list):
            return _normalize(data)
        if isinstance(data, dict):
            for key in ("results", "data", "items"):
                if isinstance(data.get(key), list):
                    return _normalize(data[key])

    # Fallback: parse JSON objects line-by-line / mixed objects.
    object_candidates: List[Dict[str, Any]] = []
    for match in re.finditer(r"\{[\s\S]*?\}", response, re.DOTALL):
        data = _try_load(match.group())
        if isinstance(data, dict):
            object_candidates.append(data)
    if object_candidates:
        return _normalize(object_candidates)

    # Parse failed, return empty list
    return []
