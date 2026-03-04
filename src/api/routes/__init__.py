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
]
