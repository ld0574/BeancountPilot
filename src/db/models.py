"""
SQLAlchemy database models
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Transaction(Base):
    """Transaction table"""

    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    peer = Column(String, nullable=True, index=True)
    item = Column(String, nullable=True)
    category = Column(String, nullable=True)
    type = Column(String, nullable=True)
    time = Column(String, nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="CNY")
    provider = Column(String, nullable=True, index=True)
    raw_data = Column(Text, nullable=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    # Relationships
    classifications = relationship(
        "Classification", back_populates="transaction", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="transaction", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_peer_item", "peer", "item"),
        Index("idx_provider_time", "provider", "time"),
    )


class Classification(Base):
    """Classification record table"""

    __tablename__ = "classifications"

    id = Column(String, primary_key=True)
    transaction_id = Column(
        String, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    account = Column(String, nullable=False)
    confidence = Column(Float, default=0.0)
    source = Column(String, default="ai")  # 'ai', 'rule', 'user'
    reasoning = Column(Text, nullable=True)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    # Relationships
    transaction = relationship("Transaction", back_populates="classifications")


class Feedback(Base):
    """Feedback table"""

    __tablename__ = "feedback"

    id = Column(String, primary_key=True)
    transaction_id = Column(
        String, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    original_account = Column(String, nullable=True)
    corrected_account = Column(String, nullable=True)
    action = Column(String, nullable=False)  # 'accept', 'reject', 'modify'
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())

    # Relationships
    transaction = relationship("Transaction", back_populates="feedbacks")


class Rule(Base):
    """Rule table"""

    __tablename__ = "rules"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    conditions = Column(Text, nullable=False)  # JSON format
    account = Column(String, nullable=False)
    confidence = Column(Float, default=1.0)
    source = Column(String, default="user")  # 'user', 'auto'
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class UserConfig(Base):
    """User configuration table"""

    __tablename__ = "user_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())
