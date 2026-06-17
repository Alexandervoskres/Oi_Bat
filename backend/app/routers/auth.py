from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ChangePassword, LoginRequest, LoginResponse, UserOut
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services.audit import record_audit


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username, User.is_active.is_(True)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    token = create_access_token(user.username, user.role.value)
    return LoginResponse(access_token=token, user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePassword,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Текущий пароль неверный")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="Новый пароль совпадает с текущим")

    user.hashed_password = hash_password(body.new_password)
    record_audit(
        db, user, "user.password_change", entity_type="user", entity_id=user.id,
        detail=f"Пользователь {user.username} сменил собственный пароль", commit=False,
    )
    db.commit()
    return Response(status_code=204)
