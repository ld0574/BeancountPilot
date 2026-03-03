"""
User management routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.repositories import UserRepository
from src.api.schemas.transaction import UserCreate, UserResponse

router = APIRouter()


@router.post("/users", response_model=UserResponse)
async def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
):
    """Create user"""
    existing = UserRepository.get_by_username(db, request.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    return UserRepository.create(db, request.username)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List users"""
    return UserRepository.list_all(db, skip=skip, limit=limit)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: Session = Depends(get_db),
):
    """Get user by id"""
    user = UserRepository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
):
    """Delete user"""
    success = UserRepository.delete(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Delete successful"}
