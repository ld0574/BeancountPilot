"""
Knowledge base routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories import KnowledgeRepository
from src.api.schemas.transaction import (
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeResponse,
)

router = APIRouter()


@router.get("/knowledge", response_model=list[KnowledgeResponse])
async def list_knowledge(
    skip: int = 0,
    limit: int = 100,
    key: str | None = None,
    db: Session = Depends(get_db),
):
    """List knowledge records"""
    if key:
        return KnowledgeRepository.search_by_key(db, key)
    return KnowledgeRepository.list_all(db, skip=skip, limit=limit)


@router.get("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(
    knowledge_id: str,
    db: Session = Depends(get_db),
):
    """Get knowledge record"""
    record = KnowledgeRepository.get_by_id(db, knowledge_id)
    if not record:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return record


@router.post("/knowledge", response_model=KnowledgeResponse)
async def create_knowledge(
    request: KnowledgeCreate,
    db: Session = Depends(get_db),
):
    """Create knowledge record"""
    return KnowledgeRepository.create(
        db=db,
        key=request.key,
        value=request.value,
        source=request.source,
    )


@router.put("/knowledge/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: str,
    request: KnowledgeUpdate,
    db: Session = Depends(get_db),
):
    """Update knowledge record"""
    record = KnowledgeRepository.update_value(db, knowledge_id, request.value)
    if not record:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return record


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: str,
    db: Session = Depends(get_db),
):
    """Delete knowledge record"""
    success = KnowledgeRepository.delete(db, knowledge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return {"message": "Delete successful"}
