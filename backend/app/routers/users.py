from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import UserCreate, UserOut
from ..security import hash_password, require_roles
from ..services.audit import record_audit


router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=409, detail="Такой логин уже существует")

    user = User(
        username=payload.username,
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    record_audit(
        db, actor, "user.create", entity_type="user", entity_id=user.id,
        detail=f"Создан пользователь {user.username} (роль {user.role.value})", commit=False,
    )
    db.commit()
    db.refresh(user)
    return user
