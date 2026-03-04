"""Rule management routes."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.rule_engine import RuleEngine
from src.api.schemas.transaction import RuleCreate, RuleUpdate, RuleResponse

router = APIRouter()


def _decode_uploaded_text(content: bytes) -> str:
    """Decode uploaded text using common UTF-8/GBK encodings."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unsupported file encoding. Please upload UTF-8 or GBK text.")


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    skip: int = 0,
    limit: int = 100,
    provider: str | None = None,
    scope: str = "all",
    db: Session = Depends(get_db),
):
    """
    List all rules
    """
    engine = RuleEngine(db)
    rules = engine.list_rules(skip=skip, limit=limit)
    normalized_provider = (provider or "").strip().lower()
    scope = (scope or "all").strip().lower()
    if scope not in {"all", "global", "provider"}:
        scope = "all"

    filtered = []
    for rule in rules:
        conditions = rule.get("conditions", {}) or {}
        cond_provider = conditions.get("provider")
        cond_provider_list: list[str] = []
        if isinstance(cond_provider, str):
            cond_provider_list = [cond_provider.strip().lower()] if cond_provider.strip() else []
        elif isinstance(cond_provider, list):
            cond_provider_list = [
                str(item).strip().lower()
                for item in cond_provider
                if str(item).strip()
            ]

        is_provider_rule = bool(cond_provider_list)
        if scope == "global" and is_provider_rule:
            continue
        if scope == "provider" and not is_provider_rule:
            continue
        if normalized_provider and is_provider_rule and normalized_provider not in cond_provider_list:
            continue
        filtered.append(rule)

    return filtered


@router.post("/rules", response_model=RuleResponse)
async def create_rule(
    request: RuleCreate,
    db: Session = Depends(get_db),
):
    """
    Create rule
    """
    engine = RuleEngine(db)
    rule = engine.create_rule(
        name=request.name,
        conditions=request.conditions,
        account=request.account,
        confidence=request.confidence,
        source=request.source,
    )
    return rule


@router.post("/rules/import-deg")
async def import_deg_rules(
    provider: str = Form(""),
    mode: str = Form("replace"),
    yaml_text: str = Form(""),
    yaml_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    """
    Import full DEG YAML rules.

    Accepts either:
    - multipart file upload (`yaml_file`)
    - plain yaml text (`yaml_text`)
    """
    content = str(yaml_text or "")
    if yaml_file is not None:
        raw = await yaml_file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded YAML file is empty")
        try:
            content = _decode_uploaded_text(raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if not content.strip():
        raise HTTPException(status_code=400, detail="YAML content is empty")

    engine = RuleEngine(db)
    try:
        result = engine.import_deg_yaml(
            yaml_text=content,
            provider=provider,
            mode=mode,
        )
        return {
            "message": "DEG rules imported",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import DEG rules: {str(e)}") from e


@router.get("/rules/export-deg", response_class=PlainTextResponse)
async def export_deg_rules(
    provider: str = "alipay",
    db: Session = Depends(get_db),
):
    """Export full DEG YAML config for a provider."""
    engine = RuleEngine(db)
    try:
        content = engine.export_deg_yaml(provider=provider)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export DEG YAML: {str(e)}") from e
    return PlainTextResponse(content=content, media_type="application/x-yaml")


@router.post("/rules/cleanup-auto")
async def cleanup_auto_rules(
    provider: str = "",
    scope: str = "all",
    db: Session = Depends(get_db),
):
    """Bulk-delete auto-generated rules with optional scope/provider filters."""
    engine = RuleEngine(db)
    try:
        result = engine.delete_auto_rules(provider=provider, scope=scope)
        return {
            "message": "Auto rules cleaned",
            **result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clean auto rules: {str(e)}") from e


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: str,
    db: Session = Depends(get_db),
):
    """Get rule by id."""
    engine = RuleEngine(db)
    rule = engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    request: RuleUpdate,
    db: Session = Depends(get_db),
):
    """
    Update rule
    """
    engine = RuleEngine(db)
    rule = engine.update_rule(
        rule_id=rule_id,
        name=request.name,
        conditions=request.conditions,
        account=request.account,
        confidence=request.confidence,
        source=request.source,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
):
    """
    Delete rule
    """
    engine = RuleEngine(db)
    success = engine.delete_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Delete successful"}
