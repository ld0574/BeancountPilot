"""
Database initialization script
Creates database tables and initializes default data
"""

import sys
import json
from pathlib import Path

from src.db.models import Base
from src.db.session import init_db, get_session, get_db_path
from src.db.repositories import UserConfigRepository
from src.utils.config import load_config, _get_default_config


DEFAULT_LEDGER_FILES = {
    "assets.bean": """; BeancountPilot default assets accounts
2010-01-01 open Assets:Bank:Cash CNY  ; 现金
2010-01-01 open Assets:Bank:Alipay CNY  ; 支付宝余额
2010-01-01 open Assets:Bank:WeChat CNY  ; 微信零钱
""",
    "equity.bean": """; BeancountPilot default equity accounts
2010-01-01 open Equity:OpeningBalances CNY  ; 期初余额
2010-01-01 open Equity:RetainedEarnings CNY  ; 留存收益
""",
    "expenses.bean": """; BeancountPilot default expenses accounts
2010-01-01 open Expenses:Food:Dining CNY  ; 餐饮
2010-01-01 open Expenses:Food:Groceries CNY  ; 买菜
2010-01-01 open Expenses:Transport:Taxi CNY  ; 打车
2010-01-01 open Expenses:Transport:Subway CNY  ; 地铁
2010-01-01 open Expenses:Utilities:Phone CNY  ; 手机费
2010-01-01 open Expenses:Utilities:Internet CNY  ; 宽带费
""",
    "income.bean": """; BeancountPilot default income accounts
2010-01-01 open Income:Salary CNY  ; 工资收入
2010-01-01 open Income:Investment CNY  ; 投资收入
2010-01-01 open Income:Other CNY  ; 其他收入
""",
    "liabilities.bean": """; BeancountPilot default liabilities accounts
2010-01-01 open Liabilities:CreditCard:Bank:CMB:C1915 CNY  ; 招商银行信用卡商务(1915)
""",
}


def init_database():
    """
    Initialize database with tables and default configuration
    """
    print("Initializing BeancountPilot database...")

    # Initialize database tables
    init_db()
    print("✓ Database tables created")

    # Initialize default configuration
    db = get_session()
    try:
        _init_default_config(db)
        print("✓ Default configuration initialized")
        created_files = _init_default_ledger_files()
        if created_files:
            print(f"✓ Ledger templates created: {', '.join(created_files)}")
        else:
            print("✓ Ledger templates already exist")
    finally:
        db.close()

    print("\nDatabase initialization complete!")


def _init_default_config(db):
    """
    Initialize default configuration values

    Args:
        db: Database session
    """
    # Default chart of accounts
    default_chart_of_accounts = """Assets:Bank:Alipay
Assets:Bank:WeChat
Assets:Bank:Cash
Expenses:Food:Dining
Expenses:Food:Groceries
Expenses:Transport:Taxi
Expenses:Transport:Subway
Expenses:Shopping:Clothing
Expenses:Shopping:Electronics
Expenses:Entertainment:Movies
Expenses:Entertainment:Games
Expenses:Utilities:Phone
Expenses:Utilities:Internet
Expenses:Utilities:Electricity
Expenses:Health:Medicine
Expenses:Health:Insurance
Expenses:Education:Books
Expenses:Education:Courses
Expenses:Travel:Hotels
Expenses:Travel:Transport
Expenses:Other
Liabilities:CreditCard:Bank:CMB:C1915
Equity:OpeningBalances
Income:Salary
Income:Investment
Income:Other"""

    # Set default chart of accounts if not exists
    if UserConfigRepository.get(db, "chart_of_accounts") is None:
        UserConfigRepository.set(db, "chart_of_accounts", default_chart_of_accounts)

    # Set default AI provider if not exists
    if UserConfigRepository.get(db, "ai_default_provider") is None:
        UserConfigRepository.set(db, "ai_default_provider", "deepseek")

    # Set default AI config snapshot if not exists
    if UserConfigRepository.get(db, "ai_config") is None:
        config = load_config()
        ai_config = config.get("ai") or _get_default_config().get("ai", {})
        UserConfigRepository.set(db, "ai_config", json.dumps(ai_config, ensure_ascii=False))

    # Set default language if not exists
    if UserConfigRepository.get(db, "language") is None:
        UserConfigRepository.set(db, "language", "en")


def _init_default_ledger_files() -> list[str]:
    """
    Initialize default Beancount ledger files in data directory.

    Returns:
        List of newly created filenames.
    """
    data_dir = get_db_path().parent
    data_dir.mkdir(parents=True, exist_ok=True)

    created = []
    for filename, content in DEFAULT_LEDGER_FILES.items():
        file_path = data_dir / filename
        if file_path.exists():
            continue

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.rstrip() + "\n")
        created.append(filename)

    return created


def reset_database():
    """
    Reset database by dropping all tables and recreating them
    WARNING: This will delete all data!
    """
    print("WARNING: This will delete all data in the database!")
    confirm = input("Are you sure you want to continue? (yes/no): ")

    if confirm.lower() != "yes":
        print("Operation cancelled.")
        return

    print("Resetting database...")

    # Get engine and drop all tables
    from src.db.session import get_engine
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    print("✓ Database tables dropped")

    # Reinitialize
    init_database()


def main():
    """
    Main entry point for database initialization
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="BeancountPilot database initialization utility"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset database (WARNING: deletes all data)"
    )

    args = parser.parse_args()

    if args.reset:
        reset_database()
    else:
        init_database()


if __name__ == "__main__":
    main()
