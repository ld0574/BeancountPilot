"""
AI provider configuration routes.
"""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.repositories import UserConfigRepository
from src.db.session import get_db
from src.utils.config import _get_default_config

router = APIRouter()

PROVIDER_ORDER = ["deepseek", "openai", "ollama", "custom"]


class ProviderConfigModel(BaseModel):
    """Single provider configuration model."""

    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    timeout: int = Field(default=30, ge=1, le=600)


class AIConfigModel(BaseModel):
    """AI configuration model."""

    default_provider: str = "deepseek"
    providers: Dict[str, ProviderConfigModel]


def _default_ai_config() -> Dict[str, Any]:
    """Build default AI config from application defaults."""
    defaults = _get_default_config().get("ai", {})
    providers = defaults.get("providers", {})

    normalized: Dict[str, Dict[str, Any]] = {}
    for provider in PROVIDER_ORDER:
        cfg = providers.get(provider, {})
        normalized[provider] = {
            "api_base": cfg.get("api_base", ""),
            "api_key": cfg.get("api_key", ""),
            "model": cfg.get("model", ""),
            "temperature": cfg.get("temperature", 0.3),
            "timeout": cfg.get("timeout", 30),
        }

    return {
        "default_provider": defaults.get("default_provider", "deepseek"),
        "providers": normalized,
    }


def _normalize_ai_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI config, ensuring all supported providers exist."""
    defaults = _default_ai_config()
    providers = config.get("providers", {}) if isinstance(config, dict) else {}

    normalized_providers: Dict[str, Dict[str, Any]] = {}
    for provider in PROVIDER_ORDER:
        default_provider_cfg = defaults["providers"][provider]
        current_cfg = providers.get(provider, {})
        normalized_providers[provider] = {
            "api_base": current_cfg.get("api_base", default_provider_cfg["api_base"]),
            "api_key": current_cfg.get("api_key", default_provider_cfg["api_key"]),
            "model": current_cfg.get("model", default_provider_cfg["model"]),
            "temperature": current_cfg.get("temperature", default_provider_cfg["temperature"]),
            "timeout": current_cfg.get("timeout", default_provider_cfg["timeout"]),
        }

    default_provider = config.get("default_provider", defaults["default_provider"])
    if default_provider not in PROVIDER_ORDER:
        default_provider = defaults["default_provider"]

    return {
        "default_provider": default_provider,
        "providers": normalized_providers,
    }


@router.get("/ai/config")
async def get_ai_config(
    db: Session = Depends(get_db),
):
    """Get current AI provider configuration."""
    raw_ai_config = UserConfigRepository.get(db, "ai_config")
    if raw_ai_config:
        try:
            parsed = json.loads(raw_ai_config)
        except json.JSONDecodeError:
            parsed = _default_ai_config()
    else:
        parsed = _default_ai_config()

    config = _normalize_ai_config(parsed)

    default_provider = UserConfigRepository.get(db, "ai_default_provider")
    if default_provider and default_provider in PROVIDER_ORDER:
        config["default_provider"] = default_provider

    return config


@router.put("/ai/config")
async def save_ai_config(
    payload: AIConfigModel,
    db: Session = Depends(get_db),
):
    """Save AI provider configuration and active provider."""
    data = payload.model_dump()
    config = _normalize_ai_config(data)

    if config["default_provider"] not in PROVIDER_ORDER:
        raise HTTPException(status_code=400, detail="Invalid default provider")

    try:
        UserConfigRepository.set(
            db,
            "ai_config",
            json.dumps(config, ensure_ascii=False),
        )
        UserConfigRepository.set(db, "ai_default_provider", config["default_provider"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

    return {
        "message": "AI configuration saved",
        "default_provider": config["default_provider"],
        "providers": config["providers"],
    }
