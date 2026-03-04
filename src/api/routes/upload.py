"""
File upload routes
"""

import csv
import io
import json
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories import TransactionRepository
from src.db.repositories import UserConfigRepository
from src.api.schemas.transaction import TransactionResponse
from src.core.deg_catalog import (
    get_default_provider_aliases,
    get_bank_style_providers,
    get_official_provider_codes,
)

router = APIRouter()


def _load_user_provider_aliases(db: Session) -> dict[str, str]:
    """Load user overrides for DEG provider aliases from DB."""
    raw = UserConfigRepository.get(db, "deg_provider_aliases")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}

    official_codes = get_official_provider_codes()
    normalized: dict[str, str] = {}
    for key, value in data.items():
        k = str(key).strip().lower()
        v = str(value).strip().lower()
        if not k or not v:
            continue
        # Keep official providers read-only for consistency with generate mapping API.
        if k in official_codes and v != k:
            continue
        normalized[k] = v
    return normalized


def _resolve_provider(provider: str, db: Session) -> tuple[str, str, bool]:
    """
    Resolve provider via shared DEG mapping source.

    Returns:
        (raw_provider, normalized_provider, is_bank_style)
    """
    raw_provider = (provider or "").strip().lower() or "alipay"
    aliases = get_default_provider_aliases()
    aliases.update(_load_user_provider_aliases(db))
    normalized_provider = aliases.get(raw_provider, raw_provider)

    bank_style_set = get_bank_style_providers()
    is_bank_style = (raw_provider in bank_style_set) or (normalized_provider in bank_style_set)
    return raw_provider, normalized_provider, is_bank_style


def _decode_csv_content(content: bytes) -> str:
    """Decode CSV bytes with common encodings used by Chinese exports."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported file encoding. Please export CSV as UTF-8 or GBK.")


def _pick_first(row: dict, keys: list[str], default: str = "") -> str:
    """Get the first non-empty value from candidate keys."""
    for key in keys:
        value = row.get(key, "")
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return default


def _parse_amount(value: str) -> float:
    """Parse amount text to float, tolerating currency symbols and separators."""
    if value is None:
        return 0.0
    cleaned = (
        str(value)
        .replace(",", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("RMB", "")
        .replace("CNY", "")
        .strip()
    )
    if not cleaned:
        return 0.0
    return float(cleaned)


def _load_table_rows(file: UploadFile, content: bytes) -> list[dict]:
    """
    Load tabular rows from CSV/XLS/XLSX into a list of dictionaries.
    """
    filename = (file.filename or "").lower()

    if filename.endswith(".csv"):
        csv_file = io.StringIO(_decode_csv_content(content))
        reader = csv.DictReader(csv_file)
        return list(reader)

    if filename.endswith(".xls") or filename.endswith(".xlsx"):
        try:
            import pandas as pd
        except Exception as e:
            raise ValueError(f"Excel parsing requires pandas/openpyxl: {str(e)}")

        df = pd.read_excel(io.BytesIO(content))
        if df is None:
            return []
        df = df.fillna("")
        return df.to_dict(orient="records")

    raise ValueError("Only CSV/XLS/XLSX files are supported")


@router.post("/upload", response_model=List[TransactionResponse])
async def upload_csv(
    file: UploadFile = File(...),
    provider: str = "alipay",
    db: Session = Depends(get_db),
):
    """
    Upload transaction file and parse transaction data

    Args:
        file: CSV/XLS/XLSX file
        provider: Data provider (alipay, wechat, etc.)
        db: Database session

    Returns:
        Parsed transaction list
    """
    # Validate file type
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xls") or filename.endswith(".xlsx")):
        raise HTTPException(status_code=400, detail="Only CSV/XLS/XLSX files are supported")

    try:
        _, provider, is_bank_style_provider = _resolve_provider(provider, db)

        # Read file content
        content = await file.read()
        rows = _load_table_rows(file, content)
        transactions = []

        for row in rows:
            # Normalize keys to text for robust matching.
            row = {str(k).strip(): v for k, v in dict(row).items()}

            # Map fields based on provider
            if provider == "alipay":
                peer = row.get("交易对方", "")
                item = row.get("商品说明", "")
                category = row.get("商品说明", "")
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount = _parse_amount(row.get("金额", "0"))
            elif provider == "wechat":
                peer = row.get("交易对方", "")
                item = row.get("商品", "")
                category = row.get("商品", "")
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount = _parse_amount(row.get("金额(元)", "0"))
            elif is_bank_style_provider:
                peer = _pick_first(
                    row,
                    [
                        "交易对方",
                        "对方户名",
                        "对方账户",
                        "对方账号",
                        "收款人",
                        "付款人",
                        "商户名称",
                        "对方名称",
                        "交易对手",
                    ],
                )
                item = _pick_first(
                    row,
                    ["摘要", "交易摘要", "用途", "附言", "备注", "交易描述", "交易名称", "item"],
                    default=peer,
                )
                category = item
                transaction_type = _pick_first(
                    row,
                    ["收/支", "借贷标志", "借贷方向", "交易类型", "支出或收入", "借贷", "type"],
                )
                time = _pick_first(
                    row,
                    ["交易时间", "交易日期", "记账日期", "入账时间", "发生时间", "日期", "time", "交易日"],
                )

                amount = 0.0
                amount_candidates = [
                    "金额",
                    "交易金额",
                    "发生额",
                    "入账金额",
                    "金额(元)",
                    "amount",
                ]
                for key in amount_candidates:
                    if str(row.get(key, "")).strip():
                        amount = _parse_amount(row.get(key))
                        break

                if amount == 0.0:
                    income_amount = _parse_amount(
                        _pick_first(row, ["收入金额", "贷方发生额", "收入", "贷方金额"])
                    )
                    expense_amount = _parse_amount(
                        _pick_first(row, ["支出金额", "借方发生额", "支出", "借方金额"])
                    )
                    amount = income_amount if income_amount > 0 else expense_amount
            else:
                # Generic CSV format
                peer = row.get("peer", "")
                item = row.get("item", "")
                category = row.get("category", "")
                transaction_type = row.get("type", "")
                time = row.get("time", "")
                amount = _parse_amount(row.get("amount", "0"))

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
