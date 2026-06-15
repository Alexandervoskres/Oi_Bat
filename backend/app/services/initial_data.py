from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import User, UserRole
from ..security import hash_password


def ensure_default_admin(db: Session) -> User:
    """Create the local demo admin once, using configurable credentials."""
    user = (
        db.query(User)
        .filter(User.username == settings.default_admin_username)
        .first()
    )
    if user:
        return user

    user = User(
        username=settings.default_admin_username,
        full_name=settings.default_admin_full_name,
        role=UserRole.admin,
        hashed_password=hash_password(settings.default_admin_password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
