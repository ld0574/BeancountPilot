"""
Reliability-focused tests for generation-time account validation.
"""

from src.api.routes.generate import _validate_required_accounts


def test_validate_required_accounts_rejects_empty_and_other():
    issues = _validate_required_accounts(
        [
            {
                "id": "tx-1",
                "peer": "Starbucks",
                "targetAccount": "Expenses:Other",
                "methodAccount": "Assets:Bank:Alipay",
            },
            {
                "id": "tx-2",
                "peer": "Taxi",
                "targetAccount": "Expenses:Transport:Taxi",
                "methodAccount": "",
            },
            {
                "id": "tx-3",
                "peer": "Transfer",
                "targetAccount": "Expenses:Food:Dining",
                "methodAccount": "Assets:Bank:Other",
            },
        ]
    )

    assert len(issues) == 3
    assert issues[0]["issues"]["targetAccount"] == "other"
    assert issues[1]["issues"]["methodAccount"] == "empty"
    assert issues[2]["issues"]["methodAccount"] == "other"


def test_validate_required_accounts_allows_legacy_rows_without_account_fields():
    issues = _validate_required_accounts(
        [
            {
                "id": "legacy-1",
                "peer": "Legacy Import",
                "item": "Coffee",
                "amount": 9.9,
            }
        ]
    )

    assert issues == []


def test_validate_required_accounts_accepts_complete_accounts():
    issues = _validate_required_accounts(
        [
            {
                "id": "ok-1",
                "peer": "Starbucks",
                "targetAccount": "Expenses:Food:Dining",
                "methodAccount": "Assets:Bank:Alipay",
            }
        ]
    )

    assert issues == []
