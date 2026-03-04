"""Generation routes."""

import json
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.deg_integration import DoubleEntryGenerator
from src.core.rule_engine import RuleEngine
from src.core.deg_catalog import (
    get_default_provider_aliases,
    get_official_provider_catalog,
    get_official_provider_codes,
)
from src.api.schemas.transaction import GenerateRequest, GenerateResponse
from src.utils.config import get_config, expand_path
from src.db.repositories import UserConfigRepository

router = APIRouter()


class DEGProviderMappingPayload(BaseModel):
    """DEG provider aliases payload."""

    mappings: Dict[str, str]
    custom_providers: list[dict[str, str]] | None = None


def _normalize_custom_providers(raw_items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Normalize custom provider catalog entries."""
    official_codes = get_official_provider_codes()
    normalized: list[dict[str, Any]] = []
    seen_codes = set()
    for item in raw_items or []:
        code = str(item.get("code", "")).strip().lower()
        if not code or code in seen_codes or code in official_codes:
            continue
        seen_codes.add(code)

        names: dict[str, str] = {}
        raw_names = item.get("names")
        if isinstance(raw_names, dict):
            for lang, text in raw_names.items():
                lang_key = str(lang).strip().lower()
                value = str(text).strip()
                if lang_key and value:
                    names[lang_key] = value

        name_en = str(item.get("name_en", "")).strip()
        name_zh = str(item.get("name_zh", "")).strip()
        if name_en and "en" not in names:
            names["en"] = name_en
        if name_zh and "zh" not in names:
            names["zh"] = name_zh

        normalized.append(
            {
                "code": code,
                "name_zh": names.get("zh", ""),
                "name_en": names.get("en", ""),
                "names": names,
                "i18n_key": str(item.get("i18n_key", "")).strip(),
            }
        )
    return sorted(normalized, key=lambda x: x["code"])


def _get_custom_providers(db: Session) -> list[dict[str, str]]:
    """Load user-defined custom provider catalog from DB."""
    raw = UserConfigRepository.get(db, "deg_custom_providers")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return _normalize_custom_providers(data)


def _build_provider_name_map(custom_providers: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Build provider code -> name map from official + custom catalogs."""
    official_name_map = {
        item["code"]: {
            "name_zh": item.get("name_zh", ""),
            "name_en": item.get("name_en", ""),
            "names": item.get("names", {}),
            "i18n_key": item.get("i18n_key", ""),
        }
        for item in get_official_provider_catalog()
    }
    custom_name_map = {
        item["code"]: {
            "name_zh": item.get("name_zh", ""),
            "name_en": item.get("name_en", ""),
            "names": item.get("names", {}),
            "i18n_key": item.get("i18n_key", ""),
        }
        for item in custom_providers
    }
    return {**official_name_map, **custom_name_map}


def _build_mapping_details(mappings: Dict[str, str], custom_providers: list[dict[str, str]]) -> list[dict]:
    """Build mapping detail rows with official/unknown flags."""
    official_codes = get_official_provider_codes()
    provider_name_map = _build_provider_name_map(custom_providers)

    details = []
    for source, target in sorted(mappings.items(), key=lambda x: x[0]):
        info = provider_name_map.get(target, {})
        details.append(
            {
                "source": source,
                "target": target,
                "is_official_target": target in official_codes,
                "target_name_zh": info.get("name_zh", ""),
                "target_name_en": info.get("name_en", ""),
                "target_names": info.get("names", {}),
                "target_i18n_key": info.get("i18n_key", ""),
            }
        )
    return details


def _get_deg_provider_aliases(db: Session) -> Dict[str, str]:
    """Load user-defined provider aliases from DB."""
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
    normalized = {}
    for key, value in data.items():
        k = str(key).strip().lower()
        v = str(value).strip().lower()
        if not k or not v:
            continue
        # Keep official providers read-only, even if legacy data contains overrides.
        if k in official_codes and v != k:
            continue
        normalized[k] = v
    return normalized


def _create_deg(db: Session | None = None) -> DoubleEntryGenerator:
    """Create DEG integration instance from app config."""
    executable = get_config("application.deg.executable", "double-entry-generator")
    config_dir_raw = get_config("application.deg.config_dir")
    config_dir = expand_path(config_dir_raw) if config_dir_raw else None
    provider_aliases = _get_deg_provider_aliases(db) if db is not None else None
    return DoubleEntryGenerator(
        config_dir=config_dir,
        executable=executable,
        provider_aliases=provider_aliases,
    )


@router.post("/generate", response_model=GenerateResponse)
async def generate_beancount(
    request: GenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Generate Beancount file

    Args:
        request: Generation request
        db: Database session

    Returns:
        Generation result
    """
    try:
        # Create DEG integrator
        deg = _create_deg(db)
        rule_engine = RuleEngine(db)
        deg_config_yaml = rule_engine.export_deg_yaml(provider=request.provider)

        # Generate Beancount file
        result = deg.generate_beancount_from_transactions(
            transactions=request.transactions,
            provider=request.provider,
            config_content=deg_config_yaml,
        )

        return GenerateResponse(
            success=result["success"],
            beancount_file=result.get("beancount_file", ""),
            message=result.get("message", ""),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/generate/check")
async def check_deg_installed():
    """
    Check if double-entry-generator is installed

    Returns:
        Check result
    """
    deg = _create_deg()
    status = deg.get_deg_status()
    installed = status["installed"]
    version = status.get("version", "")
    download_url = "https://github.com/deb-sig/double-entry-generator/releases"

    return {
        "installed": installed,
        "message": "double-entry-generator is installed" if installed else "double-entry-generator is not installed",
        "version": version,
        "download_url": download_url,
        "install_command": "double-entry-generator version",
    }


@router.get("/generate/provider-mapping")
async def get_deg_provider_mapping(
    db: Session = Depends(get_db),
):
    """
    Get DEG provider alias mappings.
    """
    user_aliases = _get_deg_provider_aliases(db)
    custom_providers = _get_custom_providers(db)
    defaults = get_default_provider_aliases()
    merged = {**defaults, **user_aliases}
    details = _build_mapping_details(merged, custom_providers)
    official_codes = get_official_provider_codes()
    official_catalog = get_official_provider_catalog()
    known_targets = official_codes.union(
        {item["code"] for item in custom_providers}
    )
    unknown_targets = sorted(
        {item["target"] for item in details if item["target"] not in known_targets}
    )
    return {
        "mappings": merged,
        "mapping_details": details,
        "defaults": defaults,
        "user_overrides": user_aliases,
        "custom_providers": custom_providers,
        "official_providers": official_catalog,
        "unknown_targets": unknown_targets,
        "storage": {
            "official_catalog": "config/deg.yaml",
            "mappings": "sqlite.user_config[deg_provider_aliases]",
            "custom_providers": "sqlite.user_config[deg_custom_providers]",
        },
        "note": "Format: source_name -> deg_provider_code (used for -p)",
        "official_note": (
            "Official providers are fixed and read-only. "
            "Non-official providers can be added as custom entries. "
            "Mappings to unsupported codes may fail unless your DEG binary/custom parser supports them."
        ),
    }


@router.put("/generate/provider-mapping")
async def save_deg_provider_mapping(
    payload: DEGProviderMappingPayload,
    db: Session = Depends(get_db),
):
    """
    Save user-defined DEG provider alias mappings.
    """
    normalized = {}
    official_codes = get_official_provider_codes()
    for key, value in payload.mappings.items():
        k = str(key).strip().lower()
        v = str(value).strip().lower()
        if not k or not v:
            continue
        if k in official_codes and v != k:
            raise HTTPException(
                status_code=400,
                detail=f"Official provider '{k}' is read-only and cannot be remapped",
            )
        if k in official_codes and v == k:
            continue
        normalized[k] = v

    if payload.custom_providers is None:
        custom_providers = _get_custom_providers(db)
    else:
        custom_providers = _normalize_custom_providers(payload.custom_providers)
        UserConfigRepository.set(
            db,
            "deg_custom_providers",
            json.dumps(custom_providers, ensure_ascii=False),
        )

    UserConfigRepository.set(
        db,
        "deg_provider_aliases",
        json.dumps(normalized, ensure_ascii=False),
    )

    defaults = get_default_provider_aliases()
    official_catalog = get_official_provider_catalog()
    merged = {**defaults, **normalized}
    details = _build_mapping_details(merged, custom_providers)
    known_targets = official_codes.union(
        {item["code"] for item in custom_providers}
    )
    unknown_targets = sorted(
        {item["target"] for item in details if item["target"] not in known_targets}
    )
    return {
        "message": "DEG provider mapping saved",
        "mappings": merged,
        "mapping_details": details,
        "user_overrides": normalized,
        "custom_providers": custom_providers,
        "official_providers": official_catalog,
        "unknown_targets": unknown_targets,
        "storage": {
            "official_catalog": "config/deg.yaml",
            "mappings": "sqlite.user_config[deg_provider_aliases]",
            "custom_providers": "sqlite.user_config[deg_custom_providers]",
        },
        "official_note": (
            "Official providers are fixed and read-only. "
            "Non-official providers can be added as custom entries. "
            "Mappings to unsupported codes may fail unless your DEG binary/custom parser supports them."
        ),
    }
