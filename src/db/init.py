"""
Database initialization script
Creates database tables and initializes default data
"""

import sys
import json
from pathlib import Path

from src.db.models import Base
from src.db.session import init_db, get_session
from src.db.repositories import UserConfigRepository
from src.utils.config import load_config, _get_default_config


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
Expenses:Misc
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
