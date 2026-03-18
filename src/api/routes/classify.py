"""
Classification routes
"""

import asyncio
import threading
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db, get_session
from src.db.repositories import (
    TransactionRepository,
    ClassificationRepository,
    UserConfigRepository,
)
from src.core.classifier import Classifier
from src.api.schemas.transaction import (
    ClassificationRequest,
    ClassificationResponse,
    ClassificationResult,
)
from src.api.progress_store import (
    create_job,
    increment,
    set_result,
    set_error,
    get_job,
    set_meta,
)
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/classify", response_model=ClassificationResponse)
async def classify_transactions(
    request: ClassificationRequest,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Batch classify transactions

    Args:
        request: Classification request
        provider: AI profile id (or provider type for backward compatibility)
        db: Database session

    Returns:
        Classification results
    """
    started_at = time.monotonic()
    try:
        # Resolve provider: explicit query param > stored default > deepseek
        resolved_provider = (
            provider
            or UserConfigRepository.get(db, "ai_default_provider")
            or "deepseek"
        )

        # Create classifier
        classifier = Classifier(db, resolved_provider)

        # Execute classification
        results = await classifier.classify_transactions(
            request.transactions,
            chart_of_accounts=request.chart_of_accounts,
            language=request.language,
        )

        # Save classification results
        classification_results = []

        for idx, result in enumerate(results):
            transaction = result.get("transaction") or (
                request.transactions[idx] if idx < len(request.transactions) else {}
            )
            account = result.get("account") or result.get("targetAccount") or "Expenses:Other"
            target_account = result.get("targetAccount", account)
            method_account = result.get("methodAccount", "")
            confidence = float(result.get("confidence", 0.0))
            reasoning = str(result.get("reasoning", ""))
            source = str(result.get("source", "ai"))

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
                    targetAccount=target_account,
                    methodAccount=method_account,
                    confidence=confidence,
                    reasoning=reasoning,
                    source=source,
                )
            )

        return ClassificationResponse(results=classification_results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
    finally:
        elapsed = time.monotonic() - started_at
        logger.info("classify.elapsed_s=%.2f", elapsed)


def _run_classify_job(job_id: str, payload: dict, provider: Optional[str]) -> None:
    """Run classification in background thread and update progress store."""
    db = get_session()
    try:
        resolved_provider = (
            provider
            or UserConfigRepository.get(db, "ai_default_provider")
            or "deepseek"
        )
        classifier = Classifier(db, resolved_provider)
        tx_total = len(payload.get("transactions") or [])
        set_meta(
            job_id,
            deg_done=0,
            deg_total=tx_total,
            ai_done=0,
            ai_total=0,
        )

        def _progress(inc: int = 1) -> None:
            increment(job_id, inc)

        def _deg_progress(done: int, total: int) -> None:
            set_meta(job_id, deg_done=max(0, int(done)), deg_total=max(0, int(total)))

        def _ai_progress(done: int, total: int) -> None:
            set_meta(job_id, ai_done=max(0, int(done)), ai_total=max(0, int(total)))

        async def _run():
            return await classifier.classify_transactions(
                payload.get("transactions") or [],
                chart_of_accounts=payload.get("chart_of_accounts"),
                language=payload.get("language") or "en",
                progress_callback=_progress,
                deg_progress_callback=_deg_progress,
                ai_progress_callback=_ai_progress,
            )

        results = asyncio.run(_run())

        classification_results: List[ClassificationResult] = []
        transactions = payload.get("transactions") or []
        for idx, result in enumerate(results):
            transaction = result.get("transaction") or (
                transactions[idx] if idx < len(transactions) else {}
            )
            account = result.get("account") or result.get("targetAccount") or "Expenses:Other"
            target_account = result.get("targetAccount", account)
            method_account = result.get("methodAccount", "")
            confidence = float(result.get("confidence", 0.0))
            reasoning = str(result.get("reasoning", ""))
            source = str(result.get("source", "ai"))

            ClassificationRepository.create(
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
                    targetAccount=target_account,
                    methodAccount=method_account,
                    confidence=confidence,
                    reasoning=reasoning,
                    source=source,
                )
            )

        set_result(job_id, ClassificationResponse(results=classification_results).model_dump())
    except Exception as e:
        set_error(job_id, str(e))
    finally:
        db.close()


@router.post("/classify/async")
async def classify_transactions_async(
    request: ClassificationRequest,
    provider: Optional[str] = None,
):
    """Start async classification job and return job id."""
    job_id = create_job(len(request.transactions or []))
    payload = request.model_dump()
    thread = threading.Thread(
        target=_run_classify_job,
        args=(job_id, payload, provider),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "total": len(request.transactions or [])}


@router.get("/classify/progress/{job_id}")
async def classify_progress(job_id: str):
    """Get progress for async classification job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    total = job.get("total", 0) or 0
    done = job.get("done", 0) or 0
    percent = round((done / total * 100), 2) if total else 0.0
    return {
        "status": job.get("status"),
        "total": total,
        "done": done,
        "progress_percent": percent,
        "deg_total": int(job.get("deg_total", total) or 0),
        "deg_done": int(job.get("deg_done", done) or 0),
        "ai_total": int(job.get("ai_total", 0) or 0),
        "ai_done": int(job.get("ai_done", 0) or 0),
        "error": job.get("error", ""),
    }


@router.get("/classify/result/{job_id}")
async def classify_result(job_id: str):
    """Get results for async classification job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") == "error":
        raise HTTPException(status_code=500, detail=job.get("error") or "Job failed")
    if job.get("status") != "done":
        raise HTTPException(status_code=202, detail="Job running")
    return job.get("result") or {"results": []}


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
