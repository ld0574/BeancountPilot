"""
Unit tests for database initialization helpers.
"""

from pathlib import Path

from src.db import init as db_init


def test_init_default_ledger_files_creates_expected_files(monkeypatch, tmp_path):
    """Should create all default .bean files when missing."""
    fake_db_path = tmp_path / "beancountpilot.db"
    monkeypatch.setattr(db_init, "get_db_path", lambda: fake_db_path)

    created = db_init._init_default_ledger_files()

    expected = {
        "assets.bean",
        "equity.bean",
        "expenses.bean",
        "income.bean",
        "liabilities.bean",
    }
    assert set(created) == expected

    liabilities_file = tmp_path / "liabilities.bean"
    assert liabilities_file.exists()
    text = liabilities_file.read_text(encoding="utf-8")
    assert "2010-01-01 open Liabilities:CreditCard:Bank:CMB:C1915 CNY" in text


def test_init_default_ledger_files_is_idempotent(monkeypatch, tmp_path):
    """Should not overwrite existing template files."""
    fake_db_path = tmp_path / "beancountpilot.db"
    monkeypatch.setattr(db_init, "get_db_path", lambda: fake_db_path)

    existing = tmp_path / "assets.bean"
    existing.write_text("custom-content\n", encoding="utf-8")

    created = db_init._init_default_ledger_files()
    assert "assets.bean" not in created
    assert existing.read_text(encoding="utf-8") == "custom-content\n"
