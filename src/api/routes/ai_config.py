"""
AI profile configuration routes.
"""

import json
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.repositories import UserConfigRepository
from src.db.session import get_db
from src.utils.config import _get_default_config

router = APIRouter()

PROVIDER_TYPES = ["deepseek", "openai", "ollama", "custom"]


class AIProfileModel(BaseModel):
    """Single AI profile."""

    id: str = ""
    name: str = ""
    provider: str = "deepseek"
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    timeout: int = Field(default=30, ge=1, le=600)


class AIConfigModel(BaseModel):
    """AI profile configuration payload."""

    default_profile_id: str = ""
    profiles: List[AIProfileModel] = Field(default_factory=list)


def _provider_defaults(provider: str) -> Dict[str, Any]:
    defaults = (_get_default_config().get("ai") or {}).get("providers", {})
    source = defaults.get(provider, {})
    return {
        "api_base": source.get("api_base", ""),
        "api_key": source.get("api_key", ""),
        "model": source.get("model", ""),
        "temperature": source.get("temperature", 0.3),
        "timeout": source.get("timeout", 30),
    }


def _provider_name(provider: str) -> str:
    names = {
        "deepseek": "DeepSeek",
        "openai": "OpenAI",
        "ollama": "Ollama",
        "custom": "Custom",
    }
    return names.get(provider, provider.capitalize())


def _build_profile_id(base: str, existing: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (base or "").lower()).strip("-")
    if not slug:
        slug = "profile"
    candidate = slug
    index = 2
    while candidate in existing:
        candidate = f"{slug}-{index}"
        index += 1
    existing.add(candidate)
    return candidate


def _normalize_profile(raw: Dict[str, Any], existing_ids: set[str], index: int) -> Dict[str, Any]:
    provider = str(raw.get("provider", "deepseek")).lower()
    if provider not in PROVIDER_TYPES:
        provider = "custom"

    defaults = _provider_defaults(provider)

    profile_id = str(raw.get("id", "")).strip()
    if not profile_id:
        profile_id = _build_profile_id(f"{provider}-{index+1}", existing_ids)
    elif profile_id in existing_ids:
        profile_id = _build_profile_id(profile_id, existing_ids)
    else:
        existing_ids.add(profile_id)

    name = str(raw.get("name", "")).strip() or f"{_provider_name(provider)} Profile"

    return {
        "id": profile_id,
        "name": name,
        "provider": provider,
        "api_base": str(raw.get("api_base", defaults["api_base"])),
        "api_key": str(raw.get("api_key", defaults["api_key"])),
        "model": str(raw.get("model", defaults["model"])),
        "temperature": float(raw.get("temperature", defaults["temperature"])),
        "timeout": int(raw.get("timeout", defaults["timeout"])),
    }


def _migrate_legacy_ai_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate old format:
    {
      "default_provider": "deepseek",
      "providers": { "deepseek": {...}, ...}
    }
    to profile format.
    """
    providers = raw.get("providers", {}) if isinstance(raw, dict) else {}
    existing_ids: set[str] = set()
    profiles: List[Dict[str, Any]] = []

    ordered = PROVIDER_TYPES + [k for k in providers.keys() if k not in PROVIDER_TYPES]
    for i, provider in enumerate(ordered):
        cfg = providers.get(provider)
        if cfg is None:
            continue
        profile = _normalize_profile(
            {
                "id": provider,
                "name": f"{_provider_name(provider)} Profile",
                "provider": provider,
                **cfg,
            },
            existing_ids,
            i,
        )
        profiles.append(profile)

    if not profiles:
        profiles = [_normalize_profile({"provider": "deepseek"}, existing_ids, 0)]

    default_ref = str(raw.get("default_profile_id") or raw.get("default_provider") or "").strip()
    default_profile_id = _resolve_default_profile_id(profiles, default_ref)

    return {
        "default_profile_id": default_profile_id,
        "profiles": profiles,
    }


def _normalize_ai_config(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normalize ai_config into profile-based shape."""
    raw = raw or {}

    # New shape
    if isinstance(raw.get("profiles"), list):
        existing_ids: set[str] = set()
        profiles = [
            _normalize_profile(item or {}, existing_ids, i)
            for i, item in enumerate(raw.get("profiles", []))
        ]
        if not profiles:
            profiles = [_normalize_profile({"provider": "deepseek"}, existing_ids, 0)]
        default_profile_id = _resolve_default_profile_id(
            profiles,
            str(raw.get("default_profile_id", "")).strip(),
        )
        return {
            "default_profile_id": default_profile_id,
            "profiles": profiles,
        }

    # Legacy shape
    return _migrate_legacy_ai_config(raw)


def _resolve_default_profile_id(profiles: List[Dict[str, Any]], ref: str) -> str:
    """Resolve default id from profile id or provider type."""
    if not profiles:
        return ""

    if ref and any(p["id"] == ref for p in profiles):
        return ref

    if ref and ref in PROVIDER_TYPES:
        for profile in profiles:
            if profile["provider"] == ref:
                return profile["id"]

    return profiles[0]["id"]


def _is_valid_profile_ref(profiles: List[Dict[str, Any]], ref: str) -> bool:
    """Whether ref can map to a profile id or provider type."""
    ref = str(ref or "").strip()
    if not ref:
        return False
    if any(p["id"] == ref for p in profiles):
        return True
    if ref in PROVIDER_TYPES and any(p["provider"] == ref for p in profiles):
        return True
    return False


@router.get("/ai/config")
async def get_ai_config(
    db: Session = Depends(get_db),
):
    """Get current AI profile configuration."""
    raw_ai_config = UserConfigRepository.get(db, "ai_config")
    if raw_ai_config:
        try:
            parsed = json.loads(raw_ai_config)
        except json.JSONDecodeError:
            parsed = {}
    else:
        parsed = {}

    config = _normalize_ai_config(parsed)

    # Backward compatibility key: could contain old provider type or profile id.
    stored_default = UserConfigRepository.get(db, "ai_default_provider")
    if stored_default and _is_valid_profile_ref(config["profiles"], stored_default):
        config["default_profile_id"] = _resolve_default_profile_id(
            config["profiles"],
            stored_default,
        )
    elif stored_default:
        # Self-heal stale compatibility key and keep profile-based default as source of truth.
        UserConfigRepository.set(db, "ai_default_provider", config["default_profile_id"])

    return config


@router.put("/ai/config")
async def save_ai_config(
    payload: AIConfigModel,
    db: Session = Depends(get_db),
):
    """Save AI profile configuration and active profile."""
    data = payload.model_dump()
    config = _normalize_ai_config(data)

    if not config["profiles"]:
        raise HTTPException(status_code=400, detail="At least one profile is required")

    config["default_profile_id"] = _resolve_default_profile_id(
        config["profiles"],
        data.get("default_profile_id", ""),
    )

    try:
        UserConfigRepository.set(
            db,
            "ai_config",
            json.dumps(config, ensure_ascii=False),
        )
        # Keep key name for compatibility; now stores active profile id.
        UserConfigRepository.set(db, "ai_default_provider", config["default_profile_id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

    return {
        "message": "AI configuration saved",
        "default_profile_id": config["default_profile_id"],
        "profiles": config["profiles"],
    }
