"""Robust CSV parsing helpers for finance export files."""

from __future__ import annotations

import csv
import io
from typing import Any


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
CSV_DELIMITERS = [",", ";", "\t", "|"]

PROVIDER_HEADER_HINTS: dict[str, list[str]] = {
    "alipay": [
        "交易时间",
        "商品说明",
        "收/支",
        "金额",
        "交易对方",
        # English-export Alipay headers
        "Transaction Time",
        "Transaction Category",
        "Counterparty",
        "Description",
        "Income/Expense",
        "Amount",
        "Payment Method",
        "Transaction Status",
        "Transaction ID",
        "Merchant Order ID",
    ],
    "wechat": [
        "交易时间",
        "商品",
        "收/支",
        "金额(元)",
        "交易类型",
        "交易对方",
        # English-export WeChat headers (if enabled)
        "Transaction Time",
        "Product",
        "Income/Expense",
        "Amount(CNY)",
        "Amount",
        "Transaction Type",
        "Counterparty",
        "Status",
        "Transaction ID",
        "Merchant ID",
    ],
}

GENERIC_HEADER_HINTS = [
    "time",
    "date",
    "amount",
    "type",
    "item",
    "peer",
    "交易时间",
    "交易日期",
    "记账日期",
    "金额",
    "收/支",
    "摘要",
    "交易对方",
]


def decode_csv_content(content: bytes) -> str:
    """Decode CSV bytes with common UTF-8/GBK encodings."""
    for encoding in CSV_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported file encoding. Please export CSV as UTF-8 or GBK.")


def _header_match_count(values: list[str], hints: list[str]) -> int:
    count = 0
    joined = " ".join(values)
    joined_lower = joined.lower()
    for hint in hints:
        hint_lower = hint.lower()
        if hint in joined or hint_lower in joined_lower:
            count += 1
    return count


def _score_header_line(
    line: str,
    delimiter: str,
    provider: str,
) -> tuple[float, list[str]]:
    """Score one line as potential header for a given delimiter."""
    if delimiter not in line:
        return -1.0, []

    values = [item.strip().lstrip("\ufeff") for item in line.split(delimiter)]
    non_empty = [item for item in values if item]
    if len(non_empty) < 3:
        return -1.0, values

    provider_hints = PROVIDER_HEADER_HINTS.get(provider, [])
    provider_hits = _header_match_count(values, provider_hints) if provider_hints else 0
    generic_hits = _header_match_count(values, GENERIC_HEADER_HINTS)

    score = float(len(non_empty))
    score += float(line.count(delimiter)) * 0.6
    if provider_hits >= 2:
        score += 120.0
    elif provider_hits == 1:
        score += 40.0
    if generic_hits >= 2:
        score += 25.0
    elif generic_hits == 1:
        score += 8.0
    return score, values


def _normalize_header(values: list[str]) -> list[str]:
    """Normalize header names and ensure uniqueness/non-empty."""
    normalized: list[str] = []
    seen: dict[str, int] = {}
    for idx, value in enumerate(values):
        base = value.strip().lstrip("\ufeff")
        if not base:
            base = f"col_{idx + 1}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count > 1:
            normalized.append(f"{base}_{count}")
        else:
            normalized.append(base)
    return normalized


def _detect_header(lines: list[str], provider: str) -> tuple[int, str]:
    """Detect best (header index, delimiter) pair."""
    provider = str(provider or "").strip().lower()
    best_score = -1.0
    best_idx = 0
    best_delimiter = ","

    max_scan = min(len(lines), 320)
    for idx in range(max_scan):
        line = lines[idx]
        for delimiter in CSV_DELIMITERS:
            score, _ = _score_header_line(line, delimiter, provider)
            if score < 0:
                continue
            adjusted = score - (idx * 0.05)
            if adjusted > best_score:
                best_score = adjusted
                best_idx = idx
                best_delimiter = delimiter

    return best_idx, best_delimiter


def parse_csv_rows(content: bytes, provider: str = "") -> list[dict[str, Any]]:
    """Parse CSV bytes into row dictionaries, auto-detecting header row."""
    text = decode_csv_content(content)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    header_idx, delimiter = _detect_header(lines, provider)
    csv_text = "\n".join(lines[header_idx:])

    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    try:
        raw_header = next(reader)
    except StopIteration:
        return []

    header = _normalize_header([str(item) for item in raw_header])
    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        row = [str(item).strip() for item in raw_row]
        if not any(row):
            continue

        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        elif len(row) > len(header):
            row = row[: len(header) - 1] + [delimiter.join(row[len(header) - 1 :])]

        # Skip repeated header lines sometimes embedded in exports.
        if [item.strip() for item in row] == [item.strip() for item in header]:
            continue

        rows.append(dict(zip(header, row)))

    return rows
