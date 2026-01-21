"""
Transaction-related Pydantic models
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
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


class ClassificationResult(BaseModel):
    """Classification result model"""

    transaction_id: str
    account: str
    confidence: float
    reasoning: str
    source: str


class ClassificationResponse(BaseModel):
    """Classification response model"""

    results: List[ClassificationResult]


# Feedback-related models
class FeedbackRequest(BaseModel):
    """Feedback request model"""

    transaction_id: str
    original_account: Optional[str]
    corrected_account: Optional[str]
    action: str = Field(..., description="Action type: accept, reject, modify")


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
