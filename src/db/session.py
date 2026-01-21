"""
Database session management
"""

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.db.models import Base

# Default database path
DEFAULT_DB_PATH = Path.home() / ".beancountpilot" / "data" / "beancountpilot.db"


def get_db_path() -> Path:
    """Get database file path"""
    # Read from environment variable first
    db_path = os.getenv("BEANCOUNTPILOT_DB_PATH")
    if db_path:
        return Path(db_path)

    # Ensure directory exists
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


def get_engine():
    """Get database engine"""
    db_path = get_db_path()
    # Use SQLite, enable WAL mode for better concurrent performance
    db_url = f"sqlite:///{db_path}?journal_mode=WAL"
    return create_engine(db_url, echo=False, pool_pre_ping=True)


# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db():
    """Initialize database, create all tables"""
    global _engine, _SessionLocal

    _engine = get_engine()
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create all tables
    Base.metadata.create_all(bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """
    Get database session
    Used for FastAPI dependency injection
    """
    if _SessionLocal is None:
        init_db()

    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session() -> Session:
    """Get database session (non-generator version)"""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()
