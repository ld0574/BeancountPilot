"""
Chart of accounts configuration routes.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.repositories import UserConfigRepository
from src.db.session import get_db

router = APIRouter()


class ChartOfAccountsPayload(BaseModel):
    chart_of_accounts: str = Field(default="")


@router.get("/config/chart-of-accounts")
async def get_chart_of_accounts(db: Session = Depends(get_db)):
    """Get chart of accounts."""
    value = UserConfigRepository.get(db, "chart_of_accounts")
    return {"chart_of_accounts": value or ""}


@router.put("/config/chart-of-accounts")
async def save_chart_of_accounts(payload: ChartOfAccountsPayload, db: Session = Depends(get_db)):
    """Save chart of accounts."""
    value = payload.chart_of_accounts or ""
    UserConfigRepository.set(db, "chart_of_accounts", value)
    return {"message": "Chart of accounts saved", "chart_of_accounts": value}
