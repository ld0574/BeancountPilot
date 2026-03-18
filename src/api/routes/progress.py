"""
Progress summary routes.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db.session import get_db
from src.db.models import Transaction, Classification

router = APIRouter()


@router.get("/progress/classification")
async def classification_progress(db: Session = Depends(get_db)):
    """Get overall classification progress."""
    total = db.query(func.count(Transaction.id)).scalar() or 0
    classified = (
        db.query(func.count(func.distinct(Classification.transaction_id))).scalar() or 0
    )
    ratio = (classified / total * 100) if total else 0.0
    return {
        "total_transactions": total,
        "classified_transactions": classified,
        "progress_percent": round(ratio, 2),
    }
