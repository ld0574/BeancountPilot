"""
Reliability-focused tests for classifier safeguards.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.classifier import Classifier
from src.db.models import Base


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


class _StubProvider:
    async def classify(self, transaction, chart_of_accounts, historical_rules, language="en"):
        return {
            "account": "Expenses:Unknown:Foo",
            "confidence": 0.95,
            "reasoning": "stub",
            "methodAccount": "Assets:Bank:Other",
        }

    async def batch_classify(
        self,
        transactions,
        chart_of_accounts,
        historical_rules,
        language="en",
        progress_callback=None,
    ):
        if progress_callback:
            progress_callback(len(transactions))
        return [
            {
                "account": "Expenses:Unknown:Foo",
                "confidence": 0.95,
                "reasoning": "stub",
                "methodAccount": "Assets:Bank:Other",
            }
            for _ in transactions
        ]


@pytest.mark.asyncio
async def test_batch_classification_normalizes_unknown_target_and_invalid_method(in_memory_db, monkeypatch):
    """Unknown target account should be normalized to chart accounts; invalid method should be cleared."""
    classifier = Classifier(in_memory_db, provider_name="deepseek")
    monkeypatch.setattr(classifier, "_get_provider", lambda: _StubProvider())
    monkeypatch.setattr(classifier, "_build_deg_prefill_map", lambda transactions: {})

    transactions = [
        {
            "id": "tx-001",
            "peer": "Demo",
            "item": "Coffee",
            "category": "Food",
            "type": "支出",
            "time": "2024-01-01 10:00:00",
            "amount": 12.0,
            "provider": "alipay",
        }
    ]
    chart = "Assets:Bank:Cash\nExpenses:Food:Dining\nExpenses:Other"

    results = await classifier.classify_transactions(transactions, chart_of_accounts=chart)

    assert len(results) == 1
    assert results[0]["targetAccount"] == "Expenses:Food:Dining"
    assert results[0]["account"] == "Expenses:Food:Dining"
    assert results[0]["methodAccount"] == ""


@pytest.mark.asyncio
async def test_single_classification_fallbacks_to_expenses_other_when_ai_account_empty(in_memory_db, monkeypatch):
    """Empty AI account should not pass through; it should fallback to a known chart account."""
    classifier = Classifier(in_memory_db, provider_name="deepseek")

    class _EmptyAccountProvider:
        async def classify(self, transaction, chart_of_accounts, historical_rules, language="en"):
            return {
                "account": "",
                "confidence": 0.8,
                "reasoning": "empty-account",
                "methodAccount": "Assets:Bank:Alipay",
            }

    monkeypatch.setattr(classifier, "_get_provider", lambda: _EmptyAccountProvider())

    tx = {
        "id": "tx-002",
        "peer": "Demo",
        "item": "Fee",
        "category": "Misc",
        "type": "支出",
        "time": "2024-01-01 12:00:00",
        "amount": 8.0,
        "provider": "alipay",
    }
    chart = "Assets:Bank:Alipay\nExpenses:Food:Dining\nExpenses:Other"

    result = await classifier.classify_transaction(tx, chart_of_accounts=chart)

    assert result["targetAccount"] == "Expenses:Other"
    assert result["account"] == "Expenses:Other"
    assert result["methodAccount"] == "Assets:Bank:Alipay"


@pytest.mark.asyncio
async def test_offset_payment_refund_pairs_are_prefiltered_before_ai(in_memory_db, monkeypatch):
    """Payment-refund offset pairs should be skipped instead of sent to AI."""
    classifier = Classifier(in_memory_db, provider_name="deepseek")

    class _FailIfCalledProvider:
        async def batch_classify(
            self,
            transactions,
            chart_of_accounts,
            historical_rules,
            language="en",
            progress_callback=None,
        ):
            raise AssertionError("AI batch classification should not be called for offset-only input")

    monkeypatch.setattr(classifier, "_get_provider", lambda: _FailIfCalledProvider())
    monkeypatch.setattr(classifier, "_build_deg_prefill_map", lambda transactions: {})

    transactions = [
        {
            "id": "tx-pay",
            "peer": "Demo Merchant",
            "item": "Demo Purchase",
            "category": "日用百货",
            "type": "支出",
            "time": "2025-01-16 13:57:25",
            "amount": 5640.0,
            "provider": "alipay",
            "raw_data": {
                "商家订单号": "T200P2444112768242375556",
                "交易状态": "交易关闭",
                "收/付款方式": "招商银行储蓄卡(8666)",
            },
        },
        {
            "id": "tx-refund",
            "peer": "Demo Merchant",
            "item": "退款-Demo Purchase",
            "category": "退款",
            "type": "不计收支",
            "time": "2025-01-16 14:25:07",
            "amount": 5640.0,
            "provider": "alipay",
            "raw_data": {
                "商家订单号": "T200P2444112768242375556",
                "交易状态": "退款成功",
                "收/付款方式": "招商银行储蓄卡(8666)",
            },
        },
    ]

    results = await classifier.classify_transactions(
        transactions,
        chart_of_accounts="Assets:Savings:Bank:CMB:D8666\nExpenses:Other\n",
    )

    assert len(results) == 2
    assert all(r["source"] == "offset" for r in results)
    assert all(bool(r.get("skipGenerate")) is True for r in results)
