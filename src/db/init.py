"""
Database initialization script
"""

import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.session import init_db
from src.db.repositories import UserConfigRepository


def main():
    """Initialize database"""
    print("🚀 Starting database initialization...")

    # Initialize database tables
    init_db()
    print("✅ Database tables created successfully")

    # Initialize default configuration
    from src.db.session import get_session

    db = get_session()

    try:
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

        UserConfigRepository.set(
            db, "chart_of_accounts", default_chart_of_accounts
        )
        print("✅ Default chart of accounts configured successfully")

        # Default AI configuration
        import json

        default_ai_config = {
            "default_provider": "deepseek",
            "providers": {
                "openai": {
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "",
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "timeout": 30,
                },
                "deepseek": {
                    "api_base": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                    "temperature": 0.3,
                    "timeout": 30,
                },
                "ollama": {
                    "api_base": "http://localhost:11434/v1",
                    "api_key": "ollama",
                    "model": "llama3.2:3b",
                    "temperature": 0.3,
                    "timeout": 60,
                },
            },
        }

        UserConfigRepository.set(
            db, "ai_config", json.dumps(default_ai_config, ensure_ascii=False)
        )
        print("✅ Default AI configuration configured successfully")

        print("\n🎉 Database initialization completed!")
        print("\n📝 Notes:")
        print("  - Database file location: ~/.beancountpilot/data/beancountpilot.db")
        print("  - Please configure AI API Key in the application")
        print("  - Default configuration can be modified through settings page")

    finally:
        db.close()


if __name__ == "__main__":
    main()
