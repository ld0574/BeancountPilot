"""
Classification routes
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories import TransactionRepository, ClassificationRepository
from src.core.classifier import Classifier
from src.api.schemas.transaction import (
    ClassificationRequest,
    ClassificationResponse,
    ClassificationResult,
)

router = APIRouter()


@router.post("/classify", response_model=ClassificationResponse)
async def classify_transactions(
    request: ClassificationRequest,
    provider: str = "deepseek",
    db: Session = Depends(get_db),
):
    """
    Batch classify transactions

    Args:
        request: Classification request
        provider: AI Provider name
        db: Database session

    Returns:
        Classification results
    """
    try:
        # Create classifier
        classifier = Classifier(db, provider)

        # Execute classification
        results = await classifier.classify_transactions(request.transactions)

        # Save classification results
        classification_results = []

        for result in results:
            transaction = result["transaction"]
            account = result["account"]
            confidence = result["confidence"]
            reasoning = result["reasoning"]
            source = result["source"]

            # Save to database
            classification = ClassificationRepository.create(
                db=db,
                transaction_id=transaction.get("id", ""),
                account=account,
                confidence=confidence,
                source=source,
                reasoning=reasoning,
            )

            classification_results.append(
                ClassificationResult(
                    transaction_id=transaction.get("id", ""),
                    account=account,
                    confidence=confidence,
                    reasoning=reasoning,
                    source=source,
                )
            )

        return ClassificationResponse(results=classification_results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")


@router.get("/classifications/{transaction_id}")
async def get_classifications(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """
    Get all classification records for a transaction

    Args:
        transaction_id: Transaction ID
        db: Database session

    Returns:
        List of classification records
    """
    classifications = ClassificationRepository.get_by_transaction_id(
        db, transaction_id
    )

    return [
        {
            "id": c.id,
            "transaction_id": c.transaction_id,
            "account": c.account,
            "confidence": c.confidence,
            "source": c.source,
            "reasoning": c.reasoning,
            "created_at": c.created_at,
        }
        for c in classifications
    ]


@router.put("/classifications/{classification_id}")
async def update_classification(
    classification_id: str,
    account: str,
    db: Session = Depends(get_db),
):
    """
    Update classification account

    Args:
        classification_id: Classification ID
        account: New account
        db: Database session

    Returns:
        Update result
    """
    success = ClassificationRepository.update_account(db, classification_id, account)

    if not success:
        raise HTTPException(status_code=404, detail="Classification not found")

    return {"message": "Update successful"}
