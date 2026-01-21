"""
File upload routes
"""

import csv
import io
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories import TransactionRepository
from src.api.schemas.transaction import TransactionResponse

router = APIRouter()


@router.post("/upload", response_model=List[TransactionResponse])
async def upload_csv(
    file: UploadFile = File(...),
    provider: str = "alipay",
    db: Session = Depends(get_db),
):
    """
    Upload CSV file and parse transaction data

    Args:
        file: CSV file
        provider: Data provider (alipay, wechat, etc.)
        db: Database session

    Returns:
        Parsed transaction list
    """
    # Validate file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    try:
        # Read file content
        content = await file.read()
        csv_file = io.StringIO(content.decode("utf-8"))

        # Parse CSV
        transactions = []
        reader = csv.DictReader(csv_file)

        for row in reader:
            # Map fields based on provider
            if provider == "alipay":
                peer = row.get("交易对方", "")
                item = row.get("商品说明", "")
                category = row.get("商品说明", "")
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount_str = row.get("金额", "0").replace(",", "")
                amount = float(amount_str) if amount_str else 0.0
            elif provider == "wechat":
                peer = row.get("交易对方", "")
                item = row.get("商品", "")
                category = row.get("商品", "")
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount_str = row.get("金额(元)", "0").replace(",", "")
                amount = float(amount_str) if amount_str else 0.0
            else:
                # 通用格式
                peer = row.get("peer", "")
                item = row.get("item", "")
                category = row.get("category", "")
                transaction_type = row.get("type", "")
                time = row.get("time", "")
                amount_str = row.get("amount", "0").replace(",", "")
                amount = float(amount_str) if amount_str else 0.0

            # Create transaction record
            transaction = TransactionRepository.create(
                db=db,
                peer=peer,
                item=item,
                category=category,
                transaction_type=transaction_type,
                time=time,
                amount=amount,
                provider=provider,
                raw_data=str(row),
            )

            transactions.append(transaction)

        return transactions

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File parsing failed: {str(e)}")


@router.get("/transactions", response_model=List[TransactionResponse])
async def list_transactions(
    provider: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Get transaction list

    Args:
        provider: Data provider (optional)
        skip: Number of records to skip
        limit: Number of records to limit
        db: Database session

    Returns:
        Transaction list
    """
    if provider:
        transactions = TransactionRepository.list_by_provider(db, provider, skip, limit)
    else:
        transactions = TransactionRepository.list_all(db, skip, limit)

    return transactions


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete transaction

    Args:
        transaction_id: Transaction ID
        db: Database session

    Returns:
        Deletion result
    """
    success = TransactionRepository.delete(db, transaction_id)

    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {"message": "Delete successful"}
