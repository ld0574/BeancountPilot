"""DEG provider catalog loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_OFFICIAL_PROVIDER_CATALOG = [
    {"code": "alipay", "i18n_key": "deg_provider_alipay"},
    {"code": "wechat", "i18n_key": "deg_provider_wechat"},
    {"code": "ccb", "i18n_key": "deg_provider_ccb"},
    {"code": "icbc", "i18n_key": "deg_provider_icbc"},
    {"code": "citic", "i18n_key": "deg_provider_citic"},
    {"code": "hsbchk", "i18n_key": "deg_provider_hsbchk"},
    {"code": "bmo", "i18n_key": "deg_provider_bmo"},
    {"code": "td", "i18n_key": "deg_provider_td"},
    {"code": "cmb", "i18n_key": "deg_provider_cmb"},
    {"code": "bocom_debit", "i18n_key": "deg_provider_bocom_debit"},
    {"code": "bocom_credit", "i18n_key": "deg_provider_bocom_credit"},
    {"code": "abc_debit", "i18n_key": "deg_provider_abc_debit"},
    {"code": "htsec", "i18n_key": "deg_provider_htsec"},
    {"code": "hxsec", "i18n_key": "deg_provider_hxsec"},
    {"code": "jd", "i18n_key": "deg_provider_jd"},
    {"code": "mt", "i18n_key": "deg_provider_mt"},
    {"code": "huobi", "i18n_key": "deg_provider_huobi"},
]

DEFAULT_NON_BANK_PROVIDER_CODES = {
    "alipay",
    "wechat",
    "htsec",
    "hxsec",
    "jd",
    "mt",
    "huobi",
}


def _deg_yaml_candidates() -> list[Path]:
    project_root = Path(__file__).resolve().parent.parent.parent
    return [
        project_root / "config" / "deg.yaml",
        Path.home() / ".beancountpilot" / "config" / "deg.yaml",
    ]


def _load_deg_yaml() -> dict[str, Any]:
    for path in _deg_yaml_candidates():
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            continue
    return {}


def _normalize_provider_item(item: dict[str, Any], code: str) -> dict[str, Any]:
    """Normalize a provider item and preserve multi-language names."""
    names: dict[str, str] = {}

    raw_names = item.get("names")
    if isinstance(raw_names, dict):
        for lang, text in raw_names.items():
            lang_key = str(lang).strip().lower()
            value = str(text).strip()
            if lang_key and value:
                names[lang_key] = value

    # Backward compatibility for old keys.
    old_name_en = str(item.get("name_en", "")).strip()
    old_name_zh = str(item.get("name_zh", "")).strip()
    if old_name_en and "en" not in names:
        names["en"] = old_name_en
    if old_name_zh and "zh" not in names:
        names["zh"] = old_name_zh

    i18n_key = str(item.get("i18n_key", "")).strip() or f"deg_provider_{code}"

    return {
        "code": code,
        "i18n_key": i18n_key,
        "names": names,
        # Keep old keys for compatibility with existing frontend tables.
        "name_en": names.get("en", ""),
        "name_zh": names.get("zh", ""),
    }


def get_official_provider_catalog() -> list[dict[str, Any]]:
    """Load official provider catalog from config/deg.yaml with fallback."""
    raw = _load_deg_yaml().get("official_providers")
    if not isinstance(raw, list):
        return list(DEFAULT_OFFICIAL_PROVIDER_CATALOG)

    items: list[dict[str, Any]] = []
    seen_codes = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip().lower()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        items.append(_normalize_provider_item(item, code))

    if items:
        return items

    return [
        _normalize_provider_item(item, str(item["code"]).strip().lower())
        for item in DEFAULT_OFFICIAL_PROVIDER_CATALOG
    ]


def get_official_provider_codes() -> set[str]:
    """Get official provider codes."""
    return {item["code"] for item in get_official_provider_catalog()}


def get_default_provider_aliases() -> dict[str, str]:
    """No built-in aliases: provider code is treated as one-to-one by default."""
    return {}


def get_bank_style_providers() -> set[str]:
    """
    Derive bank-style providers automatically from official codes.

    All official providers except explicit non-bank providers use bank-style parsing/CSV fields.
    """
    official_codes = get_official_provider_codes()
    return official_codes.difference(DEFAULT_NON_BANK_PROVIDER_CODES)
