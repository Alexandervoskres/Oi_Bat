from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import PasswordReset, UserCreate, UserOut, UserUpdate
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


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    actor: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    data = body.model_dump(exclude_none=True)

    # Lockout guards: an admin can't strip their own access.
    if user.id == actor.id:
        if "is_active" in data and not data["is_active"]:
            raise HTTPException(status_code=400, detail="Нельзя деактивировать собственную учётную запись")
        if "role" in data and data["role"] != UserRole.admin:
            raise HTTPException(status_code=400, detail="Нельзя снять с себя роль администратора")

    # Don't deactivate or demote the last remaining active admin.
    if user.role == UserRole.admin and (data.get("is_active") is False or ("role" in data and data["role"] != UserRole.admin)):
        active_admins = db.query(User).filter(User.role == UserRole.admin, User.is_active.is_(True)).count()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="Это последний активный администратор")

    for field, value in data.items():
        setattr(user, field, value)

    record_audit(
        db, actor, "user.update", entity_type="user", entity_id=user.id,
        detail=f"Изменён пользователь {user.username}: {', '.join(sorted(data.keys()))}", commit=False,
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int,
    body: PasswordReset,
    actor: User = Depends(require_roles(UserRole.admin)),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.hashed_password = hash_password(body.password)
    record_audit(
        db, actor, "user.password_reset", entity_type="user", entity_id=user.id,
        detail=f"Сброшен пароль пользователя {user.username}", commit=False,
    )
    db.commit()
    return Response(status_code=204)
