"""
Maintenance routes (data cleanup).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db.session import get_db
from src.db.models import Transaction, Classification, Feedback

router = APIRouter()


@router.post("/maintenance/cleanup-history")
async def cleanup_history(db: Session = Depends(get_db)):
    """Delete all transactions, classifications, and feedback."""
    counts = {
        "transactions": db.query(func.count(Transaction.id)).scalar() or 0,
        "classifications": db.query(func.count(Classification.id)).scalar() or 0,
        "feedbacks": db.query(func.count(Feedback.id)).scalar() or 0,
    }

    db.query(Classification).delete(synchronize_session=False)
    db.query(Feedback).delete(synchronize_session=False)
    db.query(Transaction).delete(synchronize_session=False)
    db.commit()

    return {"message": "History cleared", **counts}
