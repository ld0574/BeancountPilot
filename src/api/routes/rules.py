"""
Rule management routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.core.rule_engine import RuleEngine
from src.api.schemas.transaction import RuleCreate, RuleUpdate, RuleResponse

router = APIRouter()


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    List all rules
    """
    engine = RuleEngine(db)
    return engine.list_rules(skip=skip, limit=limit)


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: str,
    db: Session = Depends(get_db),
):
    """
    Get rule by id
    """
    engine = RuleEngine(db)
    rule = engine.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


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
