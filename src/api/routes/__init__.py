"""
API routes module
"""

from src.api.routes import (
    upload,
    classify,
    feedback,
    generate,
    rules,
    users,
    knowledge,
    ws,
    ai_config,
    chart_of_accounts,
)

__all__ = [
    "upload",
    "classify",
    "feedback",
    "generate",
    "rules",
    "users",
    "knowledge",
    "ws",
    "ai_config",
    "chart_of_accounts",
]
