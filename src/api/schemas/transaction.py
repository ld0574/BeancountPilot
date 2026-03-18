"""
Transaction-related Pydantic models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# Transaction-related models
class TransactionCreate(BaseModel):
    """Transaction creation request model"""

    peer: str = Field(..., description="Payee")
    item: str = Field(..., description="Item")
    category: str = Field(..., description="Category")
    type: str = Field(..., description="Transaction type")
    time: str = Field(..., description="Transaction time")
    amount: float = Field(..., description="Amount")
    currency: str = Field(default="CNY", description="Currency")
    provider: str = Field(default="", description="Provider")
    raw_data: Optional[str] = Field(None, description="Raw data")


class TransactionResponse(BaseModel):
    """Transaction response model"""

    id: str
    peer: str
    item: str
    category: str
    type: str
    time: str
    amount: float
    currency: str
    provider: str
    raw_data: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


# Classification-related models
class ClassificationRequest(BaseModel):
    """Classification request model"""

    transactions: List[Dict[str, Any]] = Field(
        ..., description="List of transactions to classify"
    )
    chart_of_accounts: str = Field(..., description="Chart of accounts")
    provider: str = Field(default="deepseek", description="AI Provider")
    language: str = Field(default="en", description="UI language, e.g. en/zh")


class ClassificationResult(BaseModel):
    """Classification result model"""

    transaction_id: str
    account: str
    targetAccount: Optional[str] = None
    methodAccount: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    source: str


class ClassificationResponse(BaseModel):
    """Classification response model"""

    results: List[ClassificationResult]


# Feedback-related models
class FeedbackRequest(BaseModel):
    """Feedback request model"""

    transaction_id: str
    original_account: Optional[str] = None
    corrected_account: Optional[str] = None
    action: Literal["accept", "reject", "modify"] = Field(
        ...,
        description="Action type: accept, reject, modify",
    )


class FeedbackResponse(BaseModel):
    """Feedback response model"""

    id: str
    transaction_id: str
    original_account: Optional[str]
    corrected_account: Optional[str]
    action: str
    created_at: str

    class Config:
        from_attributes = True


# Generation-related models
class GenerateRequest(BaseModel):
    """Beancount file generation request model"""

    transactions: List[Dict[str, Any]] = Field(
        ..., description="Transaction list"
    )
    provider: str = Field(default="alipay", description="Data provider")
    config_file: Optional[str] = Field(None, description="Configuration file path")


class GenerateResponse(BaseModel):
    """Generation response model"""

    success: bool
    beancount_file: str
    message: str


# Rule-related models
class RuleCreate(BaseModel):
    """Rule creation request model"""

    name: str
    conditions: Dict[str, Any]
    account: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="user", description="user or auto")


class RuleUpdate(BaseModel):
    """Rule update request model"""

    name: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    account: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source: Optional[str] = Field(default=None, description="user or auto")


class RuleResponse(BaseModel):
    """Rule response model"""

    id: str
    name: str
    conditions: Dict[str, Any]
    account: str
    confidence: float
    source: str
    created_at: str
    updated_at: Optional[str] = None


class UserCreate(BaseModel):
    """User creation request model"""

    username: str


class UserResponse(BaseModel):
    """User response model"""

    id: str
    username: str
    created_at: str

    class Config:
        from_attributes = True


class KnowledgeCreate(BaseModel):
    """Knowledge creation request model"""

    key: str
    value: str
    source: str = Field(default="feedback")


class KnowledgeUpdate(BaseModel):
    """Knowledge update request model"""

    value: str


class KnowledgeResponse(BaseModel):
    """Knowledge response model"""

    id: str
    key: str
    value: str
    source: str
    created_at: str
    updated_at: str
