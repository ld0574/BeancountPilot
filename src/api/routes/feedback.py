"""
Feedback routes
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.feedback import FeedbackHandler
from src.api.schemas.transaction import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def record_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Record user feedback

    Args:
        request: Feedback request
        db: Database session

    Returns:
        Feedback record
    """
    try:
        handler = FeedbackHandler(db)
        feedback = handler.record_feedback(
            transaction_id=request.transaction_id,
            original_account=request.original_account,
            corrected_account=request.corrected_account,
            action=request.action,
        )

        return FeedbackResponse(
            id=feedback["id"],
            transaction_id=feedback["transaction_id"],
            original_account=feedback["original_account"],
            corrected_account=feedback["corrected_account"],
            action=feedback["action"],
            created_at=feedback["created_at"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.get("/feedback/{transaction_id}")
async def get_feedback_by_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """
    Get all feedback for a transaction

    Args:
        transaction_id: Transaction ID
        db: Database session

    Returns:
        List of feedback
    """
    handler = FeedbackHandler(db)
    feedbacks = handler.get_feedback_by_transaction(transaction_id)

    return feedbacks


@router.get("/feedback")
async def list_feedback(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    List all feedback

    Args:
        skip: Number of records to skip
        limit: Number of records to limit
        db: Database session

    Returns:
        List of feedback
    """
    handler = FeedbackHandler(db)
    feedbacks = handler.list_all_feedback(skip, limit)

    return feedbacks


@router.get("/feedback/statistics")
async def get_feedback_statistics(
    db: Session = Depends(get_db),
):
    """
    Get feedback statistics

    Args:
        db: Database session

    Returns:
        Statistics information
    """
    handler = FeedbackHandler(db)
    stats = handler.get_statistics()

    return stats


@router.post("/feedback/generate-rules")
async def generate_rules_from_feedback(
    min_confidence: int = 3,
    db: Session = Depends(get_db),
):
    """
    Auto-generate rules from feedback

    Args:
        min_confidence: Minimum confidence
        db: Database session

    Returns:
        List of generated rules
    """
    try:
        handler = FeedbackHandler(db)
        rules = handler.analyze_feedback_and_generate_rules(min_confidence)

        return {
            "count": len(rules),
            "rules": rules,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate rules: {str(e)}")
