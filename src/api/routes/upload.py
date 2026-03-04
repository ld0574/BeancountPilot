"""File upload routes."""

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
from src.utils.csv_table_parser import parse_csv_rows

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
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _load_table_rows(file: UploadFile, content: bytes, provider: str = "") -> list[dict]:
    """
    Load tabular rows from CSV/XLS/XLSX into a list of dictionaries.
    """
    filename = (file.filename or "").lower()

    if filename.endswith(".csv"):
        return parse_csv_rows(content, provider=provider)

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
        rows = _load_table_rows(file, content, provider=provider)
        transactions = []

        for row in rows:
            # Normalize keys to text for robust matching.
            row = {str(k).strip(): v for k, v in dict(row).items()}
            normalized_row = dict(row)

            # Map fields based on provider
            if provider == "alipay":
                peer = row.get("交易对方", "")
                item = row.get("商品说明", "")
                category = _pick_first(
                    row,
                    ["消费分类", "交易分类", "分类", "category"],
                    default=row.get("商品说明", ""),
                )
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount = _parse_amount(row.get("金额", "0"))
                normalized_row["category"] = category
                normalized_row["method"] = _pick_first(
                    row,
                    ["支付方式", "付款方式", "支付渠道", "method"],
                )
                normalized_row["status"] = _pick_first(
                    row,
                    ["交易状态", "状态", "当前状态", "status"],
                )
            elif provider == "wechat":
                peer = row.get("交易对方", "")
                item = row.get("商品", "")
                category = row.get("商品", "")
                transaction_type = row.get("收/支", "")
                time = row.get("交易时间", "")
                amount = _parse_amount(row.get("金额(元)", "0"))
                normalized_row["status"] = _pick_first(
                    row,
                    ["当前状态", "交易状态", "状态", "status"],
                )
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
                tx_type_text = _pick_first(
                    row,
                    ["摘要", "交易摘要", "txType", "用途", "备注"],
                )
                if tx_type_text:
                    normalized_row["txType"] = tx_type_text
                time = _pick_first(
                    row,
                    ["交易时间", "交易日期", "记账日期", "入账时间", "发生时间", "日期", "time", "交易日"],
                )
                normalized_row["status"] = _pick_first(
                    row,
                    ["交易状态", "当前状态", "状态", "status"],
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
                # Generic CSV format (supports both EN and common CN headers).
                peer = _pick_first(
                    row,
                    [
                        "peer",
                        "交易对方",
                        "对方户名",
                        "对方账户",
                        "商户名称",
                        "收款方",
                        "付款方",
                    ],
                )
                item = _pick_first(
                    row,
                    ["item", "商品说明", "商品", "交易说明", "摘要", "备注", "交易描述"],
                    default=peer,
                )
                category = _pick_first(
                    row,
                    ["category", "交易分类", "消费分类", "分类", "类型"],
                    default=item,
                )
                transaction_type = _pick_first(
                    row,
                    ["type", "收/支", "交易类型", "借贷标志", "借贷方向"],
                )
                time = _pick_first(
                    row,
                    ["time", "交易时间", "交易日期", "记账日期", "日期"],
                )
                amount = 0.0
                for key in ("amount", "金额", "金额(元)", "交易金额"):
                    raw_amount = str(row.get(key, "")).strip()
                    if raw_amount:
                        amount = _parse_amount(raw_amount)
                        break
                if amount == 0.0:
                    income_amount = _parse_amount(
                        _pick_first(row, ["收入金额", "收入", "贷方金额"])
                    )
                    expense_amount = _parse_amount(
                        _pick_first(row, ["支出金额", "支出", "借方金额"])
                    )
                    amount = income_amount if income_amount > 0 else expense_amount
                normalized_row["status"] = _pick_first(row, ["status", "状态"])

            # Create transaction record
            # Skip obvious non-transaction rows (metadata/header noise).
            if (
                not str(time or "").strip()
                and not str(peer or "").strip()
                and not str(item or "").strip()
                and not str(category or "").strip()
                and amount == 0.0
            ):
                continue

            transaction = TransactionRepository.create(
                db=db,
                peer=peer,
                item=item,
                category=category,
                transaction_type=transaction_type,
                time=time,
                amount=amount,
                provider=provider,
                raw_data=json.dumps(normalized_row, ensure_ascii=False),
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
